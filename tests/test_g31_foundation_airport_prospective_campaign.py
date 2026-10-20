"""No native construction: prospective stream, admission and identity guards."""
from copy import deepcopy
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_prospective_campaign as campaign
from scripts.experiments.g31_ics_circulation.foundation_airport_prospective_control import make_prospective_planner
from test_g31_foundation_airport_pairs import fixture, PARENT


def test_stream_single_shared_current_is_complete_and_no_memory_retention(tmp_path):
    observation, baseline = fixture()
    sink = campaign.AuditStream(tmp_path/"audit.jsonl.gz")
    planner = make_prospective_planner(lambda *_a, **_kw: deepcopy(baseline), parent=PARENT,
        policy_id="frozen", information_variant="C01", activate_at=100., selector=lambda *_: 1.,
        record_sink=sink, retain_records=False, capture_all_callbacks=True)
    planner(observation, predictive=True)
    sink.close()
    assert planner.records == []
    records = list(campaign.read_audit(sink.path))
    assert records[0]["observation"] == observation
    assert len(records[0]["inference_rows"]) == 2
    assert all("observation" not in r for r in records[0]["inference_rows"])
    assert sink.report()["records"] == 1 and sink.index[0]["decision_differs"]
    assert records[0]["chosen_decision"]["intents"][1:] == baseline["intents"][1:]


def test_stream_detects_corrupted_or_missing_prior_record(tmp_path):
    path = tmp_path/"bad.jsonl.gz"
    with gzip.open(path, "wt") as stream:
        json.dump({"record_sha256": "x", "record": {"audit_sequence": 1,
            "previous_record_sha256": "0"*64}}, stream)
    with pytest.raises(ValueError, match="complete_stream_hash_chain"):
        list(campaign.read_audit(path))


def test_C00_warmup_and_current_use_same_timed_audit_without_forecast(tmp_path):
    observation, baseline = fixture()
    captured = []
    planner = make_prospective_planner(lambda *_a, **_kw: deepcopy(baseline), parent=PARENT,
        policy_id="C00", information_variant="C00", activate_at=101.,
        record_sink=lambda r: captured.append(deepcopy(r)), retain_records=False, capture_all_callbacks=True)
    assert planner(observation) == baseline
    observation["now"] = 101.
    assert planner(observation) == baseline
    assert [r["status"] for r in captured] == ["ordinary_warmup", "reference_rule"]
    assert all(r["planning_wall_ms"] >= 0. and "forecast_evidence" not in r for r in captured)


def test_no_model_freeze_only_allowed_for_development_rules(monkeypatch):
    assert campaign.validate_model_freeze(None, split="dev", information_variant="C10",
        training_domain=None, model_seed=None) is None
    from scripts.experiments.g31_ics_circulation import foundation_airport_pair_training_campaign as training
    def reject(*_a, **_kw):
        raise ValueError("all_requested_models")
    monkeypatch.setattr(training, "validate_frozen_manifest", reject)
    with pytest.raises(ValueError, match="all_requested_models"):
        campaign.validate_model_freeze(None, split="test", information_variant="C00",
            training_domain=None, model_seed=None)


def test_exact_grid_cell_cannot_change_parent_fleet_or_method():
    row = dict(name="E", batch="E", parent_seed=801, fleet=18, variant="C00",
        training_domain=None, model_seed=None)
    grid = dict(schema="g31.frozen_prospective_evaluation_grid.v1", test_opened=False,
        rows=[row], activate_at=7200., horizon=59400., cost_window=[7200., 59400.])
    options = dict(name="E", batch="E", seed=801, fleet=18, information_variant="C00",
        training_domain="primary_22", model_seed=17)
    campaign.validate_grid(grid, **options)
    with pytest.raises(ValueError, match="exact_registered"):
        campaign.validate_grid(grid, **{**options, "fleet": 26})


def test_execution_retains_rejection_and_binds_unique_real_empty_leg():
    index = [{"owner_id": "A", "observed_at": 100., "tray_id": "a", "decision_differs": True}]
    request = dict(owner_id="A", tray_id="a", request_id="q", source=10, destination=2,
        earliest_departure=102., message_delay=2.)
    index[0]["chosen_intent"] = {**request, "earliest_departure": 100.}
    calls = [{"kind": "transfer", "at": 100., "request": request, "reply": {"status": "pending"}}]
    leg = dict(kind="empty_return", transport_leg_id="q:empty_return:1", runtime_id=1, tray=0, job=-1)
    result = {"physical_clock": 130., "trays": [{"tray_id": "a"}],
        "leg_identities": [leg], "transfers": [{"request_id": "q", "tray": 0}], "receipts": [
        dict(event="LEG_START", time=102., transport_leg_id=leg["transport_leg_id"],
            tray_id="a", **{"from": 10, "to": 2}),
        dict(event="EDGE_ENTER", time=102., transport_leg_id=leg["transport_leg_id"], tray_id="a"),
        dict(event="EMPTY_RECEIVED", time=120., transport_leg_id=leg["transport_leg_id"]),
        dict(event="LOAD_START", time=121., tray_id="a", business_bag_id="bag")]}
    views = {"A": {"delivered_transfer_acks": [{"request_id": "q", "status": "granted",
        "observed_at": 102., "delivered_at": 102.2}]}}
    evidence = campaign.indexed_execution(index, result, calls, views)
    attempt = evidence["rows"][0]["attempts"][0]
    assert attempt["native_leg"] == leg and attempt["positive_delivered_ack"]
    assert attempt["selected_intent_matches_actual_submission"]
    assert evidence["different_decision_with_unique_leg"] == 1
    assert evidence["different_decision_with_complete_G1_chain"] == 1
    assert attempt["received_at"] == 120. and attempt["next_load"]["business_bag_id"] == "bag"
    rejected = campaign.indexed_execution(index, {"receipts": []}, calls,
        {"A": {"delivered_transfer_acks": [{"request_id": "q", "status": "rejected"}]}})
    assert len(rejected["rows"][0]["attempts"]) == 1
    assert rejected["rows"][0]["attempts"][0]["native_leg"] is None
    duplicate = deepcopy(result)
    duplicate["leg_identities"].append(leg)
    with pytest.raises(ValueError, match="unique_actual_empty_leg"):
        campaign.indexed_execution(index, duplicate, calls, views)
    wrong = deepcopy(result)
    wrong["receipts"][0]["to"] = 3
    assert campaign.indexed_execution(index, wrong, calls, views)["different_decision_with_unique_leg"] == 0


def test_test_model_freeze_precedes_any_test_input_read(tmp_path, monkeypatch):
    row = dict(name="D", batch="D", parent_seed=901, fleet=22, variant="C00",
        training_domain=None, model_seed=None)
    grid = dict(schema="g31.frozen_prospective_evaluation_grid.v1", test_opened=False,
        rows=[row], activate_at=7200., horizon=59400., cost_window=[7200., 59400.])
    path = tmp_path/"grid.json"
    campaign.common.write(path, grid)
    def forbidden(*_a, **_kw):
        raise AssertionError("test_input_was_opened")
    def reject(*_a, **_kw):
        raise ValueError("all_models_must_be_frozen")
    monkeypatch.setattr(campaign.common, "parent_input", forbidden)
    monkeypatch.setattr(campaign, "validate_model_freeze", reject)
    with pytest.raises(ValueError, match="all_models_must_be_frozen"):
        campaign.prepare("D", "unused", seed=901, fleet=22, information_variant="C00",
            batch="D", rule_freeze=None, grid_freeze=campaign.bound(path))


def test_worker_censored_adapter_preserves_raw_prefix_and_unknown_cost_without_native(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from collections import Counter
    from scripts.experiments.g31_ics_circulation import native_host, foundation_airport_protocol_v2 as protocol
    observation, baseline = fixture()
    observation["now"] = 7200.
    data = {"jobs": [{"business_bag_id": "bag", "arrival": 0.}],
        "node_contracts": [{"resource_owner": "A"}]}
    input_path = tmp_path/"input.json"
    campaign.common.write(input_path, data)
    plan = dict(output=str(tmp_path), input={**campaign.bound(input_path), "semantic_sha256": campaign.digest(data)}, forecast_binding=None,
        binary={"path": "must_never_be_loaded"}, selected_model=None, parent=PARENT,
        activate_at=7200., information_variant="C00", rule_freeze={"sha256": "r"},
        event_budget=100, planner_identity=campaign.IDENTITY, soft_seconds=600, controller={},
        horizon=59400., cost_window=[7200., 59400.])
    path = tmp_path/"plan.json"
    campaign.common.write(path, plan)
    class FakeSession:
        physical_time = 0.
        def __init__(self, _data):
            pass
        def offline_state_sha256(self):
            return "a"*64
        def observe_protocol(self, _owner):
            return {"delivered_transfer_acks": []}
    monkeypatch.setattr(native_host, "load_native", lambda path: SimpleNamespace(NativeSession=FakeSession))
    monkeypatch.setattr(campaign, "verify", lambda _plan: None)
    class FakePlanner:
        counts = Counter()
        def __call__(self, *_a, **_kw):
            return baseline
        def report(self):
            return {"counts": {}}
    monkeypatch.setattr(campaign, "make_prospective_planner", lambda **_kw: FakePlanner())
    def fake_run(session, _owners, **options):
        session.physical_time = 7200.
        options["precommit_observer"](observation=observation, decision=baseline,
            controller_state={"tick": 120}, client_state={"outbox": {}}, session=session)
        return {"controller_state": {}, "client_calls": [], "status": "soft_deadline",
            "result": {"physical_clock": 7200., "jobs": [{"business_bag_id": "bag",
                "status": "waiting_for_tray"}], "trays": [], "receipts": []}}
    monkeypatch.setattr(protocol, "run_airport_bounded_protocol_control", fake_run)
    report = campaign.worker(path, campaign.common.sha(path))
    assert report["status"] == "censored_soft_deadline" and report["cost"] is None
    assert (tmp_path/"activation_prefix.json.gz").exists()
    assert (tmp_path/"client_calls.json.gz").exists()
    assert campaign.common.read(tmp_path/"actual_plan_preload_receipts.json") == {}
    assert campaign.common.read(tmp_path/"evaluation.json")["cost"] is None
