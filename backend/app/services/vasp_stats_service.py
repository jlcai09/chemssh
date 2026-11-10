from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.core.errors import AppError
from backend.app.models.queue import QueueVaspStat, QueueVaspStatsResponse, VaspStatSource

if TYPE_CHECKING:
    from backend.app.services.structure_service import StructureService


class VaspStatsService:
    def __init__(self, structure_service: StructureService) -> None:
        self.structure = structure_service

    def collect(self, workdirs: list[str]) -> QueueVaspStatsResponse:
        return QueueVaspStatsResponse(items=[self._collect_one(workdir) for workdir in _dedupe(workdirs)])

    def _collect_one(self, workdir: str) -> QueueVaspStat:
        try:
            directory = self.structure.security.resolve_path(workdir)
        except AppError as exc:
            return QueueVaspStat(workdir=workdir, status="error", message=exc.message)

        traj_path = directory / "optimized.traj"
        outcar_path = directory / "OUTCAR"
        steps: int | None = None
        steps_source: VaspStatSource | None = None
        fmax: float | None = None
        fmax_source: VaspStatSource | None = None
        errors: list[str] = []

        if traj_path.is_file():
            try:
                traj_steps, traj_fmax = self.structure.quick_traj_stats(str(traj_path))
                if traj_steps > 0:
                    steps, steps_source = traj_steps, "traj"
                if traj_fmax is not None:
                    fmax, fmax_source = traj_fmax, "traj"
            except Exception as exc:
                errors.append(f"optimized.traj: {_error_text(exc)}")

        if outcar_path.is_file() and (steps is None or fmax is None):
            try:
                outcar_steps, outcar_fmax = self.structure.quick_outcar_stats(str(outcar_path))
                if steps is None:
                    steps, steps_source = outcar_steps, "outcar"
                if fmax is None and outcar_fmax is not None:
                    fmax, fmax_source = outcar_fmax, "outcar"
            except Exception as exc:
                errors.append(f"OUTCAR: {_error_text(exc)}")

        if steps is None:
            if errors:
                return QueueVaspStat(workdir=workdir, status="error", message="; ".join(errors))
            return QueueVaspStat(
                workdir=workdir,
                status="missing",
                message="no OUTCAR or optimized.traj found",
            )
        return QueueVaspStat(
            workdir=workdir,
            status="ok",
            steps=steps,
            steps_source=steps_source,
            fmax=fmax,
            fmax_source=fmax_source,
            message="; ".join(errors),
        )


def _dedupe(workdirs: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for workdir in workdirs:
        value = (workdir or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _error_text(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc) or exc.__class__.__name__
