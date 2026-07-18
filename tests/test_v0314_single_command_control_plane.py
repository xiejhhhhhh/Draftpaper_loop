from __future__ import annotations

import inspect

from draftpaper_cli.command_contracts import build_command_contracts


def test_every_cli_command_enters_through_a_registered_handler() -> None:
    report = build_command_contracts()
    assert report["status"] == "passed", report["issues"]
    assert report["legacy_dispatch_count"] == 0
    assert report["registered_handler_count"] == report["command_count"]
    assert report["namespace_adapter_count"] >= 1


def test_cli_main_has_no_command_specific_fallback_chain() -> None:
    from draftpaper_cli import cli

    source = inspect.getsource(cli._main_without_passport_refresh)
    assert "if args.command ==" not in source
    assert "dispatch_registered_command(args)" in source


def test_orchestrator_stage_commands_are_generated_from_command_registry() -> None:
    from draftpaper_cli.command_registry import pipeline_stage_commands
    from draftpaper_cli.orchestrator import STAGE_COMMANDS

    assert STAGE_COMMANDS == pipeline_stage_commands()
    assert STAGE_COMMANDS["methods"] == "verify-methods"
    assert STAGE_COMMANDS["figure_contracts"] == "assess-figure-contracts"


def test_figure_contract_command_uses_the_unified_facade() -> None:
    from draftpaper_cli.command_registry import COMMAND_SPECS

    spec = COMMAND_SPECS["assess-figure-contracts"]
    assert spec.handler_module == "figure_contracts"
    assert spec.handler_name == "assess_project_figure_contracts"
