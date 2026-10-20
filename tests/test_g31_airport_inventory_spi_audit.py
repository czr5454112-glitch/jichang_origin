"""Pure fixtures only: no NativeSession, policy fitting, or airport run outputs."""
from copy import deepcopy
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_audit as audit


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
    return {"path": str(path), "sha256": audit.sha(path)}


def fixture_run(root, name="reference", completions=None, *, status="complete", clock=59400.):
    if completions is None:
        completions = {"j0": 7300., "j1": 7400., "j2": 7500., "j3": 7600.}
    folder = root / name
    jobs = [dict(business_bag_id=f"j{i}", arrival=60000. if i == 6 else 7200.,
                 deadline=7500., origin=1, destination=1, unload_seconds=0., hold_seconds=0.)
            for i in range(7)]
    data = {"jobs": jobs, "trays": [{"tray_id": "T", "node": 1}], "transfers": [],
            "edge_records": [], "edge_contracts": [],
            "node_contracts": [{"node": 1, "capacity": 1, "zone": "z"}]}
    actual_completions = {k: v for k, v in completions.items() if v <= clock}
    receipts = [dict(time=7200., event="BAG_ARRIVAL", business_bag_id=f"j{i}", tray_id="")
                for i in range(6) if clock >= 7200.]
    for key, at in sorted(actual_completions.items(), key=lambda pair: pair[1]):
        for event, when in (("LOAD_START", at-.2), ("LOAD_COMPLETE", at-.1),
                            ("UNLOAD_START", at), ("UNLOAD_COMPLETE", at), ("HOLD_COMPLETE", at)):
            receipts.append(dict(time=when, event=event, business_bag_id=key, tray_id="T", node=1))
    receipts.sort(key=lambda r: r["time"])
    result = {
        "mode": "circulation", "physical_clock": clock,
        "advance": {"status": "reached", "horizon_complete": True},
        "population": {"observed": 6 if clock >= 7200. else 0, "completed": len(actual_completions)},
        "jobs": [dict(business_bag_id=j["business_bag_id"],
            status="completed" if j["business_bag_id"] in actual_completions else
                   "waiting_for_tray" if j["arrival"] <= clock else "unreleased",
            completed_at=actual_completions.get(j["business_bag_id"], -1.),
            loaded_at=actual_completions[j["business_bag_id"]]-.1
                      if j["business_bag_id"] in actual_completions else -1.,
            storage_entered_at=-1., storage_released_at=-1.,
            deadline_met=actual_completions.get(j["business_bag_id"], float("inf")) <= j["deadline"])
            for j in jobs],
        "trays": [dict(tray_id="T", node=1, edge_to=-1, mode="empty")],
        "transfers": [], "leg_identities": [], "receipts": receipts,
        "native_summary": {"reservation_conflicts": 0, "physical_fault_edge_entry_violation_count": 0},
        "native_events": [], "decisions": [],
    }
    input_ref = write(root/"input.json", data)
    binary = root/"dummy_binary"
    binary.write_bytes(b"DUMMY NOT EXECUTABLE")
    binary_ref = {"path": str(binary), "sha256": audit.sha(binary)}
    acceptance = write(root/"acceptance.json", {
        "schema": "g31.native030.inventory_spi_accepted_contract.v1", "status": "passed",
        "binary": binary_ref})
    source = {"files": {"dummy.py": "fixture-source-sha"}}
    source["source_manifest_sha256"] = audit.digest(source["files"])
    source_ref = write(root/"source.json", source)
    plan = {"method": "C00" if name == "reference" else "C11",
        "parent": {"parent_seed": 1301, "template": "pure_fixture"},
        "input": input_ref, "input_semantic_sha256": audit.digest(data),
        "binary": binary_ref, "native_acceptance": acceptance, "source_bundle": source_ref,
        "source_manifest_sha256": source["source_manifest_sha256"],
        "controller": {}, "controller_identity": "fixture_pi0", "pair": None,
        "cost_window": [7200., 59400.]}
    plan_ref = write(folder/"plan.json", plan)
    controller = {"config": {"stock_return": False}, "client": {}, "history": ["fixed"]}
    neutral = deepcopy(controller)
    neutral["config"].pop("stock_return")
    prefix = {"native_state_sha256": "same_fixture_native_state",
        "raw_controller_state_sha256": audit.digest(controller),
        "controller_history_sha256": audit.digest(neutral), "at": 7200.,
        "only_ignored_config_fields": ["stock_return", "stock_return_activate_at", "actual_only_activate_at"],
        "stage": "closed_timestamp_before_refresh_and_any_current_tick_publication"}
    cost = audit.window_cost(data, result, start=7200., end=59400.) if status == "complete" else None
    write(folder/"receipt.json", {"status": status, "plan_sha256": plan_ref["sha256"],
        "worker": {"status": status, "cost": cost, "observed_callback_counts": {}, "wall_seconds": .001}})
    write(folder/"final_result.json.gz", result)
    write(folder/"evaluation.json", {"status": status, "cost": cost, "parent": plan["parent"],
        "method": plan["method"], "input_semantic_sha256": plan["input_semantic_sha256"],
        "warmup_prefix": prefix})
    write(folder/"client_calls.json.gz", [])
    write(folder/"control_records.json.gz", [{"preparation_compute_ms": 1., "owner_decisions": [
        {"compute_ms": 2.}]}])
    write(folder/"warmup_prefix.json.gz", {"controller_state": controller, "prefix": prefix})
    return folder, data, result


def test_closed_cost_relief_and_lifecycle_are_independently_recomputed(tmp_path):
    folder, _, _ = fixture_run(tmp_path)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "closed_cost_verified", row["errors"]
    assert row["backlog_relief"] == {
        "J0_bag_seconds": 313200., "J_bag_seconds": 105400.,
        "relief_bag_seconds": 207800., "frozen_J_redefined": False}
    assert row["full_window_cost"]["completed_by_end"] == 4
    assert row["physical"]["lifecycle_capacity_replay"]["status"] == "passed"
    assert row["physical"]["empty_completed_edge_distance"] == 0.
    assert row["control"]["measured_controller_ms"] == 3.
    assert row["provenance"]["status"] == "bound_files_verified"
    assert row["strict_nonharm_certified"] is False


def test_comparison_keeps_all_seven_exact_and_censored_categories(tmp_path):
    reference, _, _ = fixture_run(tmp_path)
    candidate, _, _ = fixture_run(tmp_path, "candidate", {
        "j0": 7310., "j1": 7390., "j2": 7500., "j4": 7700.})
    compared = audit.compare_runs(reference, candidate, expected_population=7)
    assert compared["status"] == "closed_same_parent_comparison"
    assert compared["advantage_bag_seconds"] == -100.
    directions = compared["completion_direction"]
    assert set(directions["categories"].values()) == {1}
    assert directions["population"] == 7
    assert directions["known_direction_harm"] == 2
    assert directions["known_direction_improvement"] == 2
    assert directions["maximum_censored_delay_lower_bound_seconds"] == 51800.
    assert directions["completion_times_imputed"] is False
    assert compared["complete_callback_replay"] is False


def test_cost_tampering_is_rejected_without_partial_gain(tmp_path):
    folder, _, _ = fixture_run(tmp_path)
    path = folder/"evaluation.json"
    value = audit.read(path)
    value["cost"]["backlog_integral_bag_seconds"] -= 1
    write(path, value)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "invalid_evidence"
    assert row["full_window_cost"] is None
    assert "saved_value:cost.backlog_integral_bag_seconds" in row["errors"][0]


def test_incomplete_branch_has_no_gain_or_invented_unobserved_stall(tmp_path):
    folder, _, _ = fixture_run(tmp_path, status="censored_budget_exhausted", clock=8000.)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "retained_incomplete_no_gain"
    assert row["full_window_cost"] is None
    assert row["physical"]["global_progress"]["longest_no_edge_progress_seconds"] == 800.
    assert row["physical"]["observed_diagnostic_window"] == [7200., 8000.]
    other, _, _ = fixture_run(tmp_path, "complete")
    assert audit.compare_runs(folder, other, expected_population=7)["advantage_bag_seconds"] is None


def test_missing_calls_and_warmup_are_unknown_not_zero_or_comparable(tmp_path):
    reference, _, _ = fixture_run(tmp_path)
    candidate, _, _ = fixture_run(tmp_path, "candidate")
    (candidate/"client_calls.json.gz").unlink()
    (candidate/"warmup_prefix.json.gz").unlink()
    row = audit.audit_run(candidate, expected_population=7)
    assert row["full_window_cost"] is not None  # cost proof is separate from execution/protection proof
    assert row["control"]["client_call_count"] is None
    assert row["physical"]["lifecycle_capacity_replay"]["status"] == "unknown_missing_client_calls"
    assert audit.compare_runs(reference, candidate, expected_population=7)["status"] == "unknown_missing_common_warmup"


def test_matching_evaluation_cannot_hide_missing_actual_completion_receipt(tmp_path):
    folder, _, result = fixture_run(tmp_path)
    result["receipts"] = [r for r in result["receipts"] if not
        (r["event"] == "UNLOAD_COMPLETE" and r["business_bag_id"] == "j0")]
    write(folder/"final_result.json.gz", result)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "invalid_evidence"
    assert row["full_window_cost"] is None


def test_common_prefix_mismatch_blocks_comparison_even_when_cost_matches(tmp_path):
    reference, _, _ = fixture_run(tmp_path)
    candidate, _, _ = fixture_run(tmp_path, "candidate")
    path = candidate/"warmup_prefix.json.gz"
    saved = audit.read(path)
    saved["prefix"]["native_state_sha256"] = "different_native_prefix"
    write(path, saved)
    evaluation = audit.read(candidate/"evaluation.json")
    evaluation["warmup_prefix"] = saved["prefix"]
    write(candidate/"evaluation.json", evaluation)
    compared = audit.compare_runs(reference, candidate, expected_population=7)
    assert compared["status"] == "not_comparable_contract_mismatch"
    assert compared["mismatch"] == ["warmup.native_state_sha256"]


def test_grid_preserves_failed_unstarted_and_malformed_cells(tmp_path):
    specs = [{"parent_seed": p, "method": m, "name": f"P{p}_{m}"}
             for p in (1301, 1302) for m in audit.METHODS]
    failed = tmp_path/"runs"/specs[0]["name"]
    failed.mkdir(parents=True)
    (failed/"receipt.json").write_text("malformed", encoding="utf-8")
    grid = audit.audit_grid(tmp_path, specs, expected_parent_ids=(1301, 1302), expected_population=7)
    assert grid["registered_run_count"] == 10
    assert len(grid["rows"]) == 10 and len(grid["comparisons"]) == 20
    assert grid["audit_statuses"]["invalid_evidence"] == 1
    assert all(row["advantage_bag_seconds"] is None for row in grid["comparisons"])
    assert grid["failures_omitted"] == 0 and grid["missing_cells_imputed_as_zero"] is False
    with pytest.raises(ValueError, match="complete_unique_five_method_roster"):
        audit.audit_grid(tmp_path, specs[:-1], expected_parent_ids=(1301, 1302))


def test_unclosed_artifact_is_not_read(tmp_path):
    folder = tmp_path/"unclosed"
    folder.mkdir()
    (folder/"plan.json").write_text("not read before receipt")
    (folder/"final_result.json.gz").write_bytes(b"not read before receipt")
    row = audit.audit_run(folder, expected_population=7)
    assert row["status"] == "not_closed"
    assert row["evidence"] == {}


def test_native_violation_remains_visible_even_if_cost_is_mathematically_valid(tmp_path):
    folder, _, result = fixture_run(tmp_path)
    result["native_summary"]["reservation_conflicts"] = 1
    write(folder/"final_result.json.gz", result)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "closed_cost_verified"
    assert row["physical"]["native_invariant_status"] == "violation_reported"
    assert row["physical"]["lifecycle_capacity_replay"]["status"] == "failed"
    assert row["strict_nonharm_certified"] is False


def test_distance_counts_actual_completed_empty_edges_and_retains_recovery_failures():
    data = {"edge_records": [[1, 2, 4., 2.]]}
    leg = "r:empty_return:1"
    result = {"physical_clock": 8000., "leg_identities": [{"transport_leg_id": leg, "kind": "empty_return"}],
        "trays": [{"mode": "quarantined"}], "native_summary": {},
        "receipts": [
            {"event": "EDGE_ENTER", "time": 7201., "traversal_id": 1, "tray_id": "T",
             "transport_leg_id": leg, "from": 1, "to": 2},
            {"event": "EDGE_EXIT", "time": 7203., "traversal_id": 1, "tray_id": "T",
             "transport_leg_id": leg, "from": 1, "to": 2},
            {"event": "LEG_FAILED", "time": 7300., "reason": "expired", "business_bag_id": ""},
            {"event": "EMPTY_RECOVERY_GRANTED", "time": 7301.},
            {"event": "RECOVERY_REJECTED", "time": 7302., "reason": "recover-1:generation_mismatch"},
        ]}
    row = audit._physical_diagnostics(data, result, None, audit.WINDOW)
    assert row["empty_completed_edge_distance"] == 4.
    assert row["failed_empty_legs"] == row["empty_recovery_grants"] == row["recovery_rejections"] == 1
    assert row["final_quarantined_trays"] == 1
    assert row["native_invariant_status"] == "unknown_missing_counter"
    assert row["recovery_rejection_reasons"] == {"generation_mismatch": 1}
    result["receipts"] = result["receipts"][1:]
    assert audit._physical_diagnostics(data, result, None, audit.WINDOW)["empty_completed_edge_distance"] is None


def test_transfer_retries_preserve_first_payload_and_issue_time():
    request = {"request_id": "r", "source": 1, "destination": 2}
    calls = [{"kind": "transfer", "at": 10., "retry": False, "request": request},
             {"kind": "transfer", "at": 20., "retry": True, "request": request}]
    assert audit._transfers_from_calls({"transfers": []}, calls) == [dict(request, issued_at=10.)]
    calls[1]["request"] = dict(request, destination=3)
    with pytest.raises(ValueError, match="retry_changed_transfer_payload"):
        audit._transfers_from_calls({"transfers": []}, calls)


def test_changed_binary_is_invalid_and_missing_binary_blocks_comparison(tmp_path):
    reference, _, _ = fixture_run(tmp_path)
    candidate, _, _ = fixture_run(tmp_path, "candidate")
    (tmp_path/"dummy_binary").write_bytes(b"CHANGED DUMMY BYTES")
    row = audit.audit_run(candidate, expected_population=7)
    assert row["audit_status"] == "invalid_evidence"
    assert "changed_provenance_file:binary" in row["errors"][0]
    (tmp_path/"dummy_binary").unlink()
    row = audit.audit_run(candidate, expected_population=7)
    assert row["audit_status"] == "closed_cost_verified"
    assert row["provenance"]["missing_files"] == ["binary"]
    assert audit.compare_runs(reference, candidate, expected_population=7)["status"] == (
        "unknown_missing_executable_or_manifest_provenance")


def test_closed_receipt_cannot_contradict_worker_status(tmp_path):
    folder, _, _ = fixture_run(tmp_path)
    receipt = audit.read(folder/"receipt.json")
    receipt["worker"]["status"] = "censored_budget_exhausted"
    write(folder/"receipt.json", receipt)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "invalid_evidence"
    assert "receipt_worker_status_binding" in row["errors"][0]


def test_censored_branch_cannot_retain_complete_cost_claim(tmp_path):
    folder, _, _ = fixture_run(tmp_path, status="censored_budget_exhausted", clock=8000.)
    evaluation = audit.read(folder/"evaluation.json")
    evaluation["cost"] = {"backlog_integral_bag_seconds": 0}
    write(folder/"evaluation.json", evaluation)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "invalid_evidence"
    assert "incomplete_branch_claimed_full_cost" in row["errors"][0]


def test_controls_are_streamed_and_not_opened_with_whole_json_read(tmp_path, monkeypatch):
    folder, _, _ = fixture_run(tmp_path)
    write(folder/"control_records.json.gz", [
        {"preparation_compute_ms": 1., "owner_decisions": [{"compute_ms": 2.}], "extra": "x"*4096}
        for _ in range(1000)])
    original_read = audit.read

    def guarded_read(path):
        assert str(path).split("/")[-1] != "control_records.json.gz"
        assert getattr(path, "name", "") != "control_records.json.gz"
        return original_read(path)

    monkeypatch.setattr(audit, "read", guarded_read)
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "closed_cost_verified"
    assert row["control"]["controller_ticks"] == 1000
    assert row["control"]["owner_decisions"] == 1000
    assert row["control"]["measured_controller_ms"] == 3000.
    assert row["control"]["control_records_read_mode"].startswith("single pass")


@pytest.mark.parametrize("damage", ["trailing_json", "truncated_gzip"])
def test_streamed_controls_must_be_consumed_through_json_and_gzip_closure(tmp_path, damage):
    folder, _, _ = fixture_run(tmp_path)
    path = folder/"control_records.json.gz"
    if damage == "trailing_json":
        path.write_bytes(gzip.compress(b'[{"preparation_compute_ms":1,"owner_decisions":[]}] trailing'))
    else:
        path.write_bytes(path.read_bytes()[:-4])
    row = audit.audit_run(folder, expected_population=7)
    assert row["audit_status"] == "invalid_evidence"
    assert row["full_window_cost"] is None


def test_one_pass_control_iterator_preserves_unknown_missing_fields():
    records = iter([{"preparation_compute_ms": 1., "owner_decisions": [{"compute_ms": 2.}]},
                    {"preparation_compute_ms": 3.}])
    row = audit._control_diagnostics(records, [], {})
    assert row["controller_ticks"] == 2
    assert row["owner_decisions"] is None
    assert row["measured_controller_ms"] is None


def _fixture_actor_source(folder, frozen, collector):
    files = {}
    for relative in audit.ACTOR_SOURCE_FILES:
        path = frozen/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Identical pure fixture actor bytes\n", encoding="utf-8")
        files[relative] = audit.sha(path)
    relative = "scripts/experiments/g31_ics_circulation/foundation_airport_inventory_spi_campaign.py"
    path = frozen/relative
    path.write_text(collector, encoding="utf-8")
    files[relative] = audit.sha(path)
    source = {"root": str(frozen), "files": files, "source_manifest_sha256": audit.digest(files)}
    reference = write(frozen/"source_manifest.json", source)
    plan = audit.read(folder/"plan.json")
    plan.update(source_bundle=reference, source_manifest_sha256=source["source_manifest_sha256"])
    plan_ref = write(folder/"plan.json", plan)
    receipt = audit.read(folder/"receipt.json")
    receipt["plan_sha256"] = plan_ref["sha256"]
    write(folder/"receipt.json", receipt)


def test_collector_difference_retains_physical_diagnostic_without_formal_gain(tmp_path):
    reference, _, _ = fixture_run(tmp_path)
    candidate, _, _ = fixture_run(tmp_path, "candidate", {
        "j0": 7310., "j1": 7390., "j2": 7500., "j4": 7700.})
    _fixture_actor_source(reference, tmp_path/"frozen001", "# Old collector\n")
    _fixture_actor_source(candidate, tmp_path/"frozen002", "# New collector\n")
    compared = audit.compare_runs(reference, candidate, expected_population=7)
    assert compared["status"] == "not_comparable_contract_mismatch"
    assert compared["advantage_bag_seconds"] is None
    assert compared["source_comparison"]["full_source_manifest_equal"] is False
    assert compared["source_comparison"]["fixed_actor_source_hashes_equal"] is True
    assert compared["source_comparison"]["different_source_paths"] == [
        "scripts/experiments/g31_ics_circulation/foundation_airport_inventory_spi_campaign.py"]
    assert compared["source_comparison"]["collector_change_semantically_neutral_proven"] is False
    diagnostic = compared["physical_cost_diagnostic"]
    assert diagnostic["reference_minus_candidate_J_bag_seconds"] == -100.
    assert diagnostic["completion_direction"]["population"] == 7
    assert diagnostic["formal_same_runtime_comparison"] is False
