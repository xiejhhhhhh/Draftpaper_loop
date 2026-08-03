from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from draftpaper_cli.code_sources.archive_security import inspect_archive, safe_download_archive
from draftpaper_cli.code_sources.base import code_work_id, normalize_work_id
from draftpaper_cli.code_sources.github import github_record_from_metadata, search_github
from draftpaper_cli.code_sources.zenodo import search_zenodo, zenodo_record_from_metadata


def test_github_and_zenodo_records_preserve_work_identity_and_metadata_only() -> None:
    work = normalize_work_id({"doi": "10.1234/ABC"})
    github = github_record_from_metadata(
        {
            "full_name": "org/project",
            "html_url": "https://github.com/org/project",
            "stargazers_count": 100,
            "forks_count": 12,
            "license": {"spdx_id": "MIT"},
            "latest_release": {"tag_name": "v1.0.0", "published_at": "2025-01-01"},
        },
        work_id=work,
    )
    zenodo = zenodo_record_from_metadata(
        {
            "id": 123,
            "doi": "10.5281/zenodo.123",
            "conceptdoi": "10.5281/zenodo.100",
            "version": "1.0.0",
            "metadata": {"title": "Project", "license": "MIT", "version": "1.0.0"},
            "links": {"html": "https://zenodo.org/records/123"},
            "files": [{"key": "project.zip", "checksum": "sha256:abc", "size": 10}],
        },
        work_id=work,
    )
    assert github["work_id"] == zenodo["work_id"] == work
    assert github["quality_signals"]["github_stars"] == 100
    assert zenodo["concept_doi"] == "10.5281/zenodo.100"
    assert zenodo["verification_status"] == "metadata_only"
    assert code_work_id({"repository_url": "https://github.com/org/project"}) == github["code_work_id"]


def test_provider_receipts_classify_empty_and_rate_limit() -> None:
    def fetcher(url: str, headers: dict[str, str]):
        del url, headers
        return 429, None, {"Retry-After": "3"}

    github = search_github("project", work_id="work:x", fetcher=fetcher)
    zenodo = search_zenodo("project", work_id="work:x", fetcher=fetcher)
    assert github["status"] == zenodo["status"] == "rate_limited"
    assert github["retry_after"] == "3"


def test_archive_inspection_rejects_traversal_and_requires_confirmation(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "bad")
        handle.writestr("LICENSE", "MIT")
    report = inspect_archive(archive)
    assert report["status"] == "rejected"
    assert "unsafe_members_present" in report["errors"]
    blocked = safe_download_archive("https://zenodo.org/records/1/files/a.zip", tmp_path / "a.zip")
    assert blocked["reason"] == "explicit_confirmation_required"


def test_archive_inspection_accepts_small_safe_zip(tmp_path: Path) -> None:
    archive = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("README.md", "readme")
        handle.writestr("LICENSE", "MIT")
    report = inspect_archive(archive)
    assert report["status"] == "passed"
    assert report["license_files"] == ["LICENSE"]


def test_archive_inspection_rejects_tar_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as handle:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        handle.addfile(info)
    report = inspect_archive(archive)
    assert report["status"] == "rejected"
    assert "unsafe_members_present" in report["errors"]
