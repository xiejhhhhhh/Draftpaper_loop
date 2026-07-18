"""Plugin candidate extraction, source inspection, promotion and contribution APIs."""

from . import contribution, extractors, promotion, skill_source
from .common import PluginCandidateError
from .extractors import (
    extract_skill_capabilities,
)
from .skill_source import (
    _read_registry_json,
    _resolve_github_commit_sha,
    classify_skill_source,
    compile_skill_source,
    extract_review_rule_signals,
    index_skill_source,
    inspect_skill_source,
    map_skill_capabilities,
    snapshot_skill_source,
)
from .promotion import (
    detect_plugin_overlap,
    generalize_plugin_candidate,
    promote_plugin_candidate,
    summarize_plugin_candidates,
    validate_plugin_candidate,
)
from .contribution import (
    package_plugin_contribution,
    preflight_plugin_contribution_package,
    review_plugin_contribution_package,
    write_github_contribution_guide,
)

__all__ = [
    'PluginCandidateError',
    'classify_skill_source',
    'compile_skill_source',
    'detect_plugin_overlap',
    'extract_review_rule_signals',
    'extract_skill_capabilities',
    'generalize_plugin_candidate',
    'index_skill_source',
    'inspect_skill_source',
    'map_skill_capabilities',
    'package_plugin_contribution',
    'preflight_plugin_contribution_package',
    'promote_plugin_candidate',
    'review_plugin_contribution_package',
    'snapshot_skill_source',
    'summarize_plugin_candidates',
    'validate_plugin_candidate',
    'write_github_contribution_guide',
]
