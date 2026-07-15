"""Dependency-closed, selected-run reproducibility support for blind review."""

from __future__ import annotations

import ast
import json
import py_compile
import re
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _project_python_path(root: Path, module: str, current: Path) -> Path | None:
    parts = [part for part in module.split(".") if part]
    candidates = [
        root.joinpath(*parts).with_suffix(".py"),
        root.joinpath(*parts, "__init__.py"),
        current.parent.joinpath(*parts).with_suffix(".py"),
        root.joinpath("methods", "src", *parts).with_suffix(".py"),
        root.joinpath("data", "src", *parts).with_suffix(".py"),
    ]
    return next((item.resolve() for item in candidates if item.is_file()), None)


def _imports(path: Path, root: Path) -> list[Path]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    resolved: list[Path] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = str(node.module or "")
            if node.level:
                try:
                    relative_parent = path.parent
                    for _ in range(max(node.level - 1, 0)):
                        relative_parent = relative_parent.parent
                    candidate = relative_parent.joinpath(*base.split(".")).with_suffix(".py") if base else relative_parent / "__init__.py"
                    if candidate.is_file():
                        resolved.append(candidate.resolve())
                except ValueError:
                    pass
            if base:
                modules.append(base)
            modules.extend(f"{base}.{alias.name}".strip(".") for alias in node.names)
        for module in modules:
            candidate = _project_python_path(root, module, path)
            if candidate and candidate not in resolved:
                resolved.append(candidate)
    return resolved


def selected_run_roots(root: Path) -> list[Path]:
    run = _read(root / "methods" / "run_manifest.yaml")
    method_manifest = _read(root / "methods" / "method_code_manifest.json") or _read(root / "methods" / "analysis_code_manifest.json")
    analysis = _read(root / "methods" / "executable_analysis_spec.json")
    trace = _read(root / "results" / "figure_code_trace.json")
    values: list[str] = []
    for key in ("script", "entry_point", "implementation_entry_point"):
        if run.get(key):
            values.append(str(run[key]))
    for key in ("command_argv", "verify_command_argv", "input_files", "code_files", "owned_files"):
        for value in run.get(key) or method_manifest.get(key) or []:
            if str(value).endswith(".py"):
                values.append(str(value))
    for spec in analysis.get("analysis_specs") or []:
        if isinstance(spec, dict) and spec.get("implementation_entry_point"):
            values.append(str(spec["implementation_entry_point"]))
    for item in trace.get("traces") or trace.get("figures") or []:
        if not isinstance(item, dict):
            continue
        for key in ("script", "code_path", "method_code_path", "plot_code_path"):
            if item.get(key):
                values.append(str(item[key]))
    roots = []
    for value in values:
        candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.is_file() and candidate.suffix == ".py":
            roots.append(candidate)
    if not roots:
        roots.extend(path.resolve() for pattern in ("methods/scripts/*.py", "data/scripts/*.py") for path in root.glob(pattern))
    return sorted(set(roots))


def python_dependency_closure(root: Path, entry_points: list[Path] | None = None) -> list[Path]:
    pending = list(entry_points or selected_run_roots(root))
    closure: set[Path] = set()
    root_resolved = root.resolve()
    while pending:
        path = pending.pop().resolve()
        if path in closure or not path.is_file():
            continue
        try:
            path.relative_to(root_resolved)
        except ValueError:
            continue
        closure.add(path)
        pending.extend(item for item in _imports(path, root) if item not in closure)
    module_tokens = {path.stem for path in closure}
    for test in root.glob("methods/tests/test_*.py"):
        text = test.read_text(encoding="utf-8-sig", errors="replace")
        if any(re.search(rf"\b{re.escape(token)}\b", text) for token in module_tokens):
            closure.add(test.resolve())
    return sorted(closure)


def smoke_dependency_closure(root: Path, paths: list[Path]) -> dict[str, Any]:
    failures = []
    for path in paths:
        if path.suffix != ".py":
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append({"path": path.relative_to(root).as_posix(), "error": str(exc)})
    return {
        "decision": "pass" if not failures else "blocked",
        "compiled_python_file_count": sum(path.suffix == ".py" for path in paths),
        "failures": failures,
        "policy": "The selected-run dependency closure must compile before the anonymous review bundle is released.",
    }


def selected_result_assets(root: Path) -> tuple[list[Path], list[Path]]:
    manifest = _read(root / "results" / "result_manifest.yaml")
    figures: list[Path] = []
    tables: list[Path] = []
    for item in manifest.get("figures") or []:
        if isinstance(item, dict) and item.get("path"):
            path = (root / str(item["path"])).resolve()
            if path.is_file():
                figures.append(path)
        if isinstance(item, dict):
            for value in item.get("supporting_artifacts") or []:
                path = (root / str(value)).resolve()
                if path.is_file():
                    (figures if path.suffix.lower() in {".png", ".pdf", ".svg", ".jpg", ".jpeg"} else tables).append(path)
    for item in manifest.get("tables") or []:
        value = item.get("path") if isinstance(item, dict) else item
        if value:
            path = (root / str(value)).resolve()
            if path.is_file():
                tables.append(path)
    if not figures:
        figures = [path.resolve() for path in (root / "results" / "figures").glob("*") if path.is_file()]
    if not tables:
        tables = [path.resolve() for path in (root / "results" / "tables").glob("*") if path.is_file()]
    return sorted(set(figures)), sorted(set(tables))
