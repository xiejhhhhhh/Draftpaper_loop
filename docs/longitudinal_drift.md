# Longitudinal Baselines and Drift Governance

Draftpaper-loop no longer treats the current passport inventory as the sole long-term truth. `ScientificBaselineBundle` freezes a reviewed plan, claim, data/cohort/split, method, run, evidence, figure trace, reference set, and artifact identity. `RevisionCycle` records the reason, allowed change classes, protected facts, and expected outputs for one revision round. `CanonicalFactRegistry v2` gives shared facts stable IDs and explicit identity fields.

Baselines are immutable and can only be superseded. Passport refresh remains an inventory projection, not scientific approval. Same-identity value changes are conflicts; changed cohort, split, run, or validation identities are non-comparable; byte-only and presentation-only changes may rebuild derived outputs without silently reopening science.

## Required reconciliation route

`sync-artifact-stale` records an external edit as a pending `dpl.drift_reconciliation.v2` packet. For semantic or unresolved drift it deliberately does not refresh the passport: the project remains drifted until a route is recorded. `reconcile-project-drift` refreshes inventory only after one explicit route succeeds:

- `rebuild_derived_artifacts` is limited to non-scientific changes.
- `adopt_as_expected_change` requires an open revision cycle and a matching declared change class.
- `reopen_scientific_stage` records that the scientific upstream must be reviewed again.

Use `begin-managed-change` and `apply-managed-change` for bounded edits. A packet binds its before identities, active baseline, and revision cycle; it cannot be applied after the baseline changes, after the revision cycle closes, or after its target changes outside the managed transaction.

`audit-longitudinal-consistency` checks both the current and parent fact registries, manuscript-facing fact references, protected facts, withdrawn or superseded facts, and allowed-consumer contracts. A protected fact that changes, or a parent fact removed from the active registry but still cited by a manuscript artifact, blocks progression. The JSON/HTML report is written under `review/consistency/<revision_cycle_id>/`.
