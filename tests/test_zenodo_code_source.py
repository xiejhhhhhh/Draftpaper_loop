from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

from draftpaper_cli.code_sources.archive_security import audit_archive_license, inspect_archive
from draftpaper_cli.code_sources.base import normalize_work_id
from draftpaper_cli.code_sources.github import search_github
from draftpaper_cli.code_sources.github import github_record_from_metadata
from draftpaper_cli.code_sources.zenodo import resolve_zenodo_doi, search_zenodo, zenodo_record_from_metadata


FIXTURES = Path("tests/fixtures")


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _fetch(payload: dict, status: int = 200):
    def fetcher(_url: str, _headers: dict[str, str]):
        return status, payload, {"X-Fixture": "zenodo"}

    return fetcher


def test_zenodo_search_fixture_preserves_version_and_related_github() -> None:
    result = search_zenodo(
        "example research code",
        work_id="work:doi:10.1000/example",
        fetcher=_fetch(_fixture("zenodo_records_search.json")),
    )

    assert result["status"] == "success_with_items"
    assert result["record_count"] == 2
    assert result["provider_receipt"]["metadata_only"] is True
    first = result["records"][0]
    assert first["source_type"] == "zenodo"
    assert first["doi"] == "10.5281/zenodo.1234567"
    assert first["version_doi"] == first["doi"]
    assert first["concept_doi"] == "10.5281/zenodo.1234000"
    assert first["repository_url"] == "https://github.com/example/research-code"
    assert first["archive_available"] is True


def test_zenodo_version_doi_resolution_is_exact_and_handles_tombstone() -> None:
    result = resolve_zenodo_doi(
        "https://doi.org/10.5281/zenodo.1234567.",
        work_id="work:x",
        fetcher=_fetch(_fixture("zenodo_record_detail.json")),
    )
    assert result["status"] == "success_with_items"
    assert result["records"][0]["version_doi"] == "10.5281/zenodo.1234567"

    tombstone = zenodo_record_from_metadata(_fixture("zenodo_tombstone_record.json"), work_id="work:x")
    assert tombstone["tombstone"] is True
    assert tombstone["archive_available"] is False
    assert tombstone["latest_stable"] is False
    assert any("tombstoned" in item for item in tombstone["limitations"])


def test_zenodo_restricted_record_remains_metadata_only() -> None:
    record = zenodo_record_from_metadata(_fixture("zenodo_restricted_record.json"), work_id="work:x")
    assert record["restricted"] is True
    assert record["archive_available"] is False
    assert record["download_status"] == "not_requested"
    assert any("restricted" in item for item in record["limitations"])


def test_provider_schema_change_and_timeout_are_receipted() -> None:
    zenodo_schema = search_zenodo("x", work_id="work:x", fetcher=_fetch({"hits": []}))
    assert zenodo_schema["status"] == "provider_schema_changed"
    assert zenodo_schema["provider_receipt"]["status"] == "provider_schema_changed"

    github_schema = search_github("x", work_id="work:x", fetcher=_fetch({"unexpected": []}))
    assert github_schema["status"] == "provider_schema_changed"
    assert github_schema["provider_receipt"]["status"] == "provider_schema_changed"

    def timeout(_url: str, _headers: dict[str, str]):
        return 0, None, {}

    timed_out = search_zenodo("x", work_id="work:x", fetcher=timeout)
    assert timed_out["status"] == "provider_error"
    assert timed_out["provider_receipt"]["status"] == "provider_error"


def test_deleted_github_can_be_replaced_by_explicit_zenodo_archive_evidence() -> None:
    github = search_github("deleted", work_id="work:x", fetcher=_fetch({}, status=404))
    assert github["status"] == "provider_error"
    zenodo = search_zenodo(
        "deleted",
        work_id="work:x",
        fetcher=_fetch(_fixture("zenodo_records_search.json")),
    )
    assert zenodo["status"] == "success_with_items"
    assert all(record["source_type"] == "zenodo" for record in zenodo["records"])
    assert all(record["verification_status"] == "metadata_only" for record in zenodo["records"])


def test_archive_checksum_and_license_conflict_are_hard_failures(tmp_path: Path) -> None:
    archive = tmp_path / "license.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("LICENSE", "Apache License Version 2.0")
        handle.writestr("README.md", "example")

    checksum = inspect_archive(archive, expected_sha256="sha256:" + ("0" * 64))
    assert checksum["status"] == "rejected"
    assert "checksum_mismatch" in checksum["errors"]
    assert "checksum_not_verified" in checksum["errors"]
    license_report = audit_archive_license(archive, "MIT")
    assert license_report["status"] == "conflict"


def test_zip_symlink_is_rejected_before_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, "/etc/passwd")
    report = inspect_archive(archive)
    assert report["status"] == "rejected"
    assert any(item["reason"] == "link_or_device" for item in report["unsafe_members"])


def test_work_identity_does_not_depend_on_citation_key() -> None:
    left = normalize_work_id({"doi": "10.1234/Example"})
    right = normalize_work_id({"doi": "10.1234/example", "citation_key": "renamed"})
    assert left == right


def test_github_and_zenodo_related_identifier_share_one_code_work() -> None:
    work_id = "work:doi:10.1000/example"
    github = github_record_from_metadata(
        {"full_name": "example/research-code", "html_url": "https://github.com/example/research-code", "latest_release": {"tag_name": "v1.2.0"}},
        work_id=work_id,
    )
    zenodo = zenodo_record_from_metadata(_fixture("zenodo_record_detail.json"), work_id=work_id)
    assert github["code_work_id"] == zenodo["code_work_id"]
    assert github["code_work_id"] == "codework:github:example/research-code"
