# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.cli import build_parser


class CliFeasibilityCommandTests(unittest.TestCase):
    def test_feasibility_gate_commands_are_registered(self) -> None:
        parser = build_parser()
        commands = [
            "preflight-research-feasibility",
            "assess-research-plan-feasibility",
            "revise-research-plan",
            "assess-method-feasibility",
            "assess-figure-contracts",
        ]
        for command in commands:
            with self.subTest(command=command):
                args = parser.parse_args([command, "--project", "example-project"])
                self.assertEqual(args.command, command)
                self.assertEqual(args.project, "example-project")


if __name__ == "__main__":
    unittest.main()
