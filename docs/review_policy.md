# Tiered Review and Agent Delegation

Draftpaper-loop separates three different questions that were previously conflated at a checkpoint: whether evidence is healthy (`review_state`), who may review it (`review_requirement`), and who actually made the decision (`decision_status`). An Agent approval is always recorded as `agent_approved`; it is never written as `user_confirmed`.

## Modes and boundaries

- `manual`: every decision-capable checkpoint waits for the project owner.
- `balanced`: C0 notification checkpoints are recorded and continue automatically; C1/C2 checkpoints may be delegated only after an explicit grant.
- `delegated`: uses the same hard boundaries but allows broader scoped Agent review.

New projects default to `balanced`. Projects without a policy file retain the legacy `manual` behavior until their owner opts in. C3 scientific routes, mutually exclusive claim choices, data or method route changes, third-party promotion, authorship, licensing, final manuscript, release, and any external side effect remain human-only. A timeout never counts as consent.

## Delegation is a bounded capability

Use `configure-review-policy`, `grant-agent-review`, `evaluate-checkpoint-authority`, `review-checkpoint`, and `revoke-agent-review`. Each delegation is immutable and binds the project, policy hash, runtime fingerprint, stage scope, maximum risk, optional revision cycle, expiry, checkpoint limit, allowed change classes, and restrictions on unresolved items and external side effects. Revocation writes an append-only revocation receipt; it does not rewrite the original grant.

Before every Agent decision, Draftpaper-loop checks the current v4 summary, its hash and validation, policy hash, runtime identity, expiry, revocation state, stage/risk/scope, revision-cycle binding, change-class boundary, unresolved issues, and side-effect restriction. A policy or runtime change invalidates an old delegation. Granting an additional delegation does not invalidate existing valid grants merely because a timestamp changed.

C2 review also needs explicit scientific-freeze permission and an independent reviewer Agent distinct from the recorded producer. C3 cannot be delegated. A completed Agent review writes an immutable receipt in the checkpoint package plus the project-level decision ledger, then authorizes only the bounded downstream continuation route.
