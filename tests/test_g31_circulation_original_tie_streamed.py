"""Pure diagnostic equivalence gates; no native execution or timing claims."""
import copy
import gzip
import json
import pytest
from scripts.experiments.g31_ics_circulation import research_original_tie_streamed as streamed
from tests.test_g31_circulation_original_tie_comparison import fixture as business_fixture


def fixture():
    commands = [{"from": u, "next": v} for u, v in ((1, 2), (5, 33), (33, 51), (29, 146))]
    decisions = [{"at": float(i), "request": {**c, "message_delay": 2., "expected_generation": 1, "expected_traversal": i},
        "local_tray": {"generation": 1, "traversal_id": i},
        "delivered_ack": {"status": "updated", "executed_at": i + 2., "delivered_at": i + 2.2}}
        for i, c in enumerate(commands)]
    intent = {"status": "all_four_intents_and_edges_observed", "commands": commands, "path": [0, 1, 2],
        "decisions": decisions, "observed_edges": copy.deepcopy(commands)}
    for e in intent["observed_edges"]: e["to"] = e.pop("next")
    arm = {"status": "reached", "input_sha256": "input", "binary_sha256": "binary", "checkpoint_identity": "seed",
        "native_state_sha256": "final", "controller_state": {"pending_owners": [], "tick": 1}, "intent": intent,
        "result": {"advance": {"horizon_complete": True, "physical_time": streamed.SHORT_HORIZON},
            "receipts": [{"event": "EDGE_ENTER", "from": 1, "to": 2}], "native_event_ms": 1.},
        "all_control_calls": [{"request": {"id": "ordinary"}, "submit_compute_ms": 1.}],
        "route_calls": [{"request": {"id": "route"}, "submit_compute_ms": 1.}],
        "route_outbox": {"route": {"terminal": True}}, "activation_count": 10, "source_changed": [], "physical_audit": {"status": "passed"}}
    protocol = {"input_sha256": "input", "expected_binary_sha256": "binary", "hypothesis": {"commands": commands, "path": [0, 1, 2]}}
    return arm, copy.deepcopy(arm), protocol


def test_identical_semantics_pass_despite_diagnostic_time_difference():
    left, right, protocol = fixture(); right["result"]["native_event_ms"] = 9.
    right["route_calls"][0]["submit_compute_ms"] = 5.; right["result"]["advance"]["events_processed"] = 100
    assert streamed.conformance(left, right, protocol)["status"] == "passed"


@pytest.mark.parametrize("mutation", ["seal", "state", "call", "edge", "ack", "incomplete", "missing_identity", "audit", "source"])
def test_every_material_conformance_mismatch_prevents_admission(mutation):
    left, right, protocol = fixture()
    if mutation == "seal": right["native_state_sha256"] = "different"
    elif mutation == "state": right["controller_state"]["pending_owners"] = ["A"]
    elif mutation == "call": right["all_control_calls"][0]["request"]["id"] = "changed"
    elif mutation == "edge": right["result"]["receipts"][0]["to"] = 27
    elif mutation == "ack": right["intent"]["decisions"][0]["delivered_ack"]["status"] = "rejected"
    elif mutation == "incomplete": right["result"]["advance"]["horizon_complete"] = False
    elif mutation == "missing_identity": left["input_sha256"] = right["input_sha256"] = None
    elif mutation == "audit": left["physical_audit"]["status"] = right["physical_audit"]["status"] = "failed"
    else: right["source_changed"] = ["controller.py"]
    assert streamed.conformance(left, right, protocol)["status"] != "passed"


def test_fast_export_preserves_exact_decoded_bytes_and_order(tmp_path):
    value = {"unicode": "完整记录", "numeric": [-0.0, 1e-20, 1e30, None, True],
             "nested": [{"z": 1, "a": 2}, {"requests": list(range(100))}]}
    old, new = tmp_path / "old.json.gz", tmp_path / "new.json.gz"
    streamed.gz(old, value)
    streamed.gz(new, value, fast_export=True)
    assert gzip.decompress(old.read_bytes()) == gzip.decompress(new.read_bytes())
    assert streamed.read_gz(new) == value


def test_equal_but_invalid_acks_cannot_certify_an_executed_gate():
    left, right, protocol = fixture()
    for arm in (left, right): arm["intent"]["decisions"][0]["delivered_ack"]["status"] = "rejected"
    assert streamed.conformance(left, right, protocol)["checks"]["actual_gate_revalidated"] is False


def test_streamed_calls_require_exact_file_hash_and_contiguous_trace(tmp_path):
    part = {"run": {"control_records": [{"trace_sequence": 0}], "native_batches": [{"trace_sequence": 1}],
        "client_calls": [{"kind": "transfer", "retry": False, "request": {"id": "first"}}]}}
    path = tmp_path / "part.json.gz"; streamed.gz(path, part)
    manifest = {"shards": [{"path": path.name, "sha256": streamed.digest(path)}]}
    streamed.atomic_json(tmp_path / "shards.json", manifest)
    assert list(streamed.iter_calls(tmp_path)) == part["run"]["client_calls"]
    part["run"]["native_batches"][0]["trace_sequence"] = 3; streamed.gz(path, part)
    with pytest.raises(ValueError, match="shard_identity"): list(streamed.iter_calls(tmp_path))
    manifest["shards"][0]["sha256"] = streamed.digest(path); streamed.atomic_json(tmp_path / "shards.json", manifest)
    with pytest.raises(ValueError, match="trace_gap"): list(streamed.iter_calls(tmp_path))


def test_business_comparison_requires_bound_common_native_start_and_inputs():
    data, arms = business_fixture()
    protocol = {"input_sha256": "input", "expected_binary_sha256": "binary", "gate_receipt_sha256": "gate"}
    for arm in arms.values():
        arm.update(checkpoint_identity="seed", input_sha256="input", binary_sha256="binary", gate_receipt_sha256="gate", source_changed=[])
    assert streamed.assess_match(data, arms, protocol)["status"] == "assessed_common_prefix"
    arms["candidate"]["checkpoint_identity"] = "changed"
    report = streamed.assess_match(data, arms, protocol)
    assert report["status"] == "unknown_source_or_checkpoint_mismatch" and report["gain_all_jobs"] is None


def test_wrapper_skips_only_disabled_or_terminal_intent_and_uses_current_policy_view():
    class Native:
        physical_time = 0.
        def __init__(self): self.full = self.policy = 0
        def advance_until_owner_notification(self, *args, **kw):
            return {"status": "notified", "timestamp_complete": True, "notifications": {"A": {}}}
        def observe_protocol(self, owner):
            self.full += 1; return {"owner_id": owner, "now": 0., "trays": [], "jobs": [], "node_contracts": []}
        def observe_protocol_control_policy(self, owner):
            self.policy += 1; return {"owner_id": owner, "now": 0., "trays": [], "jobs": [], "node_contracts": []}
    for enabled, terminal, legacy, counts in ((False, False, False, (0, 0)), (True, True, False, (0, 0)),
            (True, False, False, (0, 1)), (False, False, True, (1, 0))):
        native = Native(); wrapper = streamed.InjectionBoundary(native, [0, 1], [{"from": 0, "next": 1}], enabled, legacy_observation=legacy)
        if terminal: wrapper.intent.status = "all_four_intents_and_edges_observed"
        wrapper.advance_until_owner_notification(["A"], {"A": 0}, 1., max_events=100)
        assert (native.full, native.policy) == counts
