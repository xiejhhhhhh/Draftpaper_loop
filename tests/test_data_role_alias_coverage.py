"""Keep discipline aliases symmetric without accepting absent evidence."""

import unittest

from draftpaper_cli.data_contracts import assess_role_coverage


class DataRoleAliasCoverageTests(unittest.TestCase):
    def setUp(self):
        self.aliases = {
            "section25_formal_event_manifest": "formal_event_manifest",
            "section25_acceptance_report": "data_acceptance_report",
            "spectrum_file_inventory_v3": "spectrum_file_inventory",
        }

    def test_required_and_available_aliases_use_one_vocabulary(self):
        report = assess_role_coverage(
            list(self.aliases), list(self.aliases.values()), role_aliases=self.aliases
        )
        self.assertEqual(report["decision"], "pass")
        self.assertEqual(report["missing_roles"], [])

    def test_missing_spectrum_inventory_still_blocks(self):
        report = assess_role_coverage(
            list(self.aliases),
            ["formal_event_manifest", "data_acceptance_report"],
            role_aliases=self.aliases,
        )
        self.assertEqual(report["decision"], "blocked")
        self.assertEqual(report["blocking_missing_roles"], ["spectrum_file_inventory"])

    def test_aliases_are_not_inferred_without_discipline_context(self):
        report = assess_role_coverage(list(self.aliases), list(self.aliases.values()))
        self.assertEqual(report["decision"], "blocked")

    def test_generic_callers_remain_compatible(self):
        report = assess_role_coverage(["features", "label"], ["features", "category"])
        self.assertEqual(report["decision"], "pass")

    def test_method_blueprint_preserves_missing_evidence_checks(self):
        from draftpaper_cli.method_blueprint import _missing_roles

        self.assertEqual(_missing_roles(list(self.aliases), list(self.aliases.values()), role_aliases=self.aliases), [])
        self.assertEqual(
            _missing_roles(["spectrum_file_inventory_v3"], ["missing:spectrum_file_inventory"], role_aliases=self.aliases),
            ["spectrum_file_inventory"],
        )


if __name__ == "__main__":
    unittest.main()
