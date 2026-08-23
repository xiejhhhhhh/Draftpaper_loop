# Evidence Identity and Confirmation Continuity

Draftpaper-loop v0.41.0 separates the scientific decision an author approves
from the package used to audit how that decision was assembled.

## Identities

- `scientific_decision_sha256`: scientific inputs and boundaries. It covers the
  data/cohort/split/sample-unit identity, method/run identity, primary metric
  and uncertainty, main figure semantic evidence, and claim boundaries.
- `audit_bundle_sha256`: activity receipts, artifact manifest, validation
  reports, and technical audit detail.
- `presentation_sha256`: rendering/localization of the decision page.

Only the first identity determines whether a new author scientific decision is
required. HTML/CSS changes, paths, timestamps, JSON ordering, regenerated
reports, citation mapping, and PDF compilation do not themselves reopen core
evidence. A change to the second or third identity remains visible in the audit
package.

## Continuity rules

A v5 package can preserve a prior user confirmation only when all conditions
hold:

1. the prior receipt belongs to the same project and checkpoint family;
2. both scientific-decision hashes and DecisionBrief semantic hashes match;
3. the current package is confirmable and all required evidence identities are
   complete;
4. no missing, stale, conflict, or unclassified change is present.

The result is an immutable `confirmation_continuity_receipt.json`. It records
the earlier user receipt, current audit hash, and the effect
`preserve_previous_user_confirmation`. It does not create a fake user receipt.

Metric, uncertainty, cohort, split, sample-unit, method, run, figure semantic,
or claim-boundary changes are scientific changes. The checkpoint displays a
semantic delta and remains C3/human-required. Unknown changes are blocked.

## Repair order

Evidence failures are routed in this order:

1. repair the evidence producer or source binding;
2. repair a validator/adapter contract gap;
3. repair a bounded prose ambiguity;
4. repair figure metadata or figure semantics only when needed;
5. rerun data or methods only when the science really changed.

This prevents a wording edit from hiding an evidence identity error, and
prevents an unnecessary figure redraw from becoming the default response.
