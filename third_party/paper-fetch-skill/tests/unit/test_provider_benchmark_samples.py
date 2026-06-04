from __future__ import annotations

import paper_fetch.providers  # noqa: F401
from paper_fetch.provider_catalog import official_provider_names
from tests.provider_benchmark_samples import PROVIDER_BENCHMARK_SAMPLES


def test_provider_benchmark_samples_cover_official_live_smoke_providers() -> None:
    assert set(PROVIDER_BENCHMARK_SAMPLES) == set(official_provider_names())
