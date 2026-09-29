"""The batch workflow must be reachable through the public command contract."""

from draftpaper_cli.cli import build_parser
from draftpaper_cli.command_registry import COMMAND_SPECS


def test_batch_commands_have_matching_parser_and_registry_contract() -> None:
    parser = build_parser()
    expected = {
        "prepare-core-evidence-batch": True,
        "shadow-core-evidence-batch-migration": False,
        "migrate-core-evidence-batch": True,
        "assess-core-evidence-readiness": False,
        "finalize-core-evidence-batch": True,
    }
    for command, mutates in expected.items():
        argv = [command, "--project", "C:/synthetic-project"]
        if command == "migrate-core-evidence-batch":
            argv += ["--changes", "changes.json", "--expected-legacy-sha256", "b" * 64]
        args = parser.parse_args(argv)
        assert args.command == command
        spec = COMMAND_SPECS[command]
        assert spec.mutates_project is mutates
        assert spec.coordinator == "state_kernel"
    assert parser.parse_args([
        "prepare-core-evidence-batch", "--project", "C:/synthetic-project", "--changes", "changes.json",
    ]).changes_path == "changes.json"
    assert parser.parse_args([
        "finalize-core-evidence-batch", "--project", "C:/synthetic-project",
        "--expected-scope-sha256", "a" * 64,
    ]).expected_scope_sha256 == "a" * 64
    migrated = parser.parse_args([
        "migrate-core-evidence-batch", "--project", "C:/synthetic-project",
        "--changes", "changes.json", "--expected-legacy-sha256", "b" * 64,
    ])
    assert migrated.expected_legacy_source_sha256 == "b" * 64


def test_notification_commands_are_separate_from_scientific_approval() -> None:
    parser = build_parser()
    pending = parser.parse_args([
        "pending-checkpoint-notification", "--project", "C:/synthetic-project",
        "--request-id", "a" * 12, "--consumer-id", "codex-agent",
    ])
    acknowledge = parser.parse_args([
        "acknowledge-checkpoint-notification", "--project", "C:/synthetic-project",
        "--notification-id", "b" * 24, "--consumer-id", "codex-agent",
    ])
    assert pending.request_id == "a" * 12
    assert acknowledge.notification_id == "b" * 24
    assert COMMAND_SPECS[pending.command].mutates_project is False
    assert COMMAND_SPECS[acknowledge.command].mutates_project is True
    assert COMMAND_SPECS[acknowledge.command].protected_action is False
