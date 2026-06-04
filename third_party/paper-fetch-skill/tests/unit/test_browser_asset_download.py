from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest import TestCase, mock

from paper_fetch.extraction.html.assets import FIGURE_KIND, SUPPLEMENTARY_KIND
from paper_fetch.providers.browser_workflow import assets as browser_workflow_assets
from paper_fetch.providers.browser_workflow.asset_download import (
    BrowserAssetDownloadPlan,
    BrowserAssetDownloadResult,
    BrowserAssetRecoveryContext,
    plan_browser_asset_download,
    retry_failed_browser_assets,
    run_browser_asset_download_attempt,
)
from tests.unit._browser_workflow_deps import browser_workflow_deps


class BrowserWorkflowAssetDownloadTests(TestCase):
    def test_plan_browser_asset_download_splits_assets_and_freezes_fields(self) -> None:
        figure_asset = {
            "kind": "figure",
            "heading": "Figure 1",
            "url": "https://example.test/figure.png",
            "section": "body",
        }
        supplementary_asset = {
            "kind": "supplementary",
            "heading": "Supplement",
            "source_url": "https://example.test/supplement.pdf",
            "section": "supplementary",
        }

        plan = plan_browser_asset_download(
            article_id="10.5555/example",
            output_dir=Path("/tmp/browser-assets"),
            html_text="<html></html>",
            source_url="https://example.test/article",
            profile={
                "asset_profile": "all",
                "assets": [figure_asset, supplementary_asset],
            },
            deps=browser_workflow_deps(),
        )

        self.assertIsInstance(plan, BrowserAssetDownloadPlan)
        self.assertEqual(plan.article_id, "10.5555/example")
        self.assertEqual(plan.asset_profile, "all")
        self.assertEqual(plan.body_assets, [figure_asset])
        self.assertEqual(plan.supplementary_assets, [supplementary_asset])
        with self.assertRaises(FrozenInstanceError):
            plan.article_id = "changed"  # type: ignore[misc]

    def test_run_browser_asset_download_attempt_injects_fetchers_and_patch_points(
        self,
    ) -> None:
        plan = BrowserAssetDownloadPlan(
            article_id="10.5555/example",
            output_dir=Path("/tmp/browser-assets"),
            asset_profile="all",
            body_assets=[
                {
                    "kind": "figure",
                    "heading": "Figure 1",
                    "url": "https://example.test/figure.png",
                    "section": "body",
                }
            ],
            supplementary_assets=[
                {
                    "kind": "supplementary",
                    "heading": "Supplement",
                    "source_url": "https://example.test/supplement.pdf",
                    "section": "supplementary",
                }
            ],
        )
        recovery = BrowserAssetRecoveryContext(
            runtime=SimpleNamespace(headless=False),
            provider="science",
            user_agent="test-agent",
            browser_context_seed={
                "browser_cookies": [{"name": "sid", "value": "one"}],
                "browser_user_agent": "seed-agent",
                "browser_final_url": "https://example.test/final",
            },
            browser_cookies=[{"name": "sid", "value": "one"}],
            active_seed_urls=["https://example.test/article"],
        )
        image_fetcher = mock.Mock()
        image_fetcher.close = mock.Mock()
        file_fetcher = mock.Mock()
        file_fetcher.close = mock.Mock()
        image_fetcher_factory = mock.Mock(return_value=image_fetcher)
        file_fetcher_factory = mock.Mock(return_value=file_fetcher)
        opener_requester = mock.Mock()
        figure_page_fetcher_factory = mock.Mock(side_effect=lambda fetcher: fetcher)
        body_result = {
            "assets": [{"kind": "figure", "download_url": "figure.png"}],
            "asset_failures": [{"kind": "figure", "reason": "preview_failed"}],
        }
        supplementary_result = {
            "assets": [
                {"kind": "supplementary", "download_url": "supplement.pdf"}
            ],
            "asset_failures": [],
        }

        mocked_download_assets = mock.Mock(
            side_effect=lambda kind, *_args, **_kwargs: (
                body_result if kind is FIGURE_KIND else supplementary_result
            )
        )
        deps = browser_workflow_deps(download_assets=mocked_download_assets)

        result = run_browser_asset_download_attempt(
            plan,
            recovery,
            image_fetcher_factory=image_fetcher_factory,
            file_fetcher_factory=file_fetcher_factory,
            opener_requester={
                "transport": object(),
                "asset_download_concurrency": 3,
                "figure_page_fetcher_factory": figure_page_fetcher_factory,
                "opener_requester": opener_requester,
            },
            deps=deps,
        )

        self.assertEqual(result.body_results, body_result["assets"])
        self.assertEqual(result.supplementary_results, supplementary_result["assets"])
        self.assertEqual(result.failures, body_result["asset_failures"])
        image_fetcher_factory.assert_called_once()
        file_fetcher_factory.assert_called_once()
        self.assertEqual(
            image_fetcher_factory.call_args.kwargs["attempt_body_assets"],
            plan.body_assets,
        )
        self.assertEqual(
            file_fetcher_factory.call_args.kwargs["attempt_supplementary_assets"],
            plan.supplementary_assets,
        )
        self.assertEqual(mocked_download_assets.call_count, 2)
        calls_by_kind = {call.args[0]: call for call in mocked_download_assets.call_args_list}
        figure_call = calls_by_kind[FIGURE_KIND]
        supplementary_call = calls_by_kind[SUPPLEMENTARY_KIND]
        self.assertIs(figure_call.args[0], FIGURE_KIND)
        self.assertIs(figure_call.kwargs["image_document_fetcher"], image_fetcher)
        self.assertEqual(figure_call.kwargs["asset_download_concurrency"], 3)
        self.assertIs(supplementary_call.args[0], SUPPLEMENTARY_KIND)
        self.assertIs(
            supplementary_call.kwargs["file_document_fetcher"],
            file_fetcher,
        )
        self.assertIs(
            supplementary_call.kwargs["opener_requester"],
            opener_requester,
        )
        self.assertEqual(
            supplementary_call.kwargs["seed_urls"],
            ["https://example.test/article", "https://example.test/final"],
        )
        image_fetcher.close.assert_called_once()
        file_fetcher.close.assert_called_once()

    def test_run_browser_asset_download_attempt_parallelizes_body_and_supplementary(
        self,
    ) -> None:
        plan = BrowserAssetDownloadPlan(
            article_id="10.5555/example",
            output_dir=Path("/tmp/browser-assets"),
            asset_profile="all",
            body_assets=[
                {
                    "kind": "figure",
                    "heading": "Figure 1",
                    "url": "https://example.test/figure.png",
                    "section": "body",
                }
            ],
            supplementary_assets=[
                {
                    "kind": "supplementary",
                    "heading": "Supplement",
                    "source_url": "https://example.test/supplement.pdf",
                    "section": "supplementary",
                }
            ],
        )
        recovery = BrowserAssetRecoveryContext(
            runtime=SimpleNamespace(headless=True),
            provider="science",
            user_agent="test-agent",
            browser_context_seed={"browser_final_url": "https://example.test/final"},
            browser_cookies=[],
            active_seed_urls=["https://example.test/article"],
        )
        body_started = threading.Event()
        supplementary_started = threading.Event()

        def download_assets(kind, *_args, **_kwargs):
            if kind is FIGURE_KIND:
                body_started.set()
                self.assertTrue(supplementary_started.wait(1))
                return {
                    "assets": [{"kind": "figure", "download_url": "figure.png"}],
                    "asset_failures": [],
                }
            supplementary_started.set()
            self.assertTrue(body_started.wait(1))
            return {
                "assets": [
                    {"kind": "supplementary", "download_url": "supplement.pdf"}
                ],
                "asset_failures": [],
            }

        result = run_browser_asset_download_attempt(
            plan,
            recovery,
            image_fetcher_factory=mock.Mock(return_value=None),
            file_fetcher_factory=mock.Mock(return_value=None),
            opener_requester={},
            deps=browser_workflow_deps(download_assets=download_assets),
        )

        self.assertEqual(
            result.body_results,
            [{"kind": "figure", "download_url": "figure.png"}],
        )
        self.assertEqual(
            result.supplementary_results,
            [{"kind": "supplementary", "download_url": "supplement.pdf"}],
        )

    def test_browser_workflow_asset_retry_policy_skips_deterministic_failures(
        self,
    ) -> None:
        asset = {
            "kind": "figure",
            "heading": "Figure 1",
            "url": "https://example.test/figure.png",
            "section": "body",
        }

        self.assertEqual(
            browser_workflow_assets._assets_matching_download_failures(
                [asset],
                [
                    {
                        "kind": "figure",
                        "heading": "Figure 1",
                        "source_url": "https://example.test/figure.png",
                        "section": "body",
                        "status": 404,
                        "reason": "not_found",
                    }
                ],
                retry_scope="body",
            ),
            [],
        )
        self.assertEqual(
            browser_workflow_assets._assets_matching_download_failures(
                [asset],
                [
                    {
                        "kind": "figure",
                        "heading": "Figure 1",
                        "source_url": "https://example.test/figure.png",
                        "section": "body",
                        "status": 404,
                        "reason": "image_fetch_error",
                    }
                ],
                retry_scope="body",
            ),
            [],
        )
        self.assertEqual(
            browser_workflow_assets._assets_matching_download_failures(
                [asset],
                [
                    {
                        "kind": "figure",
                        "heading": "Figure 1",
                        "source_url": "https://example.test/figure.png",
                        "section": "body",
                        "reason": "non_image_response",
                    }
                ],
                retry_scope="body",
            ),
            [],
        )

    def test_browser_workflow_asset_retry_policy_keeps_transient_failures(
        self,
    ) -> None:
        asset = {
            "kind": "figure",
            "heading": "Figure 1",
            "url": "https://example.test/figure.png",
            "section": "body",
        }

        self.assertEqual(
            browser_workflow_assets._assets_matching_download_failures(
                [asset],
                [
                    {
                        "kind": "figure",
                        "heading": "Figure 1",
                        "source_url": "https://example.test/figure.png",
                        "section": "body",
                        "reason": "image_fetch_timeout",
                    }
                ],
                retry_scope="body",
            ),
            [asset],
        )
        self.assertEqual(
            browser_workflow_assets._assets_matching_download_failures(
                [asset],
                [
                    {
                        "kind": "figure",
                        "heading": "Figure 1",
                        "source_url": "https://example.test/figure.png",
                        "section": "body",
                        "status": 403,
                        "reason": "cloudflare_challenge",
                    }
                ],
                retry_scope="body",
            ),
            [asset],
        )

    def test_retry_failed_browser_assets_retries_matching_failures_and_merges(
        self,
    ) -> None:
        failed_figure = {
            "kind": "figure",
            "heading": "Figure 1",
            "url": "https://example.test/figure1.png",
            "section": "body",
        }
        saved_figure = {
            "kind": "figure",
            "heading": "Figure 2",
            "url": "https://example.test/figure2.png",
            "section": "body",
        }
        supplementary_asset = {
            "kind": "supplementary",
            "heading": "Supplement",
            "source_url": "https://example.test/supplement.pdf",
            "section": "supplementary",
        }
        plan = BrowserAssetDownloadPlan(
            article_id="10.5555/example",
            output_dir=Path("/tmp/browser-assets"),
            asset_profile="all",
            body_assets=[failed_figure, saved_figure],
            supplementary_assets=[supplementary_asset],
        )
        previous = BrowserAssetDownloadResult(
            body_results=[
                {
                    "kind": "figure",
                    "heading": "Figure 2",
                    "download_url": "https://example.test/figure2.png",
                    "section": "body",
                }
            ],
            supplementary_results=[
                {
                    "kind": "supplementary",
                    "heading": "Supplement",
                    "download_url": "https://example.test/supplement.pdf",
                    "section": "supplementary",
                }
            ],
            failures=[
                {
                    "kind": "figure",
                    "heading": "Figure 1",
                    "source_url": "https://example.test/figure1.png",
                    "section": "body",
                    "reason": "cloudflare_challenge",
                }
            ],
        )
        recovery = BrowserAssetRecoveryContext(
            runtime=SimpleNamespace(headless=True),
            provider="pnas",
            user_agent="test-agent",
            browser_context_seed={"browser_final_url": "https://example.test/article"},
            browser_cookies=[],
            active_seed_urls=["https://example.test/article"],
        )
        retry_body_result = {
            "assets": [
                {
                    "kind": "figure",
                    "heading": "Figure 1",
                    "download_url": "https://example.test/figure1.png",
                    "section": "body",
                }
            ],
            "asset_failures": [],
        }

        mocked_warm = mock.Mock(
            return_value={"browser_final_url": "https://example.test/refreshed"}
        )
        mocked_download_assets = mock.Mock(return_value=retry_body_result)
        deps = browser_workflow_deps(
            refresh_browser_context_seed=mocked_warm,
            download_assets=mocked_download_assets,
        )

        result = retry_failed_browser_assets(
            plan,
            previous,
            recovery,
            image_fetcher_factory=mock.Mock(return_value=None),
            file_fetcher_factory=mock.Mock(return_value=None),
            opener_requester={"transport": object()},
            deps=deps,
        )

        mocked_warm.assert_called_once()
        mocked_download_assets.assert_called_once()
        self.assertIs(mocked_download_assets.call_args.args[0], FIGURE_KIND)
        self.assertEqual(mocked_download_assets.call_args.kwargs["assets"], [failed_figure])
        self.assertEqual(
            sorted(asset["download_url"] for asset in result.body_results),
            [
                "https://example.test/figure1.png",
                "https://example.test/figure2.png",
            ],
        )
        self.assertEqual(
            [asset["download_url"] for asset in result.supplementary_results],
            ["https://example.test/supplement.pdf"],
        )
        self.assertEqual(result.failures, [])
