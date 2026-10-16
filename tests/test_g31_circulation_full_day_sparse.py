from copy import deepcopy
import json
from types import SimpleNamespace
import weakref

import pytest

from scripts.experiments.g31_ics_circulation import full_day_sparse as sparse


@pytest.fixture
def args(tmp_path):
    binary = tmp_path / "native.pyd"
    binary.write_bytes(b"pinned-test-binary-never-loaded")
    output = tmp_path / "output"
    output.mkdir()
    return SimpleNamespace(binary=binary, expected_binary_sha256=sparse.shared.sha(binary),
        suite="synthetic", horizon=4., segment_seconds=2., event_budget=10,
        max_activations=100, activation_shard_budget=5, hard_timeout=30., output=output)


@pytest.mark.parametrize("field,value", [("suite", "full3x"), ("horizon", float("nan")),
    ("horizon", 0.), ("segment_seconds", -1.), ("event_budget", 0), ("max_activations", True),
    ("activation_shard_budget", 1.5), ("hard_timeout", 7201.), ("hard_timeout", float("inf")),
    ("expected_binary_sha256", "0" * 64)])
def test_sparse_bad_scope_fails_before_native(args, field, value):
    setattr(args, field, value)
    with pytest.raises(ValueError):
        sparse.validate_args(args)


def test_synthetic_input_and_joint_policy_are_exact_old_contract(args):
    data, owners, config = sparse.prepare_input(args)
    _, expected, expected_owners = sparse.streaming.scenarios()[1]
    expected["owner_notifications"] = {"enabled": True}
    assert data == expected and owners == expected_owners
    assert config == dict(control_period=.5, command_delay=.01, publication_delay=.02,
        retry_period=.5, lease_seconds=120., compact=True, routes=True, forecasts=True,
        predictive=True, prebalance=True)


def test_full_two_x_all_input_matches_independent_provenance(args):
    args.suite, args.horizon, args.event_budget = "full2x", 86400., 1000000
    data, owners, config = sparse.prepare_input(args)
    assert len(data["jobs"]) == 57012
    result = sparse.shared.verify_input_provenance(args.output, data,
        {"command": ["--suite", "full2x", "--horizon", "86400", "--event-budget", "1000000"]}, 57012, 86400.)
    assert result["suite"] == "full2x" and result["new_native_executions"] == 0
    assert owners == sorted({row.get("resource_owner", row["zone"]) for row in data["node_contracts"]})
    assert config["command_delay"] == 2. and config["retry_period"] == 60.


def run_fake(args, monkeypatch, statuses):
    session = SimpleNamespace(physical_time=0.)
    calls, seals, owner_refs = [], [], []
    data = {"jobs": [{"business_bag_id": "one", "arrival": 0.}]}
    config = dict(control_period=1., routes=True, forecasts=True)
    monkeypatch.setattr(sparse, "prepare_input", lambda a: (deepcopy(data), ["A", "B"], dict(config)))
    monkeypatch.setattr(sparse.shared, "load_native", lambda binary: SimpleNamespace(NativeSession=lambda d: session))
    def seal():
        seals.append(session.physical_time)
        return "a" * 64
    session.offline_state_sha256 = seal
    class Record(dict):
        pass
    def controller(actual, owners, **kwargs):
        assert actual is session and owners == ["A", "B"]
        assert kwargs["event_budget"] == args.event_budget and kwargs["_consume_state"] is True
        if owner_refs:
            assert owner_refs[-1]() is None, "Previous raw owner record leaked into next activation shard"
        index = len(calls)
        calls.append(deepcopy(kwargs))
        status, physical, count = statuses[index]
        session.physical_time = physical
        pending = status == "control_budget_exhausted"
        state = {"client": {"outbox": {}}, "pending_owners": ["B"] if pending else [],
            "needs_native_drain": pending, "native_timestamp_complete": not pending,
            "pending_causes": {"B": {"timer": True}} if pending else {}}
        records = [Record(trace_sequence=i, at=physical) for i in range(count)]
        if records:
            owner_refs.append(weakref.ref(records[0]))
        return {"status": status, "result": None, "controller_state": state,
            "control_records": records, "native_batches": [{"trace_sequence": count, "start_at": physical, "end_at": physical}],
            "client_calls": [{"kind": "test", "at": physical}], "control_continuation": {
                "status": status, "physical_time": physical, "requested_horizon": kwargs["horizon"]}, "wall_seconds": .001}
    monkeypatch.setattr(sparse.shared, "run_event_protocol_control", controller)
    assert sparse.worker(args) == 0
    parts = [sparse.shared.read_gz(path) for path in sorted((args.output / "segments").glob("*.json.gz"))]
    summary = json.loads((args.output / "summary.json").read_bytes())
    manifest = json.loads((args.output / "run_shards.json").read_bytes())
    for index, part in enumerate(parts):
        hash_row = json.loads((args.output / "segment_hashes" / f"{index:04d}.json").read_bytes())
        assert sparse.shared.sha(args.output / hash_row["path"]) == hash_row["sha256"]
    return calls, seals, parts, summary, manifest


def test_pending_round_keeps_target_then_crosses_hour_and_never_drops_raw(args, monkeypatch):
    calls, seals, parts, summary, manifest = run_fake(args, monkeypatch,
        [("control_budget_exhausted", 1., 5), ("reached", 2., 2), ("control_budget_exhausted", 3., 5),
         ("native_budget_exhausted", 3., 0)])
    assert [call["horizon"] for call in calls] == [2., 2., 4., 4.]
    assert calls[0]["state"] is None
    assert calls[1]["state"]["pending_owners"] == ["B"] and calls[1]["state"]["needs_native_drain"]
    assert seals == [2., 3.]
    assert ["native_state_sha256" in part for part in parts] == [False, True, False, True]
    sequences = [row["trace_sequence"] for part in parts for key in ("control_records", "native_batches") for row in part[key]]
    assert sequences == list(range(16))
    assert manifest["counts"] == {"control_records": 12, "native_batches": 4, "client_calls": 4}
    assert summary["owner_activations"] == 12 and summary["status"] == "native_budget_exhausted"
    assert summary["native_state_sha256"] == "a" * 64 and summary["retain_trace_in_memory"] is False
    assert summary["complete_100ms_requirement_certified"] is False


@pytest.mark.parametrize("last_status,physical", [("control_budget_exhausted", 1.), ("reached", 2.)])
def test_owner_limit_always_seals_final_cut_and_keeps_budget_denominator(args, monkeypatch, last_status, physical):
    args.max_activations = 7
    calls, seals, parts, summary, manifest = run_fake(args, monkeypatch,
        [("control_budget_exhausted", 1., 5), (last_status, physical, 2)])
    assert [call["max_activations"] for call in calls] == [5, 2]
    assert seals == [physical] and summary["owner_activations"] == 7
    assert summary["status"] == "control_budget_exhausted" and parts[-1]["status"] == last_status
    assert manifest["counts"]["control_records"] == 7


def test_horizon_final_is_sealed_even_with_remaining_owner_budget(args, monkeypatch):
    args.horizon = 2.
    _, seals, parts, summary, _ = run_fake(args, monkeypatch, [("reached", 2., 1)])
    assert seals == [2.] and summary["status"] == "reached" and "native_state_sha256" in parts[-1]


def test_native_failure_keeps_published_raw_prefix_without_fabricating_final_seal(args, monkeypatch):
    calls = []
    session = SimpleNamespace(physical_time=1.)
    monkeypatch.setattr(sparse, "prepare_input", lambda a: ({"jobs": []}, ["A"], {}))
    monkeypatch.setattr(sparse.shared, "load_native", lambda binary: SimpleNamespace(NativeSession=lambda d: session))
    def failed(*a, **kw):
        if calls:
            raise RuntimeError("native error")
        calls.append(True)
        return {"status": "control_budget_exhausted", "result": None,
            "controller_state": {"client": {"outbox": {}}}, "control_records": [{"trace_sequence": 0}],
            "native_batches": [], "client_calls": [], "control_continuation": {"physical_time": 1., "requested_horizon": 2.}}
    monkeypatch.setattr(sparse.shared, "run_event_protocol_control", failed)
    with pytest.raises(RuntimeError, match="native error"):
        sparse.worker(args)
    part = sparse.shared.read_gz(args.output / "segments/0000.json.gz")
    assert "native_state_sha256" not in part and not (args.output / "summary.json").exists()
    assert json.loads((args.output / "heartbeat.json").read_bytes())["latest_native_seal"] is None


def test_sparse_gate_only_omits_root_seal_on_unsealed_intermediate_cut():
    from scripts.experiments.g31_ics_circulation.validate_full_day_sparse import compare_part
    part = {"status": "control_budget_exhausted", "control_continuation": {"physical_time": 1.},
        "client_calls": [{"request": {"native_state_sha256": "payload-must-stay", "at": 1.}, "submit_compute_ms": 2.}],
        "controller_state": {"pending_owners": ["B"]}}
    reference = deepcopy(part)
    reference.update(native_state_sha256="a" * 64, diagnostic_seal_wall_ms=2.)
    reference["client_calls"][0]["submit_compute_ms"] = 1.
    assert compare_part(part, reference, 5, 100, 4.)["native_seal_compared"] is False
    part["client_calls"][0]["request"]["native_state_sha256"] = "changed"
    with pytest.raises(ValueError, match="ordered_raw_changed"):
        compare_part(part, reference, 5, 100, 4.)


@pytest.mark.parametrize("defect", ["missing_seal", "wrong_seal", "request", "controller_state", "physical_time", "ordering"])
def test_sparse_gate_does_not_weaken_final_semantics(defect):
    from scripts.experiments.g31_ics_circulation.validate_full_day_sparse import compare_part
    part = {"status": "reached", "control_continuation": {"physical_time": 2.}, "native_state_sha256": "a" * 64,
        "client_calls": [{"request": {"id": "one", "at": 2.}}], "controller_state": {"first": 1, "second": 2}}
    reference = deepcopy(part)
    if defect == "missing_seal": del part["native_state_sha256"]
    elif defect == "wrong_seal": part["native_state_sha256"] = "b" * 64
    elif defect == "request": part["client_calls"][0]["request"]["at"] = 1.
    elif defect == "controller_state": part["controller_state"]["second"] = 3
    elif defect == "physical_time": part["control_continuation"]["physical_time"] = 1.
    else: part["controller_state"] = {"second": 2, "first": 1}
    with pytest.raises(ValueError):
        compare_part(part, reference, 5, 100, 4.)
