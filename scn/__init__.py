"""
scn — scenario harness package.

Module layout per docs/atdd/scenario-harness-design.md §2.
"""
from scn.engine import (
    AUTO,
    INTEGRITY_TARGET,
    CheckpointEngine,
    CheckpointKind,
    DrainInvariantError,
    Expectation,
    Severity,
    Surface,
)
from scn.surfaces import DocReader, SheetReader, TrackerReader
from scn.session import ScenarioSession

__all__ = [
    "AUTO",
    "INTEGRITY_TARGET",
    "CheckpointEngine",
    "CheckpointKind",
    "DrainInvariantError",
    "Expectation",
    "Severity",
    "Surface",
    "DocReader",
    "SheetReader",
    "TrackerReader",
    "ScenarioSession",
]
