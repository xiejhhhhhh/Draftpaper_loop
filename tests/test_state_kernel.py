from __future__ import annotations

import json

import pytest

from draftpaper_cli.state_kernel import StateKernelError, atomic_write_json, read_json_object


def test_atomic_write_json_supports_top_level_arrays(tmp_path) -> None:
    target = tmp_path / "literature_items.json"
    payload = [{"citation_key": "Example2026"}, {"citation_key": "Example2025"}]

    atomic_write_json(target, payload)

    assert json.loads(target.read_text(encoding="utf-8")) == payload
    with pytest.raises(StateKernelError, match="must contain an object"):
        read_json_object(target)


def test_atomic_write_uses_short_temporary_name_in_deep_project_paths(tmp_path) -> None:
    padding = max(1, 228 - len(str(tmp_path)) - 1)
    deep = tmp_path / ("x" * padding)
    target = deep / "learning_manifest.json"

    atomic_write_json(target, {"status": "written"})

    assert read_json_object(target)["status"] == "written"
