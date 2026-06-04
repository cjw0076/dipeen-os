"""Capability catalog (ux-command-layer-v0) — the surface-agnostic unit Dipeen exposes.

A capability is one named action rendered identically across CLI / Slash / Web ⌘K / MCP.
This registry is the single source of truth those surfaces enumerate. NOT capabilities.py
(that is compute_effective, worker bounding). Handlers are pure-ish async fns; IO lives in
the services they call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field


class CapabilityResult(BaseModel):
    """Human-worded + structured. message renders as-is (never an HTTP code); data feeds
    non-human consumers (web/MCP)."""
    ok: bool
    message: str
    next_actions: list[str] = Field(default_factory=list)
    data: Optional[dict] = None


Handler = Callable[[dict, dict], Awaitable[CapabilityResult]]


@dataclass(frozen=True)
class Capability:
    name: str
    human_label: str
    handler: Handler
    required_permission: Optional[str] = None
    surfaces: tuple[str, ...] = ("cli", "slash", "web", "mcp")


_CATALOG: dict[str, Capability] = {}


def register(cap: Capability) -> None:
    _CATALOG[cap.name] = cap


def get(name: str) -> Optional[Capability]:
    return _CATALOG.get(name)


def catalog() -> list[Capability]:
    return sorted(_CATALOG.values(), key=lambda c: c.name)


def clear() -> None:
    _CATALOG.clear()
