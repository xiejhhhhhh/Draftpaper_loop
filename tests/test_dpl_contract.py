# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest


class DplContractTests(unittest.TestCase):
    def test_claim_and_evidence_ids_are_stable_and_content_based(self) -> None:
        from draftpaper_cli.loop_contract import stable_claim_id, stable_evidence_id

        first = stable_claim_id("Introduction", "Models require external validation.")
        second = stable_claim_id("Introduction", "  Models require external validation.  ")
        changed = stable_claim_id("Discussion", "Models require external validation.")

        self.assertEqual(first, second)
        self.assertRegex(first, r"^clm_introduction_0001_[a-f0-9]{6}$")
        self.assertNotEqual(first, changed)

        doi_id = stable_evidence_id("crossref", doi="10.1000/XYZ.2024", title="Ignored", first_author="Smith", year="2024")
        doi_id_again = stable_evidence_id("crossref", doi="https://doi.org/10.1000/xyz.2024", title="Changed", first_author="Lee", year="2026")
        title_id = stable_evidence_id("semantic_scholar", title="A Reliable Study", first_author="Smith, Jane", year="2024")

        self.assertEqual(doi_id, doi_id_again)
        self.assertRegex(doi_id, r"^evd_crossref_0001_[a-f0-9]{6}$")
        self.assertRegex(title_id, r"^evd_semantic_scholar_0001_[a-f0-9]{6}$")
        self.assertNotEqual(doi_id, title_id)


if __name__ == "__main__":
    unittest.main()
