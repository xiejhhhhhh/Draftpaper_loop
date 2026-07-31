"""Parameterized Earth Engine phenology, random-forest and zoning workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


def qa60_mask(image: Any) -> Any:
    qa = image.select("QA60")
    mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return image.updateMask(mask).divide(10000).copyProperties(image, ["system:time_start"])


def build_sentinel2_window(*, region: Any, start: str, end: str, bands: Sequence[str], cloud_max: float = 30.0) -> Any:
    import ee

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cloud_max))
        .map(qa60_mask)
    )
    image = collection.select(list(bands)).median()
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    evi = image.expression(
        "2.5*(nir-red)/(nir+6*red-7.5*blue+1)",
        {"nir": image.select("B8"), "red": image.select("B4"), "blue": image.select("B2")},
    ).rename("EVI")
    return image.addBands([ndvi, evi]).clip(region)


def train_probability_rf(
    *, predictors: Any, samples: Any, label_property: str, input_properties: Sequence[str], trees: int = 300, seed: int = 42
) -> dict[str, Any]:
    import ee

    training = predictors.sampleRegions(collection=samples, properties=[label_property], scale=10, geometries=True)
    classifier = ee.Classifier.smileRandomForest(numberOfTrees=trees, seed=seed).train(
        features=training,
        classProperty=label_property,
        inputProperties=list(input_properties),
    )
    return {
        "classifier": classifier,
        "classification": predictors.classify(classifier).rename("class"),
        "probability": predictors.classify(classifier.setOutputMode("PROBABILITY")).rename("probability"),
    }


def build_template_plan(context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "template_id": "gee_phenology_rf_agroclimate_workflow",
        "status": "plan_ready",
        "required_bindings": ["project_id", "region", "phenology_windows", "training_samples", "label_property"],
        "optional_bindings": ["sar_collection", "agroclimate_assets", "cropland_mask", "administrative_boundaries"],
        "validation_design": [
            "spatial_block_holdout",
            "temporal_holdout",
            "probability_calibration",
            "feature_group_ablation",
            "uncertainty_propagation",
            "threshold_sensitivity",
        ],
        "parameter_keys": sorted(str(key) for key in (context or {}).keys()),
    }


def run_template(
    *, input_table: Path, output_dir: Path, target_column: str = "class", context: dict[str, Any] | None = None
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = {
        **build_template_plan(context),
        "input_table": str(input_table),
        "target_column": target_column,
        "status": "template_ready_for_project_binding",
    }
    artifact = output_dir / "gee_phenology_rf_workflow_contract.json"
    artifact.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    contract["contract_artifact"] = str(artifact)
    return contract
