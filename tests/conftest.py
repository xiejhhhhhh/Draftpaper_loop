"""Pytest-only compatibility helpers for cross-platform test cleanup."""

from __future__ import annotations

import os
import tempfile
import time


class _RetryingTemporaryDirectory(tempfile.TemporaryDirectory[str]):
    """Retry transient Windows directory-cleanup races without hiding leaks."""

    _DPL_RETRY_PATCH = True

    def cleanup(self) -> None:
        if os.name != "nt":
            super().cleanup()
            return

        last_error: OSError | None = None
        for delay in (0.0, 0.05, 0.1, 0.25, 0.5, 1.0):
            if delay:
                time.sleep(delay)
            try:
                super().cleanup()
                return
            except OSError as exc:
                if getattr(exc, "winerror", None) != 145:
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error


if os.name == "nt" and not getattr(tempfile.TemporaryDirectory, "_DPL_RETRY_PATCH", False):
    tempfile.TemporaryDirectory = _RetryingTemporaryDirectory
