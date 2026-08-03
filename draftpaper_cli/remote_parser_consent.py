"""Project-scoped, private consent record for remote document parsing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def consent_path(project: str | Path) -> Path:
    path = Path(project) / "references" / "private" / "remote_parser_consent.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_consent(project: str | Path) -> dict[str, Any]:
    path = consent_path(project)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": "dpl.remote_parser_consent.v1", "decision": "ask_once"}
    return payload if isinstance(payload, dict) else {"schema_version": "dpl.remote_parser_consent.v1", "decision": "ask_once"}


def consent_for_route(project: str | Path, *, route: str, requested: str) -> dict[str, Any]:
    """Resolve an explicit CLI decision against the private project record.

    A stored project decision is inherited only by the same service class. This
    prevents consent for the official endpoint from silently authorizing a
    separately configured custom endpoint.
    """
    requested_value = str(requested or "ask_once").strip().lower()
    if requested_value != "ask_once":
        return {"decision": requested_value, "service": route, "document_classes": ["published-public"]}
    stored = load_consent(project)
    service = str(stored.get("service") or "official-agent").strip().lower()
    route_key = str(route or "official-agent").strip().lower()
    if service not in {route_key, "all-remote-parsers"}:
        return {"decision": "ask_once", "service": route_key, "document_classes": ["published-public"], "source": "service_mismatch"}
    classes = stored.get("document_classes")
    allowed = [str(value).strip() for value in classes if str(value).strip()] if isinstance(classes, list) else ["published-public"]
    return {
        "decision": str(stored.get("decision") or "ask_once").strip().lower(),
        "service": service,
        "document_classes": allowed,
        "recorded_at": stored.get("recorded_at"),
        "source": "project_record",
    }


def record_consent(project: str | Path, *, decision: str, service: str, document_classes: list[str] | None = None) -> dict[str, Any]:
    decision = str(decision or "").strip().lower()
    if decision not in {"once", "project", "deny"}:
        raise ValueError("decision must be once, project, or deny")
    service = str(service or "official-agent").strip()
    if not service or any(token in service.lower() for token in ("token=", "api_key", "cookie", "password")):
        raise ValueError("service must be a non-secret service label or endpoint origin")
    if service.startswith(("http://", "https://")):
        parsed = urlsplit(service)
        if not parsed.hostname:
            raise ValueError("service endpoint must include a hostname")
        service = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/') or ''}"
    classes = [str(value).strip() for value in (document_classes or ["published-public"]) if str(value).strip()]
    if not classes:
        classes = ["published-public"]
    payload = {
        "schema_version": "dpl.remote_parser_consent.v1",
        "decision": decision,
        "service": service,
        "document_classes": classes,
        "recorded_at": _now(),
    }
    consent_path(project).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
