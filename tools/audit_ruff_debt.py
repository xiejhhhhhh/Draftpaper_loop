"""Audit Ruff findings and enforce a reproducible no-new-debt baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "dpl.ruff_debt_audit.v1"
DEFAULT_TARGETS = ("draftpaper_cli", "tests", "tools")
DEFAULT_HISTORICAL_COUNT = 418


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise_path(value: str) -> str:
    return str(value).replace("\\", "/")


def _finding_key(finding: dict[str, Any]) -> str:
    location = finding.get("location") or {}
    filename = _normalise_path(str(finding.get("filename") or ""))
    row = location.get("row")
    column = location.get("column")
    code = str(finding.get("code") or "")
    message = " ".join(str(finding.get("message") or "").split())
    return f"{filename}|{code}|{row}|{column}|{message}"


def run_ruff(root: str | Path, targets: tuple[str, ...] = DEFAULT_TARGETS) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    command = [sys.executable, "-m", "ruff", "check", *targets, "--output-format", "json"]
    completed = subprocess.run(command, cwd=root_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    findings: list[dict[str, Any]] = []
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
            if isinstance(payload, list):
                findings = [item for item in payload if isinstance(item, dict)]
        except json.JSONDecodeError:
            return {
                "status": "error",
                "reason": "ruff_output_not_json",
                "returncode": completed.returncode,
                "stderr": completed.stderr.strip(),
                "raw_output": completed.stdout[-4000:],
                "findings": [],
            }
    if completed.returncode not in {0, 1}:
        return {
            "status": "error",
            "reason": "ruff_failed_to_run",
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip(),
            "findings": findings,
        }
    return {
        "status": "passed" if not findings else "findings",
        "returncode": completed.returncode,
        "command": command,
        "targets": list(targets),
        "findings": findings,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_report(
    root: str | Path,
    *,
    baseline_path: str | Path,
    historical_count: int = DEFAULT_HISTORICAL_COUNT,
    targets: tuple[str, ...] = DEFAULT_TARGETS,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    baseline_file = Path(baseline_path).expanduser().resolve()
    baseline = _read_json(baseline_file)
    ruff = run_ruff(root_path, targets)
    current = [item for item in ruff.get("findings") or [] if isinstance(item, dict)]
    current_keys = {_finding_key(item) for item in current}
    allowed_keys = {str(item) for item in baseline.get("allowed_finding_keys") or []}
    new_findings = sorted(current_keys - allowed_keys)
    fixed_count = max(0, int(baseline.get("historical_count") or historical_count) - len(current))
    status = "error" if ruff.get("status") == "error" else ("failed" if new_findings else "passed")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "root": str(root_path),
        "baseline_path": str(baseline_file),
        "baseline_historical_count": int(baseline.get("historical_count") or historical_count),
        "baseline_current_count": int(baseline.get("baseline_current_count") or 0),
        "current_count": len(current),
        "fixed_count_since_baseline": fixed_count,
        "legacy_debt_count": len(current),
        "status": status,
        "no_new_debt": not new_findings and status != "error",
        "new_finding_keys": new_findings,
        "current_findings": current,
        "owners": baseline.get("owners") or {"default": "Draftpaper maintainers"},
        "ruff": ruff,
    }


def write_baseline(
    root: str | Path,
    *,
    baseline_path: str | Path,
    markdown_path: str | Path,
    historical_count: int = DEFAULT_HISTORICAL_COUNT,
    targets: tuple[str, ...] = DEFAULT_TARGETS,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    baseline_file = Path(baseline_path).expanduser().resolve()
    previous = _read_json(baseline_file)
    ruff = run_ruff(root_path, targets)
    findings = [item for item in ruff.get("findings") or [] if isinstance(item, dict)]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "baseline_version": "v0.35.0",
        "created_at": previous.get("created_at") or _now(),
        "updated_at": _now(),
        "historical_count": int(previous.get("historical_count") or historical_count),
        "baseline_current_count": len(findings),
        "baseline_current_findings": findings,
        "allowed_finding_keys": sorted(_finding_key(item) for item in findings),
        "owners": previous.get("owners") or {"default": "Draftpaper maintainers"},
        "status": "active" if findings else "retired_zero_debt",
        "targets": list(targets),
        "policy": "new findings fail CI; historical findings remain accountable and are never used to hide new debt",
    }
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    baseline_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = build_report(root_path, baseline_path=baseline_file, historical_count=historical_count, targets=targets)
    markdown_file = Path(markdown_path).expanduser().resolve()
    markdown_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Ruff 技术债基线",
        "",
        f"- 基线版本：`{payload['baseline_version']}`",
        f"- 历史记录数：`{payload['historical_count']}`",
        f"- 当前基线告警数：`{payload['baseline_current_count']}`",
        f"- 当前状态：`{payload['status']}`",
        "- 质量门：新增或修改代码引入的 Ruff 告警必须失败；历史债务不得成为忽略新债务的理由。",
        "",
        "## 当前审计",
        "",
        f"- 当前告警：`{report['current_count']}`",
        f"- 新增告警：`{len(report['new_finding_keys'])}`",
        f"- no-new-debt：`{report['no_new_debt']}`",
        "",
        "## 负责人",
        "",
        *[f"- `{key}`：{value}" for key, value in sorted(payload["owners"].items())],
        "",
        "## 规则",
        "",
        "- `F601` 重复字典键属于语义错误，始终是 fatal gate。",
        "- baseline 只记录明确存在且已登记的历史发现。",
        "- 发现清零后保留历史清理记录，但切换为全量零告警检查。",
    ]
    markdown_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {**report, "baseline": str(baseline_file), "markdown": str(markdown_file)}


def audit_ruff_debt(
    root: str | Path,
    *,
    baseline_path: str | Path,
    markdown_path: str | Path | None = None,
    check: bool = False,
    historical_count: int = DEFAULT_HISTORICAL_COUNT,
    targets: tuple[str, ...] = DEFAULT_TARGETS,
) -> dict[str, Any]:
    baseline_file = Path(baseline_path).expanduser().resolve()
    markdown_file = Path(markdown_path).expanduser().resolve() if markdown_path else baseline_file.with_suffix(".md")
    if not baseline_file.is_file() or not check:
        return write_baseline(
            root,
            baseline_path=baseline_file,
            markdown_path=markdown_file,
            historical_count=historical_count,
            targets=targets,
        )
    return build_report(root, baseline_path=baseline_file, historical_count=historical_count, targets=targets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--baseline", default="docs/quality/ruff_baseline_v0.35.0.json")
    parser.add_argument("--markdown", default="docs/quality/ruff_baseline_v0.35.0.md")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--historical-count", type=int, default=DEFAULT_HISTORICAL_COUNT)
    parser.add_argument("targets", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args(argv)
    result = audit_ruff_debt(
        args.root,
        baseline_path=args.baseline,
        markdown_path=args.markdown,
        check=args.check,
        historical_count=args.historical_count,
        targets=tuple(args.targets or DEFAULT_TARGETS),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"passed", "retired_zero_debt"} or (not args.check and result.get("status") != "error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
