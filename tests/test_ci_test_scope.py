from tools.ci_test_scope import classify_changed_paths


def test_checkpoint_renderer_changes_select_checkpoint_regressions():
    scope = classify_changed_paths(["draftpaper_cli/checkpoint_html.py"])

    assert scope.mode == "focused"
    assert "tests/test_checkpoint_human_delta.py" in scope.pytest_targets
    assert "tests/test_checkpoint_html_showcase.py" in scope.pytest_targets
    assert "tests/test_v041_checkpoint_definition_of_done.py" in scope.pytest_targets


def test_test_file_change_selects_that_test():
    scope = classify_changed_paths(["tests/test_common_utils.py"])

    assert scope.mode == "focused"
    assert scope.pytest_targets == ("tests/test_common_utils.py",)


def test_high_risk_paths_require_full_suite():
    for path in (
        ".github/workflows/tests.yml",
        "pyproject.toml",
        "requirements/ci-constraints.txt",
        "draftpaper_cli/evidence_registry.py",
        "draftpaper_cli/evidence/binder.py",
        "draftpaper_cli/schemas/new_schema.py",
        "draftpaper_cli/cli.py",
    ):
        scope = classify_changed_paths([path])
        assert scope.mode == "full", path
    assert "high-risk paths" in classify_changed_paths(
        ["./.github/workflows/tests.yml"]
    ).reason


def test_unknown_source_path_fails_closed_to_full_suite():
    scope = classify_changed_paths(["draftpaper_cli/new_unmapped_component.py"])

    assert scope.mode == "full"


def test_docs_change_runs_docs_contract_tests_without_full_suite():
    scope = classify_changed_paths(["README.md"])

    assert scope.mode == "focused"
    assert "tests/test_v0317_readme_and_cli_reference.py" in scope.pytest_targets


def test_multiple_changes_union_their_focused_tests():
    scope = classify_changed_paths(
        ["draftpaper_cli/common_utils.py", "tests/test_checkpoint_human_delta.py"]
    )

    assert scope.mode == "focused"
    assert "tests/test_common_utils.py" in scope.pytest_targets
    assert "tests/test_checkpoint_human_delta.py" in scope.pytest_targets
