"""Prahari demo data generation package."""

from __future__ import annotations

from typing import Any


def generate_demo_alerts(seed: int = 42) -> list[dict[str, Any]]:
    """Lazy import wrapper to avoid module execution collision warnings."""
    from .generate import generate_demo_alerts as _gen

    return _gen(seed=seed)


__all__ = ["generate_demo_alerts"]
