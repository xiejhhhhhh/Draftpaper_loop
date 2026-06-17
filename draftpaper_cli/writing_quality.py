from __future__ import annotations

import re
from dataclasses import dataclass


CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{",
    re.IGNORECASE,
)
FIGURE_PATTERN = re.compile(r"\\begin\{figure\}|\\includegraphics", re.IGNORECASE)
TABLE_PATTERN = re.compile(r"\\begin\{table\}", re.IGNORECASE)
BULLET_PATTERN = re.compile(r"\\begin\{(?:itemize|enumerate|description)\}|\\item\b", re.IGNORECASE)
BOLD_PATTERN = re.compile(r"\\(?:textbf|bfseries)\b", re.IGNORECASE)
FORMULA_PATTERN = re.compile(
    r"\\begin\{equation\}|\\begin\{align\}|\\\(|\\\[|(?<!\\)\$(?!\$)|\\mathrm\{|\\frac\{",
    re.IGNORECASE,
)


SECTION_RULES = {
    "introduction": {"min_words": 180, "min_paragraphs": 4, "requires_citation": True},
    "data": {"min_words": 130, "min_paragraphs": 3},
    "methods": {"min_words": 150, "min_paragraphs": 3, "requires_formula": True},
    "results": {"min_words": 180, "min_paragraphs": 3, "min_figures": 5, "forbid_citation": True},
    "discussion": {"min_words": 180, "min_paragraphs": 4, "requires_citation": True},
}


@dataclass(frozen=True)
class WritingQualityIssue:
    severity: str
    code: str
    message: str


def _strip_latex_noise(tex: str) -> str:
    text = re.sub(r"\\begin\{(?:figure|table)\}.*?\\end\{(?:figure|table)\}", " ", tex, flags=re.S)
    text = re.sub(r"\\(?:section|subsection|subsubsection|caption|label|includegraphics)(?:\[[^\]]*\])?\{[^{}]*\}", " ", text)
    text = re.sub(r"\\cite[a-zA-Z*]*(?:\[[^\]]*\]){0,2}\{[^{}]*\}", " citation ", text)
    text = re.sub(r"\\[A-Za-z]+(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()


def _word_count(tex: str) -> int:
    plain = _strip_latex_noise(tex)
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", plain))


def _paragraph_count(tex: str) -> int:
    cleaned = re.sub(r"\\begin\{(?:figure|table)\}.*?\\end\{(?:figure|table)\}", "\n\n", tex, flags=re.S)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", cleaned) if block.strip()]
    narrative = []
    for block in blocks:
        without_heading = re.sub(r"\\(?:section|subsection|subsubsection)\{[^{}]*\}", " ", block).strip()
        if _word_count(without_heading) >= 18:
            narrative.append(without_heading)
    return len(narrative)


def _section_chunks(tex: str) -> list[str]:
    matches = list(re.finditer(r"\\subsection\{[^{}]+\}", tex))
    if not matches:
        return [tex]
    chunks: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(tex)
        chunks.append(tex[match.start():end])
    return chunks


def evaluate_section_quality(section: str, tex: str, *, figure_count: int | None = None) -> list[WritingQualityIssue]:
    """Evaluate manuscript-facing LaTeX against DraftPaper's prose quality rules."""
    section_key = section.lower().strip()
    rules = SECTION_RULES.get(section_key, {})
    issues: list[WritingQualityIssue] = []
    words = _word_count(tex)
    paragraphs = _paragraph_count(tex)
    min_words = int(rules.get("min_words") or 0)
    min_paragraphs = int(rules.get("min_paragraphs") or 0)

    if min_words and words < min_words:
        issues.append(WritingQualityIssue(
            "error",
            "section_too_short",
            f"{section_key} has {words} prose words; expected at least {min_words}.",
        ))
    if min_paragraphs and paragraphs < min_paragraphs:
        issues.append(WritingQualityIssue(
            "error",
            "section_too_few_paragraphs",
            f"{section_key} has {paragraphs} substantive paragraphs; expected at least {min_paragraphs}.",
        ))
    if BULLET_PATTERN.search(tex):
        issues.append(WritingQualityIssue("error", "section_uses_bullets", f"{section_key} must use natural prose rather than bullet lists."))
    if BOLD_PATTERN.search(tex):
        issues.append(WritingQualityIssue("error", "section_uses_bold", f"{section_key} must not use arbitrary bold emphasis."))

    citation_count = len(CITATION_PATTERN.findall(tex))
    if rules.get("requires_citation") and citation_count == 0:
        issues.append(WritingQualityIssue("error", f"{section_key}_missing_citations", f"{section_key} requires traceable LaTeX citations."))
    if rules.get("forbid_citation") and citation_count:
        issues.append(WritingQualityIssue("error", "results_contains_citation", "Results section must not contain citation commands."))

    if rules.get("requires_formula") and not FORMULA_PATTERN.search(tex):
        issues.append(WritingQualityIssue("error", "methods_missing_formula", "Methods section must include at least one LaTeX mathematical expression."))

    if section_key == "results":
        detected_figures = figure_count if figure_count is not None else len(FIGURE_PATTERN.findall(tex))
        min_figures = int(rules.get("min_figures") or 0)
        if detected_figures < min_figures:
            issues.append(WritingQualityIssue(
                "error",
                "results_too_few_figures",
                f"Results declares {detected_figures} figure(s); expected at least {min_figures} main figures for a manuscript draft.",
            ))
        for chunk in _section_chunks(tex):
            if "\\subsection" not in chunk:
                continue
            has_artifact = FIGURE_PATTERN.search(chunk) or TABLE_PATTERN.search(chunk)
            if not has_artifact:
                issues.append(WritingQualityIssue(
                    "error",
                    "result_subsection_missing_figure",
                    "Each Results subsection must end with the figure or table that supports its interpretation.",
                ))
                continue
            tail = re.sub(r"\s+", " ", chunk[-500:])
            if "\\end{figure}" not in tail and "\\end{table}" not in tail:
                issues.append(WritingQualityIssue(
                    "error",
                    "result_subsection_missing_figure",
                    "Each Results subsection must place its supporting figure or table at the end of the subsection.",
                ))
    return issues
