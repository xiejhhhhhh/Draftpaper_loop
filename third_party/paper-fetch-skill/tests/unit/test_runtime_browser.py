from __future__ import annotations

import inspect
import os
import sys
import threading
from types import SimpleNamespace
from typing import Any

from paper_fetch import _cloakbrowser_runtime
from paper_fetch import runtime_browser
from paper_fetch.runtime import RuntimeContext
from paper_fetch.runtime_browser import BrowserContextManager


class _FakeBrowser:
    def __init__(self, *, headless: bool, locale: str) -> None:
        self.headless = headless
        self.locale = locale
        self.context_kwargs: list[dict[str, Any]] = []
        self.close_count = 0

    def new_context(self, **kwargs: Any) -> Any:
        self.context_kwargs.append(dict(kwargs))
        return SimpleNamespace(kwargs=dict(kwargs))

    def close(self) -> None:
        self.close_count += 1


def test_browser_reused_across_calls(monkeypatch) -> None:
    launches: list[_FakeBrowser] = []

    def launch(*, headless: bool, locale: str) -> _FakeBrowser:
        browser = _FakeBrowser(headless=headless, locale=locale)
        launches.append(browser)
        return browser

    monkeypatch.setattr("cloakbrowser.launch", launch)
    lifecycle = BrowserContextManager()

    first_context = lifecycle.new_context(headless=True, locale="en-US")
    second_context = lifecycle.new_context(headless=True, viewport={"width": 800})

    assert len(launches) == 1
    assert launches[0].headless is True
    assert launches[0].locale == "en-US"
    assert first_context.kwargs == {"locale": "en-US"}
    assert second_context.kwargs == {"viewport": {"width": 800}}
    assert launches[0].context_kwargs == [{"locale": "en-US"}, {"viewport": {"width": 800}}]


def test_headless_change_restarts_browser(monkeypatch) -> None:
    launches: list[_FakeBrowser] = []

    def launch(*, headless: bool, locale: str) -> _FakeBrowser:
        browser = _FakeBrowser(headless=headless, locale=locale)
        launches.append(browser)
        return browser

    monkeypatch.setattr("cloakbrowser.launch", launch)
    lifecycle = BrowserContextManager()

    first_browser = lifecycle.browser(headless=True)
    second_browser = lifecycle.browser(headless=False)

    assert len(launches) == 2
    assert first_browser is launches[0]
    assert second_browser is launches[1]
    assert first_browser.close_count == 1
    assert second_browser.close_count == 0
    assert second_browser.headless is False


def test_browser_manager_applies_binary_path_only_during_launch(monkeypatch) -> None:
    launches: list[str | None] = []

    def launch(*, headless: bool, locale: str) -> _FakeBrowser:
        launches.append(os.environ.get("CLOAKBROWSER_BINARY_PATH"))
        return _FakeBrowser(headless=headless, locale=locale)

    monkeypatch.delenv("CLOAKBROWSER_BINARY_PATH", raising=False)
    monkeypatch.setattr("cloakbrowser.launch", launch)
    lifecycle = BrowserContextManager(binary_path="/tmp/chrome")

    lifecycle.browser(headless=True)

    assert launches == ["/tmp/chrome"]
    assert "CLOAKBROWSER_BINARY_PATH" not in os.environ


def test_browser_manager_serializes_binary_path_env_during_launch(monkeypatch) -> None:
    launches: list[str | None] = []
    errors: list[BaseException] = []
    launch_lock = threading.Lock()
    first_launch_entered = threading.Event()
    allow_first_launch_exit = threading.Event()
    second_thread_started = threading.Event()
    second_launch_entered = threading.Event()

    def launch(*, headless: bool, locale: str) -> _FakeBrowser:
        binary_path = os.environ.get("CLOAKBROWSER_BINARY_PATH")
        with launch_lock:
            launches.append(binary_path)
        if binary_path == "/tmp/chrome-a":
            first_launch_entered.set()
            if not allow_first_launch_exit.wait(timeout=5):
                raise AssertionError("timed out waiting to release first browser launch")
        if binary_path == "/tmp/chrome-b":
            second_launch_entered.set()
        return _FakeBrowser(headless=headless, locale=locale)

    def open_browser(binary_path: str, *, started: threading.Event | None = None) -> None:
        if started is not None:
            started.set()
        try:
            BrowserContextManager(binary_path=binary_path).browser(headless=True)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.delenv("CLOAKBROWSER_BINARY_PATH", raising=False)
    monkeypatch.setattr("cloakbrowser.launch", launch)
    first_thread = threading.Thread(target=open_browser, args=("/tmp/chrome-a",))
    second_thread = threading.Thread(
        target=open_browser,
        args=("/tmp/chrome-b",),
        kwargs={"started": second_thread_started},
    )

    first_thread.start()
    assert first_launch_entered.wait(timeout=2)
    second_thread.start()
    assert second_thread_started.wait(timeout=2)
    assert not second_launch_entered.wait(timeout=0.1)

    allow_first_launch_exit.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert launches == ["/tmp/chrome-a", "/tmp/chrome-b"]
    assert "CLOAKBROWSER_BINARY_PATH" not in os.environ


def test_runtime_context_passes_env_binary_path_to_browser_manager(monkeypatch) -> None:
    launches: list[str | None] = []

    def launch(*, headless: bool, locale: str) -> _FakeBrowser:
        launches.append(os.environ.get("CLOAKBROWSER_BINARY_PATH"))
        return _FakeBrowser(headless=headless, locale=locale)

    monkeypatch.delenv("CLOAKBROWSER_BINARY_PATH", raising=False)
    monkeypatch.setattr("cloakbrowser.launch", launch)
    context = RuntimeContext(env={"CLOAKBROWSER_BINARY_PATH": "/tmp/chrome"})

    try:
        context.new_browser_context(headless=True)
    finally:
        context.close()

    assert launches == ["/tmp/chrome"]
    assert "CLOAKBROWSER_BINARY_PATH" not in os.environ


def test_cloakbrowser_welcome_banner_is_suppressed(monkeypatch, capsys) -> None:
    import cloakbrowser.download

    monkeypatch.setattr(_cloakbrowser_runtime, "_WELCOME_SUPPRESSED", False)

    def noisy_welcome() -> None:
        sys.stderr.write("CloakBrowser donation banner\n")

    monkeypatch.setattr(cloakbrowser.download, "_show_welcome", noisy_welcome)

    launches: list[_FakeBrowser] = []

    def launch(*, headless: bool, locale: str) -> _FakeBrowser:
        cloakbrowser.download._show_welcome()
        browser = _FakeBrowser(headless=headless, locale=locale)
        launches.append(browser)
        return browser

    monkeypatch.setattr("cloakbrowser.launch", launch)
    lifecycle = BrowserContextManager()

    lifecycle.browser(headless=True)

    captured = capsys.readouterr()
    assert launches
    assert "CloakBrowser donation banner" not in captured.err


def test_runtime_context_recommended_browser_context_entrypoint() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeLifecycle:
        def browser(self, **kwargs: Any) -> str:
            calls.append(("browser", dict(kwargs)))
            return "browser"

        def new_context(self, **kwargs: Any) -> str:
            calls.append(("new_context", dict(kwargs)))
            return "context"

        def close(self) -> None:
            calls.append(("close", {}))

    context = RuntimeContext(env={})
    context._browser_context_manager = FakeLifecycle()  # type: ignore[assignment]

    assert context.new_browser_context(headless=True, locale="en-US") == "context"
    assert context.new_browser_context(headless=True, viewport={"width": 800}) == "context"
    context.close()

    assert calls == [
        ("new_context", {"headless": True, "locale": "en-US"}),
        ("new_context", {"headless": True, "viewport": {"width": 800}}),
        ("close", {}),
    ]


def test_no_direct_sync_playwright_usage() -> None:
    source = inspect.getsource(runtime_browser)

    assert "sync_playwright(" not in source
