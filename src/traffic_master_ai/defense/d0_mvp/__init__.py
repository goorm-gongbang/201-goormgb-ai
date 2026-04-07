"""Traffic-Master Defense D0-MVP — Spec Driven Development implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import DefenseRuntime

__all__ = ["DefenseRuntime"]


def __getattr__(name: str):
    if name == "DefenseRuntime":
        from .api import DefenseRuntime

        return DefenseRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
