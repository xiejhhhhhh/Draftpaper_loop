# Codex Authoring Guide for New Discipline Modules

When a real project reveals a reusable discipline workflow, Codex should summarize it into a module proposal rather than hard-coding it into the core loop.

Capture these items:

1. Discipline and subdiscipline scope.
2. Common data sources, API/server/local-file access patterns, and required data roles.
3. Data quality checks, preprocessing routines, and missing-data warning signs.
4. Method families and code patterns commonly used in the field.
5. Validation checks that reviewers expect.
6. Figure families, metadata requirements, and target-journal visual conventions.
7. Formula families that should appear in Methods.
8. Reviewer risks and rescue routes.
9. User-confirmation questions that must be asked before downloading data, running expensive jobs, or weakening claims.
10. Minimal fixture data and tests proving the module integrates with `prepare-method-blueprint`, `generate-analysis-code`, `verify-methods`, and `write-methods`.

The module should improve the upper bound of discipline-specific quality while the default module remains the safety fallback.
