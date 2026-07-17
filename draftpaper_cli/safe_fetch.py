"""Constrained HTTP metadata fetching for local-first workflow adapters."""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request
from typing import Iterable


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DEFAULT_ALLOWED_HOSTS = frozenset({"www.overleaf.com", "raw.githubusercontent.com", "api.github.com"})


class SafeFetchError(RuntimeError):
    """Raised before or during a metadata request that violates the fetch policy."""


def _is_forbidden_address(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return True
    return bool(
        value.is_loopback
        or value.is_private
        or value.is_link_local
        or value.is_unspecified
        or value.is_reserved
        or str(value) == "169.254.169.254"
    )


def _validate_host(host: str, allowed_hosts: Iterable[str]) -> None:
    normalized = host.rstrip(".").lower()
    allowed = {item.rstrip(".").lower() for item in allowed_hosts}
    if normalized not in allowed and not any(normalized.endswith("." + suffix) for suffix in allowed):
        raise SafeFetchError(f"Host is not allowlisted: {host}")
    try:
        addresses = {result[4][0] for result in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise SafeFetchError(f"Host DNS resolution failed: {host}") from exc
    if not addresses or any(_is_forbidden_address(address) for address in addresses):
        raise SafeFetchError(f"Host resolves to a forbidden address: {host}")


def fetch_text(
    url: str,
    *,
    user_agent: str,
    timeout: int = 30,
    allowed_hosts: Iterable[str] = DEFAULT_ALLOWED_HOSTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SafeFetchError("Only HTTPS URLs with a hostname are allowed.")
    _validate_host(parsed.hostname, allowed_hosts)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - URL policy validated above.
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise SafeFetchError("Remote response exceeds the configured size limit.")
            raw = response.read(max_bytes + 1)
    except SafeFetchError:
        raise
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise SafeFetchError(f"Unable to fetch allowlisted metadata host: {parsed.hostname}") from exc
    if len(raw) > max_bytes:
        raise SafeFetchError("Remote response exceeds the configured size limit.")
    return raw.decode("utf-8", errors="replace")
