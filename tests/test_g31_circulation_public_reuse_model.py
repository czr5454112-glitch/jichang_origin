"""Pure model mechanism/authority guards and independent all117 replay."""
from __future__ import annotations
import copy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import public_reuse_model as model

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014/reuse_v2_002"


def views(gate=6):
    with gzip.open(EVIDENCE / f"gate{gate}/old_route1_window1.json.gz", "rt") as stream:
        return json.load(stream)["seed_views"]


def bundle(gate=6, mutate=None, provenance="offline_source_authorized_capture", delivered_at=None):
    v = views(gate)
    if mutate: mutate(v)
    captures = tuple(model.Capture.from_view(v[o], identity="capture-" + o, provenance=provenance,
        delivered_at=delivered_at) for o in ("A", "B"))
    return model.assemble(model.public_contract(v["A"]), captures, model.START)


def test_capture_is_immutable_and_predictor_has_no_native_or_outcome_handle():
    v = views()
    capture = model.Capture.from_view(v["A"], identity="A", provenance="offline")
    stored = capture.payload_json
    v["A"]["jobs"][0]["storage_release_at"] = 100
    read = capture.read()
    read["jobs"][0]["storage_release_at"] = 100
    assert capture.payload_json == stored
    import inspect
    source = inspect.getsource(model)
    assert "load_native" not in source and "offline_diagnostics" not in source and "branch_ledger" not in source
    b = bundle()
    old = copy.deepcopy(b)
    p = model.predict(b, {"initial_next": 2, "departure": .11, "later_mode": "adaptive"})
    assert b == old and p["status"] == "conditional_prediction"
    assert p["native_feasibility_certified"] is False


def test_fabricated_native_provenance_never_certifies_actual_delivery():
    b = bundle(provenance="native_delivered_planning_contract", delivered_at=.11)
    assert b["declared_delivery_metadata_present"] is True
    assert b["online_information_delivered"] is False
    actions, incumbent = model.candidates_from_durations(b)
    proposal = model.propose(b, actions, incumbent)
    assert not proposal["online_executable"] and not proposal["native_protection_certified"]


@pytest.mark.parametrize("defect", ["missing_job", "future_observed", "future_capture", "past_capture", "inflight", "unexplained_lease", "future_delivery", "predelivery", "fault"])
def test_missing_stale_future_or_unobserved_state_fails_closed(defect):
    def change(v):
        if defect == "missing_job": v["A"]["jobs"].pop()
        elif defect == "future_observed": v["A"]["jobs"][0]["loaded_at"] = .12
        elif defect == "future_capture": v["A"]["now"] = .12
        elif defect == "past_capture": v["A"]["now"] = .06
        elif defect == "inflight": v["A"]["trays"][0]["edge_to"] = 1
        elif defect == "unexplained_lease": next(n for n in v["A"]["node_contracts"] if n["node"] == 1)["occupancy"] = 1
        elif defect == "fault": v["A"]["known_faults"] = [{"from": 0, "to": 1}]
    b = bundle(mutate=change, delivered_at=.12 if defect == "future_delivery" else .1 if defect == "predelivery" else None)
    assert b["status"] == "unknown"
    p = model.predict(b, {"initial_next": 1, "departure": .11, "later_mode": "adaptive"})
    assert p["status"] == "unknown_missing_input" and p["completion"] == {}


def test_missing_counterpart_and_forged_job_authority_are_unknown():
    v = views()
    c = model.Capture.from_view(v["A"], identity="A", provenance="offline")
    assert model.assemble(model.public_contract(v["A"]), (c,), .11)["status"] == "unknown"
    v["A"]["jobs"][0]["origin"] = 7
    c = model.Capture.from_view(v["A"], identity="A", provenance="offline")
    d = model.Capture.from_view(v["B"], identity="B", provenance="offline")
    assert "job_source_authority_mismatch" in model.assemble(model.public_contract(v["A"]), (c, d), .11)["reasons"]


@pytest.mark.parametrize("defect", ["export_denied", "receive_denied", "minimum_stock", "available_stock", "delayed_availability", "tray_authority"])
def test_unsupported_module_and_actual_stock_contracts_cannot_produce_protected_prediction(defect):
    v = views()
    contract = model.public_contract(v["A"])
    if defect == "export_denied": next(n for n in contract["node_contracts"] if n["node"] == 5)["allow_export"] = False
    elif defect == "receive_denied": next(n for n in contract["node_contracts"] if n["node"] == 1)["allow_receive"] = False
    elif defect == "minimum_stock": next(n for n in contract["node_contracts"] if n["node"] == 5)["export_min_stock"] = 1
    elif defect == "available_stock": next(n for n in v["B"]["node_contracts"] if n["node"] == 5)["actual_available"] = 0
    elif defect == "delayed_availability":
        v["B"]["trays"][0]["available_at"] = 1.
        next(n for n in v["B"]["node_contracts"] if n["node"] == 5)["actual_available"] = 0
    else:
        v["A"]["trays"], v["B"]["trays"] = v["B"]["trays"], v["A"]["trays"]
    captures = tuple(model.Capture.from_view(v[o], identity=o, provenance="offline") for o in ("A", "B"))
    b = model.assemble(contract, captures, .11)
    assert b["status"] == "unknown"
    actions, incumbent = model.candidates_from_durations(b)
    proposal = model.propose(b, actions, incumbent)
    assert proposal["selected_action"] is None
    assert not any(r["model_protected"] for r in proposal["candidates"])


def test_receiver_lease_applies_before_empty_physical_arrival_and_tie_is_e4():
    b = bundle()
    early = model.predict(b, {"initial_next": 1, "departure": 1.1, "later_mode": "adaptive"})
    after = model.predict(b, {"initial_next": 1, "departure": 1.101, "later_mode": "adaptive"})
    assert early["projected_rejections"] == 0
    assert after["projected_rejections"] > 0
    assert early["completion"]["loaded"] > after["completion"]["loaded"]
    assert any(w["reason"] == "receiving_full" for w in early["resource_waits"])


def test_physical_resource_and_service_model_not_freeflow():
    b = bundle()
    result = model.predict(b, {"initial_next": 2, "departure": .11, "later_mode": "adaptive"})
    assert any(w["tray"] == "E" and w["node"] == 1 and w["reason"] == "receiving_full" for w in result["resource_waits"])
    assert sum(r["event"] == "EMPTY_RECEIVED" and r["tray"] == "L" for r in result["physical_projection"]) == 2
    assert result["completion"]["reuse2"] > result["completion"]["reuse1"] > result["completion"]["loaded"] >= 6.
    closed = copy.deepcopy(b)
    next(e for e in closed["contract"]["edge_contracts"] if (e["from"], e["to"]) == (3, 4))["capacity"] = 0
    assert model.predict(closed, {"initial_next": 2, "departure": .11, "later_mode": "adaptive"})["status"] == "unknown_unfinished_projection"


def test_same_permitted_input_same_proposal_and_no_native_label_fit():
    b = bundle()
    actions, incumbent = model.candidates_from_durations(b)
    assert len(actions) == 35 and len({(a["initial_next"], a["departure"]) for a in actions}) == 35
    first = model.propose(b, actions, incumbent)
    unrelated_hidden_truth = {"gate": 999, "native_winner": "anything"}
    assert unrelated_hidden_truth and model.propose(copy.deepcopy(b), copy.deepcopy(actions), incumbent) == first
    assert first["selected_action"] == {"initial_next": 2, "departure": .11, "later_mode": "adaptive"}


def test_strict_model_protection_does_not_tolerate_a_positive_delta(monkeypatch):
    b = bundle()
    baseline = {j: 1. for j in b["jobs"]}
    def prediction(_bundle, action):
        c = baseline.copy()
        c["loaded"] += action["departure"]
        return {"status": "conditional_prediction", "completion": c, "completion_sum": sum(c.values())}
    monkeypatch.setattr(model, "predict", prediction)
    a = {"initial_next": 1, "departure": 1e-12}
    result = model.propose(b, [a], {"initial_next": 1, "departure": 0.})
    assert not result["candidates"][0]["model_protected"] and result["selected_action"] is None


def test_all117_saved_native_rows_are_in_validation_denominator():
    ledger = json.loads((EVIDENCE / "branch_ledger.json").read_text())
    bundles = {f"gate{g}": bundle(g) for g in (0, 6, 12)}
    baselines = {g: model.predict(b, {"initial_next": 1, "departure": 2.21, "later_mode": "adaptive"}) for g, b in bundles.items()}
    max_error, exact, matching_rejections, false_protection = 0., 0, 0, 0
    assert len(ledger) == 117
    for key, row in ledger.items():
        group = key.split("/")[0]
        with gzip.open(EVIDENCE / (key + ".json.gz"), "rt") as stream: raw = json.load(stream)
        action = {field: row[field] for field in ("initial_next", "departure", "later_mode")}
        p = model.predict(bundles[group], action)
        assert p["status"] == "conditional_prediction"
        delta = {j: p["completion"][j] - t for j, t in raw["summary"]["completion"].items()}
        max_error = max(max_error, *(abs(x) for x in delta.values()))
        exact += all(x == 0 for x in delta.values())
        matching_rejections += p["projected_rejections"] == raw["summary"]["recovered_rejection_count"]
        model_protected = all(t <= baselines[group]["completion"][j] for j, t in p["completion"].items())
        nativebase = ledger[group + "/old_route1_window1"]["summary"]["completion"]
        native_protected = all(t <= nativebase[j] for j, t in raw["summary"]["completion"].items())
        false_protection += model_protected and not native_protected
    assert exact == 105 and matching_rejections == 117 and false_protection == 0
    # This is an empirical diagnostic, explicitly not a protection tolerance.
    assert max_error == pytest.approx(.001)
