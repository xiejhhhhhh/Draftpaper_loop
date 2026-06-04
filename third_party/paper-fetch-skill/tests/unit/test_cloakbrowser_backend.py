from __future__ import annotations

from dataclasses import replace
import os
from unittest import mock

from paper_fetch import _cloakbrowser_runtime
from paper_fetch.providers import _cloakbrowser, browser_runtime
from paper_fetch.providers.browser_workflow.html_extraction import (
    _fetch_browser_html_payload,
    fetch_html_with_fast_browser,
)
from paper_fetch.providers.browser_workflow.fetchers.readiness import (
    atypon_body_ready_selectors,
    wait_for_atypon_body_dom_ready,
)
from paper_fetch.runtime import RuntimeContext


class _FakeResponse:
    status = 200

    def all_headers(self) -> dict[str, str]:
        return {"Content-Type": "text/html"}


class _FakeRequest:
    def __init__(self, resource_type: str) -> None:
        self.resource_type = resource_type


class _FakeRoute:
    def __init__(self, resource_type: str) -> None:
        self.request = _FakeRequest(resource_type)
        self.aborted = False
        self.continued = False

    def abort(self) -> None:
        self.aborted = True

    def continue_(self) -> None:
        self.continued = True


class _FakePage:
    def __init__(self) -> None:
        self.url = ""
        self.closed = False
        self.goto_calls: list[str] = []
        self.aborted_media = False
        self.continued_document = False

    def route(self, _pattern: str, handler) -> None:
        image_route = _FakeRoute("image")
        handler(image_route)
        document_route = _FakeRoute("document")
        handler(document_route)
        self.aborted_media = image_route.aborted
        self.continued_document = document_route.continued

    def goto(self, url: str, **_kwargs):
        self.goto_calls.append(url)
        self.url = url
        return _FakeResponse()

    def wait_for_timeout(self, _timeout_ms: int) -> None:
        return None

    def expect_response(self, *_args, **_kwargs):
        class _ResponseInfo:
            value = _FakeResponse()

            def __enter__(self):
                return self

            def __exit__(self, *_exc_info) -> None:
                return None

        return _ResponseInfo()

    def content(self) -> str:
        return (
            "<html><head><title>Example Article</title></head>"
            "<body><main>Readable full text body.</main></body></html>"
        )

    def title(self) -> str:
        return "Example Article"

    def close(self) -> None:
        self.closed = True


class _ReadinessFakePage(_FakePage):
    def __init__(
        self,
        *,
        html: str,
        title: str = "Example Article",
        readiness_payloads: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__()
        self._html = html
        self._title = title
        self.readiness_payloads = list(readiness_payloads or [])
        self.evaluate_calls: list[object] = []
        self.wait_calls: list[int] = []

    def content(self) -> str:
        return self._html

    def title(self) -> str:
        return self._title

    def evaluate(self, script, arg=None):
        self.evaluate_calls.append((script, arg))
        if self.readiness_payloads:
            return self.readiness_payloads.pop(0)
        return {
            "ready": False,
            "selector": None,
            "textLength": 0,
            "paragraphCount": 0,
            "headingCount": 0,
            "fingerprint": "",
        }

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.wait_calls.append(timeout_ms)


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False
        self.storage_state_path: str | None = None

    def new_page(self) -> _FakePage:
        return self.page

    def cookies(self) -> list[dict[str, str]]:
        return [{"name": "cf_clearance", "value": "secret", "domain": ".science.org", "path": "/"}]

    def storage_state(self, *, path: str) -> None:
        self.storage_state_path = path
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}")

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.context = _FakeContext()
        self.new_context_kwargs: dict[str, object] = {}
        self.closed = False

    def new_context(self, **kwargs):
        self.new_context_kwargs = dict(kwargs)
        return self.context

    def close(self) -> None:
        self.closed = True


class _FakeCloakBrowserModule:
    def __init__(self) -> None:
        self.browser = _FakeBrowser()
        self.launch_kwargs: dict[str, object] = {}
        self.launch_binary_path: str | None = None

    def launch(self, **kwargs):
        self.launch_kwargs = dict(kwargs)
        self.launch_binary_path = os.environ.get("CLOAKBROWSER_BINARY_PATH")
        return self.browser


def _runtime_config(tmp_path):
    return _cloakbrowser.CloakBrowserRuntimeConfig(
        provider="science",
        doi="10.1126/science.example",
        artifact_dir=tmp_path / "artifacts",
        headless=True,
        user_agent="paper-fetch-test/1",
        timeout_ms=12345,
    )


def _runtime_config_without_browser_user_agent(tmp_path):
    return _cloakbrowser.CloakBrowserRuntimeConfig(
        provider="wiley",
        doi="10.1029/2023JD040418",
        artifact_dir=tmp_path / "artifacts",
        headless=True,
        user_agent=None,
        timeout_ms=12345,
    )


def _wiley_runtime_config(tmp_path):
    return _cloakbrowser.CloakBrowserRuntimeConfig(
        provider="wiley",
        doi="10.1111/gcb.70541",
        artifact_dir=tmp_path / "artifacts",
        headless=True,
        user_agent="paper-fetch-test/1",
        timeout_ms=12345,
    )


def _ready_payload(*, selector: str, text_length: int, paragraph_count: int, heading_count: int = 0):
    return {
        "ready": True,
        "selector": selector,
        "textLength": text_length,
        "paragraphCount": paragraph_count,
        "headingCount": heading_count,
        "fingerprint": f"{selector}|{text_length}|{paragraph_count}|{heading_count}|stable",
    }


def _not_ready_payload(*, selector: str | None = None, text_length: int = 0, paragraph_count: int = 0):
    return {
        "ready": False,
        "selector": selector,
        "textLength": text_length,
        "paragraphCount": paragraph_count,
        "headingCount": 0,
        "fingerprint": f"{selector or ''}|{text_length}|{paragraph_count}|0|unstable",
    }


class _FakeWorkflowClient:
    name = "science"

    def extract_markdown(self, _html_text, _final_url, *, metadata):
        return "# Example Article\n\n## Results\n\n" + ("Readable body. " * 80), {
            "title": metadata.get("title") or "Example Article",
        }


def test_fetch_html_with_cloakbrowser_returns_existing_html_contract(tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    config = _runtime_config(tmp_path)

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        result = _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://www.science.org/doi/full/10.1126/science.example"],
            publisher="science",
            config=config,
            disable_media=True,
            wait_seconds=0,
        )

    assert result.final_url == "https://www.science.org/doi/full/10.1126/science.example"
    assert result.response_status == 200
    assert result.response_headers["content-type"] == "text/html"
    assert result.title == "Example Article"
    assert result.browser_context_seed["browser_user_agent"] == "paper-fetch-test/1"
    assert result.browser_context_seed["browser_cookies"][0]["name"] == "cf_clearance"
    assert fake_module.launch_kwargs["headless"] is True
    assert fake_module.browser.new_context_kwargs["user_agent"] == "paper-fetch-test/1"
    assert fake_module.browser.context.page.aborted_media is True
    assert fake_module.browser.context.page.continued_document is True
    assert fake_module.browser.context.closed is True
    assert fake_module.browser.closed is True


def test_fetch_html_with_cloakbrowser_reuses_and_saves_storage_state(tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    user_data_dir = tmp_path / "cloakbrowser-profile"
    state_path = user_data_dir / "storage-state.json"
    user_data_dir.mkdir()
    state_path.write_text('{"cookies":[]}', encoding="utf-8")
    config = replace(_runtime_config(tmp_path), user_data_dir=user_data_dir)

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://www.science.org/doi/full/10.1126/science.example"],
            publisher="science",
            config=config,
            disable_media=True,
            wait_seconds=0,
        )

    assert fake_module.browser.new_context_kwargs["storage_state"] == str(state_path)
    assert fake_module.browser.context.storage_state_path == str(state_path)
    assert state_path.read_text(encoding="utf-8") == "{}"


def test_load_runtime_config_accepts_cloakbrowser_user_data_dir(tmp_path) -> None:
    config = _cloakbrowser.load_runtime_config(
        {
            "CLOAKBROWSER_USER_DATA_DIR": str(tmp_path / "profile"),
            "CLOAKBROWSER_TIMEOUT_MS": "15000",
        },
        provider="wiley",
        doi="10.1111/example",
    )

    assert config.user_data_dir == tmp_path / "profile"
    assert config.timeout_ms == 15000


def test_fetch_html_with_cloakbrowser_skips_challenge_block_after_wiley_body_dom_ready(tmp_path) -> None:
    body_text = "Wiley article body text with enough substance. " * 18
    html = (
        "<html><head><title>Wiley Article</title></head><body>"
        "<div>Just a moment Cloudflare challenge text remains in the page shell.</div>"
        f"<section class='article-section__content'><p>{body_text}</p><p>{body_text}</p></section>"
        "</body></html>"
    )
    page = _ReadinessFakePage(
        html=html,
        title="Wiley Article",
        readiness_payloads=[
            _ready_payload(
                selector=".article-section__content",
                text_length=len(body_text) * 2,
                paragraph_count=2,
            ),
            _ready_payload(
                selector=".article-section__content",
                text_length=len(body_text) * 2,
                paragraph_count=2,
            ),
        ],
    )
    fake_module = _FakeCloakBrowserModule()
    fake_module.browser.context.page = page

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        result = _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://onlinelibrary.wiley.com/doi/full/10.1111/gcb.70541"],
            publisher="wiley",
            config=_wiley_runtime_config(tmp_path),
            wait_seconds=0,
            max_timeout_ms=2000,
        )

    assert result.final_url == "https://onlinelibrary.wiley.com/doi/full/10.1111/gcb.70541"
    assert "Cloudflare challenge" in result.summary
    assert page.wait_calls == [750]
    assert len(page.evaluate_calls) == 2


def test_fetch_html_with_cloakbrowser_keeps_challenge_block_when_body_dom_never_ready(tmp_path) -> None:
    html = (
        "<html><head><title>Just a moment</title></head><body>"
        "<main>Checking your browser before accessing this publisher page. Cloudflare.</main>"
        "</body></html>"
    )
    page = _ReadinessFakePage(
        html=html,
        title="Just a moment",
        readiness_payloads=[
            _not_ready_payload(),
            _not_ready_payload(),
            _not_ready_payload(),
        ],
    )
    fake_module = _FakeCloakBrowserModule()
    fake_module.browser.context.page = page

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        try:
            _cloakbrowser.fetch_html_with_cloakbrowser(
                ["https://onlinelibrary.wiley.com/doi/full/10.1111/gcb.70541"],
                publisher="wiley",
                config=_wiley_runtime_config(tmp_path),
                wait_seconds=0,
                max_timeout_ms=1000,
            )
        except browser_runtime.BrowserRuntimeFailure as exc:
            failure = exc
        else:  # pragma: no cover - assertion reports the unexpected success path
            raise AssertionError("expected Cloudflare challenge failure")

    assert failure.kind == "cloudflare_challenge"
    assert page.wait_calls[0] == 750
    assert 0 < page.wait_calls[1] <= 250
    assert sum(page.wait_calls) <= 1000
    assert len(page.evaluate_calls) == 3


def test_fetch_html_with_cloakbrowser_omits_user_agent_when_not_configured(tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    config = _runtime_config_without_browser_user_agent(tmp_path)

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        result = _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2023JD040418"],
            publisher="wiley",
            config=config,
            disable_media=True,
            wait_seconds=0,
        )

    assert "user_agent" not in fake_module.browser.new_context_kwargs
    assert result.browser_context_seed["browser_user_agent"] is None


def test_fetch_html_with_cloakbrowser_applies_config_binary_path_during_launch(tmp_path, monkeypatch) -> None:
    fake_module = _FakeCloakBrowserModule()
    config = replace(_runtime_config(tmp_path), binary_path="/tmp/chrome")
    monkeypatch.delenv("CLOAKBROWSER_BINARY_PATH", raising=False)

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://www.science.org/doi/full/10.1126/science.example"],
            publisher="science",
            config=config,
            disable_media=True,
            wait_seconds=0,
        )

    assert fake_module.launch_binary_path == "/tmp/chrome"
    assert "CLOAKBROWSER_BINARY_PATH" not in os.environ


def test_fetch_html_with_cloakbrowser_uses_runtime_context_shared_browser(tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    runtime_context = mock.Mock()
    runtime_context.new_browser_context.return_value = fake_module.browser.context

    with mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module):
        result = _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://www.science.org/doi/full/10.1126/science.example"],
            publisher="science",
            config=_runtime_config(tmp_path),
            runtime_context=runtime_context,
            wait_seconds=0,
        )

    runtime_context.new_browser_context.assert_called_once()
    assert result.final_url == "https://www.science.org/doi/full/10.1126/science.example"
    assert fake_module.launch_kwargs == {}
    assert fake_module.browser.context.closed is True
    assert fake_module.browser.closed is False


def test_fetch_html_with_fast_browser_returns_pnas_html_when_body_dom_ready_despite_challenge() -> None:
    body_text = "PNAS article body text with enough substance. " * 18
    html = (
        "<html><head><title>PNAS Article</title></head><body>"
        "<div>Just a moment Cloudflare challenge text remains in the page shell.</div>"
        f"<section class='article__fulltext'><p>{body_text}</p><p>{body_text}</p></section>"
        "</body></html>"
    )
    page = _ReadinessFakePage(
        html=html,
        title="PNAS Article",
        readiness_payloads=[
            _ready_payload(
                selector=".article__fulltext",
                text_length=len(body_text) * 2,
                paragraph_count=2,
            ),
            _ready_payload(
                selector=".article__fulltext",
                text_length=len(body_text) * 2,
                paragraph_count=2,
            ),
        ],
    )
    browser_context = _FakeContext()
    browser_context.page = page
    runtime_context = RuntimeContext(env={})

    with mock.patch.object(
        runtime_context,
        "new_browser_context",
        return_value=browser_context,
    ) as new_browser_context:
        result = fetch_html_with_fast_browser(
            ["https://www.pnas.org/doi/full/10.1073/pnas.123"],
            publisher="pnas",
            user_agent="Mozilla/5.0",
            timeout_ms=2000,
            context=runtime_context,
        )

    new_browser_context.assert_called_once()
    assert result.final_url == "https://www.pnas.org/doi/full/10.1073/pnas.123"
    assert "Cloudflare challenge" in result.summary
    assert result.browser_context_seed["browser_user_agent"] == "Mozilla/5.0"
    assert page.wait_calls == [750]
    assert len(page.evaluate_calls) == 2
    assert browser_context.closed is True


def test_atypon_body_ready_selectors_include_annualreviews_fulltext_containers() -> None:
    selectors = atypon_body_ready_selectors("annualreviews")

    assert "#itemFullTextId" in selectors
    assert "#html_fulltext" in selectors
    assert ".articleSection" in selectors


def test_atypon_body_ready_selectors_include_iop_article_body_containers() -> None:
    selectors = atypon_body_ready_selectors("iop")

    assert "[itemprop='articleBody']" in selectors
    assert "[property='articleBody']" in selectors
    assert ".article-content" in selectors


def test_atypon_body_dom_readiness_waits_for_annualreviews_dynamic_body() -> None:
    body_text = "Annual Reviews article body text with enough substance. " * 12
    page = _ReadinessFakePage(
        html="<html><body><div>Full text loading...</div></body></html>",
        readiness_payloads=[
            _not_ready_payload(
                selector="#itemFullTextId",
                text_length=len("Full text loading..."),
                paragraph_count=0,
            ),
            _ready_payload(
                selector="#itemFullTextId",
                text_length=len(body_text),
                paragraph_count=2,
                heading_count=1,
            ),
            _ready_payload(
                selector="#itemFullTextId",
                text_length=len(body_text),
                paragraph_count=2,
                heading_count=1,
            ),
        ],
    )

    result = wait_for_atypon_body_dom_ready(
        page,
        "annualreviews",
        timeout_seconds=3,
    )

    assert result.attempted is True
    assert result.ready is True
    assert result.selector == "#itemFullTextId"
    assert result.text_length == len(body_text)
    assert result.paragraph_count == 2
    assert result.heading_count == 1
    assert page.wait_calls == [750, 750]
    assert page.evaluate_calls[0][1]["selectors"] == [
        "#itemFullTextId",
        "#html_fulltext",
        ".articleSection",
    ]


def test_atypon_body_dom_readiness_rejects_short_body_dom() -> None:
    page = _ReadinessFakePage(
        html="<html></html>",
        readiness_payloads=[
            _not_ready_payload(
                selector=".article-section__content",
                text_length=120,
                paragraph_count=1,
            ),
            _not_ready_payload(
                selector=".article-section__content",
                text_length=120,
                paragraph_count=1,
            ),
            _not_ready_payload(
                selector=".article-section__content",
                text_length=120,
                paragraph_count=1,
            ),
        ],
    )

    result = wait_for_atypon_body_dom_ready(
        page,
        "wiley",
        timeout_seconds=1,
    )

    assert result.attempted is True
    assert result.ready is False
    assert result.selector == ".article-section__content"
    assert result.text_length == 120
    assert result.paragraph_count == 1
    assert page.wait_calls == [750, 250]


def test_fetch_html_with_browser_marks_diagnostic(tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    config = _runtime_config(tmp_path)
    context = RuntimeContext(env={})

    with (
        mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module),
        mock.patch.object(
            context,
            "new_browser_context",
            return_value=fake_module.browser.context,
        ) as new_browser_context,
    ):
        _html_result, payload = _fetch_browser_html_payload(
            _FakeWorkflowClient(),
            ["https://www.science.org/doi/full/10.1126/science.example"],
            runtime=config,
            metadata={"doi": "10.1126/science.example", "title": "Example Article"},
            context=context,
            wait_seconds=0,
        )

    new_browser_context.assert_called_once()
    assert fake_module.launch_kwargs == {}
    assert payload.content is not None
    assert payload.content.diagnostics["html_fetcher"] == "cloakbrowser"


def test_fetch_html_with_cloakbrowser_returns_image_payload(tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    image_payload = {
        "bodyB64": "aW1hZ2U=",
        "contentType": "image/png",
        "url": "https://www.science.org/image.png",
        "status": 200,
        "width": 10,
        "height": 20,
    }

    with (
        mock.patch.object(_cloakbrowser, "_import_cloakbrowser", return_value=fake_module),
        mock.patch.object(_cloakbrowser, "_capture_image_payload", return_value=image_payload),
    ):
        result = _cloakbrowser.fetch_html_with_cloakbrowser(
            ["https://www.science.org/image.png"],
            publisher="science",
            config=_runtime_config(tmp_path),
            return_image_payload=True,
            wait_seconds=0,
        )

    assert result.image_payload == image_payload


def test_probe_runtime_status_reports_missing_cloakbrowser_dependency() -> None:
    with (
        mock.patch.object(_cloakbrowser, "_dependency_available", return_value=False),
        mock.patch.object(_cloakbrowser, "_dependency_details", return_value={"probe": "importlib.find_spec"}),
    ):
        result = _cloakbrowser.probe_runtime_status({}, provider="science")

    checks = {check.name: check for check in result.checks}
    assert result.status == "not_configured"
    assert checks["runtime_env"].status == "not_configured"
    assert checks["cloakbrowser_dependency"].status == "not_configured"


def test_import_cloakbrowser_suppresses_welcome_banner(monkeypatch) -> None:
    import cloakbrowser.download

    calls: list[str] = []
    monkeypatch.setattr(_cloakbrowser_runtime, "_WELCOME_SUPPRESSED", False)
    monkeypatch.setattr(cloakbrowser.download, "_show_welcome", lambda: calls.append("welcome"))

    _cloakbrowser._import_cloakbrowser()
    cloakbrowser.download._show_welcome()

    assert calls == []


def test_browser_runtime_module_imports() -> None:
    assert browser_runtime.BrowserRuntimeConfig is _cloakbrowser.CloakBrowserRuntimeConfig
    assert browser_runtime.BrowserRuntimeFailure is _cloakbrowser.CloakBrowserFailure
    assert browser_runtime.BrowserFetchedHtml is _cloakbrowser.BrowserFetchedHtml
    assert hasattr(browser_runtime, "BrowserImagePayload")
    assert browser_runtime.fetch_html_with_browser.paper_fetch_html_fetcher_name == "cloakbrowser"
    assert callable(browser_runtime.warm_browser_context)
    assert callable(browser_runtime.load_runtime_config)
    assert callable(browser_runtime.ensure_runtime_ready)
    assert callable(browser_runtime.probe_runtime_status)
