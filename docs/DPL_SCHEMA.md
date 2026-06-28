# DPL Schema Family

The DPL schema family is the public data-contract identity of Draftpaper-loop.
It represents local-first paper-loop state, including project passports, stage
manifests, citation evidence, run manifests, result manifests, artifact hashes,
claim traces, loop events, discipline profiles, and manuscript projection
metadata.

The schema family is visible and additive. It is intended for compatibility,
provenance, migration, and auditability. It is not a hidden watermark, license
check, telemetry mechanism, or destructive control system.

```yaml
dpl_schema_family: dpl
schemas:
  project: dpl.project.v1
  project_passport: dpl.project_passport.v1
  stage_manifest: dpl.stage_manifest.v1
  citation_evidence: dpl.citation_evidence.v1
  evidence_registry: dpl.evidence_registry.v1
  claim_trace: dpl.claim_trace.v1
  run_manifest: dpl.run_manifest.v1
  result_manifest: dpl.result_manifest.v1
  artifact_hash: dpl.artifact_hash.v1
  loop_event: dpl.loop_event.v1
  discipline_profile: dpl.discipline_profile.v1
  manuscript_projection: dpl.manuscript_projection.v1
```

## Compatibility Principle

Draftpaper-loop keeps DPL schema metadata additive. Existing project files,
stage manifests, passports, and CLI commands should remain readable when new
schema fields are added.

Acceptable changes:

- add `dpl.schema_family` to generated metadata;
- add schema-version fields such as `dpl.stage_manifest_schema`;
- add visible `generated_by` provenance blocks;
- tolerate legacy files that do not yet contain DPL fields.

Non-goals:

- renaming existing files without migration;
- breaking existing generated projects;
- hiding executable logic in metadata;
- requiring users to regenerate all projects.

## Provenance Block

Generated project metadata may include a visible block like:

```yaml
generated_by:
  name: Draftpaper-loop
  author: Jinray Xie
  repository: https://github.com/xiejhhhhhh/Draftpaper_loop
  license: Source-Available Non-Commercial
  commercial_contact: xiejinhui22@mails.ucas.ac.cn
  sponsorship_note: Sponsorship or donation supports project maintenance but does not grant commercial use rights.
  schema_family: dpl
```

This block is visible, non-executing, and user-auditable. It is used for
attribution, compatibility, and provenance.
