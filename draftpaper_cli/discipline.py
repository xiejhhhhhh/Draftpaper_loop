# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_state import load_project


def compact_json(value: Any, limit: int = 2000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path, limit: int = 3000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def project_discipline_context(project: str | Path, *, extra_text: str = "") -> dict[str, Any]:
    state = load_project(project)
    project_path = state.path
    context = {
        "project_path": str(project_path),
        "metadata": {
            "project_id": state.metadata.get("project_id"),
            "project_slug": state.metadata.get("project_slug"),
            "idea": state.metadata.get("idea"),
            "field": state.metadata.get("field"),
            "target_journal": state.metadata.get("target_journal"),
        },
        "research_plan": read_text(project_path / "research_plan" / "research_plan.md"),
        "literature_review_notes": read_text(project_path / "references" / "literature_review_notes.html", 2200),
        "data_context": read_json(project_path / "data" / "data_writing_context.json"),
        "method_requirements": read_json(project_path / "methods" / "method_requirements.json"),
        "result_validity": read_json(project_path / "results" / "result_validity_report.json"),
        "journal_profile": read_json(project_path / "journal_profile" / "journal_profile.json"),
        "extra_text": extra_text,
    }
    return context


def discipline_context_text(context: dict[str, Any]) -> str:
    chunks = [
        compact_json(context.get("metadata") or {}, 1600),
        str(context.get("research_plan") or ""),
        str(context.get("literature_review_notes") or ""),
        compact_json(context.get("data_context") or {}, 1800),
        compact_json(context.get("method_requirements") or {}, 1800),
        compact_json(context.get("result_validity") or {}, 1600),
        compact_json(context.get("journal_profile") or {}, 1200),
        str(context.get("extra_text") or ""),
    ]
    return " ".join(chunks).lower()


def infer_discipline_from_text(text: str) -> dict[str, Any]:
    lowered = text.lower()
    geography_terms = [
        "geography",
        "geographic",
        "geospatial",
        "gis",
        "spatial",
        "remote sensing",
        "ndvi",
        "vegetation index",
        "raster",
        "yield zoning",
        "agricultural geography",
        "google earth engine",
        "gee",
        "geotiff",
        "shapefile",
    ]
    astronomy_terms = [
        "astronomy",
        "astronomical",
        "astrophysics",
        "x-ray",
        "xray",
        "light curve",
        "flare",
        "source classification",
        "catalog",
        "photometric",
        "spectral",
        "telescope",
        "survey field",
        "multiwavelength",
        "einstein probe",
        "swift",
        "wxt",
        "tde",
        "transient",
    ]
    machine_learning_terms = [
        "machine learning",
        "deep learning",
        "classifier",
        "classification",
        "random forest",
        "transformer",
        "cnn",
        "resnet",
        "tcn",
        "neural network",
        "baseline",
        "ablation",
        "f1",
        "accuracy",
    ]
    ecology_terms = [
        "ecology",
        "ecological",
        "environment",
        "environmental monitoring",
        "biodiversity",
        "habitat",
        "ecosystem",
        "netcdf",
        "geotiff",
        "pollution",
        "water quality",
    ]
    bioinformatics_terms = [
        "bioinformatics",
        "omics",
        "gene expression",
        "rna-seq",
        "rna seq",
        "geo",
        "sra",
        "ena",
        "fastq",
        "fasta",
        "genomics",
        "transcriptomics",
    ]
    geography_score = sum(1 for term in geography_terms if term in lowered)
    astronomy_score = sum(1 for term in astronomy_terms if term in lowered)
    machine_learning_score = sum(1 for term in machine_learning_terms if term in lowered)
    ecology_score = sum(1 for term in ecology_terms if term in lowered)
    bioinformatics_score = sum(1 for term in bioinformatics_terms if term in lowered)
    if bioinformatics_score >= 2:
        subdisciplines = []
        if any(term in lowered for term in ("geo", "sra", "ena")):
            subdisciplines.append("public_repository")
        if any(term in lowered for term in ("rna-seq", "rna seq", "gene expression", "transcriptomics")):
            subdisciplines.append("expression_analysis")
        if any(term in lowered for term in ("fastq", "fasta", "sequence", "genomics")):
            subdisciplines.append("sequence_data")
        return {
            "discipline": "bioinformatics",
            "engine": "bioinformatics",
            "confidence": "high" if bioinformatics_score >= 4 else "medium",
            "matched_terms": [term for term in bioinformatics_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["bioinformatics"],
        }
    if ecology_score >= 2:
        subdisciplines = []
        if any(term in lowered for term in ("environmental monitoring", "water quality", "pollution")):
            subdisciplines.append("environmental_monitoring")
        if any(term in lowered for term in ("biodiversity", "habitat", "ecosystem")):
            subdisciplines.append("ecology")
        if any(term in lowered for term in ("netcdf", "geotiff", "spatial", "raster")):
            subdisciplines.append("environmental_raster")
        return {
            "discipline": "ecology",
            "engine": "ecology",
            "confidence": "high" if ecology_score >= 4 else "medium",
            "matched_terms": [term for term in ecology_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["ecology"],
        }
    if geography_score >= 2:
        subdisciplines = []
        if any(term in lowered for term in ("remote sensing", "ndvi", "vegetation index", "raster", "google earth engine", "gee", "geotiff")):
            subdisciplines.append("remote_sensing")
        if any(term in lowered for term in ("wheat", "yield", "crop", "agriculture", "agronomy")):
            subdisciplines.append("agricultural_geography")
        if any(term in lowered for term in ("spatial", "gis", "geographic", "geospatial", "region", "zoning", "shapefile")):
            subdisciplines.append("spatial_analysis")
        return {
            "discipline": "geography",
            "engine": "geography",
            "confidence": "high" if geography_score >= 4 else "medium",
            "matched_terms": [term for term in geography_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["geography"],
        }
    if astronomy_score >= 2:
        subdisciplines = []
        if any(term in lowered for term in ("light curve", "flare", "time series", "transient", "tde")):
            subdisciplines.append("time_series")
        if any(term in lowered for term in ("source classification", "classifier", "classification")):
            subdisciplines.append("source_classification")
        if any(term in lowered for term in ("catalog", "crossmatch", "cross-match")):
            subdisciplines.append("catalog_crossmatch")
        if any(term in lowered for term in ("multiwavelength", "photometric", "spectral", "x-ray", "xray", "wxt", "swift")):
            subdisciplines.append("multiwavelength")
        if machine_learning_score >= 2:
            subdisciplines.append("astronomy_machine_learning")
        return {
            "discipline": "astronomy",
            "engine": "astronomy",
            "confidence": "high" if astronomy_score >= 4 else "medium",
            "matched_terms": [term for term in astronomy_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["astronomy"],
        }
    if machine_learning_score >= 2:
        subdisciplines = []
        if any(term in lowered for term in ("classification", "classifier", "f1", "accuracy")):
            subdisciplines.append("supervised_learning")
        if any(term in lowered for term in ("deep learning", "transformer", "cnn", "resnet", "tcn", "neural network")):
            subdisciplines.append("deep_learning")
        if any(term in lowered for term in ("baseline", "ablation", "validation", "cross-validation")):
            subdisciplines.append("model_validation")
        return {
            "discipline": "machine_learning",
            "engine": "machine_learning",
            "confidence": "high" if machine_learning_score >= 4 else "medium",
            "matched_terms": [term for term in machine_learning_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["machine_learning"],
        }
    return {
        "discipline": "default",
        "engine": "default",
        "confidence": "fallback",
        "matched_terms": [],
        "subdisciplines": [],
    }


def infer_discipline_profile(project: str | Path, *, extra_text: str = "") -> dict[str, Any]:
    context = project_discipline_context(project, extra_text=extra_text)
    return infer_discipline_from_text(discipline_context_text(context))
