"""Human-readable governance report rendered from the structured report only."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    return html.escape(str(value or ""))


def _eligibility_label(key: str, *, english: bool) -> str:
    labels = {
        "allow_edit": ("\u5141\u8bb8\u7f16\u8f91", "Allow edit"),
        "allow_preview": ("\u5141\u8bb8\u751f\u6210\u9884\u89c8", "Allow preview"),
        "allow_promote": ("\u5141\u8bb8\u664b\u5347", "Allow promotion"),
        "allow_close": ("\u5141\u8bb8\u7ed3\u6848", "Allow close"),
        "allow_release": ("\u5141\u8bb8\u53d1\u5e03", "Allow release"),
    }
    localized = labels.get(key)
    return localized[1 if english else 0] if localized else key


def _eligibility_value(value: Any, *, english: bool) -> str:
    if isinstance(value, bool):
        if english:
            return "Yes" if value else "No"
        return "\u662f" if value else "\u5426"
    if value is None:
        return "Not evaluated" if english else "\u672a\u8bc4\u4f30"
    return _text(value)


def render_governance_html(report: dict[str, Any], *, language: str = "zh-CN") -> str:
    english = language == "en"
    title = "Evidence governance and manuscript drift audit" if english else "证据治理与论文漂移审计"
    raw_checks = report.get("checks")
    checks: list[dict[str, Any]] = [item for item in raw_checks if isinstance(item, dict)] if isinstance(raw_checks, list) else []
    raw_drift = report.get("drift")
    drift: dict[str, Any] = raw_drift if isinstance(raw_drift, dict) else {}
    raw_scope = report.get("scope")
    scope: dict[str, Any] = raw_scope if isinstance(raw_scope, dict) else {}
    raw_eligibility = report.get("action_eligibility")
    eligibility: dict[str, Any] = raw_eligibility if isinstance(raw_eligibility, dict) else {}
    raw_blocking = eligibility.get("blocking_finding_ids")
    blocking: list[Any] = raw_blocking if isinstance(raw_blocking, list) else []
    changed: list[dict[str, Any]] = []
    for key in ("changed_artifacts", "added_artifacts", "missing_artifacts"):
        values = drift.get(key)
        if isinstance(values, list):
            changed.extend(item for item in values if isinstance(item, dict))
    raw_baseline = report.get("baseline")
    baseline: dict[str, Any] = raw_baseline if isinstance(raw_baseline, dict) else {}
    if english:
        sentence = (
            f"This read-only audit compared the current workspace with the fixed scientific baseline, "
            f"found {len(changed)} observed artifact changes, checked {scope.get('checked_count', 0)} of "
            f"{scope.get('expected_count', 0)} expected objects, and identified {len(blocking)} blocking findings. "
            "Editing and preview remain available; this page does not certify an unreconciled draft for release."
        )
        labels = {"purpose": "Purpose", "project": "Project", "baseline": "Baseline", "scope": "Coverage", "changed": "Observed changes", "blocks": "Blocking findings", "actions": "Action eligibility", "path": "Path", "kind": "Kind", "rule": "Rule", "outcome": "Outcome", "summary": "Summary"}
        no_changes = "No observed changes"
    else:
        sentence = (
            f"本次只读审计将当前工作区与固定科学基线进行比较，发现 {len(changed)} 项产物变化，"
            f"预期 {scope.get('expected_count', 0)} 项对象中已核验 {scope.get('checked_count', 0)} 项，"
            f"并识别出 {len(blocking)} 个阻断发现。当前仍允许继续编辑和生成预览，但本页不会把未对账草稿认证为可发布版本。"
        )
        labels = {"purpose": "审计用途", "project": "项目", "baseline": "基线", "scope": "覆盖范围", "changed": "发现的变化", "blocks": "阻断发现", "actions": "动作资格", "path": "路径", "kind": "变化类型", "rule": "规则", "outcome": "结果", "summary": "说明"}
        no_changes = "未发现变化"
    change_rows = "".join(
        f"<tr><td class='path'>{_text(item.get('path'))}</td><td>{_text(item.get('drift_kind') or 'unknown')}</td><td>{_text(item.get('current_sha256') or item.get('previous_sha256'))}</td></tr>"
        for item in changed
    ) or f"<tr><td colspan='3'>{no_changes}</td></tr>"
    check_rows = "".join(
        f"<tr><td>{_text(item.get('rule_id'))}</td><td><span class='status {_text(item.get('outcome'))}'>{_text(item.get('outcome'))}</span></td><td>{_text(item.get('summary_en') if english else item.get('summary_zh'))}</td></tr>"
        for item in checks
    )
    action_rows = "".join(
        f"<li><b>{_text(_eligibility_label(key, english=english))}</b>: {_eligibility_value(value, english=english)}</li>"
        for key, value in eligibility.items()
        if key != "blocking_finding_ids"
    )
    return f"""<!doctype html>
<html lang='{'en' if english else 'zh-CN'}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title><style>
body{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;max-width:1180px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#202124}}
.notice{{border-left:4px solid #b45309;background:#fff7ed;padding:1rem;margin:1rem 0}} .facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.6rem}}
.fact{{border:1px solid #d1d5db;padding:.7rem;border-radius:6px}} table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #cbd5e1;padding:.5rem;text-align:left;vertical-align:top}} th{{background:#f8fafc}}
.path{{font-family:ui-monospace,monospace;word-break:break-all}} .status{{font-weight:700}} .passed{{color:#166534}} .failed,.error{{color:#b91c1c}} .not_evaluated{{color:#92400e}}
</style></head><body><h1>{title}</h1><div class='notice'>{sentence}</div>
<div class='facts'><div class='fact'><b>{labels['purpose']}</b><br>{_text(report.get('purpose'))}</div><div class='fact'><b>{labels['project']}</b><br><span class='path'>{_text(report.get('project_path'))}</span></div><div class='fact'><b>{labels['baseline']}</b><br>{_text(baseline.get('status'))}</div><div class='fact'><b>{labels['scope']}</b><br>{scope.get('checked_count', 0)} / {scope.get('expected_count', 0)}</div><div class='fact'><b>{labels['blocks']}</b><br>{len(blocking)}</div></div>
<h2>{labels['actions']}</h2><ul>{action_rows}</ul>
<h2>{labels['changed']}</h2><table><thead><tr><th>{labels['path']}</th><th>{labels['kind']}</th><th>SHA-256</th></tr></thead><tbody>{change_rows}</tbody></table>
<h2>Governance checks</h2><table><thead><tr><th>{labels['rule']}</th><th>{labels['outcome']}</th><th>{labels['summary']}</th></tr></thead><tbody>{check_rows}</tbody></table>
<p class='path'>report_sha256: {_text(report.get('report_sha256'))}</p></body></html>"""


def write_governance_html(report: dict[str, Any], path: str | Path, *, language: str = "zh-CN") -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_governance_html(report, language=language), encoding="utf-8")
    return str(target)


__all__ = ["render_governance_html", "write_governance_html"]
