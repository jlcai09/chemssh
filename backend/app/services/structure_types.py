from __future__ import annotations

import threading

from backend.app.core.errors import AppError


STRUCTURE_BINARY_MEDIA_TYPE = "application/vnd.chemssh.structure+bin"
STRUCTURE_BINARY_MAGIC = b"CWB1"


class StructureCancellationToken:
    """Lightweight cancellation flag shared by the structures API and parser."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self._event.is_set():
            raise AppError("REQUEST_CANCELLED", "Request was cancelled", 499)
