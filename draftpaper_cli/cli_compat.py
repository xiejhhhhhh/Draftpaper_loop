"""Namespace compatibility adapters for commands awaiting direct typed handlers."""

from __future__ import annotations

from typing import Any

from .cli import (
    AnalysisCodeGenerationError,
    AnalysisRevisionError,
    ArtifactDriftError,
    CitationAuditError,
    CitationIntegrityError,
    CitationRepairError,
    ClaimContractError,
    CodeOwnershipError,
    CoreEvidenceError,
    DataAcquisitionError,
    DataGateError,
    DiscussionCitationIntegrityError,
    EvidenceSnapshotMismatch,
    FigureContractGateError,
    FigurePlanError,
    FigureRepairError,
    FigureSemanticAnnotationError,
    IntegrityGateError,
    InvalidStageStatusError,
    JournalProfileError,
    LatexAssemblyError,
    MethodBlueprintError,
    MethodFeasibilityError,
    MethodPlanError,
    MethodsGateError,
    MissingDiscussionInputsError,
    MissingIntroductionInputsError,
    MissingReferencesError,
    NoveltyOverlapError,
    ObservationError,
    OrchestratorError,
    PaperNarrativeError,
    PassportError,
    Path,
    PluginCandidateError,
    PluginExecutionError,
    PluginRescueError,
    ProjectAlreadyExistsError,
    ProjectStateError,
    ResearchCodeMiningError,
    ResearchFeasibilityError,
    ResultDisciplineReviewError,
    ResultEvidenceError,
    ResultRescueError,
    ResultSupportError,
    ResultValidityError,
    ResultsGateError,
    ReviewEngineError,
    ReviewRevisionError,
    UnknownStageError,
    WritingArchitectureError,
    WritingStyleError,
    ZoteroAdapterError,
    _single_skill_source_file_from_args,
    _skill_source_label,
    _skill_source_root_from_args,
    _skill_source_url,
    apply_citation_repair,
    apply_result_downgrade,
    apply_revision,
    assemble_latex,
    assess_core_evidence,
    assess_data_feasibility,
    assess_data_quality,
    assess_figure_contracts,
    assess_method_feasibility,
    assess_plugin_sufficiency,
    assess_publication_readiness,
    assess_research_plan_feasibility,
    assess_result_support,
    assess_result_validity,
    assess_results_manuscript_quality,
    assess_review_rules,
    assess_scientific_figure_quality,
    audit_project_capabilities,
    bootstrap_discipline_foundation,
    build_argument_matrices,
    build_code_provenance,
    build_data_writing_context,
    build_method_writing_context,
    build_panel_writing_contracts,
    build_paper_narrative,
    build_results_synthesis_plan,
    build_section_lifecycles,
    build_section_outline,
    capture_discipline_learning,
    checkpoint_project,
    classify_code_ownership,
    classify_data_access,
    classify_plugin_reusability,
    classify_skill_source,
    collect_method_plan,
    compile_latex_pdf,
    compile_skill_source,
    create_project,
    detect_artifact_drift,
    diagnose_figure_execution,
    diagnose_gate_failures,
    discover_capability_packs,
    discover_research_repos,
    discover_review_workflow_gaps,
    evaluate_capability_routing,
    execute_data_plugins,
    execute_method_plugins,
    extract_method_formulas,
    extract_plugin_candidates,
    extract_review_rule_signals,
    extract_skill_capabilities,
    generalize_plugin_candidate,
    generate_analysis_code,
    generate_citation_repair_plan,
    generate_research_plan,
    generate_revision_plan,
    index_skill_source,
    inspect_research_repo,
    inspect_skill_source,
    inventory_data,
    inventory_results,
    json,
    learn_writing_style_from_draft,
    list_zotero_collections,
    load_project,
    map_repository_workflow,
    map_skill_capabilities,
    mark_stage_stale,
    package_plugin_contribution,
    plan_figures,
    preflight_plugin_contribution_package,
    preflight_research_feasibility,
    prepare_analysis_revision,
    prepare_data_acquisition,
    prepare_discussion_comparison,
    prepare_method_blueprint,
    prepare_panel_repair,
    prepare_plugin_rescue,
    prepare_result_rescue,
    prepare_results_semantic_repair,
    promote_plugin_candidate,
    propose_review_engineering_plan,
    re_audit_citations,
    re_review,
    recommend_statistical_revision,
    record_observation,
    record_plugin_rescue_outcome,
    record_scientific_editor_revision,
    render_third_party_notices,
    reopen_evidence_snapshot,
    repair_figure_data,
    repair_figure_method,
    resolve_journal_template,
    resolve_research_capabilities,
    resolve_result_evidence,
    resolve_venue_style_adapter,
    resume_project,
    review_draft,
    review_plugin_contribution_package,
    review_results_with_discipline_rules,
    revise_research_plan,
    route_stage_code,
    run_citation_repair_loop,
    run_integrity_gate,
    run_pipeline,
    score_research_repos,
    search_literature_for_project,
    snapshot_skill_source,
    status_project,
    submit_figure_semantic_annotations,
    summarize_plugin_candidates,
    sync_artifact_stale,
    sys,
    trace_figures_to_code,
    update_stage_status,
    validate_figure_plugin_trace,
    validate_plugin_candidate,
    validate_project,
    validate_template_registry,
    validate_third_party_provenance,
    verify_methods,
    write_data,
    write_discussion,
    write_github_contribution_guide,
    write_introduction,
    write_methods,
    write_results,
)


def dispatch_compat_command(args: Any) -> int:
    if args.command == "list-capability-packs":
        packs = discover_capability_packs()
        print(json.dumps({"status": "listed", "pack_count": len(packs), "packs": packs}, ensure_ascii=False))
        return 0


    if args.command == "evaluate-capability-routing":
        result = evaluate_capability_routing()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "validate-third-party-provenance":
        result = validate_third_party_provenance()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "render-third-party-notices":
        print(json.dumps(render_third_party_notices(), ensure_ascii=False))
        return 0


    if args.command == "create-project":
        try:
            if args.root and not args.allow_external_project_root:
                from .workspace_policy import resolve_projects_root

                configured = resolve_projects_root()
                requested = Path(args.root).expanduser().resolve()
                if requested != configured:
                    raise ValueError(
                        f"External project root requires --allow-external-project-root; configured root is {configured}"
                    )
            project = create_project(
                root=Path(args.root) if args.root else None,
                idea=args.idea,
                field=args.field,
                target_journal=args.target_journal,
                overwrite=args.overwrite,
            )
        except ProjectAlreadyExistsError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1

        print(json.dumps({
            "status": "created",
            "project_id": project.project_id,
            "project_slug": project.project_slug,
            "project_path": str(project.path),
            "project_json": str(project.path / "project.json"),
            "project_yaml": str(project.path / "project.yaml"),
        }, ensure_ascii=False))
        return 0


    if args.command == "load-project":
        try:
            state = load_project(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "loaded",
            "project_path": str(state.path),
            "metadata": state.metadata,
        }, ensure_ascii=False))
        return 0


    if args.command == "validate-project":
        report = validate_project(args.project)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("status") == "passed" else 1


    if args.command == "validate-template-registry":
        result = validate_template_registry(Path(args.root) if args.root else None)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "status":
        try:
            result = status_project(args.project)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "checkpoint":
        try:
            result = checkpoint_project(args.project, stage=args.stage, note=args.note)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "resume":
        try:
            result = resume_project(args.project, checkpoint_hash=args.checkpoint_hash, note=args.note)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "run-pipeline":
        try:
            result = run_pipeline(args.project)
        except (OrchestratorError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") in {"planned", "awaiting_confirmation", "drift_detected"} else 1


    if args.command == "detect-artifact-drift":
        try:
            result = detect_artifact_drift(args.project)
        except (ArtifactDriftError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "sync-artifact-stale":
        try:
            result = sync_artifact_stale(args.project)
        except (ArtifactDriftError, PassportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "update-stage-status":
        try:
            state = update_stage_status(args.project, args.stage, args.status)
        except (ProjectStateError, UnknownStageError, InvalidStageStatusError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "updated",
            "project_path": str(state.path),
            "stage": args.stage,
            "stage_status": state.metadata["stages"][args.stage]["status"],
            "stale": state.metadata["stages"][args.stage]["stale"],
        }, ensure_ascii=False))
        return 0


    if args.command == "mark-stage-stale":
        try:
            changed = mark_stage_stale(args.project, args.stage, include_self=args.include_self)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "updated",
            "stage": args.stage,
            "stale_stages": changed,
        }, ensure_ascii=False))
        return 0


    if args.command == "search-literature":
        try:
            result = search_literature_for_project(
                args.project,
                query=args.query,
                limit=args.limit,
                from_json=args.from_json,
                zotero_collection=args.zotero_collection,
                zotero_context=args.zotero_context,
                zotero_min_items=args.zotero_min_items,
                zotero_supplement=not args.no_zotero_supplement,
            )
        except (ValueError, ZoteroAdapterError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "list-zotero-collections":
        try:
            collections = list_zotero_collections()
        except ZoteroAdapterError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "listed",
            "count": len(collections),
            "collections": collections,
        }, ensure_ascii=False))
        return 0


    if args.command == "resolve-journal-template":
        try:
            result = resolve_journal_template(
                args.project,
                target_journal=args.target_journal,
                overleaf_url=args.overleaf_url,
                guideline_url=args.guideline_url,
                from_html=args.from_html,
            )
        except (JournalProfileError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "preflight-research-feasibility":
        try:
            result = preflight_research_feasibility(args.project)
        except (ResearchFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1


    if args.command == "generate-plan":
        try:
            result = generate_research_plan(args.project, allow_high_similarity=args.allow_high_similarity)
        except MissingReferencesError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except NoveltyOverlapError as exc:
            print(json.dumps({
                "status": "blocked_high_similarity",
                "message": str(exc),
                "novelty_overlap_report": str(exc.report_path),
            }, ensure_ascii=False), file=sys.stderr)
            return 3
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-research-plan-feasibility":
        try:
            result = assess_research_plan_feasibility(args.project)
        except (ResearchFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1


    if args.command == "revise-research-plan":
        try:
            result = revise_research_plan(args.project)
        except (ResearchFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "write-introduction":
        try:
            result = write_introduction(args.project)
        except (MissingIntroductionInputsError, CitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "record-observation":
        try:
            result = record_observation(args.project, stage=args.stage, kind=args.kind, text=args.text, source=args.source)
        except (ObservationError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "resolve-research-capabilities":
        try:
            result = resolve_research_capabilities(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-plugin-sufficiency":
        try:
            result = assess_plugin_sufficiency(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "rescue_required"} else 1


    if args.command == "audit-project-capabilities":
        try:
            result = audit_project_capabilities(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "rescue_required"} else 1


    if args.command == "prepare-plugin-rescue":
        try:
            result = prepare_plugin_rescue(
                args.project,
                academicforge_root=args.academicforge_root,
                github_metadata=args.github_metadata,
            )
        except (PluginRescueError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "record-plugin-rescue-outcome":
        try:
            route_evidence = {}
            for item in args.route_evidence:
                if "=" not in item:
                    raise PluginRescueError("--route-evidence must use route=path syntax.")
                route, path = item.split("=", 1)
                route_evidence[route.strip()] = path.strip()
            result = record_plugin_rescue_outcome(
                args.project,
                requirement_id=args.requirement_id,
                outcome=args.outcome,
                attempted_routes=args.attempted_route,
                route_evidence=route_evidence,
                evidence_note=args.evidence_note,
            )
        except (PluginRescueError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked_unavailable" else 1


    if args.command == "inventory-data":
        try:
            result = inventory_data(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "classify-data-access":
        try:
            result = classify_data_access(args.project, source_root=args.source_root)
        except (DataAcquisitionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command in {"prepare-data-acquisition", "inventory-data-sources"}:
        try:
            result = prepare_data_acquisition(args.project, source_root=args.source_root)
        except (DataAcquisitionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "execute-data-plugins":
        try:
            result = execute_data_plugins(args.project)
        except (PluginExecutionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "written" else 1


    if args.command == "assess-data-quality":
        try:
            result = assess_data_quality(
                args.project,
                required_columns=args.required_column,
                max_missing_ratio=args.max_missing_ratio,
            )
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-data-feasibility":
        try:
            result = assess_data_feasibility(args.project, min_rows=args.min_rows)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "conditional_pass"} else 1


    if args.command == "build-data-context":
        try:
            context = build_data_writing_context(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "written",
            "project_id": context.get("project_id"),
            "data_writing_context": "data/data_writing_context.json",
            "observation_count": context.get("observation_count", 0),
        }, ensure_ascii=False))
        return 0


    if args.command == "write-data":
        try:
            result = write_data(args.project)
        except DataGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "verify-methods":
        try:
            result = verify_methods(
                args.project,
                command=args.method_command,
                output_files=args.output,
                input_data=args.input,
                allow_system_binary=args.allow_system_binary,
            )
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "success" else 1


    if args.command == "plan-figures":
        try:
            result = plan_figures(args.project, use_review_tasks=args.use_review_tasks)
        except (FigurePlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-figure-contracts":
        try:
            result = assess_figure_contracts(args.project)
        except (FigureContractGateError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1


    if args.command == "validate-figure-plugin-trace":
        try:
            result = validate_figure_plugin_trace(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"ready_for_codegen", "pass"} else 1


    if args.command == "generate-analysis-code":
        try:
            result = generate_analysis_code(args.project, output_files=args.output, auto_plan_figures=args.auto_plan_figures, use_review_tasks=args.use_review_tasks)
        except (AnalysisCodeGenerationError, FigurePlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "classify-code-ownership":
        try:
            result = classify_code_ownership(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "route-stage-code":
        try:
            result = route_stage_code(
                args.project,
                mode=args.mode,
                keep_compat_launchers=not args.no_compat_launchers,
            )
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "build-code-provenance":
        try:
            result = build_code_provenance(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "extract-method-formulas":
        try:
            result = extract_method_formulas(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "trace-figures-to-code":
        try:
            result = trace_figures_to_code(args.project)
        except (CodeOwnershipError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "collect-method-plan":
        try:
            result = collect_method_plan(
                args.project,
                user_method="\n".join(args.method_note or []),
                primary_metric=args.primary_metric,
                minimum_primary_metric=args.minimum_primary_metric,
            )
        except (MethodPlanError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "prepare-method-blueprint":
        try:
            result = prepare_method_blueprint(args.project)
        except (MethodBlueprintError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "execute-method-plugins":
        try:
            result = execute_method_plugins(args.project)
        except (PluginExecutionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "written" else 1


    if args.command == "assess-method-feasibility":
        try:
            result = assess_method_feasibility(args.project)
        except (MethodFeasibilityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "blocked" else 1


    if args.command == "write-methods":
        try:
            result = write_methods(args.project)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "build-method-context":
        try:
            context = build_method_writing_context(args.project)
        except MethodsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps({
            "status": "written",
            "project_id": context.get("project_id"),
            "method_writing_context": "methods/method_writing_context.json",
            "observation_count": context.get("observation_count", 0),
        }, ensure_ascii=False))
        return 0


    if args.command == "inventory-results":
        try:
            result = inventory_results(args.project)
        except ResultsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-result-validity":
        try:
            result = assess_result_validity(
                args.project,
                primary_metric=args.primary_metric,
                minimum_value=args.minimum_value,
            )
        except (ResultValidityError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-review-rules":
        try:
            state = load_project(args.project)
            output = None if args.no_write else Path(args.output) if args.output else state.path / "results" / "review_rule_gate_report.json"
            result = assess_review_rules(state.path, stage=args.stage, write_path=output)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "warn_and_repair"} else 1


    if args.command == "assess-result-support":
        try:
            result = assess_result_support(args.project)
        except (ResultSupportError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1


    if args.command == "apply-result-downgrade":
        try:
            result = apply_result_downgrade(args.project, reason=args.reason)
        except (ClaimContractError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "prepare-result-rescue":
        try:
            result = prepare_result_rescue(args.project)
        except (ResultRescueError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-core-evidence":
        try:
            result = assess_core_evidence(args.project)
        except (CoreEvidenceError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "diagnose-figure-execution":
        try:
            result = diagnose_figure_execution(args.project)
        except (FigureRepairError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "repair-figure-data":
        try:
            result = repair_figure_data(args.project)
        except (FigureRepairError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "repair-figure-method":
        try:
            result = repair_figure_method(args.project)
        except (FigureRepairError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "write-results":
        try:
            result = write_results(args.project)
        except ResultsGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "review-results-with-discipline-rules":
        try:
            result = review_results_with_discipline_rules(args.project)
        except (ResultDisciplineReviewError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") in {"pass", "repair_required"} else 1


    if args.command == "resolve-result-evidence":
        try:
            result = resolve_result_evidence(args.project)
        except (ResultEvidenceError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "reopen-core-evidence":
        try:
            result = reopen_evidence_snapshot(args.project, reason=args.reason)
        except (EvidenceSnapshotMismatch, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "build-paper-narrative":
        try:
            result = build_paper_narrative(args.project)
        except (PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "prepare-section-outline":
        try:
            result = build_section_outline(args.project, args.section)
        except (PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "build-results-synthesis":
        try:
            result = build_results_synthesis_plan(args.project)
        except (PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command in {"build-argument-matrices", "build-section-lifecycles", "build-panel-contracts", "prepare-panel-repair", "resolve-venue-writing-style", "record-scientific-editor-revision"}:
        try:
            if args.command == "build-argument-matrices":
                result = build_argument_matrices(args.project)
            elif args.command == "build-section-lifecycles":
                result = build_section_lifecycles(args.project)
            elif args.command == "build-panel-contracts":
                result = build_panel_writing_contracts(args.project)
            elif args.command == "prepare-panel-repair":
                result = prepare_panel_repair(args.project)
            elif args.command == "resolve-venue-writing-style":
                result = resolve_venue_style_adapter(args.project)
            elif args.command == "record-scientific-editor-revision":
                result = record_scientific_editor_revision(args.project, args.section, args.before, args.after, args.iteration)
        except (WritingArchitectureError, PaperNarrativeError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-manuscript-quality":
        try:
            text = Path(args.input).read_text(encoding="utf-8-sig") if args.input else None
            result = assess_results_manuscript_quality(args.project, text=text)
        except (OSError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1


    if args.command == "assess-figure-publication-quality":
        try:
            result = assess_scientific_figure_quality(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") == "pass" else 1


    if args.command == "prepare-results-semantic-repair":
        try:
            result = prepare_results_semantic_repair(args.project)
        except ProjectStateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "submit-figure-semantic-annotations":
        try:
            result = submit_figure_semantic_annotations(args.project, args.input)
        except (FigureSemanticAnnotationError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "write-discussion":
        try:
            result = write_discussion(args.project)
        except (MissingDiscussionInputsError, DiscussionCitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "prepare-discussion-comparison":
        try:
            result = prepare_discussion_comparison(args.project)
        except (MissingDiscussionInputsError, DiscussionCitationIntegrityError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assemble-latex":
        try:
            result = assemble_latex(args.project, compile_pdf=args.compile_pdf)
        except LatexAssemblyError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "compile-latex-pdf":
        try:
            result = compile_latex_pdf(args.project)
        except LatexAssemblyError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "run-integrity-gate":
        try:
            result = run_integrity_gate(args.project)
        except IntegrityGateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        except Exception as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "generate-citation-repair-plan":
        try:
            result = generate_citation_repair_plan(args.project)
        except (CitationAuditError, CitationRepairError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "apply-citation-repair":
        try:
            result = apply_citation_repair(args.project, dry_run=args.dry_run)
        except CitationRepairError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "re-audit-citations":
        try:
            result = re_audit_citations(args.project)
        except CitationAuditError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "run-citation-repair-loop":
        try:
            result = run_citation_repair_loop(args.project, max_iterations=args.max_iterations)
        except (CitationAuditError, CitationRepairError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "diagnose-gate-failures":
        try:
            result = diagnose_gate_failures(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "review-draft":
        try:
            result = review_draft(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "assess-publication-readiness":
        try:
            result = assess_publication_readiness(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "discover-review-workflow-gaps":
        try:
            result = discover_review_workflow_gaps(args.project)
        except (ReviewEngineError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "propose-review-engineering-plan":
        try:
            result = propose_review_engineering_plan(args.project)
        except (ReviewEngineError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "recommend-statistical-revision":
        try:
            result = recommend_statistical_revision(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "prepare-analysis-revision":
        try:
            result = prepare_analysis_revision(args.project)
        except (AnalysisRevisionError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "discover-research-repos":
        try:
            result = discover_research_repos(
                output_root=args.output_root,
                discipline=args.discipline,
                query=args.query,
                from_json=args.from_json,
                limit=args.limit,
            )
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "score-research-repos":
        try:
            result = score_research_repos(input_file=args.input, output_root=args.output_root)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "extract-plugin-candidates":
        try:
            result = extract_plugin_candidates(input_file=args.input, output_root=args.output_root, top_n=args.top_n)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "inspect-research-repo":
        try:
            result = inspect_research_repo(
                candidate=args.candidate,
                local_repo=args.local_repo,
                output_root=args.output_root,
                mode=args.mode,
            )
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "map-repository-workflow":
        try:
            result = map_repository_workflow(inspection_file=args.inspection, output_root=args.output_root)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "bootstrap-discipline-foundation":
        try:
            result = bootstrap_discipline_foundation(workflow_map=args.workflow_map, output_root=args.output_root)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "capture-discipline-learning":
        try:
            result = capture_discipline_learning(args.project, output_root=args.output_root)
        except (ResearchCodeMiningError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "classify-plugin-reusability":
        try:
            result = classify_plugin_reusability(args.candidate)
        except ResearchCodeMiningError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "summarize-plugin-candidates":
        try:
            result = summarize_plugin_candidates(args.project, source_file=args.source_file, method=args.method)
        except (PluginCandidateError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "snapshot-skill-source":
        try:
            result = snapshot_skill_source(
                _skill_source_root_from_args(args),
                source=_skill_source_label(args),
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref or args.ref,
                include_hashes=not args.no_hashes,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "inspect-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("inspect-skill-source requires --source-root/--path or a SNAPSHOT.json with source_root.")
            result = inspect_skill_source(
                source_root,
                source=_skill_source_label(args),
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "index-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("index-skill-source requires --source-root/--path or a snapshot/inspection report with source_root.")
            result = index_skill_source(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "classify-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("classify-skill-source requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = classify_skill_source(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "map-skill-capabilities":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("map-skill-capabilities requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = map_skill_capabilities(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "extract-review-rule-signals":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("extract-review-rule-signals requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = extract_review_rule_signals(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                source_url=_skill_source_url(args),
                source_ref=args.source_ref,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "extract-skill-capabilities":
        try:
            source_file = _single_skill_source_file_from_args(args)
            if not source_file:
                raise PluginCandidateError("extract-skill-capabilities requires --source-file/--path or a SNAPSHOT.json with exactly one source record. Use compile-skill-source for multi-file snapshots.")
            result = extract_skill_capabilities(
                source_file,
                source=_skill_source_label(args),
                skill_id=args.skill_id,
                discipline=args.discipline,
                output_root=args.output_root,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "compile-skill-source":
        try:
            source_root = _skill_source_root_from_args(args)
            if not source_root:
                raise PluginCandidateError("compile-skill-source requires --source-root/--path or a snapshot/inspection/index report with source_root.")
            result = compile_skill_source(
                source_root,
                source=_skill_source_label(args),
                discipline=args.discipline,
                output_root=args.output_root,
                stop_after=args.stop_after,
                jobs=args.jobs,
                resume=args.resume,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "generalize-plugin-candidate":
        try:
            result = generalize_plugin_candidate(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "validate-plugin-candidate":
        try:
            result = validate_plugin_candidate(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "promote-plugin-candidate":
        try:
            result = promote_plugin_candidate(
                args.candidate,
                require_human_confirmation=args.require_human_confirmation,
                dry_run=not args.write,
                target_root=args.target_root,
            )
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "package-plugin-contribution":
        try:
            result = package_plugin_contribution(args.candidate)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "preflight-plugin-contribution":
        try:
            result = preflight_plugin_contribution_package(args.package)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") == "passed" else 1


    if args.command == "review-plugin-contribution":
        try:
            result = review_plugin_contribution_package(args.package)
        except PluginCandidateError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("maintainer_recommendation") == "ready_for_human_review" else 1


    if args.command == "write-github-contribution-guide":
        try:
            result = write_github_contribution_guide(args.project)
        except (PluginCandidateError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "generate-revision-plan":
        try:
            result = generate_revision_plan(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "apply-revision":
        try:
            result = apply_revision(args.project, issue_ids=args.issue_id, dry_run=args.dry_run)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "re-review":
        try:
            result = re_review(args.project)
        except ReviewRevisionError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    if args.command == "learn-writing-style-from-draft":
        try:
            result = learn_writing_style_from_draft(args.project, args.draft)
        except (WritingStyleError, ProjectStateError) as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False))
        return 0


    print(json.dumps({"status": "error", "message": f"No compatibility handler for {args.command}."}, ensure_ascii=False), file=sys.stderr)
    return 1
