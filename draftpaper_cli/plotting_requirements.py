# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import re
from typing import Any


BASE_PUBLICATION_REQUIREMENTS = [
    ("matplotlib>=3.8", "Base plotting backend for publication figures."),
    ("SciencePlots>=2.1", "Scientific paper styles for Matplotlib."),
    ("numpy>=1.24", "Numerical arrays and figure statistics."),
    ("pandas>=2.0", "Tabular data handling for plotting workflows."),
    ("seaborn>=0.13", "Statistical plot styling and high-level chart helpers."),
]


PACKAGE_RULES = [
    {
        "name": "machine_learning_evaluation",
        "patterns": [
            r"\bclassification\b",
            r"\bclassifier\b",
            r"\bconfusion\b",
            r"\broc\b",
            r"\bprecision\b",
            r"\brecall\b",
            r"\bf1\b",
            r"\bmetric_summary\b",
            r"\bperformance\b",
            r"\brandom forest\b",
            r"\bxgboost\b",
            r"\bdeep learning\b",
            r"\bcnn\b",
            r"\btransformer\b",
        ],
        "requirements": [
            ("scikit-learn>=1.4", "Model metrics, validation curves, confusion matrices, and ML preprocessing."),
            ("scikit-plot>=0.3.7", "Quick scientific visualizations for common machine-learning evaluation outputs."),
        ],
    },
    {
        "name": "composable_heatmap",
        "patterns": [
            r"\bheatmap\b",
            r"\bcorrelation_heatmap\b",
            r"\bcluster\b",
            r"\bmatrix\b",
            r"\bcomposable\b",
            r"\bmulti[- ]?panel\b",
            r"\bomics\b",
            r"\becolog",
        ],
        "requirements": [
            ("marsilea>=0.5", "Composable heatmaps and multi-panel scientific figures."),
            ("legendkit>=0.3", "Publication-style legends for complex Matplotlib-based figures."),
        ],
    },
    {
        "name": "geospatial_remote_sensing",
        "patterns": [
            r"\bgis\b",
            r"\bgeograph",
            r"\bspatial\b",
            r"\bmap\b",
            r"\bzoning\b",
            r"\bremote sensing\b",
            r"\bndvi\b",
            r"\braster\b",
            r"\bsentinel\b",
            r"\blandsat\b",
            r"\bclimate\b",
            r"\bagricultur",
            r"\benvironment",
        ],
        "requirements": [
            ("geopandas>=0.14", "Vector geospatial data handling for maps and regional summaries."),
            ("rasterio>=1.3", "Raster and remote-sensing data access for map-like figures."),
            ("cartopy>=0.22", "Projection-aware cartographic plotting."),
            ("contextily>=1.5", "Basemap tiles for spatial context when appropriate."),
        ],
    },
    {
        "name": "astronomy",
        "patterns": [
            r"\bastronom",
            r"\bastrophys",
            r"\bx-ray\b",
            r"\blight curve\b",
            r"\bflare\b",
            r"\bspectrum\b",
            r"\bfits\b",
            r"\bcelestial\b",
            r"\bsky\b",
        ],
        "requirements": [
            ("astropy>=6.0", "Astronomical tables, FITS handling, coordinates, and time-series support."),
            ("astroquery>=0.4.7", "Optional access to astronomical archive metadata and catalog context."),
            ("reproject>=0.13", "Astronomical image reprojection for sky-map figures."),
        ],
    },
    {
        "name": "statistics_ecology",
        "patterns": [
            r"\becolog",
            r"\bbiodiversity\b",
            r"\bspecies\b",
            r"\babundance\b",
            r"\bregression\b",
            r"\blinear_fit\b",
            r"\banova\b",
            r"\bmixed model\b",
        ],
        "requirements": [
            ("scipy>=1.11", "Statistical tests, distributions, and numerical routines."),
            ("statsmodels>=0.14", "Regression diagnostics and statistical model summaries."),
        ],
    },
]


def _blob(*items: Any) -> str:
    return " ".join(str(item or "") for item in items).lower()


def _figure_blob(figure_plan: dict[str, Any]) -> str:
    parts: list[str] = []
    for figure in figure_plan.get("figures") or []:
        for key in [
            "id",
            "title",
            "figure_type",
            "visualization_type",
            "scientific_question",
            "result_claim_template",
            "x",
            "y",
            "group",
        ]:
            parts.append(str(figure.get(key) or ""))
        parts.extend(str(item) for item in figure.get("required_columns") or [])
        parts.extend(str(item) for item in figure.get("statistical_transform") or [])
    return _blob(*parts)


def plan_plotting_requirements(
    *,
    figure_plan: dict[str, Any],
    project_meta: dict[str, Any],
    method_requirements: dict[str, Any],
    method_text: str = "",
) -> dict[str, Any]:
    """Return publication plotting packages implied by the current figure plan and research context."""
    context = _blob(
        project_meta.get("idea"),
        project_meta.get("field"),
        project_meta.get("target_journal"),
        method_requirements.get("user_method"),
        " ".join(str(item) for item in method_requirements.get("method_families") or []),
        method_text,
        _figure_blob(figure_plan),
    )
    requirement_map: dict[str, dict[str, str]] = {
        package: {"package": package, "reason": reason, "source": "base_publication"}
        for package, reason in BASE_PUBLICATION_REQUIREMENTS
    }
    matched_rules: list[str] = []
    for rule in PACKAGE_RULES:
        if not any(re.search(pattern, context, flags=re.IGNORECASE) for pattern in rule["patterns"]):
            continue
        matched_rules.append(str(rule["name"]))
        for package, reason in rule["requirements"]:
            requirement_map.setdefault(package, {"package": package, "reason": reason, "source": str(rule["name"])})
    requirements = list(requirement_map.values())
    return {
        "status": "planned",
        "matched_rules": matched_rules,
        "requirements": requirements,
        "packages": [item["package"] for item in requirements],
        "install_command": "python -m pip install -r methods/requirements-publication.txt",
        "notes": [
            "Requirements are inferred from the current figure plan, project idea, field, and method description.",
            "The generated analysis runtime still checks imports at execution time and uses available backends conservatively.",
        ],
    }


def render_requirements_txt(plan: dict[str, Any]) -> str:
    lines = [
        "# Auto-generated publication plotting requirements.",
        "# Install from the project root with:",
        "# python -m pip install -r methods/requirements-publication.txt",
        "",
    ]
    for item in plan.get("requirements") or []:
        package = str(item.get("package") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not package:
            continue
        lines.append(f"# {reason}")
        lines.append(package)
    return "\n".join(lines).rstrip() + "\n"
