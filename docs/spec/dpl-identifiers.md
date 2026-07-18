# Draftpaper-loop Stable Identifier Contract

Draftpaper-loop uses content-derived identifiers only when an upstream artifact does not already provide an explicit identifier. Existing project identifiers remain authoritative and are never rewritten during migration.

## Claim identifiers

`stable_claim_id(section, claim_text, sequence=N)` produces:

```text
clm_<normalized-section>_<sequence>_<content-hash>
```

The research claim contract uses this form for blueprint claims that omit `claim_id`. Explicit blueprint IDs remain unchanged so figure, result and review traces do not lose identity.

## Evidence identifiers

`stable_evidence_id(source_type, ...)` produces:

```text
evd_<normalized-source-type>_<sequence>_<identity-hash>
```

The Scientific Evidence Registry uses this form only when structured evidence or result metrics omit `evidence_id`. DOI is the preferred literature identity; otherwise the normalized structured scope is hashed. Numeric value alone is never an evidence identity.

## Stability boundary

- Whitespace and case normalization do not change an identifier.
- Changing the semantic section, source type or normalized identity changes the identifier.
- Sequence is part of the public identity and must be assigned deterministically.
- Product release numbers are not embedded in schema or scientific identifiers.
