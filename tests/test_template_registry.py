from __future__ import annotations

import json
import subprocess
import sys
import unittest

from draftpaper_cli.template_registry import validate_template_registry


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


if __name__ == "__main__":
    unittest.main()
