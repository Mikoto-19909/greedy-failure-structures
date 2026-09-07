"""Small, explicit exceptions to automatic test discovery."""
from pathlib import PurePosixPath

# Reviewed existing cases only: new methods in these modules also default to core.
EXTENDED_CASES = {
    'test_cartography.CartographyPlanValidationTests.test_absent_repetition_is_rejected_even_after_recomputing_tables': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_coordinated_objective_edits_fail_even_after_rebuilding_tables': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_instance_table_is_checked_against_generated_instances': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_invalid_design_leaves_legacy_cartography_manifest_untouched': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_present_error_run_remains_a_missing_metric': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_real_outputs_validate_without_a_manifest': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_resume_removes_legacy_cartography_manifest_without_rerunning': 'cartography',
    'test_cartography.CartographyPlanValidationTests.test_wrong_run_algorithm_options_and_coordinated_seeds_are_rejected': 'cartography',
    'test_cartography.CartographyTests.test_bundled_design_has_formal_seed_and_algorithm_matrix': 'cartography',
    'test_cartography.CartographyTests.test_design_rejects_declared_pairs_that_are_not_seed_paired': 'cartography',
    'test_cartography.CartographyTests.test_force_clears_only_cartography_owned_artifacts_before_benchmark': 'cartography',
    'test_cartography.CartographyTests.test_pair_estimator_rejects_mismatched_observed_seeds': 'cartography',
    'test_cartography.CartographyTests.test_seed_group_is_a_nonempty_schema_three_case_field': 'cartography',
    'test_cartography.CartographyTests.test_seed_groups_produce_actual_paired_seeds': 'cartography',
    'test_ci_routing.GitRoutingTests.test_advanced_base_uses_common_ancestor_not_direct_base_diff': 'routing',
    'test_ci_routing.GitRoutingTests.test_allowlisted_document_rename_is_docs': 'routing',
    'test_ci_routing.GitRoutingTests.test_code_renamed_into_allowlist_is_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_document_renamed_out_of_allowlist_is_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_empty_diff_and_non_pr_events_are_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_existing_mode_change_is_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_malformed_events_and_bad_sha_values_are_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_missing_objects_and_unrelated_histories_are_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_symlink_and_gitlink_entries_are_full': 'routing',
    'test_ci_routing.GitRoutingTests.test_timeout_shallow_and_multiple_merge_bases_are_full': 'routing',
    'test_cli_e2e.CliEndToEndTests.test_default_quick_explicit_quick_and_demo': 'cli',
    'test_cli_e2e.CliEndToEndTests.test_replay_rejects_oversized_input_without_echoing_payload': 'cli',
    'test_cli_e2e.CliEndToEndTests.test_replay_uses_a_serialized_instance_end_to_end': 'cli',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_coverage_tamper_is_detected': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_derived_flag_conflict_is_a_hard_error': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_identical_copy_reproduces': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_instance_id_tamper_is_detected': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_missing_artifact_is_a_hard_error': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_row_order_reversal_is_detected': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_run_id_tamper_is_detected': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_runtime_difference_is_exempt': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_seed_change_is_detected_and_names_instance_id': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_selected_tamper_is_detected': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_status_difference_is_detected': 'artifacts',
    'test_compare_matrix_outputs.CompareMatrixOutputsTests.test_timeout_incumbent_difference_is_exempt': 'artifacts',
    'test_dashboard.DashboardHttpSecurityTests.test_alternate_ipv4_loopback_host_is_allowed': 'dashboard',
    'test_dashboard.DashboardHttpSecurityTests.test_ipv6_loopback_binding_is_supported': 'dashboard',
    'test_fault_injection.FaultInjectionGateTests.test_certificate_injection_on_a_legacy_adversarial_instance_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_certificate_injection_on_a_stochastic_family_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_complete_feasible_to_optimal_disguise_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_coverage_tamper_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_gap_tamper_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_instance_row_order_tamper_is_a_measured_blind_spot': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_instance_seed_tamper_is_a_measured_blind_spot': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_partial_certificate_injection_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_raw_result_seed_tamper_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_raw_row_order_tamper_is_a_measured_blind_spot': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_report_rewriting_does_not_change_numeric_validation': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_seed_and_run_id_tampers_are_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_selected_tamper_on_a_non_lazy_run_is_a_measured_blind_spot': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_selected_tamper_on_an_exact_run_is_a_measured_blind_spot': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_status_only_disguise_is_rejected': 'artifacts',
    'test_fault_injection.FaultInjectionGateTests.test_the_fixture_itself_validates': 'artifacts',
    'test_p4_adversarial.AdversarialSeverityConstructionTests.test_extended_grid': 'generators',
    'test_structure.GeneratorCalibrationTests.test_existing_random_generators_match_repaired_density_theory': 'generators',
}

def extended_group(test_id: str) -> str | None:
    return EXTENDED_CASES.get(test_id)

GROUPS = {'artifacts', 'cartography', 'routing', 'cli', 'generators', 'dashboard'}
RESEARCH_MODULES = {
    'pilot': ('test_core_overlap_pilot',),
    'r1': ('test_greedy_failure_paths', 'test_research_verification'),
    'r1c': ('test_r1c_confirmation', 'test_r1c_report'),
}
# Producer, verifier, and shared helper ownership; tools need no fake second solver.
ANALYSIS_OWNERS = {
    'core_overlap_pilot.py': 'pilot',
    'greedy_failure_paths.py': 'r1',
    'validate_greedy_failure_paths.py': 'r1',
    'r1c_confirmation.py': 'r1c',
    'validate_r1c_confirmation.py': 'r1c',
    'r1c_design_check.py': 'r1c',
    'render_r1c_confirmation_report.py': 'r1c',
    'compare_research_workflow_speed.py': 'tool',
}

def is_research(test_id: str) -> bool:
    module = test_id.split('.')[0]
    return (module in {m for values in RESEARCH_MODULES.values() for m in values}
            and not test_id.endswith('test_chart_displays_failure_fractions_on_fixed_zero_to_one_axis'))

def is_platform(test_id: str) -> bool:
    module = test_id.split('.')[0]
    return module in {'test_reproducibility', 'test_records', 'test_benchmark_compatibility',
                      'test_benchmark_modules', 'test_contracts_compatibility', 'test_cli'} or test_id.endswith(
                          'test_config_to_summary_checkpoint_lifecycle')

def affected_groups(paths: list[str]) -> set[str]:
    groups: set[str] = set()
    for path in paths:
        p = PurePosixPath(path)
        if p.suffix == '.md' and (len(p.parts) == 1 or p.parts[0] in {'docs', 'analysis'}):
            continue
        name = p.name
        if path.startswith(('scripts/', '.github/workflows/')) or name in {'check_profiles.py', 'test_check_profiles.py', 'classify_ci_changes.py', 'test_ci_routing.py'}:
            groups |= GROUPS
        elif 'cartography' in name:
            groups.add('cartography')
        elif 'generator' in name or 'adversarial' in name or name == 'test_structure.py':
            groups |= {'generators', 'artifacts', 'cartography'}
        elif 'dashboard' in path:
            groups.add('dashboard')
        elif 'cli' in name or name == 'run_project.py':
            groups.add('cli')
        elif path.startswith('tests/test_'):
            # Related test changes must not leave their extended cases unselected.
            if name in {'test_fault_injection.py', 'test_compare_matrix_outputs.py', 'test_output_validation.py'}:
                groups.add('artifacts')
            elif name in {'test_records.py', 'test_contracts_compatibility.py', 'test_reproducibility.py'}:
                groups |= GROUPS
            else:
                groups |= GROUPS  # Unknown dependency: conservative single-environment fallback.
        elif path.startswith('analysis/') and name in ANALYSIS_OWNERS:
            continue  # All registered research verification always runs.
        else:
            groups |= GROUPS
    return groups

REQUIRED_RESEARCH = {
    'pilot': (
        'test_core_overlap_pilot.PilotInputTest.test_complete_synthetic_input_is_accepted',
        'test_core_overlap_pilot.PilotStatisticsTest.test_four_cells_and_exact_two_sided_tail',
        'test_core_overlap_pilot.PilotInputTest.test_selected_coverage_mismatch_is_rejected_for_both_algorithms',
        'test_core_overlap_pilot.PilotInputTest.test_nonoptimal_reference_is_rejected',
    ),
    'r1': (
        'test_research_verification.ResearchVerificationTests.test_saved_r1_evidence_recomputes_without_producer',
        'test_research_verification.ResearchVerificationTests.test_false_r1_optimum_is_rejected',
        'test_greedy_failure_paths.GreedyFailurePathTests.test_partial_neighborhood_never_claims_local_optimality',
    ),
    'r1c': (
        'test_r1c_confirmation.R1cInputTests.test_valid_chain_and_invalid_outputs',
        'test_r1c_confirmation.R1cInputTests.test_partial_budget_or_failed_verification_never_publishes_output',
        'test_r1c_confirmation.R1cInputTests.test_self_consistent_but_false_optimum_is_rejected_by_enumeration',
        'test_r1c_report.R1cReportPathTests.test_nested_data_paths_resolve_from_repository_not_report_directory',
        'test_r1c_report.R1cReportPathTests.test_external_data_remains_an_absolute_executable_path',
    ),
}
OPTIONAL_CASES = {
    'test_p3_oracle.OptionalOracleTests.test_oracle_matches_branch_and_bound_on_200_random_instances',
    'test_core_overlap_pilot.PilotStatisticsTest.test_chart_displays_failure_fractions_on_fixed_zero_to_one_axis',
}
