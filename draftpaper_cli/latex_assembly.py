# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .bibliography import BibliographyError, materialize_effective_bibliography
from .citation_utils import bibtex_keys_in_text, citation_keys_in_text
from .evidence_snapshot import EvidenceSnapshotMismatch, validate_promoted_snapshot_for_writing
from .journal_profile import JournalProfileError, validate_journal_profile_for_writing
from .latex_utils import safe_latex_text
from .metadata import GENERATOR_TEX_COMMENT
from .manuscript_artifacts import SECTION_CANONICAL_ARTIFACTS, SECTION_ORDER
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .section_contracts import validate_section_writing


SECTION_INPUTS = [(section, SECTION_CANONICAL_ARTIFACTS[section]) for section in SECTION_ORDER]

LATEX_INPUTS = [relative for _name, relative in SECTION_INPUTS] + [
    "references/library.bib",
    "journal_profile/journal_profile.json",
    "core_evidence/core_evidence_report.json",
    "results/result_manifest.yaml",
    "latex/template/main.tex",
]

SECTION_TITLES = {
    "introduction": "Introduction",
    "data": "Data",
    "methods": "Methods",
    "results": "Results",
    "discussion": "Discussion",
}

LATEX_OUTPUTS = [
    "latex/main.tex",
    "latex/library.bib",
    "latex/sections/introduction.tex",
    "latex/sections/data.tex",
    "latex/sections/methods.tex",
    "latex/sections/results.tex",
    "latex/sections/result_artifacts.tex",
    "latex/sections/discussion.tex",
]

PDF_OUTPUTS = [
    "latex/main.pdf",
    "latex/main.compile.log",
    "latex/pdf_compile_manifest.json",
]


def _pdf_compile_input_hashes(project_path: Path) -> dict[str, str]:
    """Hash the assembled sources and publication assets consumed by LaTeX."""
    candidates = {
        project_path / "latex" / "main.tex",
        project_path / "latex" / "library.bib",
        *list((project_path / "latex" / "sections").glob("*.tex")),
        *list((project_path / "latex").glob("*.bst")),
        *list((project_path / "writing" / "table_fragments").glob("*.tex")),
        *list((project_path / "results" / "tables").glob("*.tex")),
        *list((project_path / "results" / "figures").glob("*")),
    }
    return {
        path.relative_to(project_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(candidates)
        if path.is_file()
    }


def pdf_compile_is_current(project: str | Path, manifest: dict[str, Any] | None = None) -> bool:
    """Return whether the recorded PDF was built from the current assembled inputs."""
    project_path = Path(project)
    pdf_path = project_path / "latex" / "main.pdf"
    if manifest is None:
        manifest_path = project_path / "latex" / "pdf_compile_manifest.json"
        if not manifest_path.is_file():
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return False
    if manifest.get("status") != "success" or not pdf_path.is_file():
        return False
    recorded_inputs = manifest.get("input_artifact_hashes")
    if not isinstance(recorded_inputs, dict) or not recorded_inputs:
        return False
    if recorded_inputs != _pdf_compile_input_hashes(project_path):
        return False
    return manifest.get("pdf_sha256") == hashlib.sha256(pdf_path.read_bytes()).hexdigest()


class LatexAssemblyError(RuntimeError):
    """Raised when final LaTeX assembly would use incomplete or stale inputs."""


class LatexCitationError(LatexAssemblyError):
    """Raised when assembled LaTeX cites keys that are absent from library.bib."""


def _bibtex_keys(content: str) -> set[str]:
    return bibtex_keys_in_text(content)


def _latex_citation_keys(content: str) -> set[str]:
    return citation_keys_in_text(content)


def _safe_latex_text(text: str) -> str:
    return safe_latex_text(text)


def _draftpaper_acknowledgments(*, aastex: bool = False) -> str:
    text = (
        "This study used Draftpaper-loop as an assistive tool for staged literature organization, "
        "analysis traceability, figure inventory, and manuscript drafting. The project is available at "
        r"\href{https://github.com/xiejhhhhhh/Draftpaper_loop}{Draftpaper-loop repository}."
    )
    if aastex:
        return "\\begin{acknowledgments}\n" + text + "\n\\end{acknowledgments}"
    return "\\section*{Acknowledgments}\n" + text


def _insert_acknowledgments(main_tex: str, acknowledgments: str) -> str:
    if "Draftpaper-loop" in main_tex:
        return main_tex
    match = re.search(r"\\bibliography(?:style)?\{", main_tex)
    if match:
        return main_tex[:match.start()].rstrip() + "\n\n" + acknowledgments + "\n\n" + main_tex[match.start():].lstrip()
    if "\\end{document}" in main_tex:
        return main_tex.replace("\\end{document}", acknowledgments + "\n\n\\end{document}", 1)
    return main_tex.rstrip() + "\n\n" + acknowledgments + "\n"


def _read_manuscript_metadata(project_path: Path) -> dict[str, Any]:
    path = project_path / "writing" / "manuscript_metadata.yaml"
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise LatexAssemblyError("writing/manuscript_metadata.yaml must contain a mapping.")
    abstract = str(payload.get("abstract") or "").strip()
    registry_path = project_path / "writing" / "scientific_evidence_registry.json"
    if abstract and registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise LatexAssemblyError("Scientific evidence registry is invalid JSON.") from exc
        report = validate_section_writing("abstract", abstract, registry if isinstance(registry, dict) else {})
        if report.get("decision") != "pass":
            details = "; ".join(str(item.get("detail") or item.get("kind")) for item in report.get("issues") or [])
            raise LatexAssemblyError("Manuscript abstract is stale or violates the current evidence contract: " + details)
    return payload


def _metadata_affiliations(metadata: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    lookup: dict[str, str] = {}
    ordered: list[str] = []
    for index, item in enumerate(metadata.get("affiliations") or [], start=1):
        if isinstance(item, dict):
            key = str(item.get("id") or index)
            name = str(item.get("name") or item.get("affiliation") or "").strip()
        else:
            key, name = str(index), str(item).strip()
        if name:
            lookup[key] = name
            ordered.append(name)
    return lookup, ordered


def _metadata_author_block(metadata: dict[str, Any], *, aastex: bool, elsarticle: bool = False) -> str:
    authors = metadata.get("authors") or []
    if not authors:
        return ""
    affiliation_lookup, ordered_affiliations = _metadata_affiliations(metadata)
    if elsarticle:
        lines: list[str] = []
        corresponding = str(metadata.get("corresponding_author") or "").strip()
        for item in authors:
            author = item if isinstance(item, dict) else {"name": str(item)}
            name = _safe_latex_text(str(author.get("name") or "").strip())
            if not name:
                continue
            keys = author.get("affiliations") or author.get("affiliation_ids") or []
            if isinstance(keys, (str, int)):
                keys = [keys]
            keys = [str(key) for key in keys]
            marker = ""
            if bool(author.get("corresponding")) or (corresponding and str(author.get("name") or "").strip() == corresponding):
                marker = r"\corref{cor1}"
            optional = "[" + ",".join(_safe_latex_text(key) for key in keys) + "]" if keys else ""
            lines.append(rf"\author{optional}{{{name}{marker}}}")
            email = author.get("email") or (metadata.get("email") if marker else None)
            if email:
                lines.append(rf"\ead{{{_safe_latex_text(str(email))}}}")
        if corresponding:
            lines.append(r"\cortext[cor1]{Corresponding author.}")
        for index, affiliation in enumerate(ordered_affiliations, start=1):
            item = metadata.get("affiliations")[index - 1] if isinstance(metadata.get("affiliations"), list) else None
            key = str(item.get("id") if isinstance(item, dict) and item.get("id") else index)
            lines.append(rf"\address[{_safe_latex_text(key)}]{{{_safe_latex_text(str(affiliation))}}}")
        return "\n".join(lines)
    if aastex:
        lines: list[str] = []
        for item in authors:
            author = item if isinstance(item, dict) else {"name": str(item)}
            name = _safe_latex_text(str(author.get("name") or "").strip())
            if not name:
                continue
            author_options: list[str] = []
            if author.get("orcid"):
                author_options.append("orcid=" + _safe_latex_text(str(author.get("orcid"))))
            if author.get("gname"):
                author_options.append("gname=" + _safe_latex_text(str(author.get("gname"))))
            if author.get("sname"):
                author_options.append("sname=" + _safe_latex_text(str(author.get("sname"))))
            optional = "[" + ",".join(author_options) + "]" if author_options else ""
            lines.append(rf"\author{optional}{{{name}}}")
            keys = author.get("affiliations") or author.get("affiliation_ids") or []
            if isinstance(keys, (str, int)):
                keys = [keys]
            affiliations = [affiliation_lookup.get(str(key), str(key)) for key in keys]
            if not affiliations and len(ordered_affiliations) == 1:
                affiliations = ordered_affiliations
            for affiliation in affiliations:
                lines.append(rf"\affiliation{{{_safe_latex_text(str(affiliation))}}}")
            email = author.get("email") or (metadata.get("email") if author.get("corresponding") else None)
            if email:
                lines.append(rf"\email{{{_safe_latex_text(str(email))}}}")
        return "\n".join(lines)
    names = []
    for item in authors:
        author = item if isinstance(item, dict) else {"name": str(item)}
        name = str(author.get("name") or "").strip()
        if name:
            names.append(_safe_latex_text(name))
    if not names:
        return ""
    joined_names = r" \and ".join(names)
    lines = [rf"\author{{{joined_names}"]
    details = [_safe_latex_text(value) for value in ordered_affiliations]
    corresponding = metadata.get("corresponding_author")
    email = metadata.get("email")
    if corresponding:
        details.append("Correspondence: " + _safe_latex_text(str(corresponding)))
    if email:
        details.append(_safe_latex_text(str(email)))
    if details:
        lines[0] += r" \\ \small " + r"; ".join(details)
    lines[0] += "}"
    return "\n".join(lines)


def _metadata_back_matter(metadata: dict[str, Any], *, aastex: bool) -> str:
    fields = [
        ("credit_contributions", "Author Contributions"),
        ("funding", "Funding"),
        ("data_availability", "Data Availability"),
        ("code_availability", "Code Availability"),
        ("competing_interests", "Competing Interests"),
        ("ethics_consent", "Ethics and Consent"),
        ("supplementary_material", "Supplementary Material"),
    ]
    parts: list[str] = []
    acknowledgments = metadata.get("acknowledgments")
    if acknowledgments:
        content = _safe_latex_text(str(acknowledgments))
        parts.append(
            "\\begin{acknowledgments}\n" + content + "\n\\end{acknowledgments}"
            if aastex else "\\section*{Acknowledgments}\n" + content
        )
    for key, title in fields:
        value = metadata.get(key)
        if value:
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            parts.append(rf"\section*{{{title}}}" + "\n" + _safe_latex_text(str(value)))
    links = []
    for key in ("repository_links", "doi_links"):
        value = metadata.get(key) or []
        if isinstance(value, str):
            value = [value]
        links.extend(str(item) for item in value)
    if links:
        parts.append(r"\section*{Related Links}" + "\n" + r"; ".join(rf"\url{{{item}}}" for item in links))
    return "\n\n".join(parts)


def _apply_manuscript_metadata(main_tex: str, metadata: dict[str, Any], *, aastex: bool) -> str:
    if not metadata:
        return main_tex
    # A journal profile can identify an AAS target before the candidate
    # template has been replaced with an actual AASTeX document class. Do not
    # emit AASTeX-only author options into a generic test or user template.
    aastex = bool(aastex and re.search(r"\\documentclass(?:\[[^\]]*\])?\{aastex", main_tex, flags=re.I))
    elsarticle = bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{elsarticle\}", main_tex, flags=re.I))
    title = metadata.get("title")
    if title:
        replacement = rf"\title{{{_safe_latex_text(str(title))}}}"
        if re.search(r"\\title\{[^{}]*\}", main_tex):
            main_tex = re.sub(r"\\title\{[^{}]*\}", lambda _match: replacement, main_tex, count=1)
        else:
            main_tex = main_tex.replace("\\begin{document}", replacement + "\n\\begin{document}", 1)
    short_title = metadata.get("short_title")
    if short_title and aastex:
        short_title_command = rf"\shorttitle{{{_safe_latex_text(str(short_title))}}}"
        if re.search(r"\\shorttitle\{[^{}]*\}", main_tex):
            main_tex = re.sub(r"\\shorttitle\{[^{}]*\}", lambda _match: short_title_command, main_tex, count=1)
        else:
            main_tex = main_tex.replace("\\begin{document}", short_title_command + "\n\\begin{document}", 1)
    abstract = metadata.get("abstract")
    if abstract:
        abstract_block = "\\begin{abstract}\n" + str(abstract).strip() + "\n\\end{abstract}"
        if re.search(r"\\begin\{abstract\}.*?\\end\{abstract\}", main_tex, flags=re.S):
            main_tex = re.sub(
                r"\\begin\{abstract\}.*?\\end\{abstract\}",
                lambda _match: abstract_block,
                main_tex,
                count=1,
                flags=re.S,
            )
        else:
            main_tex = main_tex.replace("\\begin{document}", "\\begin{document}\n\n" + abstract_block, 1)
    keywords = metadata.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    if keywords:
        rendered_keywords = "; ".join(_safe_latex_text(str(item)) for item in keywords if str(item).strip())
        if aastex:
            keyword_block = rf"\keywords{{{rendered_keywords}}}"
            if re.search(r"\\keywords\{[^{}]*\}", main_tex):
                main_tex = re.sub(r"\\keywords\{[^{}]*\}", lambda _match: keyword_block, main_tex, count=1)
            else:
                main_tex = main_tex.replace("\\begin{document}", keyword_block + "\n\\begin{document}", 1)
        elif elsarticle:
            keyword_block = "\\begin{keyword}\n" + rendered_keywords + "\n\\end{keyword}"
            if re.search(r"\\begin\{keyword\}.*?\\end\{keyword\}", main_tex, flags=re.S):
                main_tex = re.sub(
                    r"\\begin\{keyword\}.*?\\end\{keyword\}",
                    lambda _match: keyword_block,
                    main_tex,
                    count=1,
                    flags=re.S,
                )
            elif "\\end{frontmatter}" in main_tex:
                main_tex = main_tex.replace("\\end{frontmatter}", keyword_block + "\n\\end{frontmatter}", 1)
            else:
                main_tex = main_tex.replace("\\begin{document}", "\\begin{document}\n\n" + keyword_block, 1)
        elif rendered_keywords and "\\textbf{Keywords:}" not in main_tex:
            keyword_block = rf"\noindent\textbf{{Keywords:}} {rendered_keywords}"
            abstract_end = "\\end{abstract}"
            if abstract_end in main_tex:
                main_tex = main_tex.replace(abstract_end, abstract_end + "\n\n" + keyword_block, 1)
    author_block = _metadata_author_block(metadata, aastex=aastex, elsarticle=elsarticle)
    if author_block:
        main_tex = re.sub(r"(?m)^\s*\\(?:author|affiliation|email|orcid|address|cortext|ead)\b[^\n]*\n?", "", main_tex)
        title_match = re.search(r"\\title\{[^{}]*\}", main_tex)
        if title_match:
            main_tex = main_tex[:title_match.end()] + "\n" + author_block + main_tex[title_match.end():]
    back_matter = _metadata_back_matter(metadata, aastex=aastex)
    if back_matter:
        main_tex = _insert_acknowledgments(main_tex, back_matter)
    return main_tex


def _ensure_aastex_author_block(main_tex: str) -> str:
    """AASTeX 7 requires every author to carry an affiliation.

    Public templates often ship with placeholder author fields, while local
    Draftpaper-loop projects may not know final author metadata yet.  Keep the
    placeholder explicit and review-oriented so PDF compilation works without
    pretending that the manuscript metadata is final.
    """
    if not re.search(r"\\documentclass(?:\[[^\]]*\])?\{aastex", main_tex, flags=re.I):
        return main_tex
    author_block = (
        "\\author{Manuscript author to be supplied}\n"
        "\\affiliation{Affiliation to be supplied by the authors}\n"
        "\\email{corresponding.author@placeholder.invalid}"
    )
    if re.search(r"\\author\{\s*\}", main_tex):
        return re.sub(r"\\author\{\s*\}", lambda _match: author_block, main_tex, count=1)
    if re.search(r"\\author\{[^{}]+\}", main_tex) and re.search(r"\\affiliation\{[^{}]+\}", main_tex):
        return main_tex
    title_match = re.search(r"\\title\{[^{}]*\}", main_tex)
    if title_match:
        return main_tex[:title_match.end()] + "\n" + author_block + main_tex[title_match.end():]
    return main_tex


def _require_inputs(project_path: Path) -> None:
    missing = [relative for relative in LATEX_INPUTS if not (project_path / relative).exists()]
    if missing:
        raise LatexAssemblyError("LaTeX assembly requires all section files and library.bib. Missing: " + ", ".join(missing))


def _require_non_stale_input_stages(project_meta: dict[str, Any]) -> None:
    stale = []
    invalid_status = []
    stages = project_meta.get("stages") or {}
    for stage in [
        "introduction",
        "data",
        "data_writing",
        "method_plan",
        "methods",
        "methods_writing",
        "result_validity",
        "core_evidence",
        "results",
        "discussion",
        "references",
        "journal_profile",
    ]:
        stage_meta = stages.get(stage) or {}
        if stage_meta.get("stale"):
            stale.append(stage)
        if stage_meta.get("status") not in {"draft", "approved", "completed"}:
            invalid_status.append(f"{stage}={stage_meta.get('status')}")
    if stale:
        raise LatexAssemblyError("Cannot assemble LaTeX while input stages are stale: " + ", ".join(stale))
    if invalid_status:
        raise LatexAssemblyError("Cannot assemble LaTeX before input stages are ready: " + ", ".join(invalid_status))


def _read_sections(project_path: Path) -> dict[str, str]:
    sections = {}
    for name, relative in SECTION_INPUTS:
        sections[name] = (project_path / relative).read_text(encoding="utf-8")
    return sections


def _validate_citations(project_path: Path, sections: dict[str, str]) -> tuple[set[str], set[str]]:
    try:
        bibtex, _report = materialize_effective_bibliography(project_path)
    except BibliographyError as exc:
        raise LatexCitationError(str(exc)) from exc
    bib_keys = _bibtex_keys(bibtex)
    citation_keys: set[str] = set()
    for content in sections.values():
        citation_keys.update(_latex_citation_keys(content))
    missing = sorted(citation_keys - bib_keys)
    if missing:
        raise LatexCitationError("LaTeX cites keys that are missing from library.bib: " + ", ".join(missing))
    return citation_keys, bib_keys


def _compact_data_roles_table(project_path: Path) -> str | None:
    """Render the canonical Table 1 values at a readable review width.

    The machine-readable result table retains every registered field.  The
    manuscript projection uses five wrapped columns and omits only the
    redundant key-field column, which lets the role, unit, count, audit use,
    and claim boundary stay readable without a shrink-to-fit transform.
    """
    source = project_path / "results" / "tables" / "table_01_data_roles.csv"
    if not source.is_file():
        return None
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream))
    except (OSError, csv.Error):
        return None
    required = {
        "Dataset or asset",
        "Analytical role",
        "Observation unit",
        "Spatial/temporal support",
        "n",
        "Validation use",
        "Qualification",
    }
    if not records or not required.issubset(records[0]):
        return None
    rendered_rows = []
    for record in records:
        values = [
            f"{record['Dataset or asset']}; {record['Analytical role']}",
            f"{record['Observation unit']}; {record['Spatial/temporal support']}",
            record["n"],
            record["Validation use"],
            record["Qualification"],
        ]
        rendered_rows.append(" & ".join(_safe_latex_text(value) for value in values) + r" \\")
    return "\n".join([
        r"\begin{table*}[!t]",
        r"\centering",
        r"\footnotesize",
        r"\renewcommand{\arraystretch}{1.16}",
        r"\setlength{\tabcolsep}{3.0pt}",
        r"\caption{Data sources, analytical units, and validation roles. GEE = Google Earth Engine; CRS = coordinate reference system. Cartographic context and injected anomalies are not independent external ground truth.}",
        r"\label{tab:data-roles}",
        r"\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.18\textwidth}>{\raggedright\arraybackslash}p{0.20\textwidth}r>{\raggedright\arraybackslash}p{0.24\textwidth}>{\raggedright\arraybackslash}p{0.25\textwidth}@{}}",
        r"\toprule",
        r"\textbf{Asset and declared role} & \textbf{Unit and support} & \textbf{n} & \textbf{Audit or validation use} & \textbf{Interpretive boundary} \\",
        r"\midrule",
        *rendered_rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
        "",
    ])


def _compact_self_audit_table(project_path: Path) -> str | None:
    """Render the canonical B0--B4 ablation in readable audit columns."""
    source = project_path / "results" / "tables" / "table_02_self_audit_ablation.csv"
    if not source.is_file():
        return None
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream))
    except (OSError, csv.Error):
        return None
    required = {
        "Variant",
        "Added rule",
        "Retained n (%)",
        "Delta retained n",
        "Newly flagged n",
        "Unique support Q",
        "Reporting units U",
        "Raw Neff",
        "Category purity",
        "Rank stability",
        "Event denominator",
    }
    if not records or not required.issubset(records[0]):
        return None
    rendered_rows = []
    for record in records:
        values = [
            record["Variant"],
            record["Added rule"],
            f"{record['Retained n (%)']}; delta n = {record['Delta retained n']}",
            f"{record['Newly flagged n']}; {record['Event denominator']}",
            f"Q = {record['Unique support Q']}; U = {record['Reporting units U']}; Neff = {record['Raw Neff']}",
            record["Category purity"],
            record["Rank stability"],
        ]
        rendered_rows.append(" & ".join(_safe_latex_text(value) for value in values) + r" \\")
    return "\n".join([
        r"\begin{table*}[!t]",
        r"\centering",
        r"\scriptsize",
        r"\renewcommand{\arraystretch}{1.14}",
        r"\setlength{\tabcolsep}{2.5pt}",
        r"\caption{Quantitative self-audit ablation and denominator changes across B0--B4. New-event denominators remain explicit; B2--B4 rank stability is NE (one unit).}",
        r"\label{tab:self-audit-ablation}",
        r"\begin{tabular}{@{}l>{\raggedright\arraybackslash}p{0.13\textwidth}>{\raggedright\arraybackslash}p{0.12\textwidth}>{\raggedright\arraybackslash}p{0.23\textwidth}>{\raggedright\arraybackslash}p{0.16\textwidth}>{\raggedright\arraybackslash}p{0.12\textwidth}>{\raggedright\arraybackslash}p{0.13\textwidth}@{}}",
        r"\toprule",
        r"\textbf{Variant} & \textbf{Added rule} & \textbf{Retained $n$ and delta} & \textbf{New event and denominator} & \textbf{Support ($Q$, $U$, $N_{\mathrm{eff}}$)} & \textbf{Category purity} & \textbf{Rank stability} \\",
        r"\midrule",
        *rendered_rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
        "",
    ])


def _copy_sections(project_path: Path, sections: dict[str, str]) -> list[str]:
    section_dir = project_path / "latex" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, content in sections.items():
        relative = f"latex/sections/{name}.tex"
        rendered = content
        if name == "results":
            compact_table = _compact_data_roles_table(project_path)
            compact_self_audit = _compact_self_audit_table(project_path)
            compact_relative = "latex/sections/table_01_data_roles_review.tex"
            if compact_table is not None:
                (project_path / compact_relative).write_text(compact_table, encoding="utf-8")
                outputs.append(compact_relative)
            compact_self_audit_relative = "latex/sections/table_02_self_audit_ablation_review.tex"
            if compact_self_audit is not None:
                (project_path / compact_self_audit_relative).write_text(compact_self_audit, encoding="utf-8")
                outputs.append(compact_self_audit_relative)

            # Candidate prose refers to publication tables by their semantic
            # manuscript namespace. Resolve that namespace only in the
            # assembled source, where the LaTeX working directory is `latex/`.
            def _resolve_result_table(match: re.Match[str]) -> str:
                table_name = match.group(1)
                if compact_table is not None and Path(table_name).stem == "table_01_data_roles":
                    return r"\input{sections/table_01_data_roles_review}"
                if compact_self_audit is not None and Path(table_name).stem == "table_02_self_audit_ablation":
                    return r"\input{sections/table_02_self_audit_ablation_review}"
                return rf"\input{{../results/tables/{table_name}}}"

            rendered = re.sub(r"\\input\{tables/([^{}\n]+)\}", _resolve_result_table, rendered)
        (project_path / relative).write_text(rendered, encoding="utf-8")
        outputs.append(relative)
    return outputs


def _copy_bibtex(project_path: Path) -> None:
    try:
        bibtex, _report = materialize_effective_bibliography(project_path)
    except BibliographyError as exc:
        raise LatexAssemblyError(str(exc)) from exc
    (project_path / "latex" / "library.bib").write_text(bibtex, encoding="utf-8")


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_result_label(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9:-]+", "-", str(value or "result")).strip("-") or "result"


def _figure_caption(entry: dict[str, Any], metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in (
        entry.get("caption_draft"),
        entry.get("result_claim"),
        metadata.get("interpretation_summary"),
    ):
        text = str(value or "").strip().rstrip(".")
        if text and text.lower() not in {item.lower() for item in parts}:
            parts.append(text)
    boundary = str(metadata.get("claim_boundary") or entry.get("claim_boundary") or "").strip().rstrip(".")
    if boundary and not any(boundary.lower() in part.lower() for part in parts):
        parts.append(boundary)
    caption = ". ".join(parts).strip()
    if caption and not caption.endswith("."):
        caption += "."
    return caption or "Result figure."


def _result_figure_entries(project_path: Path) -> list[dict[str, Any]]:
    manifest = _read_mapping(project_path / "results" / "result_manifest.yaml")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    main_items = list(manifest.get("main_figures") or [])
    appendix_items = list(manifest.get("appendix_figures") or [])
    if not main_items and not appendix_items:
        # Read legacy manifests that only expose the combined figure list.
        main_items = list(manifest.get("figures") or [])
    if not main_items and not appendix_items:
        # A minimal legacy project may have a successful run manifest but no
        # figure projection yet. Use only its existing declared images as a
        # compatibility input; normal projects should populate result_manifest.
        run_manifest = _read_mapping(project_path / "methods" / "run_manifest.yaml")
        declared_outputs = []
        for key in ("figures_generated", "output_files", "declared_outputs"):
            values = run_manifest.get(key) or []
            declared_outputs.extend([values] if isinstance(values, str) else values)
        for value in dict.fromkeys(str(item).replace("\\", "/") for item in declared_outputs):
            if Path(value).suffix.lower() not in {".png", ".jpg", ".jpeg", ".pdf", ".svg"}:
                continue
            if not value.startswith("results/figures/") or not (project_path / value).is_file():
                continue
            main_items.append({"id": Path(value).stem, "path": value, "manuscript_role": "main"})
    else:
        # Older structured manifests may omit one of the projections while
        # retaining the combined list. Fill only the missing projection and
        # keep the explicit main/appendix classification authoritative.
        for item in manifest.get("figures") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("manuscript_role") or "").lower() == "appendix":
                if not any(str(existing.get("path") or existing.get("id") or "") == str(item.get("path") or item.get("id") or "") for existing in appendix_items if isinstance(existing, dict)):
                    appendix_items.append(item)
            elif not any(str(existing.get("path") or existing.get("id") or "") == str(item.get("path") or item.get("id") or "") for existing in main_items if isinstance(existing, dict)):
                main_items.append(item)
    for collection in (main_items, appendix_items):
        for item in collection if isinstance(collection, list) else []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("path") or item.get("id") or "")
            if key and key not in seen:
                seen.add(key)
                entries.append(item)
    # Only manifest-declared figures belong in the manuscript. The project may
    # retain older renderings and candidate formats under results/figures, but
    # silently importing every file creates duplicate floats and can make the
    # final paper non-reproducible with respect to the frozen figure contract.
    return entries


def _render_result_artifacts(project_path: Path) -> tuple[str, list[str]]:
    metadata_payload = _read_mapping(project_path / "results" / "figure_metadata.json")
    metadata_entries = [item for item in metadata_payload.get("figures") or [] if isinstance(item, dict)]
    by_path = {str(item.get("path") or ""): item for item in metadata_entries}
    by_id = {
        str(item.get("figure_id") or item.get("storyboard_id") or ""): item
        for item in metadata_entries
    }
    manuscript_metadata = _read_manuscript_metadata(project_path)
    raw_caption_overrides = manuscript_metadata.get("figure_captions")
    caption_overrides: dict[str, Any] = dict(raw_caption_overrides) if isinstance(raw_caption_overrides, dict) else {}
    blocks: list[str] = []
    labels: list[str] = []
    for entry in _result_figure_entries(project_path):
        relative = str(entry.get("path") or "").replace("\\", "/")
        if not relative or not (project_path / relative).is_file():
            raise LatexAssemblyError(f"Result figure declared by the manifest is missing: {relative or '<empty path>'}")
        identifier = str(entry.get("id") or Path(relative).stem)
        label = "fig:" + _safe_result_label(identifier)
        metadata = by_path.get(relative) or by_id.get(str(entry.get("storyboard_id") or "")) or {}
        override = next(
            (
                caption_overrides.get(key)
                for key in (identifier, str(entry.get("storyboard_id") or ""), relative, Path(relative).stem)
                if key and caption_overrides.get(key)
            ),
            None,
        )
        caption = _safe_latex_text(str(override) if override else _figure_caption(entry, metadata))
        environment = "figure" if str(entry.get("manuscript_role") or "main").lower() != "appendix" else "figure"
        blocks.append(
            "\n".join(
                [
                    rf"\begin{{{environment}}}[htbp]",
                    r"\centering",
                    rf"\includegraphics[width=0.98\linewidth]{{{relative}}}",
                    rf"\caption{{{caption}}}",
                    rf"\label{{{label}}}",
                    rf"\end{{{environment}}}",
                ]
            )
        )
        labels.append(label)
    return "\n\n".join(blocks).rstrip() + ("\n" if blocks else ""), labels


def _semantic_result_table_sources(project_path: Path, source: str) -> list[str]:
    """Return declared publication-table fragments for cross-reference checks.

    Section candidates refer to result tables through the stable semantic
    namespace ``tables/<name>``.  The physical table fragments live under
    ``results/tables`` and are resolved only when assembling the manuscript.
    Include their labels in the validation source so valid table references
    are not mistaken for missing manuscript artifacts.
    """
    table_dir = project_path / "results" / "tables"
    fragments: list[str] = []
    for raw_name in dict.fromkeys(re.findall(r"\\input\{tables/([^{}\n]+)\}", source)):
        name = Path(raw_name).name
        table_path = table_dir / name
        if table_path.suffix.lower() != ".tex":
            table_path = table_path.with_suffix(".tex")
        if table_path.is_file():
            fragments.append(table_path.read_text(encoding="utf-8-sig"))
    return fragments


def _validate_result_cross_references(project_path: Path, sections: dict[str, str], artifact_tex: str) -> None:
    source = "\n".join([*sections.values(), artifact_tex])
    source = "\n".join([source, *_semantic_result_table_sources(project_path, source)])
    references = set(re.findall(r"\\ref\{([^{}]+)\}", source))
    labels = set(re.findall(r"\\label\{([^{}]+)\}", source))
    unresolved = sorted(reference for reference in references if reference.startswith(("fig:", "tab:")) and reference not in labels)
    if unresolved:
        raise LatexAssemblyError(
            "Result figure/table references have no declared LaTeX artifact: " + ", ".join(unresolved)
        )


def _render_default_main(project_meta: dict[str, Any]) -> str:
    title = _safe_latex_text(project_meta.get("title") or project_meta.get("idea") or "Draft Paper")
    acknowledgments = _draftpaper_acknowledgments()
    return "\n".join([
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{natbib}",
        r"\usepackage{xurl}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\graphicspath{{../}}",
        "",
        f"\\title{{{title}}}",
        r"\author{}",
        r"\date{}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
        r"\input{sections/introduction}",
        r"\input{sections/data}",
        r"\input{sections/methods}",
        r"\input{sections/results}",
        r"\input{sections/result_artifacts}",
        r"\clearpage",
        r"\input{sections/discussion}",
        "",
        acknowledgments,
        "",
        r"\bibliographystyle{plainnat}",
        r"\bibliography{library}",
        "",
        r"\end{document}",
        "",
    ])


def _section_input(project_path: Path, name: str) -> str:
    """Wrap prose-only section artifacts with a manuscript-level heading."""
    relative = dict(SECTION_INPUTS)[name]
    content = (project_path / relative).read_text(encoding="utf-8-sig", errors="replace")
    input_line = rf"\input{{sections/{name}}}"
    if re.match(r"\s*\\section\*?\{", content):
        return input_line
    return rf"\section{{{SECTION_TITLES[name]}}}" + "\n" + input_line


def _results_embeds_figures(project_path: Path) -> bool:
    """Avoid inserting the derived figure inventory when Results already has floats."""
    for relative in ("results/results.tex", "latex/sections/results.tex"):
        path = project_path / relative
        if path.is_file() and "\\begin{figure" in path.read_text(encoding="utf-8-sig", errors="replace"):
            return True
    return False


def _ensure_math_support(tex: str) -> str:
    """Ensure journal-supplied templates can compile generated scientific formulas."""
    package_groups = re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", tex)
    packages = {item.strip() for group in package_groups for item in group.split(",")}
    missing = [package for package in ("amsmath", "amssymb") if package not in packages]
    if not missing:
        return tex
    documentclass = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", tex)
    if not documentclass:
        return tex
    insertion = "\n" + rf"\usepackage{{{','.join(missing)}}}"
    return tex[:documentclass.end()] + insertion + tex[documentclass.end():]


def _render_main(project_path: Path, project_meta: dict[str, Any]) -> str:
    manuscript_metadata = _read_manuscript_metadata(project_path)
    template_path = project_path / "latex" / "template" / "main.tex"
    if not template_path.exists():
        rendered = _render_default_main(project_meta)
        if manuscript_metadata:
            rendered = rendered.replace(_draftpaper_acknowledgments(), "")
            rendered = _apply_manuscript_metadata(rendered, manuscript_metadata, aastex=False)
        return GENERATOR_TEX_COMMENT + rendered
    template = template_path.read_text(encoding="utf-8")
    artifact_input = [] if _results_embeds_figures(project_path) else [r"\input{sections/result_artifacts}"]
    sections = "\n".join([
        _section_input(project_path, "introduction"),
        _section_input(project_path, "data"),
        _section_input(project_path, "methods"),
        _section_input(project_path, "results"),
        *artifact_input,
        r"\clearpage",
        _section_input(project_path, "discussion"),
    ])
    journal_profile = _read_journal_profile(project_path)
    journal_intent = _read_mapping(project_path / "journal_profile" / "journal_intent.json")
    bibliography_style = journal_profile.get("bibliography_style") or "plainnat"
    bibliography = "\n".join([rf"\bibliographystyle{{{bibliography_style}}}", r"\bibliography{library}"])
    title = _safe_latex_text(project_meta.get("title") or project_meta.get("idea") or "Draft Paper")
    rendered = template.replace("%%DRAFTPAPER_TITLE%%", title)
    rendered = rendered.replace("%%DRAFTPAPER_SECTIONS%%", sections)
    rendered = rendered.replace("%%DRAFTPAPER_BIBLIOGRAPHY%%", bibliography)
    rendered = re.sub(r"\\author\{\s*Draft Author\s*\}", r"\\author{}", rendered, flags=re.I)
    rendered = re.sub(r"\\affiliation\{\s*Draft affiliation\s*\}\s*", "", rendered, flags=re.I)
    rendered = re.sub(r"\\email\{\s*author@example\.com\s*\}\s*", "", rendered, flags=re.I)
    rendered = re.sub(r"placeholder abstract", "", rendered, flags=re.I)
    rendered = re.sub(r"\\bibliography\{library\}\s*\{\s*\}", r"\\bibliography{library}", rendered)
    if "%%DRAFTPAPER_SECTIONS%%" not in template and "\\input{sections/" not in rendered:
        rendered = rendered.rstrip() + "\n\n" + sections + "\n"
    if "%%DRAFTPAPER_BIBLIOGRAPHY%%" not in template and "\\bibliography{" not in rendered:
        rendered = rendered.rstrip() + "\n\n" + bibliography + "\n"
    rendered = _enforce_bibliography_style(rendered, bibliography_style)
    rendered = _ensure_math_support(rendered)
    if "\\graphicspath" not in rendered:
        rendered = rendered.replace("\\begin{document}", "\\graphicspath{{../}}\n\\begin{document}", 1)
    aastex = "aastex" in str(journal_profile.get("documentclass") or "").lower() or bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{aastex", rendered, flags=re.I))
    if manuscript_metadata:
        rendered = _apply_manuscript_metadata(rendered, manuscript_metadata, aastex=aastex)
    else:
        acknowledgments = _draftpaper_acknowledgments(aastex=aastex)
        rendered = _insert_acknowledgments(rendered, acknowledgments)
    rendered = _ensure_aastex_author_block(rendered)
    if journal_intent.get("selection_status") != "confirmed":
        rendered = re.sub(r"(?m)^\s*\\submitjournal\{[^{}]*\}\s*$", "% Target journal is provisional or unset.", rendered)
    if "Generated with Draftpaper-loop" not in rendered:
        rendered = GENERATOR_TEX_COMMENT + rendered
    return rendered.rstrip() + "\n"


def _enforce_bibliography_style(tex: str, style: str) -> str:
    """Make the journal profile the sole bibliography-style source."""
    without_styles = re.sub(r"(?m)^\s*\\bibliographystyle\{[^}]+\}\s*\n?", "", tex)
    bibliography_match = re.search(r"(?m)^\s*\\bibliography\{[^}]+\}", without_styles)
    style_line = rf"\bibliographystyle{{{style}}}"
    if bibliography_match:
        return without_styles[: bibliography_match.start()] + style_line + "\n" + without_styles[bibliography_match.start():]
    end_document = without_styles.rfind(r"\end{document}")
    insertion = style_line + "\n" + r"\bibliography{library}" + "\n"
    if end_document >= 0:
        return without_styles[:end_document] + insertion + without_styles[end_document:]
    return without_styles.rstrip() + "\n" + insertion


def _read_journal_profile(project_path: Path) -> dict[str, Any]:
    path = project_path / "journal_profile" / "journal_profile.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _set_latex_manifest(project_path: Path) -> None:
    manifest_path = project_path / "latex" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = LATEX_INPUTS
    existing_outputs = manifest.get("output_files") or []
    pdf_outputs = [relative for relative in PDF_OUTPUTS if relative in existing_outputs or (project_path / relative).exists()]
    manifest["output_files"] = LATEX_OUTPUTS + [relative for relative in pdf_outputs if relative not in LATEX_OUTPUTS]
    _write_json(manifest_path, manifest)


def _find_latex_executable(names: list[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    candidate_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
        Path("C:/Program Files/MiKTeX/miktex/bin/x64"),
    ]
    for directory in candidate_dirs:
        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)
    return None


def _write_pdf_manifest(project_path: Path, payload: dict[str, Any]) -> None:
    profile = _read_journal_profile(project_path)
    requested_style = str(profile.get("bibliography_style") or "plainnat")
    main_tex = (project_path / "latex" / "main.tex").read_text(encoding="utf-8-sig", errors="replace") if (project_path / "latex" / "main.tex").is_file() else ""
    aux_text = (project_path / "latex" / "main.aux").read_text(encoding="utf-8-sig", errors="replace") if (project_path / "latex" / "main.aux").is_file() else ""
    bbl = project_path / "latex" / "main.bbl"
    payload["bibliography"] = {
        "profile_style": requested_style,
        "main_tex_styles": re.findall(r"\\bibliographystyle\{([^}]+)\}", main_tex),
        "aux_styles": re.findall(r"\\bibstyle\{([^}]+)\}", aux_text),
        "bbl_sha256": hashlib.sha256(bbl.read_bytes()).hexdigest() if bbl.is_file() else None,
        "engine": "BibTeX",
    }
    payload["input_artifact_hashes"] = _pdf_compile_input_hashes(project_path)
    pdf = project_path / "latex" / "main.pdf"
    payload["pdf_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.is_file() else None
    _write_json(project_path / "latex" / "pdf_compile_manifest.json", payload)
    _set_latex_manifest(project_path)


def _aux_requests_bibtex(aux_path: Path) -> bool:
    """Return True when the LaTeX aux file explicitly requests a BibTeX pass."""
    if not aux_path.exists():
        return False
    content = aux_path.read_text(encoding="utf-8", errors="ignore")
    return "\\bibdata" in content and "\\bibstyle" in content


def _bibstyle_from_tex(tex_file: Path) -> str | None:
    content = tex_file.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"\\bibliographystyle\{([^{}]+)\}", content)
    if not match:
        return None
    style = match.group(1).strip()
    return style or None


def _find_bst_file(latex_dir: Path, style: str) -> Path | None:
    local = latex_dir / f"{style}.bst"
    if local.exists():
        return local
    kpsewhich = _find_latex_executable(["kpsewhich", "kpsewhich.exe"])
    if not kpsewhich:
        return None
    try:
        completed = subprocess.run(
            [kpsewhich, f"{style}.bst"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    candidate = Path(completed.stdout.strip())
    return candidate if candidate.exists() else None


def _ensure_local_bibstyle_fallback(latex_dir: Path, tex_file: Path) -> dict[str, Any] | None:
    requested = _bibstyle_from_tex(tex_file)
    if not requested or _find_bst_file(latex_dir, requested):
        return None
    for fallback_style in ["plainnat", "abbrvnat", "unsrtnat"]:
        fallback = _find_bst_file(latex_dir, fallback_style)
        if not fallback:
            continue
        target = latex_dir / f"{requested}.bst"
        shutil.copyfile(fallback, target)
        return {
            "status": "used",
            "requested_style": requested,
            "fallback_style": fallback_style,
            "local_bst": str(target),
            "reason": f"{requested}.bst was not available in the local TeX installation.",
        }
    return {
        "status": "unavailable",
        "requested_style": requested,
        "fallback_style": None,
        "local_bst": None,
        "reason": f"{requested}.bst was not available and no natbib fallback style was found.",
    }


def compile_latex_pdf(project: str | Path, *, timeout_seconds: int = 120) -> dict[str, Any]:
    """Compile latex/main.tex into latex/main.pdf when a local LaTeX engine is available."""
    state = load_project(project)
    from .workspace_policy import WorkspacePolicyError, require_path_budget

    try:
        require_path_budget(state.path)
    except WorkspacePolicyError as exc:
        raise LatexAssemblyError(str(exc)) from exc
    tex_file = state.path / "latex" / "main.tex"
    bib_file = state.path / "latex" / "library.bib"
    log_file = state.path / "latex" / "main.compile.log"
    if not tex_file.exists():
        raise LatexAssemblyError("latex/main.tex is required before compiling a review PDF.")
    if not bib_file.exists():
        raise LatexAssemblyError("latex/library.bib is required before compiling a review PDF.")

    engine = _find_latex_executable(["xelatex", "xelatex.exe", "pdflatex", "pdflatex.exe"])
    if not engine:
        message = "Skipped PDF generation: no local LaTeX engine was found. Install MiKTeX or TeX Live and retry."
        manifest = {
            "status": "skipped",
            "message": message,
            "engine": None,
            "bibtex": None,
            "commands": [],
            "pdf": None,
            "log": str(log_file),
        }
        log_file.write_text(message + "\n", encoding="utf-8")
        _write_pdf_manifest(state.path, manifest)
        return {
            "status": "skipped",
            "project_path": str(state.path),
            "pdf": None,
            "compile_log": str(log_file),
            "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
            "message": message,
        }

    bibtex = _find_latex_executable(["bibtex", "bibtex.exe"])
    latex_command = [engine, "-interaction=nonstopmode", "-halt-on-error", tex_file.name]
    aux_file = tex_file.with_suffix(".aux")
    bst_fallback = _ensure_local_bibstyle_fallback(tex_file.parent, tex_file)

    command_reports: list[dict[str, Any]] = []
    log_chunks: list[str] = []
    commands: list[list[str]] = [latex_command]
    for index, command in enumerate(commands):
        try:
            completed = subprocess.run(
                command,
                cwd=tex_file.parent,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except Exception as exc:
            message = f"PDF generation failed while running {' '.join(command)}: {exc}"
            command_reports.append({"command": command, "returncode": None, "error": str(exc)})
            log_chunks.append(message)
            log_file.write_text("\n\n".join(log_chunks), encoding="utf-8")
            manifest = {
                "status": "failed",
                "message": message,
                "engine": str(engine),
                "bibtex": str(bibtex) if bibtex else None,
                "commands": command_reports,
                "bst_fallback": bst_fallback,
                "pdf": None,
                "log": str(log_file),
            }
            _write_pdf_manifest(state.path, manifest)
            return {
                "status": "failed",
                "project_path": str(state.path),
                "pdf": None,
                "compile_log": str(log_file),
                "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
                "message": message,
            }

        command_reports.append({"command": command, "returncode": completed.returncode})
        log_chunks.append(
            f"$ {' '.join(command)}\n"
            f"exit={completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )
        if completed.returncode != 0:
            message = f"PDF generation failed while running {' '.join(command)}. See {log_file.name}."
            log_file.write_text("\n\n".join(log_chunks), encoding="utf-8")
            manifest = {
                "status": "failed",
                "message": message,
                "engine": str(engine),
                "bibtex": str(bibtex) if bibtex else None,
                "commands": command_reports,
                "bst_fallback": bst_fallback,
                "pdf": None,
                "log": str(log_file),
            }
            _write_pdf_manifest(state.path, manifest)
            return {
                "status": "failed",
                "project_path": str(state.path),
                "pdf": None,
                "compile_log": str(log_file),
                "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
                "message": message,
            }

        if index == 0:
            if bibtex and bib_file.exists() and _aux_requests_bibtex(aux_file):
                commands.append([bibtex, tex_file.stem])
            else:
                reason = (
                    "aux file does not request BibTeX"
                    if bibtex and bib_file.exists()
                    else "BibTeX executable or library.bib is unavailable"
                )
                command_reports.append(
                    {
                        "command": ["bibtex", tex_file.stem],
                        "returncode": None,
                        "status": "skipped",
                        "reason": reason,
                    }
                )
                log_chunks.append(f"$ bibtex {tex_file.stem}\nskipped: {reason}")
            commands.extend([latex_command, latex_command])

    log_file.write_text("\n\n".join(log_chunks), encoding="utf-8")
    pdf_file = tex_file.with_suffix(".pdf")
    status = "success" if pdf_file.exists() else "failed"
    message = (
        f"PDF generated successfully using {Path(engine).name}."
        if pdf_file.exists()
        else f"PDF generation finished but {pdf_file.name} was not created. See {log_file.name}."
    )
    manifest = {
        "status": status,
        "message": message,
        "engine": str(engine),
        "bibtex": str(bibtex) if bibtex else None,
        "commands": command_reports,
        "bst_fallback": bst_fallback,
        "pdf": str(pdf_file) if pdf_file.exists() else None,
        "log": str(log_file),
    }
    _write_pdf_manifest(state.path, manifest)
    return {
        "status": status,
        "project_path": str(state.path),
        "pdf": str(pdf_file) if pdf_file.exists() else None,
        "compile_log": str(log_file),
        "pdf_compile_manifest": str(state.path / "latex" / "pdf_compile_manifest.json"),
        "message": message,
    }


def assemble_latex(project: str | Path, *, compile_pdf: bool = False) -> dict[str, Any]:
    """Assemble staged manuscript sections into latex/main.tex and latex/library.bib."""
    state = load_project(project)
    from .workspace_policy import WorkspacePolicyError, require_path_budget

    try:
        require_path_budget(state.path)
    except WorkspacePolicyError as exc:
        raise LatexAssemblyError(str(exc)) from exc
    try:
        promoted_snapshot = validate_promoted_snapshot_for_writing(state.path)
    except EvidenceSnapshotMismatch as exc:
        raise LatexAssemblyError(str(exc)) from exc
    try:
        validate_journal_profile_for_writing(state.path)
    except JournalProfileError as exc:
        raise LatexAssemblyError(str(exc)) from exc
    _require_inputs(state.path)
    _require_non_stale_input_stages(state.metadata)
    sections = _read_sections(state.path)
    snapshot_id = str(promoted_snapshot.get("snapshot_id") or "legacy_unpromoted")
    if promoted_snapshot:
        mismatches = []
        for section_name, _relative in SECTION_INPUTS:
            report_path = state.path / "writing" / "section_validation" / f"{section_name}.json"
            if not report_path.exists():
                mismatches.append(f"{section_name}:missing_validation")
                continue
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            if report.get("decision") != "pass" or report.get("evidence_snapshot_id") != snapshot_id:
                mismatches.append(f"{section_name}:snapshot_mismatch")
        if mismatches:
            raise LatexAssemblyError(
                "Manuscript sections are not validated against the promoted evidence snapshot: " + ", ".join(mismatches)
            )
    citation_keys, bib_keys = _validate_citations(state.path, sections)
    latex_dir = state.path / "latex"
    latex_dir.mkdir(parents=True, exist_ok=True)
    _copy_sections(state.path, sections)
    _copy_bibtex(state.path)
    result_artifacts, result_labels = _render_result_artifacts(state.path)
    _validate_result_cross_references(state.path, sections, result_artifacts)
    (state.path / "latex" / "sections" / "result_artifacts.tex").write_text(result_artifacts, encoding="utf-8")
    main_tex = latex_dir / "main.tex"
    main_tex.write_text(_render_main(state.path, state.metadata), encoding="utf-8")

    update_stage_status(state.path, "latex", "draft")
    _set_latex_manifest(state.path)
    result = {
        "status": "written",
        "project_path": str(state.path),
        "main_tex": str(main_tex),
        "library_bib": str(latex_dir / "library.bib"),
        "section_count": len(sections),
        "result_figure_count": len(result_labels),
        "citation_count": len(citation_keys),
        "bibtex_entry_count": len(bib_keys),
        "evidence_snapshot_id": snapshot_id,
        "outputs": LATEX_OUTPUTS,
    }
    if compile_pdf:
        pdf_result = compile_latex_pdf(state.path)
        result["pdf_status"] = pdf_result["status"]
        result["pdf"] = pdf_result["pdf"]
        result["compile_log"] = pdf_result["compile_log"]
        result["pdf_compile_manifest"] = pdf_result["pdf_compile_manifest"]
        result["pdf_message"] = pdf_result["message"]
    return result
