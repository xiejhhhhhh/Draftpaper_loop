"""Optional HTTP client for the official MinerU Agent lightweight endpoint.

The client is intentionally dependency-free. It is a connector, not a local
MinerU deployment and never decides whether a document may be uploaded.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


DEFAULT_ENDPOINT = "https://mineru.net/api/v1/agent/parse/file"


def installation_device_id(config_path: str | Path) -> str:
    path = Path(config_path)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("device_id"):
                return str(payload["device_id"])
        except (OSError, json.JSONDecodeError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    device_id = secrets.token_urlsafe(24)
    path.write_text(json.dumps({"schema_version": "dpl.remote_device.v1", "device_id": device_id}, indent=2) + "\n", encoding="utf-8")
    return device_id


def _multipart(path: Path, *, device_id: str) -> tuple[bytes, str]:
    boundary = "----DraftpaperMineru" + secrets.token_hex(12)
    content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"device_id\"\r\n\r\n{device_id}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def parse_with_official_agent(
    path: str | Path,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    device_id: str = "",
    timeout_seconds: int = 120,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    source = Path(path)
    body, content_type = _multipart(source, device_id=device_id)
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json", "User-Agent": "Draftpaper-loop mineru-agent connector"},
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("MinerU Agent returned a non-object response.")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    markdown = data.get("markdown") or data.get("content") or data.get("text")
    return {
        "status": "parsed" if markdown else "submitted",
        "route": "official-agent",
        "endpoint": urllib.parse.urlsplit(endpoint)._replace(path="", query="", fragment="").geturl(),
        "markdown": str(markdown or ""),
        "task_id": data.get("task_id") or data.get("id"),
        "result_url": data.get("result_url") or data.get("url"),
        "raw_status": payload.get("code") or payload.get("status"),
    }
