from __future__ import annotations

from pathlib import Path

from paper_fetch.providers import ieee as ieee_provider


PROVIDER_ROOT = Path(__file__).resolve().parents[2] / "src" / "paper_fetch" / "providers"


def test_ieee_provider_module_line_counts_stay_split() -> None:
    assert len((PROVIDER_ROOT / "ieee.py").read_text(encoding="utf-8").splitlines()) <= 700
    for path in PROVIDER_ROOT.glob("_ieee_*.py"):
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 500, path.name


def test_ieee_client_declares_only_client_public_export() -> None:
    assert ieee_provider.__all__ == ["IeeeClient"]
    assert not hasattr(ieee_provider, "ProviderContent")
    assert not hasattr(ieee_provider, "RawFulltextPayload")

    lines = (PROVIDER_ROOT / "ieee.py").read_text(encoding="utf-8").splitlines()
    direct_private_imports = [line for line in lines if line.startswith("from ._ieee_")]
    assert len(direct_private_imports) <= 5
