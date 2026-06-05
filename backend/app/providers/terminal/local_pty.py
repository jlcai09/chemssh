from __future__ import annotations

import locale
import os
import queue
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from backend.app.providers.terminal.base import TerminalProvider


class LocalPtyTerminalProvider(TerminalProvider):
    def __init__(self) -> None:
        self._shell = ""
        self._pty: Any | None = None
        self._winpty: Any | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._output_queue: queue.Queue[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._line_buffer = ""
        self._in_escape_sequence = False
        self._pipe_encoding = locale.getpreferredencoding(False) or "utf-8"
        self._transfer_shim_dir: Path | None = None
        self.vim_compatibility = True

    @property
    def shell(self) -> str:
        return self._shell

    def start(self, cwd: str, rows: int, cols: int, shell: str | None = None) -> None:
        self._shell = shell or self._default_shell()
        if os.name == "nt":
            try:
                self._start_winpty(cwd, rows, cols)
            except ImportError:
                self._start_subprocess(cwd)
            return

        from ptyprocess import PtyProcessUnicode

        self._pty = PtyProcessUnicode.spawn(
            [self._shell],
            cwd=cwd,
            dimensions=(rows, cols),
            env=self._terminal_env(),
        )

    def write(self, data: str) -> None:
        if self._pty is not None:
            self._pty.write(data)
            return

        if self._winpty is not None:
            self._winpty.write(data)
            return

        if self._process is None or self._process.stdin is None:
            return
        self._write_subprocess_input(data)

    def write_control(self, data: str) -> None:
        if self._pty is not None:
            self._pty.write(data)
            return

        if self._winpty is not None:
            self._winpty.write(data)
            return

        if self._process is None or self._process.stdin is None:
            return
        self._line_buffer = ""
        self._in_escape_sequence = False
        self._process.stdin.write(data.encode(self._pipe_encoding, errors="replace"))
        self._process.stdin.flush()

    def read(self, size: int = 4096) -> str:
        if self._pty is not None:
            return self._read_pty(size)
        if self._winpty is not None:
            return self._read_winpty(size)
        return self._read_subprocess()

    def resize(self, rows: int, cols: int) -> None:
        if self._pty is not None and self.is_alive():
            self._pty.setwinsize(rows, cols)
        elif self._winpty is not None and self.is_alive():
            self._winpty.setwinsize(rows, cols)

    def terminate(self) -> None:
        if self._pty is not None:
            try:
                self._pty.terminate(force=True)
            except Exception:
                pass

        if self._winpty is not None:
            try:
                self._winpty.terminate(force=True)
            except Exception:
                pass

        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

        if self._transfer_shim_dir is not None:
            shutil.rmtree(self._transfer_shim_dir, ignore_errors=True)
            self._transfer_shim_dir = None

    def is_alive(self) -> bool:
        if self._pty is not None:
            return bool(self._pty.isalive())
        if self._winpty is not None:
            return bool(self._winpty.isalive())
        if self._process is not None:
            return self._process.poll() is None
        return False

    def exit_code(self) -> int | None:
        if self._pty is not None:
            status = getattr(self._pty, "exitstatus", None)
            if status is not None:
                return int(status)
            signal = getattr(self._pty, "signalstatus", None)
            return None if signal is None else 128 + int(signal)
        if self._winpty is not None:
            status = getattr(self._winpty, "exitstatus", None)
            return None if status is None else int(status)
        if self._process is not None:
            return self._process.poll()
        return None

    def build_cd_command(self, path: str) -> str:
        if os.name != "nt":
            return super().build_cd_command(path)

        shell_name = Path(self._shell).name.lower()
        if "powershell" in shell_name or shell_name.startswith("pwsh"):
            quoted = "'" + path.replace("'", "''") + "'"
            return f"Set-Location -LiteralPath {quoted}\r\n"

        quoted = path.replace('"', '""')
        return f'cd /d "{quoted}"\r\n'

    def resolve_transfer_ack_path(self, raw_path: str) -> Path | None:
        if self._transfer_shim_dir is None:
            return None
        try:
            path = Path(raw_path).expanduser().resolve()
            shim_dir = self._transfer_shim_dir.resolve()
            if path == shim_dir or shim_dir in path.parents:
                return path
        except OSError:
            return None
        return None

    def _default_shell(self) -> str:
        if os.name == "nt":
            return (
                shutil.which("pwsh")
                or shutil.which("powershell")
                or os.environ.get("COMSPEC")
                or "cmd.exe"
            )
        return os.environ.get("SHELL") or ("/bin/bash" if Path("/bin/bash").exists() else "/bin/sh")

    def _terminal_env(self) -> dict[str, str]:
        env = os.environ.copy()
        shim_dir = self._ensure_transfer_shims()
        path_parts = [str(shim_dir)]
        existing_path = env.get("PATH")
        if existing_path:
            path_parts.append(existing_path)
        env["PATH"] = os.pathsep.join(path_parts)
        env["CHEMSSH_TRANSFER_SHIM"] = "1"
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        shell_name = Path(self._shell).name.lower()
        if os.name == "nt" and "powershell" not in shell_name and not shell_name.startswith("pwsh"):
            env["PROMPT"] = f"$E]633;P;Cwd=$P$E\\{env.get('PROMPT', '$P$G')}"
        elif "bash" in shell_name:
            cwd_marker = r'printf "\033]633;P;Cwd=%s\007" "$PWD"'
            existing = env.get("PROMPT_COMMAND", "")
            env["PROMPT_COMMAND"] = f"{cwd_marker}; {existing}" if existing else cwd_marker
        return env

    def _ensure_transfer_shims(self) -> Path:
        if self._transfer_shim_dir is not None:
            return self._transfer_shim_dir

        directory = Path(tempfile.mkdtemp(prefix="chemssh-terminal-shim-"))
        helper = directory / "_chemssh_transfer_shim.py"
        helper.write_text(_TRANSFER_SHIM_PYTHON, encoding="utf-8", newline="\n")
        for command, direction in (("rz", "upload"), ("sz", "download")):
            script = directory / command
            script.write_text(_posix_transfer_wrapper(direction, helper), encoding="utf-8", newline="\n")
            script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            cmd_script = directory / f"{command}.cmd"
            cmd_script.write_text(_windows_transfer_wrapper(direction, helper), encoding="utf-8", newline="\r\n")
        if self.vim_compatibility:
            for command in ("vi", "vim"):
                script = directory / command
                script.write_text(_posix_vim_wrapper(command), encoding="utf-8", newline="\n")
                script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self._transfer_shim_dir = directory
        return directory

    def _shell_args(self) -> list[str]:
        args = [self._shell]
        shell_name = Path(self._shell).name.lower()
        if "powershell" not in shell_name and not shell_name.startswith("pwsh"):
            return args

        startup = (
            "[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false); "
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding=[Console]::OutputEncoding; "
            "try { Set-PSReadLineOption -HistorySaveStyle SaveNothing } catch {}; "
            "$global:__chemssh_original_prompt=(Get-Command prompt -CommandType Function -ErrorAction SilentlyContinue).ScriptBlock; "
            "function global:prompt { "
            "[Console]::Write(\"$([char]27)]633;P;Cwd=$((Get-Location).ProviderPath)$([char]7)\"); "
            "if ($global:__chemssh_original_prompt) { & $global:__chemssh_original_prompt } "
            "else { \"PS $($executionContext.SessionState.Path.CurrentLocation)$('>' * ($nestedPromptLevel + 1)) \" } "
            "}"
        )
        return [
            self._shell,
            "-NoLogo",
            "-NoExit",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            startup,
        ]

    def _read_pty(self, size: int) -> str:
        if self._pty is None or not self.is_alive():
            return ""

        ready, _, _ = select.select([self._pty.fd], [], [], 0.1)
        if not ready:
            return ""

        try:
            data = os.read(self._pty.fd, size)
        except OSError:
            return ""
        return data.decode("utf-8", errors="replace")

    def _start_winpty(self, cwd: str, rows: int, cols: int) -> None:
        from winpty import PtyProcess

        self._winpty = PtyProcess.spawn(
            self._shell_args(),
            cwd=cwd,
            env=self._terminal_env(),
            dimensions=(rows, cols),
        )

    def _read_winpty(self, size: int) -> str:
        if self._winpty is None or not self.is_alive():
            return ""

        try:
            return self._winpty.read(size)
        except EOFError:
            return ""

    def _start_subprocess(self, cwd: str) -> None:
        env = self._terminal_env()

        self._output_queue = queue.Queue()
        self._process = subprocess.Popen(
            self._shell_args(),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        self._reader_thread = threading.Thread(target=self._pump_subprocess_output, daemon=True)
        self._reader_thread.start()

    def _write_subprocess_input(self, data: str) -> None:
        if self._process is None or self._process.stdin is None:
            return

        for char in data:
            if self._in_escape_sequence:
                if char.isalpha() or char == "~":
                    self._in_escape_sequence = False
                continue

            if char in ("\x7f", "\b"):
                if self._line_buffer:
                    self._line_buffer = self._line_buffer[:-1]
                    self._echo_subprocess_input("\b \b")
                continue

            if char in ("\r", "\n"):
                command = self._line_buffer + "\n"
                self._line_buffer = ""
                self._echo_subprocess_input("\r\n")
                self._process.stdin.write(command.encode(self._pipe_encoding, errors="replace"))
                self._process.stdin.flush()
                continue

            if char == "\x03":
                self._line_buffer = ""
                self._echo_subprocess_input("^C\r\n")
                continue

            if char == "\x1b":
                self._in_escape_sequence = True
                continue

            self._line_buffer += char
            self._echo_subprocess_input(char)

    def _echo_subprocess_input(self, data: str) -> None:
        if self._output_queue is not None:
            self._output_queue.put(data)

    def _pump_subprocess_output(self) -> None:
        if self._process is None or self._process.stdout is None or self._output_queue is None:
            return

        while True:
            chunk = self._process.stdout.read(1)
            if not chunk:
                break
            self._output_queue.put(chunk.decode(self._pipe_encoding, errors="replace"))

    def _read_subprocess(self) -> str:
        if self._output_queue is None:
            return ""

        chunks: list[str] = []
        try:
            chunks.append(self._output_queue.get(timeout=0.1))
        except queue.Empty:
            return ""

        while True:
            try:
                chunks.append(self._output_queue.get_nowait())
            except queue.Empty:
                break
        return "".join(chunks)


_TRANSFER_SHIM_PYTHON = r'''from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import time


def main() -> int:
    direction = sys.argv[1] if len(sys.argv) > 1 else ""
    command = "rz" if direction == "upload" else "sz"
    ack_dir = pathlib.Path(__file__).resolve().parent / "acks"
    ack_dir.mkdir(parents=True, exist_ok=True)
    ack_path = ack_dir / f"{os.getpid()}-{time.monotonic_ns()}.json"
    argv = [command, *sys.argv[2:]]
    payload = {
        "direction": direction,
        "argv": argv,
        "cwd": os.getcwd(),
        "ack_path": str(ack_path),
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sys.stdout.write(f"\033]777;chemssh-transfer;{encoded}\007")
    sys.stdout.flush()
    deadline = time.monotonic() + 86400
    while time.monotonic() < deadline:
        if ack_path.exists():
            try:
                ack = json.loads(ack_path.read_text(encoding="utf-8"))
            except Exception:
                ack = {}
            try:
                ack_path.unlink()
            except OSError:
                pass
            if ack.get("success"):
                return 0
            message = ack.get("message")
            if isinstance(message, str) and message:
                sys.stderr.write(message + "\n")
                sys.stderr.flush()
            return 1
        time.sleep(0.1)
    sys.stderr.write("ChemSSH transfer timed out\n")
    sys.stderr.flush()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _posix_transfer_wrapper(direction: str, helper: Path) -> str:
    python = str(Path(sys.executable))
    return f"#!/bin/sh\nexec {_shell_quote(python)} {_shell_quote(str(helper))} {_shell_quote(direction)} \"$@\"\n"


def _windows_transfer_wrapper(direction: str, helper: Path) -> str:
    python = str(Path(sys.executable))
    return f'@"{python}" "{helper}" {direction} %*\r\n'


def _posix_vim_wrapper(command: str) -> str:
    return f"""#!/bin/sh
shim_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
clean_path=
old_ifs=$IFS
IFS=:
for item in $PATH; do
    [ "$item" = "$shim_dir" ] && continue
    if [ -z "$clean_path" ]; then
        clean_path=$item
    else
        clean_path=$clean_path:$item
    fi
done
IFS=$old_ifs
PATH=$clean_path
export PATH

real_command=$(command -v {command} 2>/dev/null)
if [ -z "$real_command" ]; then
    echo "{command}: command not found" >&2
    exit 127
fi

if "$real_command" --version 2>/dev/null | sed -n '1p' | grep -qi 'vim'; then
    exec "$real_command" --cmd 'set t_RV= t_u7= t_RF= t_RB= t_RK=' "$@"
fi

exec "$real_command" "$@"
"""


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
