# chemweb

English | [中文](README.zh-CN.md)

`chemweb` is a lightweight web workspace for computational catalysis, computational chemistry, and materials simulation directories. It is designed to run on a remote Linux server or HPC login node and be accessed locally through SSH port forwarding.

The current version provides file management, text/log preview, custom 3D structure preview, Slurm queue inspection, `sbatch` submission, and `scancel` cancellation.

## Stack

- Backend: Python 3.10+, FastAPI, Uvicorn, Pydantic
- Frontend: Vue 3, Vite, Element Plus, custom Canvas structure viewer
- Scheduler: Slurm-first MVP

## Install

Create a virtual environment in the project root, such as `D:\path\to\chemweb` on Windows or the project directory on a remote server.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"

npm.cmd --prefix frontend install
npm.cmd --prefix frontend run build
```

Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"

npm --prefix frontend install
npm --prefix frontend run build
```

After installation, the command-line entry point is:

```bash
chemweb --help
```

## Configuration

Copy and edit `config.yaml`. The most important setting is the workspace root:

```yaml
workspace:
  root: /home/user
```

All file reads, writes, uploads, downloads, deletes, renames, and job submissions are restricted to `workspace.root`.

## Start

```bash
chemweb --config config.yaml --host 127.0.0.1 --port 8888
```

Before starting, the CLI checks whether the target port is already in use. If it finds an existing Chemweb server on the same port and with the same `workspace.root`, it reuses that server and prints the existing URL instead of failing. If the port is occupied by another application, or by Chemweb serving a different workspace, startup fails with a clear error.

Reuse behavior can be adjusted with:

```bash
chemweb --config config.yaml --reuse-existing auto
chemweb --config config.yaml --reuse-existing never
chemweb --config config.yaml --reuse-existing any-chemweb
```

To check the port without starting a server, use:

```bash
chemweb --config config.yaml --check-port
```

This exits with code `0` when the port is free or points to a reusable Chemweb server, and exits with code `1` when the port is occupied by something that should not be reused.

For development, run the backend and frontend separately:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8888 --reload
npm.cmd --prefix frontend run dev
```

On Linux or macOS, use `npm` instead of `npm.cmd`.

## Server PID Checks

If the server was started with `chemweb --config config.yaml`, check the server-side process with:

```bash
pgrep -af 'chemweb'
```

If it was started directly with `uvicorn`, use:

```bash
pgrep -af 'uvicorn'
```

## SSH Port Forwarding

Start Chemweb on the remote server:

```bash
chemweb --config config.yaml --host 127.0.0.1 --port 8888
```

Forward the remote port from your local machine:

```bash
ssh -p 22 -L 8888:127.0.0.XX:8888 user@server
```

Then open the local browser at:

```text
http://localhost:8888
```

## MVP Features

- Browse `workspace.root` and its subdirectories
- Upload, download, delete, rename, and create files or folders
- Read and save text files
- Preview `.txt`, `.log`, `.out`, `.in`, `.inp`, and similar text files
- Preview `.xyz`, `.pdb`, `.mol`, `.sdf`, `.cif`, and related structure files
- Switch browser structure styles: stick, sphere, line
- Inspect the Slurm queue with manual and automatic refresh
- View Slurm job details and cancel jobs
- Submit `sbatch run.sh` from the current directory
- Read the tail of log files with manual and automatic refresh

## Slurm Notes

The backend calls only fixed allowlisted commands:

- `squeue`
- `scontrol show job <job_id>`
- `scancel <job_id>`
- `sbatch <script>`

The job submission API accepts only script filenames such as `run.sh`. It does not execute arbitrary shell commands or accept script parameters containing paths or shell control characters.

## Security Notes

- The server binds to `127.0.0.1` by default; SSH tunneling is recommended.
- Set `workspace.root` to the smallest practical working directory.
- Plain file reads are limited by `workspace.max_read_size_mb`; use log tail or download for large files.
- Set `workspace.allow_delete: false` to disable delete operations.

## API

API details are documented in [docs/API.md](docs/API.md).

FastAPI's generated docs are also available while the server is running:

```text
http://127.0.0.1:8888/docs
```

## Tests

```bash
python -m pytest
```

The minimal test suite covers path safety, file type detection, file API read/write, plugins, and basic app startup.
