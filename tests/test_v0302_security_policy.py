from __future__ import annotations

import json
import os
import sys
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from draftpaper_cli.execution_policy import sanitized_environment
from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.cli import main
from draftpaper_cli.doctor import doctor_project
from draftpaper_cli.journal_profile import JournalProfileError, _fetch_text
from draftpaper_cli.literature_search import search_free_literature_with_outcome, search_literature_for_project
from draftpaper_cli.methods import MethodsGateError, _resolve_verification_inputs, _validate_verify_argv
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.orchestrator import status_project
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.safe_fetch import SafeFetchError, _RejectRedirects, fetch_text
from draftpaper_cli.write_set_guard import WriteSetGuard


class _FakeResponse:
    def __init__(self, *, body: bytes, content_type: str, content_length: str | None = None) -> None:
        self._body = body
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": content_length if content_length is not None else str(len(body)),
        }

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return "https://www.overleaf.com/template"

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]


class _FakeOpener:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    def open(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        return self.response


def test_safe_fetch_rejects_redirects() -> None:
    handler = _RejectRedirects()

    with pytest.raises(SafeFetchError, match="redirect"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://www.overleaf.com/final")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_FakeResponse(body=b"binary", content_type="application/octet-stream"), "content type"),
        (_FakeResponse(body=b"0123456789", content_type="text/plain", content_length="10"), "size limit"),
    ],
)
def test_safe_fetch_rejects_disallowed_content_and_oversize(response: _FakeResponse, message: str) -> None:
    with patch("draftpaper_cli.safe_fetch._validate_host"), patch(
        "draftpaper_cli.safe_fetch.urllib.request.build_opener",
        return_value=_FakeOpener(response),
    ):
        with pytest.raises(SafeFetchError, match=message):
            fetch_text("https://www.overleaf.com/template", user_agent="test", max_bytes=8)


def test_journal_policy_rejects_http_even_when_host_is_known() -> None:
    with pytest.raises(JournalProfileError):
        _fetch_text("http://www.overleaf.com/latex/templates")


def test_sanitized_environment_keeps_scientific_keys_but_not_arbitrary_secrets() -> None:
    source = {
        "PATH": "path",
        "SEMANTIC_SCHOLAR_API_KEY": "scholar",
        "ZOTERO_LIBRARY_ID": "library",
        "ZOTERO_API_KEY": "zotero",
        "SERPAPI_API_KEY": "serp",
        "DRAFTPAPER_REMOTE_HOST": "host",
        "DRAFTPAPER_REMOTE_USER": "user",
        "RANDOM_SECRET": "do-not-pass",
    }

    result = sanitized_environment(source)

    assert result["SEMANTIC_SCHOLAR_API_KEY"] == "scholar"
    assert result["ZOTERO_LIBRARY_ID"] == "library"
    assert result["ZOTERO_API_KEY"] == "zotero"
    assert result["SERPAPI_API_KEY"] == "serp"
    assert result["DRAFTPAPER_REMOTE_HOST"] == "host"
    assert result["DRAFTPAPER_REMOTE_USER"] == "user"
    assert "RANDOM_SECRET" not in result


def test_method_verify_argv_rejects_external_executable_and_inline_code(tmp_path: Path) -> None:
    with pytest.raises(MethodsGateError, match="executable"):
        _validate_verify_argv(tmp_path, ["curl", "https://example.com"], allow_inline_runner=False)
    with pytest.raises(MethodsGateError, match="[Ii]nline"):
        _validate_verify_argv(tmp_path, [os.fspath(Path(os.sys.executable)), "-c", "print(1)"], allow_inline_runner=False)


def test_method_verify_argv_accepts_project_runner(tmp_path: Path) -> None:
    runner = tmp_path / "methods" / "scripts" / "run_analysis.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("print('ok')", encoding="utf-8")

    argv, execution_mode = _validate_verify_argv(
        tmp_path,
        [os.fspath(Path(os.sys.executable)), "methods/scripts/run_analysis.py"],
        allow_inline_runner=False,
    )

    assert argv[1].replace("\\", "/") == "methods/scripts/run_analysis.py"
    assert execution_mode == "project_local_python_runner"


def test_external_executable_requires_explicit_system_binary_opt_in(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-runner.exe"
    outside.write_bytes(b"fixture")
    outside.chmod(0o755)

    with pytest.raises(MethodsGateError, match="inside the project|system binary"):
        _validate_verify_argv(
            tmp_path,
            [str(outside)],
            allow_inline_runner=False,
            allow_system_binary=False,
        )

    argv, execution_mode = _validate_verify_argv(
        tmp_path,
        [str(outside)],
        allow_inline_runner=False,
        allow_system_binary=True,
    )

    assert Path(argv[0]).resolve() == outside.resolve()
    assert execution_mode == "explicit_system_binary"


def test_cli_override_is_validated_like_manifest_runner(tmp_path: Path) -> None:
    with pytest.raises(MethodsGateError, match="executable"):
        _resolve_verification_inputs(tmp_path, "curl https://example.com", None, None)
    with pytest.raises(MethodsGateError, match="[Ii]nline"):
        _resolve_verification_inputs(tmp_path, f'"{sys.executable}" -c "print(1)"', None, None)


def test_method_input_and_output_paths_are_confined_before_execution(tmp_path: Path) -> None:
    runner = tmp_path / "methods" / "scripts" / "run_analysis.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("print('ok')", encoding="utf-8")
    command = f'"{sys.executable}" methods/scripts/run_analysis.py'

    with pytest.raises(MethodsGateError, match="[Oo]utput.*escapes|Unsafe path"):
        _resolve_verification_inputs(tmp_path, command, ["../escape.csv"], None)
    with pytest.raises(MethodsGateError, match="[Ii]nput.*escapes|Unsafe path"):
        _resolve_verification_inputs(tmp_path, command, None, ["../secret.csv"])


def test_literature_provider_outcome_distinguishes_empty_error_auth_and_rate_limit() -> None:
    rate_error = urllib.error.HTTPError("https://example.org", 429, "rate", {}, None)
    with patch("draftpaper_cli.literature_search.search_semantic_scholar", side_effect=rate_error), patch(
        "draftpaper_cli.literature_search.search_arxiv",
        return_value=[],
    ), patch("draftpaper_cli.literature_search.search_crossref", side_effect=OSError("offline")), patch.dict(
        os.environ,
        {},
        clear=True,
    ):
        result = search_free_literature_with_outcome("test query", limit=5)

    statuses = {item["provider"]: item["status"] for item in result["providers"]}
    assert statuses["semantic_scholar"] == "rate_limited"
    assert statuses["arxiv"] == "success_empty"
    assert statuses["crossref"] == "provider_error"
    assert statuses["serpapi"] == "auth_required"
    assert result["status"] == "provider_error"
    assert result["items"] == []


def test_local_literature_import_records_offline_fallback_in_stage_manifest(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Local evidence import", field="workflow engineering")
    source = tmp_path / "references.json"
    source.write_text("[]", encoding="utf-8")

    result = search_literature_for_project(project.path, from_json=source)

    report = json.loads((project.path / "references" / "literature_provider_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((project.path / "references" / "stage_manifest.json").read_text(encoding="utf-8"))
    assert result["provider_status"] == "offline_fallback"
    assert report["status"] == "offline_fallback"
    assert manifest["provider_status"] == "offline_fallback"
    assert "references/literature_provider_report.json" in manifest["output_files"]


def test_status_and_doctor_surface_literature_provider_errors(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Provider diagnostics", field="workflow engineering")
    report_path = project.path / "references" / "literature_provider_report.json"
    report_path.write_text(
        json.dumps({"schema_version": "dpl.literature_provider_report.v1", "status": "rate_limited", "queries": []}),
        encoding="utf-8",
    )
    refresh_project_passport(project.path, event="test_provider_report")

    status = status_project(project.path)
    doctor = doctor_project(project.path)

    assert status["literature_provider_status"] == "rate_limited"
    finding = next(item for item in doctor["findings"] if item["category"] == "literature_provider")
    assert finding["severity"] == "warning"
    assert "rate" in finding["cause"].lower()


def test_write_set_preflight_rejects_unsafe_declared_prefix(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Unsafe write policy", field="workflow engineering")
    spec = replace(COMMAND_SPECS["inventory-data"], allowed_write_globs=("../outside/**",))

    report = WriteSetGuard(project.path, spec).preflight()

    assert report["status"] == "boundary_violation"
    assert report["violations"]


def test_cli_stops_before_handler_when_write_set_preflight_fails(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Preflight before handler", field="workflow engineering")
    blocked = {
        "schema_version": "dpl.write_set_preflight.v1",
        "status": "boundary_violation",
        "violations": ["unsafe prefix"],
    }

    with patch.object(WriteSetGuard, "preflight", return_value=blocked):
        exit_code = main(["inventory-data", "--project", str(project.path), "--json-full"])

    assert exit_code == 4
    assert not (project.path / "data" / "inventory.json").exists()
