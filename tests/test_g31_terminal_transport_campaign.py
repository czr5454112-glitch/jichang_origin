"""Independent campaign accounting, fair-pair and receiver-claim regressions."""
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_control as flow
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import bound
from scripts.experiments.g31_ics_circulation.foundation_airport_transport_allocation import DEFAULT_CONFIG
from test_g31_terminal_transport_control import prepared
from test_g31_airport_joint_interface import two_sources


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf8") as stream:
            json.dump(value, stream)
    else:
        path.write_text(json.dumps(value), encoding="utf8")
    return bound(path)


def run_plan(tmp_path, method, *, input_hash="same-input", source_hash="same-source", ack="received",
             status="closed", cost=100., parent=2201, horizon=59400.):
    directory = tmp_path / method
    reference = save(directory / "plan.json", dict(task_id=method, method=method,
        parent=dict(parent_seed=parent, split="train" if parent == 2101 else "dev"), horizon=horizon,
        input=dict(path="input.json", sha256=input_hash),
        source_bundle=dict(path="source.json", sha256=source_hash),
        binary=dict(path="native.pyd", sha256="native030"),
        controller=dict(control_period=60., command_delay=2., routes=False),
        projection_horizon_seconds=600., supply_mode="committed_only", activation=7200.,
        mapping=dict(path="mapping.json", sha256="same-mapping"),
        transport_config=DEFAULT_CONFIG if method.startswith("TF") else None,
        forecast_horizon_seconds=1800.,
        demand_model=dict(path="demand-model.json", sha256="frozen-demand-model") if method == "TF-predictor" else None,
        recompute_period_seconds=300. if method.endswith("replan300") else 60.,
        forecast_bin_edges_seconds=list(range(0, 1801,
            300 if "300" in method or method == "TF-predictor" else 60))))
    worker = dict(scientific_status=status, cost={}, process_status="completed", final_physical_time=horizon)
    save(directory / "worker_report.json", worker)
    save(directory / "receipt.json", dict(plan_sha256=reference["sha256"],
        process=dict(exitcode=0 if status == "closed" else 1), worker=worker))
    if status == "closed":
        save(directory / "trajectory.json.gz", dict(system_J=cost, physical_clock=horizon,
            logs_complete=True, scientific_status="closed_finite_horizon", process_status="completed", rows=[dict(
            requested_action=dict(kind="transfer"), actual_submission=dict(request_id="req"),
            ack=[dict(status=ack)], received_event={} if ack == "received" else None,
            physical_failure=False)]))
    return reference


def block(tmp_path, refs):
    path = tmp_path / "block.json"
    save(path, dict(schema=campaign.SCHEMA, task_plans=refs))
    return path


@pytest.mark.parametrize("ack", ["departed", "in_transit"])
def test_later_delivered_ack_proves_acceptance_without_retained_initial_ack(tmp_path, ack):
    result = campaign.evaluate([block(tmp_path, [run_plan(tmp_path, "TF-current", ack=ack)])])
    row = result["runs"][0]
    assert row["submitted"] == 1
    assert row["accepted"] == 1
    assert row["received"] == 0


@pytest.mark.parametrize("difference", ["input_hash", "source_hash"])
def test_paired_gain_requires_same_frozen_physical_execution_contract(tmp_path, difference):
    refs = [run_plan(tmp_path, "C10"), run_plan(tmp_path, "TF-B1-60", **{difference: "different"})]
    result = campaign.evaluate([block(tmp_path, refs)])
    assert not any(row["method"] == "TF-B1-60" for row in result["paired"])


@pytest.mark.parametrize("variant,reference", [
    ("TF-B1-300", "TF-B1-60"),
    ("TF-B1-300-replan300", "TF-B1-300"),
    ("TF-predictor", "TF-B1-300"),
])
def test_bin_period_and_predictor_gains_compare_same_allocator(tmp_path, variant, reference):
    refs = [run_plan(tmp_path, "C10", cost=1000.),
            run_plan(tmp_path, reference, cost=200.), run_plan(tmp_path, variant, cost=150.)]
    result = campaign.evaluate([block(tmp_path, refs)])
    comparisons = [row for row in result["paired"] if row["method"] == variant]
    assert any(row["reference"] == reference and row["backlog_gain_bag_seconds"] == 50.
               for row in comparisons)


def test_failure_and_unstarted_denominators_remain_visible(tmp_path):
    failed = run_plan(tmp_path, "TF-current", status="unknown_missing_export")
    waiting = save(tmp_path / "TF-B1-60" / "plan.json", dict(
        task_id="waiting", method="TF-B1-60", parent=dict(parent_seed=2201), horizon=59400.))
    result = campaign.evaluate([block(tmp_path, [failed, waiting])])
    assert [row["status"] for row in result["runs"]] == ["unknown_missing_export", "not_started"]
    assert not result["all_registered_closed"]
    assert not result["paired"]


def test_empty_evaluation_is_not_a_complete_comparison_block():
    assert campaign.evaluate([])["all_registered_closed"] is False


def test_received_then_loaded_tray_does_not_leave_permanent_receiver_claim():
    current, catalog, projected = prepared(two_sources())
    destination = next(r["destination"] for r in catalog["candidates"] if r["action_type"] == "transfer")
    state = {}
    orders.ledger(state)["orders"]["past"] = dict(status="RECEIVED", request_id="req",
        physical_tray_id="already_loaded", destination_terminal=destination,
        received_at=projected.now-1., owner_scope=projected.owner)
    assert projected.nodes[destination]["inventory_as_of"] >= projected.now-1.
    assert orders.outstanding_uncredited(state, projected) == {}


def test_ordinary_fallback_respects_other_owner_pending_receiver_claims():
    current, catalog, projected = prepared(two_sources())
    state = {}
    book = orders.ledger(state)
    destinations = {r["destination"] for r in catalog["candidates"] if r["action_type"] == "transfer"}
    for destination in destinations:
        for number in range(current.contracts[destination]["capacity"]):
            identity = f"other-owner:{destination}:{number}"
            book["orders"][identity] = dict(status="SUBMITTED", request_id=identity,
                physical_tray_id=identity, destination_terminal=destination, owner_scope="other-owner")
    result = flow.TransportPolicy().select(current, catalog, projected,
        policy_state=state, decision_context=dict(tick=1))
    assert result["action_id"] == "a_noop"


@pytest.mark.parametrize("constraint", ["time", "evidence", "free_disk"])
def test_registration_reserves_resource_headroom_for_whole_comparison_block(tmp_path, monkeypatch, constraint):
    cycle = tmp_path / "cycle"
    source = tmp_path / "source.json"
    save(source, {})
    save(cycle / "training/mapping_fit_001/mapping.json", {})
    limits = dict(native_start_limit=160, allocations=dict(reserve=8),
        active_seconds_limit=172800., new_evidence_bytes_limit=40*1024**3,
        free_space_floor_bytes=30*1024**3)
    save(cycle / "campaign_budget.json", limits)
    state = dict(open_runners=[], unfinished_native_tasks=[], by_batch=dict(reserve=0), native_starts=10,
        active_seconds=0., evidence_bytes=0, free_bytes=100*1024**3)
    if constraint == "time":
        state["active_seconds"] = limits["active_seconds_limit"] - 720.
    elif constraint == "evidence":
        state["evidence_bytes"] = limits["new_evidence_bytes_limit"] - 128*1024**2
    else:
        state["free_bytes"] = limits["free_space_floor_bytes"] + 128*1024**2
    monkeypatch.setattr(campaign.campaign, "CYCLE", cycle)
    monkeypatch.setattr(campaign, "ROOT", cycle / "terminal_flow")
    monkeypatch.setattr(campaign.budget, "status", lambda _: state)
    attempts = []
    def native_prepare(*args, **kwargs):
        attempts.append((args, kwargs))
        raise AssertionError("preparing native plans before whole-block resource validation")
    monkeypatch.setattr(campaign.campaign, "prepare", native_prepare)
    with pytest.raises(ValueError, match="budget|time|disk|block|evidence"):
        campaign.prepare_block("limited", phase="gate", source=source)
    assert not attempts


def change_plan(reference, **updates):
    path = campaign.Path(reference["path"])
    plan = campaign.read(path)
    plan.update(updates)
    reference = save(path, plan)
    receipt = campaign.read(path.parent/"receipt.json")
    receipt["plan_sha256"] = reference["sha256"]
    save(path.parent/"receipt.json", receipt)
    return reference


@pytest.mark.parametrize("method,reference,mutation", [
    ("TF-B1-300", "TF-B1-60", {"recompute_period_seconds": 300.}),
    ("TF-B1-300-replan300", "TF-B1-300", {"forecast_bin_edges_seconds": list(range(0, 1801, 60))}),
    ("TF-predictor", "TF-B1-300", {"forecast_bin_edges_seconds": list(range(0, 1801, 60))}),
    ("TF-predictor", "TF-B1-300", {"recompute_period_seconds": 300.}),
    ("TF-B1-300", "TF-B1-60", {"demand_model": {"sha256": "hidden-predictor"}}),
])
def test_method_axis_cannot_hide_a_second_change(tmp_path, method, reference, mutation):
    baseline = run_plan(tmp_path, reference)
    candidate = change_plan(run_plan(tmp_path, method), **mutation)
    report = campaign.evaluate([block(tmp_path, [baseline, candidate])])
    assert not report["paired"]
    assert not report["all_registered_closed"]
    assert next(r for r in report["runs"] if r["method"] == method)["method_contract_errors"]


@pytest.mark.parametrize("method,reference,allowed", [
    ("TF-B1-300", "TF-B1-60", "forecast_bin_edges_seconds"),
    ("TF-B1-300-replan300", "TF-B1-300", "recompute_period_seconds"),
    ("TF-predictor", "TF-B1-300", "demand_model"),
])
def test_evaluation_records_exact_allowed_experiment_axis(tmp_path, method, reference, allowed):
    report = campaign.evaluate([block(tmp_path, [run_plan(tmp_path, reference), run_plan(tmp_path, method)])])
    paired = next(r for r in report["paired"] if r["method"] == method)
    assert paired["allowed_differences"] == [allowed]
    assert set(paired["observed_differences"]) == {allowed}
    assert all("forecast_bin_edges_seconds" in r["comparison_contract"]
        and "recompute_period_seconds" in r["comparison_contract"] for r in report["runs"])


def test_same_axis_pair_rejects_different_public_schedule_binding(tmp_path):
    baseline = change_plan(run_plan(tmp_path, "TF-B1-60"), forecast_binding={"sha256": "schedule-A"})
    candidate = change_plan(run_plan(tmp_path, "TF-B1-300"), forecast_binding={"sha256": "schedule-B"})
    report = campaign.evaluate([block(tmp_path, [baseline, candidate])])
    assert not report["paired"]
    assert any(r["reason"] == "comparison_contract_mismatch" for r in report["missing_pair_reasons"])


@pytest.mark.parametrize("failure", ["nonzero_exit", "wrong_plan_hash", "incomplete_clock", "missing_worker", "missing_trajectory"])
def test_scientific_closed_string_alone_does_not_unlock_dependency(tmp_path, failure):
    reference = run_plan(tmp_path, "TF-B1-60")
    directory = campaign.Path(reference["path"]).parent
    receipt = campaign.read(directory/"receipt.json")
    if failure == "nonzero_exit":
        receipt["process"]["exitcode"] = 1
    elif failure == "wrong_plan_hash":
        receipt["plan_sha256"] = "different"
    elif failure == "incomplete_clock":
        receipt["worker"]["final_physical_time"] = 18000.
        save(directory/"worker_report.json", receipt["worker"])
    elif failure == "missing_worker":
        (directory/"worker_report.json").unlink()
    else:
        (directory/"trajectory.json.gz").unlink()
    save(directory/"receipt.json", receipt)
    report = campaign.evaluate([block(tmp_path, [reference])])
    assert report["runs"][0]["status"] == "closed"
    assert not report["runs"][0]["closure_verified"]
    assert not report["all_registered_closed"]


def registered_block(tmp_path, phase, *, source_hash="same-source", dependencies=(), parents=None):
    parents = parents or ([2101] if phase in campaign.NATIVE_GATE_PHASES else [2201])
    refs = [run_plan(tmp_path/f"P{parent}", method, source_hash=source_hash, parent=parent,
                    horizon=18000. if phase in campaign.NATIVE_GATE_PHASES else 59400.)
            for parent in parents for method in campaign.METHODS[phase]]
    path = tmp_path/"block.json"
    save(path, dict(schema=campaign.SCHEMA, name=tmp_path.name, phase=phase, parents=parents,
        methods=list(campaign.METHODS[phase]), source_bundle=dict(path="source.json", sha256=source_hash),
        fixed_allocator=DEFAULT_CONFIG, task_plans=refs, dependencies=list(dependencies)))
    return path


@pytest.mark.parametrize("problem", ["missing", "wrong_source", "wrong_phase", "unfinished", "wrong_parent"])
def test_run_rechecks_dependency_phase_source_parent_and_closure_before_launch(tmp_path, monkeypatch, problem):
    phase = "bins" if problem == "wrong_parent" else "bridge"
    prior_phase = "bridge" if problem == "wrong_parent" else "bins" if problem == "wrong_phase" else "confirm"
    prior = registered_block(tmp_path/"prior", prior_phase,
        source_hash="different-source" if problem == "wrong_source" else "same-source",
        parents=[2202] if problem == "wrong_parent" else None)
    if problem == "unfinished":
        prior_data = campaign.read(prior)
        (campaign.Path(prior_data["task_plans"][0]["path"]).parent/"receipt.json").unlink()
    target = registered_block(tmp_path/"target", phase, dependencies=[] if problem == "missing" else [bound(prior)])
    launches = []
    monkeypatch.setattr(campaign.campaign, "launch", lambda directory: launches.append(directory))
    with pytest.raises(ValueError, match="dependency"):
        campaign.run_block(target)
    assert not launches


def test_same_source_closed_gate_satisfies_complete_bridge_preflight(tmp_path):
    prior = registered_block(tmp_path/"prior", "confirm")
    target = registered_block(tmp_path/"target", "bridge", dependencies=[bound(prior)])
    data = campaign.read(target)
    campaign._validate_block_manifest(data)
    campaign._validate_dependencies(data)


def test_individually_closed_parent_blocks_cover_combined_dependency(tmp_path):
    first = registered_block(tmp_path/"first", "bridge", parents=[2201])
    second = registered_block(tmp_path/"second", "bridge", parents=[2202])
    target = registered_block(tmp_path/"target", "bins", parents=[2201, 2202], dependencies=[bound(first), bound(second)])
    campaign._validate_dependencies(campaign.read(target))


def test_run_rejects_mixed_source_or_missing_methods_before_launch(tmp_path, monkeypatch):
    target = registered_block(tmp_path/"target", "bridge")
    data = campaign.read(target)
    data["task_plans"].pop()
    save(target, data)
    launches = []
    monkeypatch.setattr(campaign.campaign, "launch", lambda directory: launches.append(directory))
    with pytest.raises(ValueError, match="incomplete_registered"):
        campaign.run_block(target)
    assert not launches


def test_baseline_selection_uses_matching_frozen_contract_not_first_or_best_result(tmp_path):
    wrong = run_plan(tmp_path/"old", "TF-B1-60", source_hash="old-source", cost=9999.)
    matching = run_plan(tmp_path/"matching", "TF-B1-60", cost=200.)
    candidate = run_plan(tmp_path/"candidate", "TF-B1-300", cost=150.)
    report = campaign.evaluate([block(tmp_path, [wrong, matching, candidate])])
    pair = next(row for row in report["paired"] if row["method"] == "TF-B1-300")
    assert pair["backlog_gain_bag_seconds"] == 50.


@pytest.mark.parametrize("field", ["source_bundle", "input"])
def test_block_preflight_rejects_hidden_execution_input_change(tmp_path, field):
    path = registered_block(tmp_path/"target", "bridge")
    data = campaign.read(path)
    ref = data["task_plans"][-1]
    data["task_plans"][-1] = change_plan(ref, **{field: {"path": "different.json", "sha256": "different"}})
    with pytest.raises(ValueError, match="source|contract_mismatch"):
        campaign._validate_block_manifest(data)


def test_offline_granularity_rejects_TEST_before_loading_observations(tmp_path):
    ref = run_plan(tmp_path, "TF-B1-60")
    ref = change_plan(ref, parent={"parent_seed": 2301, "split": "test"})
    with pytest.raises(ValueError, match="closed_non_TEST_offline_source_required"):
        campaign.offline_granularity([campaign.Path(ref["path"]).parent])


def test_closed_export_gate_unlocks_only_same_source_full_bridge(tmp_path):
    prior = registered_block(tmp_path/"export", "export_gate")
    prior_data = campaign.read(prior)
    assert prior_data["methods"] == ["C00", "TF-B1-300"]
    campaign._validate_block_manifest(prior_data)
    assert campaign._dependency_phase("export_gate") is None
    target = registered_block(tmp_path/"bridge", "bridge", dependencies=[bound(prior)])
    campaign._validate_dependencies(campaign.read(target))
    mismatch = registered_block(tmp_path/"changed", "bridge", source_hash="another-source",
                                dependencies=[bound(prior)])
    with pytest.raises(ValueError, match="source_mismatch"):
        campaign._validate_dependencies(campaign.read(mismatch))


def test_export_gate_cannot_substitute_full_horizon_or_omit_one_method(tmp_path):
    path = registered_block(tmp_path/"export", "export_gate")
    data = campaign.read(path)
    data["task_plans"][0] = change_plan(data["task_plans"][0], horizon=59400.)
    with pytest.raises(ValueError, match="registered_phase_horizon"):
        campaign._validate_block_manifest(data)
    data["task_plans"] = data["task_plans"][1:]
    with pytest.raises(ValueError, match="incomplete_registered_comparison_block"):
        campaign._validate_block_manifest(data)


@pytest.mark.parametrize("bridge_used", [5, 19])
def test_export_gate_charges_existing_bridge_quota_without_reopening_reserve(tmp_path, monkeypatch, bridge_used):
    cycle = tmp_path/"cycle"
    source = tmp_path/"source.json"
    save(source, {})
    save(cycle/"training/mapping_fit_001/mapping.json", {})
    save(cycle/"campaign_budget.json", dict(native_start_limit=160,
        allocations=dict(reserve=8, bridge=20), active_seconds_limit=172800.,
        new_evidence_bytes_limit=40*1024**3, free_space_floor_bytes=30*1024**3))
    state = dict(open_runners=[], unfinished_native_tasks=[], by_batch=dict(reserve=8, bridge=bridge_used),
                 native_starts=32, active_seconds=0., evidence_bytes=0, free_bytes=100*1024**3)
    monkeypatch.setattr(campaign.campaign, "CYCLE", cycle)
    monkeypatch.setattr(campaign, "ROOT", cycle/"terminal_flow")
    monkeypatch.setattr(campaign.budget, "status", lambda _: state)
    ledger = []
    monkeypatch.setattr(campaign.budget, "append", lambda *args, **kwargs: ledger.append((args, kwargs)))
    attempts = []
    def prepare(identity, **options):
        attempts.append((identity, options))
        reference = run_plan(tmp_path/"runs", options["method"], parent=options["seed"],
                             horizon=options["horizon"])
        reference = change_plan(reference, task_id=identity, source_bundle=options["source_bundle"])
        return campaign.Path(reference["path"]).parent
    monkeypatch.setattr(campaign.campaign, "prepare", prepare)
    if bridge_used == 19:
        with pytest.raises(ValueError, match="whole_block_batch_budget"):
            campaign.prepare_block("export", phase="export_gate", source=source)
        assert attempts == [] and ledger == []
    else:
        result = campaign.prepare_block("export", phase="export_gate", source=source)
        assert result["batch"] == "bridge" and result["dependencies"] == []
        assert result["prior_budget"]["by_batch"]["reserve"] == 8
        assert len(attempts) == 2
        for identity, options in attempts:
            assert options["batch"] == "bridge" and options["horizon"] == 18000.
            assert options["soft_seconds"] == 660. and options["hard_seconds"] == 720.
        assert len(ledger) == 1
