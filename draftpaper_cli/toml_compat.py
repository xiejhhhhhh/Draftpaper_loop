"""TOML parser compatibility for the supported Python 3.10+ runtime."""

from __future__ import annotations

try:
    import tomllib as tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI matrix
    import tomli as tomllib

__all__ = ["tomllib"]
