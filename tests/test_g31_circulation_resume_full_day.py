"""Pure pinning, continuation, seal-gate and failure tests; no native extension."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from scripts.experiments.g31_ics_circulation import resume_full_day as resume


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def source(tmp_path, monkeypatch):
    root, source = tmp_path / "root", tmp_path / "source"
    root.mkdir(); source.mkdir()
    monkeypatch.setattr(resume, "ROOT", root)
    pins = {}
    for name in resume.REQUIRED_POLICY:
        relative = "policy/" + name
        path = root / relative; path.parent.mkdir(exist_ok=True)
        path.write_text(name, encoding="utf-8")
        archived = source / "source_archive" / relative
        archived.parent.mkdir(parents=True, exist_ok=True); archived.write_bytes(path.read_bytes())
        pins[relative] = resume.sha(path)
    binary = root / "native.pyd"; binary.write_bytes(b"not a native extension")
    config = {"owners": ["A", "B"], "control_period": 1.}
    state = {"config": config, "native_timestamp_complete": True,
        "pending_owners": ["B"], "pending_causes": {"B": {"tick": 1}}, "needs_native_drain": True,
        "client": {"outbox": {}}}
    part = {"status": "control_budget_exhausted", "result": None, "controller_state": state,
        "control_records": [], "native_batches": [{"trace_sequence": 0, "start_at": 0., "end_at": 1.}],
        "client_calls": [], "wall_seconds": .1, "native_state_sha256": "a" * 64,
        "diagnostic_seal_wall_ms": 5., "control_continuation": {"status": "control_budget_exhausted",
            "physical_time": 1., "requested_horizon": 2.}}
    (source / "segments").mkdir()
    resume.streaming.gz(source / "segments/0000.json.gz", part)
    resume.streaming.gz(source / "input.json.gz", {"jobs": [{"business_bag_id": "one"}], "unchanged": True})
    receipt = {"schema": "g31.lt2.profile_worker.v1", "status": "failed", "source_before": pins,
        "source_changed": [], "binary_sha256": resume.sha(binary), "command": ["python", "-m", "source",
            "--suite", "synthetic", "--horizon", "4", "--segment-seconds", "2", "--event-budget", "10",
            "--max-activations", "100", "--activation-shard-budget", "5", "--binary", str(binary),
            "--expected-binary-sha256", resume.sha(binary)]}
    heartbeat = {"stage": "segment_saved", "segment": 0, "status": part["status"], "physical_time": 1.,
        "owner_activations": 0, "offered_total": 1, "controller_wall_seconds": .15,
        "diagnostic_export_wall_seconds": .02, "diagnostic_seal_wall_seconds": .005}
    write(source / "receipt.json", receipt); write(source / "heartbeat.json", heartbeat)
    monkeypatch.setattr(resume, "verify_input_provenance", lambda directory, data, actual, total, horizon:
        {"scope": "independent-provenance-hook-called", "total": total, "horizon": horizon})
    return SimpleNamespace(root=root, source=source, part=part, receipt=receipt, heartbeat=heartbeat,
        binary=binary, output=tmp_path / "cut")


def prepare(source):
    cut = resume.prepare_cut(source.source, source.output)
    path = source.output / "cut_manifest.json"
    return cut, path, resume.sha(path)


def test_prepare_pins_published_cut_and_preserves_same_timestamp_owner_round(source):
    cut, path, pin = prepare(source)
    assert cut["next_target"] == 2. and cut["owner_activations"] == 0
    assert cut["provenance"]["scope"] == "independent-provenance-hook-called"
    assert resume.validate_cut(path, pin) == cut
    assert resume.read_gz(source.source / "segments/0000.json.gz") == source.part
    assert json.loads((source.source / "heartbeat.json").read_bytes()) == source.heartbeat


def test_source_parent_receipt_can_finalize_after_snapshot_without_rewriting_pin(source):
    cut, path, pin = prepare(source)
    write(source.source / "receipt.json", {**source.receipt, "status": "failed", "wall_seconds": 15.})
    assert resume.validate_cut(path, pin) == cut


@pytest.mark.parametrize("defect", ["no_heartbeat", "no_seal", "wrong_physical", "missing_prefix", "bad_binary",
    "live_policy", "archive_policy", "scope", "budget", "finished", "owner_budget", "source_changed"])
def test_prepare_rejects_invalid_prefix_before_any_native_session(source, defect):
    if defect == "no_heartbeat":
        write(source.source / "heartbeat.json", {**source.heartbeat, "stage": "worker_finished"})
    elif defect in {"no_seal", "wrong_physical"}:
        part = deepcopy(source.part)
        if defect == "no_seal": part.pop("native_state_sha256")
        else: part["control_continuation"]["physical_time"] = .5
        resume.streaming.gz(source.source / "segments/0000.json.gz", part)
    elif defect == "missing_prefix": (source.source / "segments/0000.json.gz").unlink()
    elif defect == "bad_binary": source.binary.write_bytes(b"changed")
    elif defect == "live_policy": (source.root / "policy/analytic_control.py").write_text("changed")
    elif defect == "archive_policy": (source.source / "source_archive/policy/analytic_control.py").write_text("changed")
    elif defect in {"finished", "owner_budget"}:
        hb = deepcopy(source.heartbeat)
        hb["physical_time" if defect == "finished" else "owner_activations"] = 4 if defect == "finished" else 100
        write(source.source / "heartbeat.json", hb)
    else:
        receipt = deepcopy(source.receipt)
        if defect == "source_changed": receipt["source_changed"] = ["x"]
        else:
            key = "--suite" if defect == "scope" else "--event-budget"
            receipt["command"][receipt["command"].index(key) + 1] = "unknown" if defect == "scope" else "0"
        write(source.source / "receipt.json", receipt)
    with pytest.raises((ValueError, FileNotFoundError)):
        prepare(source)


@pytest.mark.parametrize("field,value", [("event_budget", 11), ("horizon", 5.), ("max_activations", 101),
    ("activation_shard_budget", 6), ("segment_seconds", 3.), ("suite", "full2x"),
    ("known_native_seal", "b" * 64), ("next_target", 4.), ("physical_time", 2.),
    ("owner_activations", 1), ("offered_total", 2), ("cut_controller_state_sha256", "c" * 64)])
def test_rebound_manifest_hash_does_not_authorize_changed_source_contract(source, field, value):
    cut, path, _ = prepare(source)
    cut[field] = value; write(path, cut)
    with pytest.raises(ValueError):
        resume.validate_cut(path, resume.sha(path))


@pytest.mark.parametrize("defect", ["hash", "order", "traversal", "file", "receipt", "cost"])
def test_prefix_integrity_and_metadata_fail_closed(source, defect):
    cut, path, pin = prepare(source)
    if defect == "hash": write(path, {**cut, "extra": True})
    elif defect == "file": (source.source / "segments/0000.json.gz").write_bytes(b"changed")
    elif defect == "receipt": (source.output / "source_receipt_snapshot.json").write_text("{}")
    else:
        if defect == "order": cut["shards"].append(cut["shards"][0])
        elif defect == "traversal": cut["shards"][0]["path"] = "../segments/0000.json.gz"
        else: cut["prior_costs"]["controller_wall_seconds"] = .01
        write(path, cut); pin = resume.sha(path)
    with pytest.raises((ValueError, FileNotFoundError)):
        resume.validate_cut(path, pin)


def test_reached_target_advances_only_after_complete_timestamp():
    part = {"status": "reached", "control_continuation": {"status": "reached", "requested_horizon": 2., "physical_time": 2.},
        "controller_state": {"native_timestamp_complete": True, "pending_owners": [], "pending_causes": {}, "needs_native_drain": False}}
    assert resume.next_target(part, 5., 2.) == 4.
    for key, value in (("native_timestamp_complete", False), ("pending_owners", ["A"]),
                       ("pending_causes", {"A": {}}), ("needs_native_drain", True)):
        broken = deepcopy(part); broken["controller_state"][key] = value
        with pytest.raises(ValueError, match="incomplete_reached"):
            resume.next_target(broken, 5., 2.)


@pytest.mark.parametrize("status,count,physical,wanted", [("control_budget_exhausted", 5, 1., False),
    ("control_budget_exhausted", 10, 1., True), ("reached", 5, 2., True),
    ("native_budget_exhausted", 5, 1., True), ("control_budget_exhausted", 5, 4., True)])
def test_seal_schedule_never_skips_normal_exit_or_completed_horizon(status, count, physical, wanted):
    part = {"status": status, "control_continuation": {"physical_time": physical}}
    assert resume.should_seal(part, count, 10, 4.) is wanted


@pytest.mark.parametrize("field,value", [("source_worker_stopped", False), ("unchanged_policy", False),
    ("cut_manifest_sha256", "b" * 64), ("schema", "unknown")])
def test_actual_stop_attestation_required(tmp_path, field, value):
    receipt = {"schema": "g31.full_day_resume_stop.v1", "source_worker_stopped": True,
        "unchanged_policy": True, "cut_manifest_sha256": "a" * 64}
    receipt[field] = value
    path = tmp_path / "stop.json"; write(path, receipt)
    with pytest.raises(ValueError, match="source_worker_not_confirmed"):
        resume.validate_stop(path, resume.sha(path), "a" * 64)


def test_known_seal_gate_precedes_session_release_and_original_state_return(source, tmp_path):
    cut, _, _ = prepare(source)
    events = []
    session = SimpleNamespace()
    factory = lambda path: SimpleNamespace(NativeSession=lambda data: session)
    class Reconstructor:
        def __init__(self, actual, event_budget): assert actual is session and event_budget == 10
        def replay_part(self, part): events.append("replay"); return {}
        def finish(self, seal):
            assert seal == "a" * 64; events.append("verified")
            return {"owners": 0, "parts": 1, "physical_time": 1., "trace_records": 1}
        def verified_session(self):
            assert events == ["replay", "verified"]; events.append("released"); return session
    output = tmp_path / "run"; output.mkdir()
    actual, part, segments, report, data = resume.reconstruct(cut, output, factory, Reconstructor)
    assert actual is session and part == source.part and events[-1] == "released"
    assert segments[-1]["cumulative_control_wall_seconds"] == .15
    assert report["prefix_outer_wrapper_residual_seconds"] == pytest.approx(.05)
    assert resume.sha(output / "segments/0000.json.gz") == cut["shards"][0]["sha256"]


def test_failed_seal_cannot_release_reconstructed_session(source, tmp_path):
    cut, _, _ = prepare(source)
    factory = lambda path: SimpleNamespace(NativeSession=lambda data: object())
    class Reconstructor:
        def __init__(self, *args, **kwargs): pass
        def replay_part(self, part): return {}
        def finish(self, seal): raise ValueError("native_seal_mismatch")
        def verified_session(self): pytest.fail("unverified native state escaped")
    output = tmp_path / "run"; output.mkdir()
    with pytest.raises(ValueError, match="native_seal_mismatch"):
        resume.reconstruct(cut, output, factory, Reconstructor)


def test_failed_independent_verifier_replaces_success_receipt(tmp_path):
    receipt = {"status": "completed", "exit_code": 0, "source_changed": []}
    write(tmp_path / "receipt.json", receipt)
    write(tmp_path / "summary.json", {"status": "reached", "physical_time": 4.})
    def invalid(*args): raise ValueError("business row missing")
    with pytest.raises(ValueError, match="business row missing"):
        resume.finalize_verification(tmp_path, receipt, {"horizon": 4., "offered_total": 1}, invalid)
    actual = json.loads((tmp_path / "receipt.json").read_bytes())
    assert actual["status"] == "failed_independent_full_day_verification" and actual["exit_code"] == 2


def test_worker_keeps_call_arguments_pending_round_trace_and_all_new_hashes(source, tmp_path, monkeypatch):
    cut, path, pin = prepare(source)
    stopped = tmp_path / "stop.json"
    write(stopped, {"schema": "g31.full_day_resume_stop.v1", "source_worker_stopped": True,
                   "unchanged_policy": True, "cut_manifest_sha256": pin})
    output = tmp_path / "continued"; output.mkdir()
    session = SimpleNamespace(physical_time=1.)
    seals, calls = [], []
    def seal(): seals.append(session.physical_time); return "a" * 64
    session.offline_state_sha256 = seal
    def reconstructed(actual_cut, actual_output):
        assert actual_cut == cut and actual_output == output
        (output / "segments").mkdir()
        (output / "segments/0000.json.gz").write_bytes((source.source / "segments/0000.json.gz").read_bytes())
        return session, deepcopy(source.part), [{"horizon": 2., "physical_time": 1.,
            "status": source.part["status"], "cumulative_control_wall_seconds": .15}], {
                "owners": 0, "trace_records": 1, "status": "verified_against_known_native_seal"}, {
                    "jobs": [{"business_bag_id": "one", "arrival": 0.}]}
    monkeypatch.setattr(resume, "reconstruct", reconstructed)
    def controller(actual_session, owners, **kwargs):
        assert actual_session is session and owners == ["A", "B"]
        assert kwargs["horizon"] == 2. and kwargs["event_budget"] == 10 and kwargs["max_activations"] == 5
        assert kwargs["_consume_state"] is True and kwargs["control_period"] == 1.
        assert kwargs["state"]["pending_owners"] == ["B"] and kwargs["state"]["needs_native_drain"]
        calls.append(deepcopy(kwargs))
        first = len(calls) == 1
        status = "control_budget_exhausted" if first else "native_budget_exhausted"
        return {"status": status, "result": None, "controller_state": kwargs["state"],
            "control_records": [{"trace_sequence": 0, "at": 1.}] if first else [],
            "native_batches": [{"trace_sequence": 1 if first else 0, "start_at": 1., "end_at": 1.}],
            "client_calls": [], "control_continuation": {"status": status, "physical_time": 1., "requested_horizon": 2.},
            "wall_seconds": .001}
    monkeypatch.setattr(resume, "run_event_protocol_control", controller)
    args = SimpleNamespace(cut_manifest=path, expected_cut_sha256=pin, stop_receipt=stopped,
        expected_stop_sha256=resume.sha(stopped), output=output, binary=source.binary, suite="synthetic",
        horizon=4., event_budget=10)
    assert resume.worker(args) == 0
    assert len(calls) == 2 and seals == [1.]
    first, last = [resume.read_gz(output / "segments" / f"{i:04d}.json.gz") for i in (1, 2)]
    assert "native_state_sha256" not in first and last["native_state_sha256"] == "a" * 64
    assert first["control_records"][0]["trace_sequence"] == 1
    assert first["native_batches"][0]["trace_sequence"] == 2 and last["native_batches"][0]["trace_sequence"] == 3
    for index in (1, 2):
        saved = json.loads((output / "segment_hashes" / f"{index:04d}.json").read_bytes())
        assert saved["sha256"] == resume.sha(output / saved["path"])
    summary = json.loads((output / "summary.json").read_bytes())
    assert summary["owner_activations"] == 1 and summary["status"] == "native_budget_exhausted"
    assert summary["prior_costs"] == cut["prior_costs"] and summary["wall_seconds"] >= .15


def test_native_gate_ignores_only_existing_top_level_submit_wall_diagnostic():
    from scripts.experiments.g31_ics_circulation.validate_resume_full_day import encoded
    original = {"client_calls": [{"submit_compute_ms": 1., "at": 2.,
        "request": {"submit_compute_ms": 7., "earliest_departure": 2.}, "reply": {"status": "pending"}}]}
    timed = deepcopy(original); timed["client_calls"][0]["submit_compute_ms"] = 2.
    assert encoded(timed) == encoded(original)
    timed["client_calls"][0]["request"]["submit_compute_ms"] = 8.
    assert encoded(timed) != encoded(original)
    timed = deepcopy(original); timed["client_calls"][0]["at"] = 3.
    assert encoded(timed) != encoded(original)
