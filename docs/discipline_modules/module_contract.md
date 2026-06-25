# Discipline Module Contract

A discipline module is a lightweight Python object that exposes a `DisciplineModuleSpec`.

Required fields:

- `module_id`: stable lowercase id, for example `geography`.
- `display_name`: human-readable discipline name.
- `keywords`: terms used by Codex and maintainers to understand module scope.
- `data_roles`: data roles that methods may require.
- `method_families`: method families that code generation may implement.
- `validation_checks`: checks that must be considered before claiming results.
- `figure_families`: figure types expected by the discipline.
- `minimum_main_figures`: minimum generated main figures for a first complete draft. Default target is five or more.
- `target_main_figures`: preferred generated main-figure count. Default target is six.
- `required_figure_groups`: discipline-specific evidence groups that `plan-figures` should cover before code generation.
- `formula_families`: mathematical expressions that Methods may need.
- `reviewer_risks`: common reviewer objections.
- `code_generation_constraints`: constraints applied before generating project code.
- `data_connectors`: plan-first data acquisition routes. Each connector should declare `connector_id`, `access_modes`, `packages`, `package_modules`, `download_or_access`, `data_formats`, whether credentials are required, and optional credential environment variables.
- `method_templates`: reusable project-code templates. Each method template should declare `template_id`, `method_family`, required and optional input roles, package modules, output artifacts, figure groups, formulas, validation checks, a template path, aliases, variants, fixture paths, and genericity rules.

The minimum module shape is:

```python
from draftpaper_cli.discipline_modules.base import DisciplineModule, DisciplineModuleSpec


class MyDisciplineModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="my_discipline",
        display_name="My Discipline",
        keywords=["keyword"],
        data_roles=["analysis_ready_table", "target_or_response"],
        method_families=["baseline_model"],
        validation_checks=["missingness_check"],
        figure_families=["metric_summary"],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=["data_overview", "feature_distribution", "metric_summary"],
        formula_families=["primary_metric"],
        reviewer_risks=["unsupported_claim_strength"],
        code_generation_constraints=["Do not generate method code without the declared data roles."],
        data_connectors=[
            {
                "connector_id": "local_files",
                "display_name": "Local files",
                "access_modes": ["local_files"],
                "packages": ["pandas"],
                "package_modules": ["pandas"],
                "download_or_access": ["read local processed tables"],
                "data_formats": ["CSV", "Parquet"],
                "requires_credentials": False,
            }
        ],
    )


MODULE = MyDisciplineModule()
```

Add the module to `draftpaper_cli/discipline_modules/registry.py` and include tests under `tests/`.

## Candidate Merge Rules

Use one discipline module and one plugin directory per reusable capability. If a new candidate overlaps an existing capability, merge aliases, variants, source provenance, fixtures, and tests into the existing plugin directory instead of creating a research-direction-specific branch.

Overlap decisions should prefer:

- same `discipline`
- same `plugin_type`
- same `method_family`
- compatible `input_roles`
- compatible `output_artifacts`
- overlapping `aliases`

Branches and forks are temporary PR channels. `main` is the stable registry.

## Scientific Plugin Boundaries

Reusable plugins should capture discipline-general code patterns, not one paper's exact execution. For example, an astronomy connector may define how to query a photon API with RA/Dec and write a normalized light-curve table, but it must not include a private API account, a fixed source list, or one project's date window. A deep-learning template may define checkpoint shape diagnostics or few-label probe aggregation, but it must not include local checkpoint files, private image folders, or fixed object ids.

Every plugin directory should include at least one small fixture that can run in CI without external credentials, large downloads, private servers, or GPUs. Heavy execution belongs to the local paper project that binds the plugin, not to the reusable plugin itself.
