from __future__ import annotations

import unittest

from paper_fetch.runtime import RuntimeContext
from paper_fetch.workflow import routing
from paper_fetch.workflow.session_cache import LANDING_PDF_PROBE_KEY


class WorkflowRoutingTests(unittest.TestCase):
    def test_cached_landing_pdf_probe_uses_typed_session_cache_key(self) -> None:
        context = RuntimeContext(env={})
        probe = routing.LandingPageCitationPdfProbeResult(
            has_citation_pdf_url=True,
            title="Cached Landing",
            citation_pdf_urls=["https://example.test/article.pdf"],
        )
        context.set_session_cache(LANDING_PDF_PROBE_KEY.materialize("https://example.test/article"), probe)

        self.assertEqual(
            routing.get_cached_landing_page_citation_pdf_probe("https://example.test/article", context=context),
            probe,
        )


if __name__ == "__main__":
    unittest.main()
