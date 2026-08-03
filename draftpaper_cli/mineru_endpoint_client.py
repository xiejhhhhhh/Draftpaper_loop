"""Generic custom MinerU endpoint contract; deployment remains external."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


def parse_with_custom_endpoint(
    path: str | Path,
    *,
    endpoint: str,
    timeout_seconds: int = 600,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    source = Path(path)
    payload = json.dumps({"filename": source.name, "content_base64": __import__("base64").b64encode(source.read_bytes()).decode("ascii")}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Draftpaper-loop custom MinerU endpoint"}, method="POST")
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(body, dict):
        raise ValueError("Custom MinerU endpoint returned a non-object response.")
    markdown = body.get("markdown") or body.get("content") or body.get("text")
    return {
        "status": "parsed" if markdown else "submitted",
        "route": "custom-endpoint",
        "endpoint": urllib.parse.urlsplit(endpoint)._replace(path="", query="", fragment="").geturl(),
        "markdown": str(markdown or ""),
        "schema_version": body.get("schema_version") or "custom.v1",
    }
