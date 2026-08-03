"""Static inspection and guarded download for third-party code archives."""

from __future__ import annotations

import hashlib
import os
import posixpath
import stat
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "dpl.code_archive_inspection.v1"
DEFAULT_HOSTS = {"zenodo.org", "www.zenodo.org", "files.zenodo.org", "github.com", "objects.githubusercontent.com"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unsafe_member(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("\\"):
        return "absolute_path"
    if len(normalized) >= 2 and normalized[1] == ":":
        return "drive_absolute_path"
    collapsed = posixpath.normpath(normalized)
    if collapsed == ".." or collapsed.startswith("../"):
        return "path_traversal"
    return None


def _license_names(names: list[str]) -> list[str]:
    return [
        name
        for name in names
        if Path(name).name.upper() in {"LICENSE", "LICENSE.TXT", "LICENSE.MD", "COPYING", "COPYING.TXT", "NOTICE"}
    ]


def inspect_archive(
    archive: str | Path,
    *,
    expected_sha256: str | None = None,
    max_files: int = 10000,
    max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 1000.0,
) -> dict[str, Any]:
    """Inspect ZIP/TAR metadata without extracting or executing archive files."""
    path = Path(archive).expanduser().resolve()
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "rejected",
        "archive_path": str(path),
        "inspected_at": _now(),
        "sha256": None,
        "expected_sha256": expected_sha256,
        "checksum_match": None,
        "file_count": 0,
        "uncompressed_bytes": 0,
        "compression_ratio": None,
        "license_files": [],
        "unsafe_members": [],
        "errors": [],
        "extracted": False,
        "executed": False,
    }
    if not path.is_file():
        result["errors"].append("archive_missing")
        return result
    result["sha256"] = _sha256(path)
    if expected_sha256:
        result["checksum_match"] = result["sha256"].lower() == expected_sha256.lower().replace("sha256:", "")
        if not result["checksum_match"]:
            result["errors"].append("checksum_mismatch")
    names: list[str] = []
    total_size = 0
    compressed_size = max(1, path.stat().st_size)
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive_file:
                infos = archive_file.infolist()
                result["file_count"] = len(infos)
                for info in infos:
                    names.append(info.filename)
                    reason = _unsafe_member(info.filename)
                    if reason:
                        result["unsafe_members"].append({"name": info.filename, "reason": reason})
                    mode = (info.external_attr >> 16) & 0o170000
                    if stat.S_ISLNK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode):
                        result["unsafe_members"].append({"name": info.filename, "reason": "link_or_device"})
                    if len(infos) > max_files:
                        result["errors"].append("file_count_limit_exceeded")
                        break
                    total_size += int(info.file_size or 0)
        elif tarfile.is_tarfile(path):
            with tarfile.open(path, mode="r:*") as archive_file:
                members = archive_file.getmembers()
                result["file_count"] = len(members)
                for member in members:
                    names.append(member.name)
                    reason = _unsafe_member(member.name)
                    if reason:
                        result["unsafe_members"].append({"name": member.name, "reason": reason})
                    if member.issym() or member.islnk() or member.isdev():
                        result["unsafe_members"].append({"name": member.name, "reason": "link_or_device"})
                    if len(members) > max_files:
                        result["errors"].append("file_count_limit_exceeded")
                        break
                    total_size += int(member.size or 0)
        else:
            result["errors"].append("unsupported_archive_format")
            return result
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        result["errors"].append(f"archive_read_error:{type(exc).__name__}")
        return result
    result["uncompressed_bytes"] = total_size
    result["compression_ratio"] = round(total_size / compressed_size, 3)
    result["license_files"] = _license_names(names)
    if total_size > max_uncompressed_bytes:
        result["errors"].append("uncompressed_size_limit_exceeded")
    if result["compression_ratio"] > max_compression_ratio:
        result["errors"].append("compression_ratio_limit_exceeded")
    if result["unsafe_members"]:
        result["errors"].append("unsafe_members_present")
    if expected_sha256 and result["checksum_match"] is not True:
        result["errors"].append("checksum_not_verified")
    result["status"] = "passed" if not result["errors"] else "rejected"
    return result


def audit_archive_license(archive: str | Path, metadata_license: str | None = None) -> dict[str, Any]:
    """Compare archive license evidence with provider metadata without extracting code."""
    path = Path(archive).expanduser().resolve()
    names: list[str] = []
    snippets: list[str] = []
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as handle:
                for info in handle.infolist():
                    if Path(info.filename).name.upper() in {"LICENSE", "LICENSE.TXT", "LICENSE.MD", "COPYING", "NOTICE"}:
                        names.append(info.filename)
                        snippets.append(handle.read(info)[:65536].decode("utf-8", errors="replace"))
        elif tarfile.is_tarfile(path):
            with tarfile.open(path, mode="r:*") as handle:
                for member in handle.getmembers():
                    if Path(member.name).name.upper() in {"LICENSE", "LICENSE.TXT", "LICENSE.MD", "COPYING", "NOTICE"} and member.isfile():
                        names.append(member.name)
                        stream = handle.extractfile(member)
                        snippets.append(stream.read(65536).decode("utf-8", errors="replace") if stream else "")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        return {"status": "error", "metadata_license": metadata_license, "license_files": names, "error": type(exc).__name__}
    text = "\n".join(snippets).lower()
    normalized_metadata = str(metadata_license or "").lower().replace("-", "")
    known_tokens = {"mit": "mit", "apache": "apache", "gpl": "gpl", "bsd": "bsd", "lgpl": "lgpl", "agpl": "agpl", "mpl": "mpl"}
    archive_families = [value for key, value in known_tokens.items() if key in text]
    metadata_family = next((value for key, value in known_tokens.items() if key in normalized_metadata), None)
    if not names:
        status = "unknown"
    elif metadata_family and archive_families and metadata_family not in archive_families:
        status = "conflict"
    else:
        status = "consistent" if metadata_family and archive_families else "archive_present_metadata_unknown"
    return {
        "status": status,
        "metadata_license": metadata_license,
        "license_files": names,
        "license_in_archive": bool(names),
        "metadata_and_archive_consistent": status == "consistent",
    }


def _allowed_url(url: str, allowed_hosts: set[str]) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in allowed_hosts


def safe_download_archive(
    url: str,
    destination: str | Path,
    *,
    expected_sha256: str | None = None,
    confirm_download: bool = False,
    allowed_hosts: set[str] | None = None,
    max_bytes: int = 2 * 1024 * 1024 * 1024,
) -> dict[str, Any]:
    """Download only after explicit confirmation and host/size checks."""
    destination_path = Path(destination).expanduser().resolve()
    hosts = allowed_hosts or DEFAULT_HOSTS
    result: dict[str, Any] = {
        "schema_version": "dpl.code_archive_download.v1",
        "status": "blocked",
        "url": url,
        "destination": str(destination_path),
        "downloaded_at": _now(),
        "metadata_only": False,
        "downloaded": False,
    }
    if not confirm_download:
        result["reason"] = "explicit_confirmation_required"
        return result
    if not _allowed_url(url, hosts):
        result["reason"] = "host_or_scheme_not_allowed"
        return result
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_name(destination_path.name + ".part")

    def blocked(reason: str) -> dict[str, Any]:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        result["reason"] = reason
        return result

    request = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
            final_host = urllib.parse.urlsplit(response.geturl()).hostname
            if final_host not in hosts:
                return blocked("redirect_host_not_allowed")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    return blocked("download_size_limit_exceeded")
                handle.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        return blocked(f"download_error:{type(exc).__name__}")
    if not temporary.is_file():
        return blocked("download_missing")
    digest = _sha256(temporary)
    result["sha256"] = digest
    if expected_sha256 and digest.lower() != expected_sha256.lower().replace("sha256:", ""):
        return blocked("checksum_mismatch")
    os.replace(temporary, destination_path)
    result.update({"status": "downloaded", "downloaded": True, "checksum_match": True if expected_sha256 else None})
    return result
