import json
from pathlib import Path

from draftpaper_cli.reproducibility_bundle import python_dependency_closure, selected_result_assets


def test_python_dependency_closure_includes_imported_implementation_not_unrelated_history(tmp_path: Path) -> None:
    root = tmp_path
    (root / "methods" / "scripts").mkdir(parents=True)
    (root / "methods" / "src").mkdir(parents=True)
    entry = root / "methods" / "scripts" / "run.py"
    implementation = root / "methods" / "src" / "model.py"
    unrelated = root / "methods" / "src" / "old_model.py"
    entry.write_text("from methods.src.model import fit\nfit()\n", encoding="utf-8")
    implementation.write_text("def fit():\n    return 1\n", encoding="utf-8")
    unrelated.write_text("def old():\n    return 0\n", encoding="utf-8")
    closure = python_dependency_closure(root, [entry])
    assert entry.resolve() in closure
    assert implementation.resolve() in closure
    assert unrelated.resolve() not in closure


def test_selected_result_assets_excludes_unreferenced_historical_tables(tmp_path: Path) -> None:
    (tmp_path / "results" / "figures").mkdir(parents=True)
    (tmp_path / "results" / "tables").mkdir(parents=True)
    figure = tmp_path / "results" / "figures" / "primary.png"
    table = tmp_path / "results" / "tables" / "primary.csv"
    history = tmp_path / "results" / "tables" / "old.csv"
    figure.write_bytes(b"png")
    table.write_text("a\n1\n", encoding="utf-8")
    history.write_text("a\n0\n", encoding="utf-8")
    (tmp_path / "results" / "result_manifest.yaml").write_text(json.dumps({"figures": [{"path": "results/figures/primary.png"}], "tables": [{"path": "results/tables/primary.csv"}]}), encoding="utf-8")
    figures, tables = selected_result_assets(tmp_path)
    assert figures == [figure.resolve()]
    assert tables == [table.resolve()]
    assert history.resolve() not in tables
