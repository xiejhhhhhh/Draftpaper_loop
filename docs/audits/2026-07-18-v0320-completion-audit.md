# Draftpaper-loop v0.32.0 Completion Audit

Date: 2026-07-18
Release branch: `codex/v0301-v0320`
Release baseline: `09b7021` (`origin/main` when the branch was created)
Integrated plan: `docs/superpowers/plans/2026-07-18-draftpaper-loop-integrated-completion-and-code-audit-optimization.md`

## 1. Audit scope and decision

This audit reconciles the implementation from v0.30.1 through v0.32.0 against the integrated plan, the 2026-07-17 code audit, the final-manuscript completion design, and the release contract. It covers the public CLI, scientific hard gates, security boundaries, stale propagation, final-author completion, package installation, documentation, release fixtures and distribution identity.

The release does not claim that fixtures prove scientific findings, that application-level controls form a production sandbox, or that the current non-commercial license permits public PyPI publication. It does claim one versioned control plane across source checkout, editable installation and isolated wheel installation, subject to the verification recorded in section 7.

## 2. Versioned implementation inventory

| Version | Commit | Authoritative change | Primary verification |
|---|---|---|---|
| v0.30.1 | `c5890bd` | Hard-gate exit contract, MCP artifact boundary, initial safe-fetch policy and release reconciliation | `tests/test_v0301_p0_contracts.py`; `docs/audits/2026-07-18-v0301-release-reconciliation.md` |
| v0.30.2 | `022a97f` | Execution allowlist, write-set preflight, provider-result contract and complete URL boundary | `tests/test_v0302_security_policy.py` |
| v0.30.3 | `407a9c6` | One change taxonomy for revisions, citation changes and artifact-DAG stale propagation | `tests/test_v0303_change_taxonomy.py` |
| v0.30.4 | `edaa649` | `dpl.manuscript_completion.v1`, journal missing-field report and command registration | `tests/test_v0304_manuscript_completion_schema.py` |
| v0.30.5 | `5912776` | Stable paragraph IDs, expected text/hash and line-hint locator | `tests/test_v0305_completion_locators.py` |
| v0.30.6 | `7801571` | Immutable preview, atomic apply, idempotency and rollback | `tests/test_v0306_completion_transaction.py` |
| v0.30.7 | `c91c939` | Completion manifest, evidence, citation, review and PDF release binding | `tests/test_v0307_final_release_binding.py` |
| v0.31.0 | `4b2d8a1` | General, AAS and MNRAS completion regression | `tests/test_v0310_completion_multi_journal.py` |
| v0.31.1 | `b08616e` | Shared I/O and production identifier contracts | `tests/test_v0311_architecture_hygiene.py` |
| v0.31.2 | `bac4584` | `plugin_candidates` package split with stable public façade | `tests/test_v0312_plugin_candidates_package.py` |
| v0.31.3 | `a6bff44` | Methods package split and figure-contract façade | `tests/test_v0313_method_and_figure_facades.py` |
| v0.31.4 | `ac14372` | `CommandSpec` as the single public dispatch/control-plane inventory | `tests/test_v0314_single_command_control_plane.py` |
| v0.31.5 | `a79f74c` | Schema registry and enforceable resource/coverage gates | `tests/test_v0315_schema_and_quality_gates.py` |
| v0.31.6 | `8fd77ed` | Minimal, plotting, fulltext, MCP and research install profiles | `tests/test_v0316_install_profiles.py`; `tools/verify_install_matrix.py` |
| v0.31.7 | `d1e77b5` | Concise bilingual start pages and generated CLI reference | `tests/test_v0317_readme_and_cli_reference.py` |
| v0.31.8 | `5b9aed3` | Token/cost report, generated risk matrix and product boundary docs | `tests/test_v0318_cost_risk_product_docs.py` |
| v0.31.9 | `fe6398a` | Cross-platform CI smoke and tag-to-wheel identity verification | `tests/test_v0319_cross_platform_release.py`; `tools/verify_release_tag.py` |
| v0.32.0 | release commit | Requirement reconciliation, sandbox/container evaluation and one release identity | `tests/test_v0320_release_completion.py`; this audit |

The v0.30.1 release reconciliation was deliberately produced before experimental completion code entered the release branch. Completion became a release capability only through v0.30.4-v0.31.0 and its dedicated regressions.

## 3. High-severity findings reconciliation

| ID | Resolution | Authoritative evidence | Status |
|---|---|---|---|
| H-01 | Journal fetches use centralized HTTPS, hostname, DNS/IP, redirect, content-type and response-size policy. Private, loopback and link-local destinations are rejected. | `draftpaper_cli/safe_fetch.py`, `draftpaper_cli/journal_profile.py`, `tests/test_v0301_p0_contracts.py`, `tests/test_v0302_security_policy.py` | Resolved |
| H-02 | Plugin/registry loading no longer accepts arbitrary URL or `file://` input. Remote sources are allowlisted and local sources are confined to trusted roots. | `draftpaper_cli/safe_fetch.py`, `draftpaper_cli/plugin_candidates/skill_source.py`, `tests/test_v0302_security_policy.py` | Resolved |
| H-03 | MCP artifact access rejects private locators and credential/secret artifacts and redacts sensitive path information. Protected actions retain capability checks. | `draftpaper_cli/mcp/service.py`, `tests/test_v0301_p0_contracts.py`, `tests/test_v0302_security_policy.py` | Resolved |
| H-04 | Method verification parses argv without a shell, rejects shell operators and unapproved interpreters/binaries, confines project paths and uses an explicit runtime environment. | `draftpaper_cli/execution_policy.py`, `draftpaper_cli/methods/verification.py`, `tests/test_methods.py`, `tests/test_v0302_security_policy.py` | Resolved |
| H-05 | Parser, `CommandSpec`, release manifest and wheel inventory are generated from one authoritative command set. v0.32.0 exposes 210 commands. | `draftpaper_cli/command_registry.py`, `draftpaper_cli/command_contracts.py`, `draftpaper_cli/release_contract.py`, `tests/test_v0314_single_command_control_plane.py`, `tests/test_v0320_release_completion.py` | Resolved |
| H-06 | Core-evidence and other scientific hard-gate decisions return zero only for their declared passing state; revise/fail/blocked decisions return nonzero. | `draftpaper_cli/gate_handlers.py`, `tests/test_v0301_p0_contracts.py` | Resolved |
| H-07 | Change classification and artifact roots are centralized; revisions no longer own a divergent stale map. Stage stale markers are compatibility summaries of artifact-DAG propagation. | `draftpaper_cli/change_impact.py`, `draftpaper_cli/artifact_dag.py`, `tests/test_v0303_change_taxonomy.py` | Resolved |

## 4. Medium-severity findings reconciliation

| ID | Resolution | Authoritative evidence | Status |
|---|---|---|---|
| M-01 | All registered scientific hard gates declare a non-`always_success` exit policy and a callable handler. | `draftpaper_cli/command_contracts.py`, `tests/test_v0301_p0_contracts.py`, `tests/test_v0314_single_command_control_plane.py` | Resolved |
| M-02 | Commands declare write globs and side-effect class; preflight rejects writes outside the project boundary before execution. | `draftpaper_cli/write_set_guard.py`, `draftpaper_cli/command_registry.py`, `tests/test_v0302_security_policy.py` | Resolved |
| M-03 | Completion `content_file` and revision inputs use confined resolution and reject absolute, parent, symlink and sensitive-environment escapes. | `draftpaper_cli/manuscript_completion.py`, `draftpaper_cli/manuscript_revision.py`, `tests/test_v0304_manuscript_completion_schema.py`, `tests/test_v0305_completion_locators.py` | Resolved |
| M-04 | Literature providers distinguish successful empty results from provider/runtime failures and expose recovery metadata. | `draftpaper_cli/literature_search.py`, `draftpaper_cli/doctor.py`, `tests/test_v0302_security_policy.py` | Resolved |
| M-05 | Heavy capabilities are grouped into explicit extras and install profiles; minimal installation does not claim absent plotting/fulltext/MCP capabilities. | `pyproject.toml`, `draftpaper_cli/install_profiles.py`, `docs/install_profiles.md`, `tests/test_v0316_install_profiles.py` | Resolved for supported profiles |
| M-06 | Core coverage has an enforced floor, schema resources are validated and Pyright is a CI gate. Plugin and release behavior remains fixture-tested. | `.coveragerc`, `.github/workflows/tests.yml`, `draftpaper_cli/schema_registry.py`, `tests/test_v0315_schema_and_quality_gates.py` | Resolved for the staged target; strict whole-repository typing remains intentionally out of scope |
| M-07 | The largest duplication points were split behind stable façades: plugin candidates, Methods, figure contracts and CLI compatibility dispatch. | `draftpaper_cli/plugin_candidates/`, `draftpaper_cli/methods/`, `draftpaper_cli/figure_contracts.py`, `draftpaper_cli/cli_compat.py`, v0.31.2-v0.31.4 tests | Resolved for audited hotspots |
| M-08 | README files are concise start pages; command details are generated from `CommandSpec` into a dedicated CLI reference. | `README.md`, `README.zh-CN.md`, `docs/cli_reference.md`, `tools/generate_cli_reference.py`, `tests/test_v0317_readme_and_cli_reference.py` | Resolved |
| M-09 | Scientific subprocesses receive an explicit allowlist of required runtime keys while secrets are excluded/redacted. | `draftpaper_cli/execution_policy.py`, `draftpaper_cli/methods/verification.py`, `tests/test_v0302_security_policy.py` | Resolved |
| M-10 | Release verification clears/rejects stale distributions and verifies the selected wheel against the current package and manifest version. | `tools/verify_wheel_install.py`, `tools/verify_release_tag.py`, `.github/workflows/tag-build-verify.yml`, `tests/test_v0319_cross_platform_release.py` | Resolved |
| M-11 | A hard gate cannot register with `always_success` or without a handler; registry validation fails the release contract. | `draftpaper_cli/command_contracts.py`, `draftpaper_cli/command_registry.py`, `tests/test_v0301_p0_contracts.py` | Resolved |
| M-12 | Production IDs and shared JSON I/O have authoritative helpers and documented formats; fixtures cannot substitute for project-run identities. | `draftpaper_cli/io_utils.py`, `docs/spec/dpl-identifiers.md`, `tests/test_v0311_architecture_hygiene.py` | Resolved |

Lower-severity duplication, empty directories, test-only plugin breadth, macOS coverage and `_vendor`/`third_party` role ambiguity were addressed where they affected release truth. `_vendor/paper_fetch_skill` remains the runtime wheel fallback; `third_party/registry.json` remains the provenance and license record. They are intentionally not collapsed into one directory.

## 5. Final requirements R01-R11

### R01: hard-gate and command-inventory truth

All hard-gate failure states return nonzero. Parser choices, `CommandSpec`, generated CLI reference, release manifest and isolated wheel expose the same 210-command inventory. Evidence: v0.30.1 and v0.31.4 tests plus command-contract and wheel verification.

### R02: security boundaries

SSRF, private MCP artifacts, unsafe argv, project-path escape and sensitive environment propagation are blocked by centralized policies with adversarial tests. These are application-level defense-in-depth controls, not an OS or production cloud sandbox.

### R03: one change taxonomy

`draftpaper_cli/change_impact.py` owns canonical change classes. Revisions, citation changes, metadata completion and scientific changes use the same artifact roots and stale propagation. Evidence: `tests/test_v0303_change_taxonomy.py` and artifact-DAG regressions.

### R04: one completion packet

One `dpl.manuscript_completion.v1` YAML covers publication metadata, new references and multiple bounded section revisions. Journal missing-field output and normalized packets are schema-validated. Evidence: v0.30.4 and v0.31.0 tests.

### R05: stable revision targets

Paragraph ID, expected text and expected SHA-256 protect each revision. Line numbers are hints only. Drift can be relocated only when a unique stable locator still matches; ambiguity or stale content rejects the packet. Evidence: `tests/test_v0305_completion_locators.py`.

### R06: evidence-aware preview

Preview reports missing publication fields, normalized diff, stale/evidence impact, citation warnings, compile state and an immutable packet hash. When TeX is available it builds a candidate PDF overlay; no-TeX is `compile_required`, never release-ready. Evidence: `tests/test_v0306_completion_transaction.py`.

### R07: atomic apply and rollback

Apply rechecks packet, source and evidence hashes, writes through `ScopedProjectTransaction`, is idempotent by packet identity, and records a rollback receipt. Rollback refuses to overwrite later edits. User locks prevent a later writer from silently replacing accepted exact text. Evidence: v0.30.6 transaction/fault-injection tests.

### R08: precise science reopening

Publication metadata does not reopen data, methods, results or figures. Citation additions stale final citation audit. Evidence/cohort/run/method/figure changes cannot be disguised as prose and reopen the scientific chain. Claim narrowing follows its explicit claim-boundary route. Evidence: v0.30.3, v0.30.6 and v0.30.7 tests.

### R09: one final release version

Final confirmation binds canonical sections, references, evidence snapshot, citation audit, independent reviews, completion manifest and PDF hash. Any stale or mismatched member blocks final release. Evidence: `tests/test_v0307_final_release_binding.py`.

### R10: bilingual user entry point

The English and Chinese README openings explain evidence-first ordering, human checkpoints, final-author completion, mock/live distinction and recovery. Public command documentation is generated from `CommandSpec`. Evidence: `tests/test_v0317_readme_and_cli_reference.py`.

### R11: installation and platform release truth

Source checkout, editable installation and isolated wheel use the same release manifest, schemas, command inventory, plugin catalog and vendored fulltext fallback. CI covers Windows and Linux, plus macOS control-plane smoke. Tag verification binds Git tag, package, README, workflow contract, manifest and wheel. Evidence: v0.31.6, v0.31.9 and wheel/tag verification.

The supported Python 3.10 path uses `draftpaper_cli.toml_compat` with an explicit conditional `tomli` development dependency; release tests and tag tooling do not import the Python 3.11-only `tomllib` module directly.

## 6. Required release regressions

The **three-journal completion** regression covers General, AAS and MNRAS profiles with journal-specific metadata projection, completion preview/apply and final release binding. It is a workflow regression, not a claim that every publisher template is visually identical.

The **five-domain release regression** uses the versioned fixtures `astronomy_ml`, `geography_ml`, `bioinformatics_medicine`, `physics_quantum` and `scientific_image_ml`. Each fixture checks semantic evidence rejection and release contracts. Fixtures validate control behavior only; real paper evidence still requires a live-runnable plugin or audited project-local implementation and verified project outputs.

## 7. Verification record

Final source-checkout regression after the v0.32.0 version bump and the optional `kpsewhich` timeout hardening:

```text
python -m pytest --cov=draftpaper_cli --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=65
785 collected; 785 passed; 20 ResourceWarning messages; 0 failures
coverage: 76.88%
runtime: 1258.35 seconds
```

The warnings are the existing SQLite connection warnings emitted by `tests/test_v026_statistics_figures.py`; they do not change the test result and remain visible rather than being suppressed.

Static, contract and security verification:

```text
pyright: 0 errors, 0 warnings
Ruff E9/F63/F7/F82: passed
CommandSpec: passed; 210 commands; 210 handlers; 0 legacy dispatch entries
Template/plugin registry: passed; 210 entries; 0 issues
Third-party provenance: passed; 6 sources; 210 formal plugins; notices present
Secret scan: no likely first-party credentials detected
Tag identity preflight for v0.32.0: passed
Python 3.10 compatibility: centralized tomllib/tomli parser; release tests and source tag tool use the compatibility layer
```

Distribution verification started from an empty `dist/` directory:

```text
python -m build --wheel
Successfully built draftpaper_cli-0.32.0-py3-none-any.whl (2,299,787 bytes)

python tools/verify_install_matrix.py --wheel-dir dist
status: passed; minimal, plotting, fulltext and MCP profiles; issues: []

temporary venv + pip install --no-deps -e .
version: 0.32.0; module: current worktree; release manifest: passed; changed_fields: []

python tools/verify_wheel_install.py --wheel-dir dist
matched: true; package version: 0.32.0; entries: 210; fixtures: 546
capability packs: 6; vendored paper-fetch: present; provenance: passed
five-domain release regression: passed; all adversarial checks rejected invalid evidence
```

The committed tree and annotated tag must preserve this identity. GitHub Actions remain the remote release gate after push.

## 8. Sandbox/container boundary

`docs/audits/2026-07-18-v0320-sandbox-container-evaluation.md` is the authoritative assessment. Path confinement, write-set preflight, executable allowlists, environment filtering, MCP capability checks and transaction rollback improve local safety, but this is **not a production sandbox**. A public hosted API remains prohibited until authentication, multi-tenant isolation, outbound network control and per-tenant data isolation are implemented and independently tested.

## 9. Release decision

The local release candidate satisfies the integrated plan at the source, contract and distribution levels. Full-suite, static/security, source/editable/isolated-wheel and tag-identity preflight verification passed. The branch may be committed and pushed; successful GitHub Actions remain mandatory before the v0.32.0 release is declared complete. Any remote failure reopens this audit and blocks final release status.
