from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_startup_does_not_import_structure_stack() -> None:
    """The ASGI app must not pull ase/scipy/numpy into the startup path.

    Structure parsing is imported lazily on the first preview/scheduler-stats
    request; importing it here costs seconds of cold-start time on Windows.
    """
    code = (
        "import sys\n"
        "import backend.app.main\n"
        "heavy = [name for name in ('ase', 'scipy', 'backend.app.services.structure_service') "
        "         if name in sys.modules]\n"
        "assert not heavy, f'unexpected startup imports: {heavy}'\n"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        check=True,
        timeout=120,
    )
