"""Small deterministic algorithms used by explicitly promoted runnable profiles."""

from __future__ import annotations

import json
import math
from importlib import resources
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any


def _numpy() -> Any:
    try:
        import numpy
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'This scientific plugin operation requires NumPy. Install the plotting profile with '
            '`python -m pip install "draftpaper-cli[plotting]"`.'
        ) from exc
    return numpy


def runnable_profiles() -> dict[str, dict[str, Any]]:
    payload = json.loads(resources.files("draftpaper_cli").joinpath("resources", "runnable_plugin_profiles.json").read_text(encoding="utf-8"))
    return dict(payload.get("profiles") or {})


def runnable_profile(plugin_id: str) -> dict[str, Any] | None:
    profile = runnable_profiles().get(str(plugin_id))
    return dict(profile) if isinstance(profile, dict) else None


def apply_runnable_profile(manifest: dict[str, Any]) -> dict[str, Any]:
    result = dict(manifest)
    plugin_id = str(result.get("template_id") or result.get("connector_id") or result.get("rule_id") or result.get("rule_group_id") or "")
    profile = runnable_profile(plugin_id)
    if not profile:
        return result
    result["maturity"] = "runnable"
    result["validation_level"] = "fixture_runnable"
    result["runtime_level"] = "code_generator" if profile.get("kind") != "review" else "fixture_executed"
    result["runnable_profile"] = profile
    if profile.get("kind") == "review":
        result["deployment_state"] = "runtime_integrated"
        result["threshold_validation_status"] = "fixture_validated"
        result["threshold_source"] = {"type": "discipline_contract", "citation_or_note": profile.get("threshold_source")}
        result["runnable_profile_required_fields"] = list(profile.get("required_fields") or [])
        result["runnable_profile_applicable_stages"] = list(profile.get("applicable_stages") or ["post_results"])
        result["blocking_level"] = "warn_and_repair"
        result["human_confirmation_required"] = False
    return result


def _load_fixture(profile: dict[str, Any], fixture_path: str | Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if fixture_path and Path(fixture_path).is_file():
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Runnable fixture must contain one JSON object.")
        if "roles" in payload and not payload.get("roles"):
            raise ValueError("Failure fixture intentionally omits required scientific roles.")
    return dict(payload.get("input") or profile.get("fixture_input") or {})


def _tabular_profile(data: dict[str, Any]) -> dict[str, Any]:
    rows = list(data.get("rows") or [])
    fields = sorted({str(key) for row in rows if isinstance(row, dict) for key in row})
    return {"row_count": len(rows), "fields": fields, "missing_by_field": {field: sum(row.get(field) in (None, "") for row in rows if isinstance(row, dict)) for field in fields}}


def _matrix_profile(data: dict[str, Any]) -> dict[str, Any]:
    np = _numpy()
    matrix = np.asarray(data.get("matrix") or [], dtype=float)
    if matrix.ndim != 2 or not matrix.size:
        raise ValueError("A non-empty two-dimensional matrix is required.")
    return {"shape": list(matrix.shape), "nonzero_fraction": float(np.count_nonzero(matrix) / matrix.size), "column_totals": matrix.sum(axis=0).tolist()}


def _numeric_summary(data: dict[str, Any]) -> dict[str, Any]:
    values = [float(item) for item in data.get("values") or []]
    if len(values) < 2:
        raise ValueError("At least two numeric values are required.")
    return {"n": len(values), "mean": mean(values), "median": median(values), "standard_deviation": pstdev(values), "minimum": min(values), "maximum": max(values)}


def _two_group(data: dict[str, Any]) -> dict[str, Any]:
    np = _numpy()
    a = np.asarray(data.get("group_a") or [], dtype=float)
    b = np.asarray(data.get("group_b") or [], dtype=float)
    if min(a.size, b.size) < 2:
        raise ValueError("Both groups require at least two observations.")
    pooled = math.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / (a.size + b.size - 2))
    effect = float((b.mean() - a.mean()) / pooled) if pooled else 0.0
    return {"n_a": int(a.size), "n_b": int(b.size), "mean_a": float(a.mean()), "mean_b": float(b.mean()), "difference": float(b.mean() - a.mean()), "cohens_d": effect}


def _power(data: dict[str, Any]) -> dict[str, Any]:
    effect = abs(float(data.get("effect_size") or 0))
    alpha = float(data.get("alpha") or 0.05)
    power = float(data.get("power") or 0.8)
    if effect <= 0 or not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("Effect size must be positive and alpha/power must lie in (0,1).")
    z_alpha = 1.959963984540054 if abs(alpha - 0.05) < 1e-9 else 1.6448536269514722
    z_power = 0.8416212335729143 if abs(power - 0.8) < 1e-9 else 1.2815515655446004
    return {"effect_size": effect, "alpha": alpha, "target_power": power, "n_per_group_approx": int(math.ceil(2 * ((z_alpha + z_power) / effect) ** 2))}


def _split(data: dict[str, Any]) -> dict[str, Any]:
    groups = {key: {str(item) for item in value} for key, value in data.items() if key.endswith("_ids") and isinstance(value, list)}
    overlaps = []
    names = sorted(groups)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            shared = sorted(groups[left] & groups[right])
            if shared:
                overlaps.append({"left": left, "right": right, "ids": shared})
    return {"split_sizes": {key: len(value) for key, value in groups.items()}, "overlaps": overlaps, "passes_gate": not overlaps}


def _classification(data: dict[str, Any]) -> dict[str, Any]:
    truth = [int(item) for item in data.get("y_true") or []]
    pred = [int(item) for item in data.get("y_pred") or []]
    if not truth or len(truth) != len(pred):
        raise ValueError("y_true and y_pred must be non-empty and equal length.")
    tp = sum(a == b == 1 for a, b in zip(truth, pred)); tn = sum(a == b == 0 for a, b in zip(truth, pred))
    fp = sum(a == 0 and b == 1 for a, b in zip(truth, pred)); fn = sum(a == 1 and b == 0 for a, b in zip(truth, pred))
    precision = tp / (tp + fp) if tp + fp else 0.0; recall = tp / (tp + fn) if tp + fn else 0.0
    return {"n": len(truth), "accuracy": (tp + tn) / len(truth), "precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0, "confusion_matrix": [[tn, fp], [fn, tp]]}


def _linear(data: dict[str, Any]) -> dict[str, Any]:
    np = _numpy()
    x = np.asarray(data.get("x") or [], dtype=float); y = np.asarray(data.get("y") or [], dtype=float)
    if x.size < 3 or x.size != y.size:
        raise ValueError("Regression requires at least three paired observations.")
    slope, intercept = np.polyfit(x, y, 1); fitted = slope * x + intercept
    ss_res = float(np.sum((y - fitted) ** 2)); ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {"n": int(x.size), "slope": float(slope), "intercept": float(intercept), "r_squared": 1.0 - ss_res / ss_tot if ss_tot else 0.0, "rmse": math.sqrt(ss_res / x.size)}


def _execute(operation: str, data: dict[str, Any]) -> dict[str, Any]:
    if operation == "tabular_profile": return _tabular_profile(data)
    if operation == "matrix_profile": return _matrix_profile(data)
    if operation == "numeric_summary": return _numeric_summary(data)
    if operation == "two_group_effect": return _two_group(data)
    if operation == "power_analysis": return _power(data)
    if operation == "split_audit": return _split(data)
    if operation == "classification_metrics": return _classification(data)
    if operation == "linear_regression": return _linear(data)
    if operation == "coordinate_profile":
        np = _numpy()
        points = np.asarray(data.get("coordinates") or [], dtype=float)
        if points.ndim != 2 or points.shape[1] != 2: raise ValueError("Coordinates must be an N x 2 array.")
        return {"crs": data.get("crs"), "count": int(points.shape[0]), "bounds": [float(points[:,0].min()), float(points[:,1].min()), float(points[:,0].max()), float(points[:,1].max())]}
    if operation == "count_profile":
        counts = {str(key): int(value) for key, value in (data.get("counts") or {}).items()}; total = sum(counts.values())
        if total <= 0: raise ValueError("Counts must have a positive total.")
        return {"total_shots": total, "probabilities": {key: value / total for key, value in counts.items()}}
    if operation == "unit_conversion":
        factor = float(data.get("factor") or 0); values = [float(item) for item in data.get("values") or []]
        if not values or factor == 0: raise ValueError("Values and a non-zero conversion factor are required.")
        return {"source_unit": data.get("source_unit"), "target_unit": data.get("target_unit"), "values": values, "converted_values": [value * factor for value in values]}
    if operation == "ablation_effect":
        full = [float(item) for item in data.get("full") or []]; ablated = [float(item) for item in data.get("ablated") or []]
        if not full or not ablated: raise ValueError("Full and ablated repeated metrics are required.")
        return {"full_mean": mean(full), "ablated_mean": mean(ablated), "effect": mean(full) - mean(ablated)}
    if operation == "uncertainty_propagation":
        np = _numpy()
        s = np.asarray(data.get("sensitivities") or [], dtype=float); u = np.asarray(data.get("uncertainties") or [], dtype=float)
        if not s.size or s.size != u.size: raise ValueError("Sensitivities and uncertainties must have equal non-zero length.")
        return {"combined_standard_uncertainty": float(np.sqrt(np.sum((s * u) ** 2))), "component_count": int(s.size)}
    if operation == "differential_expression":
        np = _numpy()
        control = np.asarray(data.get("control") or [], dtype=float); treatment = np.asarray(data.get("treatment") or [], dtype=float)
        if control.ndim != 2 or treatment.shape != control.shape: raise ValueError("Control and treatment matrices must share feature x replicate shape.")
        features = data.get("features") or [f"feature_{i}" for i in range(control.shape[0])]
        return {"features": [{"feature": str(features[i]), "log2_fold_change": float(np.log2((treatment[i].mean()+0.5)/(control[i].mean()+0.5))), "control_mean": float(control[i].mean()), "treatment_mean": float(treatment[i].mean())} for i in range(control.shape[0])]}
    raise ValueError(f"Unsupported runnable operation: {operation}")


def execute_runnable_fixture(plugin_id: str, output_dir: str | Path, *, fixture_path: str | Path | None = None) -> dict[str, Any]:
    profile = runnable_profile(plugin_id)
    if not profile or profile.get("kind") == "review":
        raise ValueError(f"No runnable data/method profile exists for {plugin_id}.")
    data = _load_fixture(profile, fixture_path)
    result = {"schema_version": profile.get("output_schema"), "plugin_id": plugin_id, "operation": profile.get("operation"), "result": _execute(str(profile.get("operation")), data)}
    destination = Path(output_dir) / "scientific_fixture_result.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "written", "execution_status": "fixture_executed", "result": str(destination), "output": result}


def evaluate_runnable_review(plugin_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    profile = runnable_profile(plugin_id)
    if not profile or profile.get("kind") != "review":
        raise ValueError(f"No runnable review profile exists for {plugin_id}.")
    stage = str(evidence.get("stage") or "post_results")
    applicable = {str(item) for item in profile.get("applicable_stages") or ["post_results"]}
    if stage not in applicable:
        return {"rule_id": plugin_id, "decision": "not_applicable", "passes_gate": True, "blocking": False, "missing_evidence": [], "threshold_source": profile.get("threshold_source")}
    present = set(str(item) for item in evidence.get("roles") or evidence.get("evidence_roles") or []) | set(str(key) for key in evidence)
    records = [item for item in evidence.get("records") or [] if isinstance(item, dict)]
    if evidence.get("metrics") and any(any(token in str(item.get("split") or "").lower() for token in ("held", "holdout", "test", "validation")) for item in records):
        present.add("held_out_metrics")
    if evidence.get("uncertainty_records"):
        present.add("uncertainty")
    required = [str(item) for item in profile.get("required_fields") or []]
    missing = [item for item in required if item not in present]
    return {"rule_id": plugin_id, "decision": "revise_required" if missing else "pass", "passes_gate": not missing, "blocking": False, "missing_evidence": missing, "threshold_source": profile.get("threshold_source")}
