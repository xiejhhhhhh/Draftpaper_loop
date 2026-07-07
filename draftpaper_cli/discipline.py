# Copyright (c) 2026 Jinray Xie
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
        "xgboost",
        "gradient boosting",
        "stacking",
        "shap",
        "feature importance",
        "observed-predicted",
        "r2",
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
    finance_terms = [
        "finance",
        "financial",
        "asset pricing",
        "portfolio",
        "return",
        "volatility",
        "event study",
        "factor model",
        "stock",
        "market",
        "risk",
        "backtest",
    ]
    medicine_terms = [
        "medicine",
        "clinical",
        "patient",
        "ehr",
        "cohort",
        "trial",
        "survival analysis",
        "diagnosis",
        "treatment",
        "hazard ratio",
        "medical",
    ]
    biology_terms = [
        "biology",
        "gene",
        "protein",
        "assay",
        "cell",
        "differential expression",
        "pathway",
        "replicate",
        "fold change",
        "fdr",
    ]
    engineering_terms = [
        "engineering",
        "sensor",
        "signal",
        "finite element",
        "cfd",
        "simulation",
        "control",
        "reliability",
        "fatigue",
        "boundary condition",
        "mesh",
    ]
    geography_score = sum(1 for term in geography_terms if term in lowered)
    astronomy_score = sum(1 for term in astronomy_terms if term in lowered)
    machine_learning_score = sum(1 for term in machine_learning_terms if term in lowered)
    ecology_score = sum(1 for term in ecology_terms if term in lowered)
    bioinformatics_score = sum(1 for term in bioinformatics_terms if term in lowered)
    finance_score = sum(1 for term in finance_terms if term in lowered)
    medicine_score = sum(1 for term in medicine_terms if term in lowered)
    biology_score = sum(1 for term in biology_terms if term in lowered)
    engineering_score = sum(1 for term in engineering_terms if term in lowered)
    scores = {
        "geography": geography_score,
        "astronomy": astronomy_score,
        "machine_learning": machine_learning_score,
        "ecology": ecology_score,
        "bioinformatics": bioinformatics_score,
        "finance": finance_score,
        "medicine": medicine_score,
        "biology": biology_score,
        "engineering": engineering_score,
    }

    def select_primary_discipline() -> str:
        """Choose the subject discipline before method-only secondaries.

        The discipline profile is later used to select data, method, and review
        plugins. A project can mention generic method terms such as
        classification, validation, treatment, or signal while still being an
        astronomy or geography paper. The primary module should therefore be the
        strongest subject domain, while method families such as machine learning
        remain secondary modules unless no subject domain is detected.
        """

        subject_priority = [
            "astronomy",
            "geography",
            "medicine",
            "biology",
            "bioinformatics",
            "finance",
            "engineering",
            "ecology",
        ]
        subject_scores = {
            discipline: scores.get(discipline, 0)
            for discipline in subject_priority
            if scores.get(discipline, 0) >= 2
        }
        if subject_scores:
            return max(
                subject_scores,
                key=lambda item: (subject_scores[item], -subject_priority.index(item)),
            )
        if machine_learning_score >= 2:
            return "machine_learning"
        return "default"

    primary_discipline = select_primary_discipline()

    def with_composite_fields(profile: dict[str, Any]) -> dict[str, Any]:
        primary = str(profile.get("discipline") or "default")
        secondaries = []
        for discipline, score in scores.items():
            if discipline == primary:
                continue
            threshold = 2 if discipline == "machine_learning" else 4
            if score >= threshold:
                secondaries.append(discipline)
        modules = ["default"]
        if primary != "default":
            modules.append(primary)
        for discipline in sorted(secondaries, key=lambda item: (-scores[item], item)):
            if discipline not in modules:
                modules.append(discipline)
        profile["primary_discipline"] = primary
        profile["secondary_disciplines"] = secondaries
        profile["discipline_scores"] = scores
        profile["discipline_modules"] = modules
        profile["is_composite"] = len([item for item in modules if item != "default"]) > 1
        return profile

    if primary_discipline == "bioinformatics":
        subdisciplines = []
        if any(term in lowered for term in ("geo", "sra", "ena")):
            subdisciplines.append("public_repository")
        if any(term in lowered for term in ("rna-seq", "rna seq", "gene expression", "transcriptomics")):
            subdisciplines.append("expression_analysis")
        if any(term in lowered for term in ("fastq", "fasta", "sequence", "genomics")):
            subdisciplines.append("sequence_data")
        return with_composite_fields({
            "discipline": "bioinformatics",
            "engine": "bioinformatics",
            "confidence": "high" if bioinformatics_score >= 4 else "medium",
            "matched_terms": [term for term in bioinformatics_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["bioinformatics"],
        })
    if primary_discipline == "medicine":
        subdisciplines = []
        if any(term in lowered for term in ("ehr", "patient", "cohort")):
            subdisciplines.append("clinical_cohort")
        if any(term in lowered for term in ("survival analysis", "hazard ratio", "follow-up")):
            subdisciplines.append("survival_analysis")
        if any(term in lowered for term in ("trial", "treatment", "diagnosis")):
            subdisciplines.append("clinical_study")
        return with_composite_fields({
            "discipline": "medicine",
            "engine": "medicine",
            "confidence": "high" if medicine_score >= 4 else "medium",
            "matched_terms": [term for term in medicine_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["medicine"],
        })
    if primary_discipline == "biology":
        subdisciplines = []
        if any(term in lowered for term in ("gene", "differential expression", "fold change", "fdr")):
            subdisciplines.append("molecular_analysis")
        if any(term in lowered for term in ("protein", "pathway")):
            subdisciplines.append("protein_pathway")
        if any(term in lowered for term in ("assay", "cell", "replicate")):
            subdisciplines.append("assay_qc")
        return with_composite_fields({
            "discipline": "biology",
            "engine": "biology",
            "confidence": "high" if biology_score >= 4 else "medium",
            "matched_terms": [term for term in biology_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["biology"],
        })
    if primary_discipline == "finance":
        subdisciplines = []
        if any(term in lowered for term in ("event study", "return", "stock", "market")):
            subdisciplines.append("empirical_asset_pricing")
        if any(term in lowered for term in ("portfolio", "backtest")):
            subdisciplines.append("portfolio_backtesting")
        if any(term in lowered for term in ("volatility", "risk")):
            subdisciplines.append("risk_modeling")
        return with_composite_fields({
            "discipline": "finance",
            "engine": "finance",
            "confidence": "high" if finance_score >= 4 else "medium",
            "matched_terms": [term for term in finance_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["finance"],
        })
    if primary_discipline == "engineering":
        subdisciplines = []
        if any(term in lowered for term in ("sensor", "signal")):
            subdisciplines.append("signal_processing")
        if any(term in lowered for term in ("finite element", "cfd", "mesh", "boundary condition")):
            subdisciplines.append("simulation_analysis")
        if any(term in lowered for term in ("reliability", "fatigue")):
            subdisciplines.append("reliability_engineering")
        return with_composite_fields({
            "discipline": "engineering",
            "engine": "engineering",
            "confidence": "high" if engineering_score >= 4 else "medium",
            "matched_terms": [term for term in engineering_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["engineering"],
        })
    if primary_discipline == "ecology":
        subdisciplines = []
        if any(term in lowered for term in ("environmental monitoring", "water quality", "pollution")):
            subdisciplines.append("environmental_monitoring")
        if any(term in lowered for term in ("biodiversity", "habitat", "ecosystem")):
            subdisciplines.append("ecology")
        if any(term in lowered for term in ("netcdf", "geotiff", "spatial", "raster")):
            subdisciplines.append("environmental_raster")
        return with_composite_fields({
            "discipline": "ecology",
            "engine": "ecology",
            "confidence": "high" if ecology_score >= 4 else "medium",
            "matched_terms": [term for term in ecology_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["ecology"],
        })
    if primary_discipline == "geography":
        subdisciplines = []
        if any(term in lowered for term in ("remote sensing", "ndvi", "vegetation index", "raster", "google earth engine", "gee", "geotiff")):
            subdisciplines.append("remote_sensing")
        if any(term in lowered for term in ("wheat", "yield", "crop", "agriculture", "agronomy")):
            subdisciplines.append("agricultural_geography")
        if any(term in lowered for term in ("spatial", "gis", "geographic", "geospatial", "region", "zoning", "shapefile")):
            subdisciplines.append("spatial_analysis")
        return with_composite_fields({
            "discipline": "geography",
            "engine": "geography",
            "confidence": "high" if geography_score >= 4 else "medium",
            "matched_terms": [term for term in geography_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["geography"],
        })
    if primary_discipline == "astronomy":
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
        return with_composite_fields({
            "discipline": "astronomy",
            "engine": "astronomy",
            "confidence": "high" if astronomy_score >= 4 else "medium",
            "matched_terms": [term for term in astronomy_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["astronomy"],
        })
    if primary_discipline == "machine_learning":
        subdisciplines = []
        if any(term in lowered for term in ("classification", "classifier", "f1", "accuracy")):
            subdisciplines.append("supervised_learning")
        if any(term in lowered for term in ("deep learning", "transformer", "cnn", "resnet", "tcn", "neural network")):
            subdisciplines.append("deep_learning")
        if any(term in lowered for term in ("baseline", "ablation", "validation", "cross-validation")):
            subdisciplines.append("model_validation")
        return with_composite_fields({
            "discipline": "machine_learning",
            "engine": "machine_learning",
            "confidence": "high" if machine_learning_score >= 4 else "medium",
            "matched_terms": [term for term in machine_learning_terms if term in lowered],
            "subdisciplines": sorted(set(subdisciplines)) or ["machine_learning"],
        })
    return with_composite_fields({
        "discipline": "default",
        "engine": "default",
        "confidence": "fallback",
        "matched_terms": [],
        "subdisciplines": [],
    })


def infer_discipline_profile(project: str | Path, *, extra_text: str = "") -> dict[str, Any]:
    context = project_discipline_context(project, extra_text=extra_text)
    return infer_discipline_from_text(discipline_context_text(context))
