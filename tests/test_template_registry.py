from __future__ import annotations

import json
import subprocess
import sys
import unittest

from draftpaper_cli.template_registry import discover_template_registry, validate_template_registry


class TemplateRegistryTests(unittest.TestCase):
    def test_builtin_template_registry_passes(self) -> None:
        report = validate_template_registry()
        self.assertEqual(report["status"], "passed")
        self.assertGreater(report["entry_count"], 10)
        self.assertFalse([issue for issue in report["issues"] if issue["severity"] == "error"])

    def test_cli_validate_template_registry(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "draftpaper_cli.cli", "validate-template-registry"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertGreater(payload["entry_count"], 10)

    def test_plan_fixture_wrappers_are_truthfully_contract_only(self) -> None:
        registry = discover_template_registry()
        wrappers = [
            item for item in registry["entries"]
            if item["manifest_data"].get("validation_level") == "fixture_runnable"
            and item["runtime_level"] == "contract_only"
        ]
        self.assertTrue(wrappers)
        self.assertTrue(all(item["runtime_level"] != "project_validated" for item in wrappers))

    def test_plain_fixture_name_is_discovered_and_executed(self) -> None:
        registry = discover_template_registry()
        entry = next(item for item in registry["entries"] if item["plugin_id"] == "sky_partition_overlap_validation")
        self.assertIn("fixture.json", entry["fixtures"])
        self.assertNotEqual(entry["manifest_data"].get("deployment_state"), "live_runnable")
        report = validate_template_registry()
        self.assertFalse([
            issue for issue in report["issues"]
            if issue.get("plugin_id") == "sky_partition_overlap_validation"
        ])


if __name__ == "__main__":
    unittest.main()
