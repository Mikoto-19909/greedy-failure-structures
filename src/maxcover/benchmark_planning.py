"""Types shared by benchmark planning and execution."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import AlgorithmRunOptions
from .model import MaximumCoverageInstance


@dataclass(frozen=True, slots=True)
class _PlannedInstance:
    case_id: str
    repetition: int
    instance: MaximumCoverageInstance
    instance_id: str
    coupling_pair_id: str | None = None
    coupling_seed: int | None = None


@dataclass(frozen=True, slots=True)
class _RunTask:
    case_id: str
    repetition: int
    instance: MaximumCoverageInstance
    algorithm_id: str
    algorithm_seed: int | None
    algorithm: str
    options: AlgorithmRunOptions
    option_values: dict[str, object]
    config_hash: str
    instance_id: str
    run_id: str
