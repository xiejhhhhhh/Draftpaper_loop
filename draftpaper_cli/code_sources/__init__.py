"""Provider-neutral metadata records for public research-code sources."""

from .base import (
    CodeSourceRecord,
    code_work_id,
    normalize_code_source,
    normalize_work_id,
)
from .github import github_record_from_metadata, search_github
from .zenodo import resolve_zenodo_doi, search_zenodo, zenodo_record_from_metadata
from .archive_security import inspect_archive, safe_download_archive

__all__ = [
    "CodeSourceRecord",
    "code_work_id",
    "github_record_from_metadata",
    "inspect_archive",
    "normalize_code_source",
    "normalize_work_id",
    "safe_download_archive",
    "search_github",
    "search_zenodo",
    "resolve_zenodo_doi",
    "zenodo_record_from_metadata",
]
