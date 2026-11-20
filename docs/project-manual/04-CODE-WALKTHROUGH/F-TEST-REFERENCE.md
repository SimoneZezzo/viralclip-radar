# Indice dei casi di test

[Indice delle schede](00-GUIDE.md) · [Matrice e significato delle prove](../10-TESTING-AND-RELIABILITY.md)

L'elenco segue ogni file vero e riporta le fixture e i test dichiarati a livello modulo. Per i decoratori parametrizzati, i nomi dei parametri identificano la famiglia di casi. Un nome di funzione può corrispondere a più esecuzioni nella suite.

## test_audit.py

[Apri il file](../../../tests/test_audit.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`db`](../../../tests/test_audit.py#L16) | Fixture (`tmp_path`). |
| [`client_for`](../../../tests/test_audit.py#L23) | Helper (`handler`). |
| [`test_page_survives_later_failure_and_checkpoint_does_not_advance`](../../../tests/test_audit.py#L32) | Test (`db`). |
| [`test_saturation_without_cursor_is_flagged_and_children_cannot_skip_gap`](../../../tests/test_audit.py#L51) | Test (`db, monkeypatch`). |
| [`test_malformed_refresh_is_failed_not_unavailable`](../../../tests/test_audit.py#L71) | Test (`db, payload`). Parametrizzato su `'payload'`. |
| [`test_snapshot_and_completion_roll_back_together`](../../../tests/test_audit.py#L82) | Test (`db`). |
| [`test_full_http_flow_restart_and_delayed_snapshot`](../../../tests/test_audit.py#L100) | Test (`tmp_path`). |
| [`test_second_collector_rejected_but_status_available`](../../../tests/test_audit.py#L143) | Test (`db`). |
| [`test_additive_migration_preserves_existing_measurements`](../../../tests/test_audit.py#L154) | Test (`tmp_path`). |
| [`test_invalid_oauth_response_is_safe`](../../../tests/test_audit.py#L183) | Test (`payload`). Parametrizzato su `'payload'`. |
| [`test_token_validation_hourly_and_token_expiry`](../../../tests/test_audit.py#L190) | Test. |
| [`test_rate_limit_respects_later_header_and_never_zero_delay`](../../../tests/test_audit.py#L214) | Test. |
| [`test_status_cli_without_credentials`](../../../tests/test_audit.py#L223) | Test (`monkeypatch, tmp_path, capsys`). |
| [`test_invalid_counts_are_not_measurements`](../../../tests/test_audit.py#L233) | Test (`views`). Parametrizzato su `'views'`. |
| [`test_failed_jobs_have_delay_and_bounded_attempts`](../../../tests/test_audit.py#L238) | Test (`db`). |
| [`test_search_exact_category_on_second_page`](../../../tests/test_audit.py#L259) | Test (`db`). |
| [`test_repeated_401_is_bounded`](../../../tests/test_audit.py#L272) | Test. |
| [`test_network_retry_is_bounded`](../../../tests/test_audit.py#L281) | Test. |
| [`test_snapshot_tick_runs_between_discovery_intervals`](../../../tests/test_audit.py#L295) | Test (`monkeypatch, tmp_path`). |
| [`test_bad_category_does_not_starve_other_categories`](../../../tests/test_audit.py#L329) | Test (`db`). |
| [`test_successful_clip_pagination_uses_cursor_and_actual_page_times`](../../../tests/test_audit.py#L338) | Test (`db`). |
| [`test_impossible_age_rejected_without_any_rows`](../../../tests/test_audit.py#L363) | Test (`db`). |
| [`test_invalid_selectors_rejected_without_http`](../../../tests/test_audit.py#L375) | Test (`kwargs`). Parametrizzato su `'kwargs'`. |

## test_backup.py

[Apri il file](../../../tests/test_backup.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`test_online_backup_and_restore_see_committed_wal_only`](../../../tests/test_backup.py#L12) | Test (`tmp_path`). |
| [`test_copy_refuses_existing_destination_or_source_alias`](../../../tests/test_backup.py#L33) | Test (`tmp_path`). |
| [`test_validation_rejects_incorrect_completed_job_link`](../../../tests/test_backup.py#L45) | Test (`tmp_path`). |

## test_collector.py

[Apri il file](../../../tests/test_collector.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`clip`](../../../tests/test_collector.py#L18) | Helper (`clip_id`). |
| [`make_client`](../../../tests/test_collector.py#L33) | Helper (`handler`). |
| [`test_game_lookup_exact_match_and_missing_category`](../../../tests/test_collector.py#L48) | Test (`tmp_path`). |
| [`test_credentials_loaded_from_environment`](../../../tests/test_collector.py#L68) | Test (`monkeypatch, tmp_path`). |
| [`test_401_refreshes_token_once_and_retries_request`](../../../tests/test_collector.py#L80) | Test. |
| [`test_overlapping_discovery_preserves_first_seen_and_appends_snapshots`](../../../tests/test_collector.py#L103) | Test (`tmp_path`). |
| [`test_late_discovery_marks_old_targets_missed_without_backdating`](../../../tests/test_collector.py#L141) | Test (`tmp_path`). |
| [`test_due_snapshot_batches_under_one_hundred_and_handles_unordered_results`](../../../tests/test_collector.py#L164) | Test (`tmp_path`). |
| [`test_429_waits_for_retry_after_and_retries`](../../../tests/test_collector.py#L206) | Test. |
| [`test_5xx_retries_with_bounded_backoff`](../../../tests/test_collector.py#L226) | Test. |
| [`test_oauth_5xx_retries_without_exposing_credentials`](../../../tests/test_collector.py#L246) | Test. |
| [`test_rate_limit_remaining_defers_next_request_until_reset`](../../../tests/test_collector.py#L266) | Test. |
| [`test_unavailable_clip_is_not_recorded_as_zero`](../../../tests/test_collector.py#L300) | Test (`tmp_path`). |
| [`test_discovery_uses_persisted_watermark_after_a_long_gap`](../../../tests/test_collector.py#L329) | Test (`tmp_path`). |
| [`test_restart_recovers_running_jobs_without_duplicates`](../../../tests/test_collector.py#L348) | Test (`tmp_path`). |
| [`test_snapshots_cannot_be_updated_or_deleted`](../../../tests/test_collector.py#L369) | Test (`tmp_path`). |
| [`test_status_is_local_and_timestamps_require_timezone`](../../../tests/test_collector.py#L388) | Test (`tmp_path`). |

## test_dataset.py

[Apri il file](../../../tests/test_dataset.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`db`](../../../tests/test_dataset.py#L23) | Fixture (`tmp_path`). |
| [`seen`](../../../tests/test_dataset.py#L30) | Helper (`db, name, offset, views`). |
| [`job_ids`](../../../tests/test_dataset.py#L34) | Helper (`db, name`). |
| [`scheduled`](../../../tests/test_dataset.py#L41) | Helper (`db, name, offset`). |
| [`selection`](../../../tests/test_dataset.py#L51) | Helper (`watermark, outages`). |
| [`features`](../../../tests/test_dataset.py#L55) | Helper (`source, name, cutoff, outages`). |
| [`test_prediction_boundary_is_inclusive_to_the_microsecond`](../../../tests/test_dataset.py#L61) | Test (`db, cutoff`). Parametrizzato su `'cutoff'`. |
| [`test_delayed_discovery_and_cutoff_maturity`](../../../tests/test_dataset.py#L74) | Test (`db`). |
| [`test_no_measurement_preserves_missing_features`](../../../tests/test_dataset.py#L90) | Test (`db`). |
| [`test_recovery_snapshot_uses_actual_time_and_is_deduplicated`](../../../tests/test_dataset.py#L101) | Test (`db`). |
| [`test_outcome_requires_full_window_and_accepts_shared_recovery_link`](../../../tests/test_dataset.py#L117) | Test (`db`). |
| [`test_missing_unavailable_invalid_and_out_of_window_are_never_zero`](../../../tests/test_dataset.py#L131) | Test (`db`). |
| [`outcome_statuses`](../../../tests/test_dataset.py#L157) | Helper (`db`). |
| [`test_future_jobs_and_mutable_metadata_cannot_change_candidate_features`](../../../tests/test_dataset.py#L164) | Test (`db`). |
| [`test_cli_exports_separate_audit_files_and_blackout_coverage`](../../../tests/test_dataset.py#L181) | Test (`db, tmp_path, monkeypatch, capsys`). |

## test_deployment.py

[Apri il file](../../../tests/test_deployment.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`test_service_uses_fixed_non_root_paths_and_graceful_shutdown`](../../../tests/test_deployment.py#L21) | Test. |
| [`test_synthetic_transfer_preserves_links_pending_jobs_and_real_times`](../../../tests/test_deployment.py#L51) | Test (`tmp_path`). |
| [`test_manifest_rejects_wal_and_verify_rejects_wrong_transfer`](../../../tests/test_deployment.py#L100) | Test (`tmp_path, capsys`). |
| [`test_service_preflight_declines_missing_schema_or_changed_configuration`](../../../tests/test_deployment.py#L119) | Test (`tmp_path, monkeypatch`). |

## test_dual_collector_runbook.py

[Apri il file](../../../tests/test_dual_collector_runbook.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`_bash`](../../../tests/test_dual_collector_runbook.py#L11) | Helper. |
| [`test_health_preflight_reports_both_results_under_errexit`](../../../tests/test_dual_collector_runbook.py#L35) | Test (`gta_v, gta_vi, v_status, vi_status`). Parametrizzato su `('gta_v', 'gta_vi', 'v_status', 'vi_status')`. |

## test_evaluation.py

[Apri il file](../../../tests/test_evaluation.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`test_ranking_metrics_use_true_outcomes_and_include_boundary_ties`](../../../tests/test_evaluation.py#L32) | Test. |
| [`examples`](../../../tests/test_evaluation.py#L44) | Helper (`start, end`). |
| [`add_clip`](../../../tests/test_evaluation.py#L48) | Helper (`inputs, clip_id, created, views`). |
| [`test_chronological_evaluation_scores_cutoff_and_matched_pools`](../../../tests/test_evaluation.py#L67) | Test. |
| [`test_embargo_requires_full_label_window_even_for_already_observed_labels`](../../../tests/test_evaluation.py#L105) | Test. |
| [`test_several_partial_intervals_on_one_day_do_not_create_independent_days`](../../../tests/test_evaluation.py#L119) | Test. |
| [`test_future_feature_timestamp_is_rejected`](../../../tests/test_evaluation.py#L131) | Test. |
| [`replays`](../../../tests/test_evaluation.py#L147) | Fixture (`tmp_path, monkeypatch`). |
| [`test_overlap_deduplicates_and_report_manifest_is_reproducible`](../../../tests/test_evaluation.py#L171) | Test (`replays, monkeypatch, capsys`). |
| [`test_hash_mismatch_is_rejected`](../../../tests/test_evaluation.py#L197) | Test (`replays`). |
| [`test_conflicting_labels_fail_even_if_hash_is_internally_consistent`](../../../tests/test_evaluation.py#L205) | Test (`replays`). |
| [`test_valid_label_with_an_unelapsed_window_is_rejected`](../../../tests/test_evaluation.py#L217) | Test (`replays`). |

## test_gta_vi.py

[Apri il file](../../../tests/test_gta_vi.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`test_helix_verifies_exact_name_then_returned_id`](../../../tests/test_gta_vi.py#L17) | Test (`reverse_id`). Parametrizzato su `'reverse_id'`. |
| [`test_resolver_rejects_missing_and_wrong_categories`](../../../tests/test_gta_vi.py#L45) | Test (`data`). Parametrizzato su `'data'`. |
| [`pilot`](../../../tests/test_gta_vi.py#L51) | Fixture (`tmp_path, monkeypatch`). |
| [`test_pilot_dispatches_only_pinned_game_with_existing_database`](../../../tests/test_gta_vi.py#L71) | Test (`pilot, monkeypatch`). |
| [`test_preflight_rejects_id_drift_and_donor_alias`](../../../tests/test_gta_vi.py#L85) | Test (`pilot, tmp_path, monkeypatch`). |
| [`test_unit_has_separate_paths_and_activation_marker`](../../../tests/test_gta_vi.py#L104) | Test. |

## test_health.py

[Apri il file](../../../tests/test_health.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`db`](../../../tests/test_health.py#L16) | Fixture (`tmp_path`). |
| [`discovery`](../../../tests/test_health.py#L22) | Helper (`db, game`). |
| [`add_clip`](../../../tests/test_health.py#L31) | Helper (`db, clip_id`). |
| [`job_id`](../../../tests/test_health.py#L38) | Helper (`db, clip_id, target`). |
| [`report`](../../../tests/test_health.py#L44) | Helper (`db, interval`). |
| [`test_healthy_reports_real_lateness_and_strict_coverage`](../../../tests/test_health.py#L49) | Test (`db`). |
| [`test_delayed_jobs_and_discovery`](../../../tests/test_health.py#L67) | Test (`db`). |
| [`test_execution_failure_retry_and_exhaustion`](../../../tests/test_health.py#L79) | Test (`db`). |
| [`test_discovery_reports_unresolved_truncation_and_per_category_staleness`](../../../tests/test_health.py#L94) | Test (`db`). |
| [`test_recent_errors_are_reported_without_stored_message`](../../../tests/test_health.py#L110) | Test (`db`). |
| [`test_empty_database_reports_no_history`](../../../tests/test_health.py#L121) | Test (`db`). |
| [`test_invalid_record_and_missing_completed_link`](../../../tests/test_health.py#L129) | Test (`db`). |
| [`test_cli_reads_concurrent_wal_without_initializing`](../../../tests/test_health.py#L141) | Test (`monkeypatch, db, capsys`). |
| [`test_cli_handles_unavailable_database_without_mutation`](../../../tests/test_health.py#L161) | Test (`tmp_path, capsys, kind`). Parametrizzato su `'kind'`. |
| [`test_late_observation_p95_can_degrade_without_backlog`](../../../tests/test_health.py#L177) | Test (`db`). |

## test_http_telemetry.py

[Apri il file](../../../tests/test_http_telemetry.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`test_http_retry_sequence_rate_pressure_and_secret_exclusion`](../../../tests/test_http_telemetry.py#L14) | Test (`tmp_path`). |
| [`test_oauth_refresh_after_401_and_invalid_response`](../../../tests/test_http_telemetry.py#L113) | Test (`refresh_fails`). Parametrizzato su `'refresh_fails'`. |
| [`test_logging_failures_preserve_requests_and_retries`](../../../tests/test_http_telemetry.py#L150) | Test (`tmp_path, monkeypatch, capsys, sink`). Parametrizzato su `'sink'`. |
| [`test_rotation_retains_complete_records_and_caps_backups`](../../../tests/test_http_telemetry.py#L190) | Test (`tmp_path, monkeypatch`). |
| [`test_collect_cli_uses_configured_log_directory`](../../../tests/test_http_telemetry.py#L216) | Test (`tmp_path, monkeypatch`). |

## test_operations.py

[Apri il file](../../../tests/test_operations.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`live`](../../../tests/test_operations.py#L22) | Fixture (`tmp_path, monkeypatch`). |
| [`test_verified_backup_and_retention_with_live_wal`](../../../tests/test_operations.py#L34) | Test (`live, tmp_path, monkeypatch`). |
| [`test_remote_failure_preserves_verified_local_backup_and_previous_marker`](../../../tests/test_operations.py#L58) | Test (`live, tmp_path`). |
| [`test_backup_aborts_before_creating_bundle_if_disk_reserve_not_met`](../../../tests/test_operations.py#L75) | Test (`live, tmp_path, monkeypatch`). |
| [`test_restore_drill_calls_real_sqlite_verifier`](../../../tests/test_operations.py#L90) | Test (`live, tmp_path`). |
| [`test_backup_rejects_wrong_game_before_publish`](../../../tests/test_operations.py#L110) | Test (`live, tmp_path`). |
| [`_legacy_bundle`](../../../tests/test_operations.py#L123) | Helper (`tmp_path, game_ids`). |
| [`_fake_restore`](../../../tests/test_operations.py#L141) | Helper (`bundle, output`). |
| [`test_restore_rejects_untrusted_database_identity`](../../../tests/test_operations.py#L161) | Test (`tmp_path, game_ids, expected_id, record_discovery, message`). Parametrizzato su `('game_ids', 'expected_id', 'record_discovery', 'message')`. |
| [`test_restore_rejects_bad_metadata`](../../../tests/test_operations.py#L187) | Test (`tmp_path, changes, message`). Parametrizzato su `('changes', 'message')`. |
| [`test_restore_checks_database_even_when_manifest_claims_expected_game`](../../../tests/test_operations.py#L202) | Test (`tmp_path`). |
| [`test_restore_requires_independent_expected_game_id`](../../../tests/test_operations.py#L214) | Test (`tmp_path`). |
| [`test_restore_accepts_legacy_empty_discovery_for_expected_game`](../../../tests/test_operations.py#L227) | Test (`tmp_path, game_id`). Parametrizzato su `'game_id'`. |
| [`test_monitor_combines_state_disk_and_backup_freshness`](../../../tests/test_operations.py#L234) | Test (`live, tmp_path, monkeypatch`). |
| [`test_restic_passes_isolated_credentials_without_logging_remote_output`](../../../tests/test_operations.py#L273) | Test (`tmp_path, monkeypatch`). |
| [`test_heartbeat_only_sends_severity`](../../../tests/test_operations.py#L296) | Test (`tmp_path, monkeypatch`). |
| [`test_operations_units_do_not_own_or_restart_collector`](../../../tests/test_operations.py#L321) | Test. |
| [`test_live_wal_mount_probe_and_http_rates`](../../../tests/test_operations.py#L348) | Test (`live, tmp_path, monkeypatch`). |
| [`test_gta_vi_operations_isolate_paths_and_schedule`](../../../tests/test_operations.py#L373) | Test. |

## test_release_packaging.py

[Apri il file](../../../tests/test_release_packaging.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`git`](../../../tests/test_release_packaging.py#L13) | Helper (`repo`). |
| [`commit`](../../../tests/test_release_packaging.py#L31) | Helper (`repo`). |
| [`source_repo`](../../../tests/test_release_packaging.py#L47) | Fixture (`tmp_path, monkeypatch`). |
| [`test_exact_commit_is_independent_of_git_and_checkout_configuration`](../../../tests/test_release_packaging.py#L62) | Test (`source_repo, tmp_path`). |
| [`test_rejects_unsafe_committed_inputs`](../../../tests/test_release_packaging.py#L94) | Test (`source_repo, tmp_path, name, data, error`). Parametrizzato su `('name', 'data', 'error')`. |
| [`test_rejects_symlink_blob_without_following_it`](../../../tests/test_release_packaging.py#L104) | Test (`source_repo, tmp_path`). |
| [`test_rejects_abbreviated_revision_and_preserves_existing_output`](../../../tests/test_release_packaging.py#L113) | Test (`source_repo, tmp_path`). |
| [`test_rejects_archives_that_do_not_match_the_commit`](../../../tests/test_release_packaging.py#L132) | Test (`source_repo, change, error`). Parametrizzato su `('change', 'error')`. |
| [`test_rejects_corrupt_gzip_checksum`](../../../tests/test_release_packaging.py#L146) | Test (`source_repo`). |

## test_windows_supervision.py

[Apri il file](../../../tests/test_windows_supervision.py)

| Simbolo | Tipo / parametri fixture o decoratori |
| --- | --- |
| [`test_disabled_task_xml_configures_boot_restarts_and_single_instance`](../../../tests/test_windows_supervision.py#L22) | Test (`tmp_path`). |
| [`test_prepare_generates_local_xml_without_opening_database`](../../../tests/test_windows_supervision.py#L50) | Test (`tmp_path, monkeypatch`). |
| [`test_preflight_keeps_existing_wal_and_rejects_drift_or_missing_file`](../../../tests/test_windows_supervision.py#L63) | Test (`tmp_path, monkeypatch`). |
| [`test_pause_survives_attempts_resume_never_launches`](../../../tests/test_windows_supervision.py#L97) | Test (`tmp_path`). |
| [`test_unexpected_exits_preserve_scheduler_failure`](../../../tests/test_windows_supervision.py#L123) | Test (`tmp_path, collector_exit, event, code`). Parametrizzato su `('collector_exit', 'event', 'code')`. |
| [`test_crash_is_reported_without_exception_message`](../../../tests/test_windows_supervision.py#L136) | Test (`tmp_path`). |
| [`test_pause_interrupts_and_runs_synthetic_cleanup`](../../../tests/test_windows_supervision.py#L148) | Test (`tmp_path`). |
| [`test_runner_checks_before_dispatch_and_records_failure`](../../../tests/test_windows_supervision.py#L182) | Test (`tmp_path, monkeypatch`). |
| [`test_real_cross_process_database_lock_rejects_second_owner`](../../../tests/test_windows_supervision.py#L216) | Test (`tmp_path`). |
