"""Pure handwritten evidence, never a native outcome or large-run scan."""
from copy import deepcopy
import gzip
import hashlib
import json

import pytest

from scripts.experiments.g31_ics_circulation import audit_saved_horizon as audit
from scripts.experiments.g31_ics_circulation.read_sharded_raw import (
    KEYS, decode_shard, read_bound_shard, single_object_boundary,
)
from test_g31_circulation_full_day_verification import complete_fixture, write_fixture


def fixture(tmp_path, monkeypatch):
    f = complete_fixture(tmp_path, monkeypatch)
    part = f["part"]
    part.update(wall_seconds=1., complete_100ms_requirement_certified=False, scope="pure handwritten test")
    f["part"] = {key: part[key] for key in KEYS}
    f["part"]["native_state_sha256"] = "a" * 64
    f["manifest"]["schema"] = "g31.lt2.complete_sharded_trace.v1"
    src = tmp_path / "test_only_source.py"
    src.write_text("# handwritten fixture, no native\n")
    archive = tmp_path / "source_archive"
    archive.mkdir()
    (archive / src.name).write_bytes(src.read_bytes())
    f["receipt"]["source_before"] = {src.name: hashlib.sha256(src.read_bytes()).hexdigest()}
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    return f


def test_exact_projection_preserves_every_other_field(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    raw = json.dumps(f["part"]).encode()
    projected = decode_shard(raw)
    assert projected == dict(f["part"], controller_state=None)
    assert decode_shard(raw, final=True) == f["part"]
    assert f["part"]["controller_state"] is not None


@pytest.mark.parametrize("mutation", ["nested_marker", "duplicate_marker", "reordered", "spacing", "nonobject", "trailing", "duplicate_json_key", "nan"])
def test_ambiguous_or_unsupported_projection_fails_closed(tmp_path, monkeypatch, mutation):
    f = fixture(tmp_path, monkeypatch)
    part = f["part"]
    if mutation == "nested_marker": part["controller_state"]["control_records"] = []
    if mutation == "duplicate_marker": part["result"]["controller_state"] = {}
    if mutation == "reordered": part = dict(reversed(list(part.items())))
    if mutation == "nonobject": part["controller_state"] = []
    if mutation == "nan": part["wall_seconds"] = float("nan")
    raw = json.dumps(part).encode()
    if mutation == "spacing": raw = raw.replace(b', "controller_state": ', b',"controller_state":')
    if mutation == "trailing": raw += b"{}"
    if mutation == "duplicate_json_key": raw = raw.replace(b'"wall_seconds": 1.0', b'"wall_seconds": 1.0, "wall_seconds": 2.0')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        decode_shard(raw)


def test_escaped_marker_lookalikes_do_not_cut_a_string(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    f["part"]["scope"] = ', "controller_state": {}, "control_records": [\\\"escaped\\\"]'
    raw = json.dumps(f["part"]).encode()
    assert decode_shard(raw)["scope"] == f["part"]["scope"]


@pytest.mark.parametrize("injection", [b'"injected": {}, ', b'"injected": {"nested": []}, ', b'"injected": {"string": "}][{\\\""}, '])
def test_state_projection_cannot_hide_an_extra_top_level_field(tmp_path, monkeypatch, injection):
    raw = json.dumps(fixture(tmp_path, monkeypatch)["part"]).encode()
    marker = b', "control_records": '
    raw = raw.replace(marker, b', ' + injection + b'"control_records": ')
    with pytest.raises(ValueError, match="extra_value_in_skipped_state_region"):
        decode_shard(raw)


@pytest.mark.parametrize("raw", [b'{"a": [}] }', b'{"a":"unterminated}', b'{"a":"bad\\q"}', b'{}{}', b'{[}'])
def test_state_boundary_rejects_invalid_container_or_strings(raw):
    with pytest.raises(ValueError): single_object_boundary(raw)


def test_state_boundary_ignores_escaped_brackets_and_unicode():
    single_object_boundary(b'{"a":"}][{\\\"\\\\\\u1234", "b":[{},[]]}')


def test_exact_compressed_hash_and_gzip_crc_are_required(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    path = tmp_path / "raw.gz"
    data = gzip.compress(json.dumps(f["part"]).encode())
    path.write_bytes(data)
    with pytest.raises(ValueError, match="compressed_hash_mismatch"):
        read_bound_shard(path, "0" * 64)
    broken = data[:-1] + bytes([data[-1] ^ 1])
    path.write_bytes(broken)
    with pytest.raises((gzip.BadGzipFile, EOFError)):
        read_bound_shard(path, hashlib.sha256(broken).hexdigest())


@pytest.mark.parametrize("status", ["completed", "hard_timeout", "failed"])
@pytest.mark.parametrize("has_summary", [True, False])
def test_terminal_worker_status_is_preserved_separate_from_saved_horizon(tmp_path, monkeypatch, status, has_summary):
    f = fixture(tmp_path, monkeypatch)
    f["receipt"].update(status=status, exit_code=0 if status == "completed" else None)
    write_fixture(tmp_path, f)
    if not has_summary: (tmp_path / "summary.json").unlink()
    before = (tmp_path / "receipt.json").read_bytes()
    report = audit.audit_saved(tmp_path, 2, 50., expected_final_seal="a" * 64)
    assert report["status"] == "passed_saved_physical_horizon"
    assert report["producer_receipt_status"] == status
    assert report["producer_process_success"] is (status == "completed")
    assert report["producer_summary_present"] is has_summary
    assert report["new_native_executions"] == 0
    assert report["unfinished"] == 2 and not report["unpaired_zero_regression_certified"]
    assert (tmp_path / "receipt.json").read_bytes() == before


@pytest.mark.parametrize("defect", ["running", "source_changed", "archive_changed", "hash_changed", "missing_shard", "extra_shard", "trace_gap", "trace_reorder", "clock_gap", "mutated_retry", "outbox_payload", "outbox_reply", "pending_owner", "pending_cause", "needs_drain", "native_incomplete", "last_not_horizon", "bad_result", "missing_job", "future_job", "future_receipt", "summary_wrong", "offline_wrong", "binary_changed", "seal_wrong"])
def test_saved_horizon_denominator_and_physical_guards(tmp_path, monkeypatch, defect):
    f = fixture(tmp_path, monkeypatch)
    part = f["part"]
    if defect == "running": f["receipt"]["status"] = "running"
    elif defect == "source_changed": f["receipt"]["source_changed"] = ["test_only_source.py"]
    elif defect == "trace_gap": part["native_batches"][-1]["trace_sequence"] += 1
    elif defect == "trace_reorder": part["control_records"].reverse()
    elif defect == "clock_gap": part["native_batches"][0]["start_at"] = 1.
    elif defect == "mutated_retry": part["client_calls"][-1]["request"]["target_owner"] = "X"
    elif defect == "outbox_payload": part["controller_state"]["client"]["outbox"]["one"]["payload"]["target_owner"] = "X"
    elif defect == "outbox_reply": part["controller_state"]["client"]["outbox"]["one"]["submission_reply"] = {}
    elif defect == "pending_owner": part["controller_state"]["pending_owners"] = ["A"]
    elif defect == "pending_cause": part["controller_state"]["pending_causes"] = {"A": {}}
    elif defect == "needs_drain": part["controller_state"]["needs_native_drain"] = True
    elif defect == "native_incomplete": part["native_batches"][-1]["timestamp_complete"] = False
    elif defect == "last_not_horizon": part["native_batches"][-1]["status"] = "notified"
    elif defect == "bad_result": part["result"]["advance"]["horizon_complete"] = False
    elif defect == "missing_job": part["result"]["jobs"].pop()
    elif defect == "future_job": part["result"]["jobs"][0]["completed_at"] = 51.
    elif defect == "future_receipt": part["result"]["receipts"].append({"time": 51.})
    elif defect == "summary_wrong": f["summary"]["owner_activations"] = 1
    elif defect == "offline_wrong": f["offline"]["now"] = 49.
    elif defect == "seal_wrong": part["native_state_sha256"] = "b" * 64
    write_fixture(tmp_path, f)
    raw = tmp_path / "segments/0000.json.gz"
    if defect == "archive_changed": (tmp_path / "source_archive/test_only_source.py").write_text("changed")
    elif defect == "hash_changed": raw.write_bytes(raw.read_bytes() + b"junk")
    elif defect == "missing_shard": raw.unlink()
    elif defect == "extra_shard": (tmp_path / "segments/0001.json.gz").write_bytes(raw.read_bytes())
    elif defect == "binary_changed": (tmp_path / "test_binary_not_native.bin").write_bytes(b"changed")
    with pytest.raises((ValueError, FileNotFoundError, AssertionError)):
        audit.audit_saved(tmp_path, 2, 50., expected_final_seal="a" * 64)


def test_receipt_posthash_stability(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    write_fixture(tmp_path, f)
    def corrupt(*_):
        (tmp_path / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="evidence_changed_during_audit"):
        audit.audit_saved(tmp_path, 2, 50., progress=corrupt)


def test_auditor_source_posthash_stability(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    write_fixture(tmp_path, f)
    source = [{"auditor.py": "initial"}]
    monkeypatch.setattr(audit, "auditor_sources", lambda: deepcopy(source[0]))
    def corrupt(*_): source[0]["auditor.py"] = "changed"
    with pytest.raises(ValueError, match="auditor_source_changed_during_audit"):
        audit.audit_saved(tmp_path, 2, 50., progress=corrupt)


def test_unknown_resume_schema_cannot_skip_prefix_validation(tmp_path):
    with pytest.raises(ValueError, match="unsupported_resume_schema"):
        audit.verify_resume_proof(tmp_path, {"schema": "new_resume", "command": []}, {}, {})


def resume_fixture(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    config = {"owners": ["A"]}
    f["part"]["controller_state"]["config"] = config
    prefix = deepcopy(f["part"])
    prefix["result"] = None
    prefix["native_state_sha256"] = "b" * 64
    prefix["control_continuation"] = {"status": "reached", "requested_horizon": 0., "physical_time": 0.}
    prefix["control_records"] = prefix["control_records"][:1]
    prefix["client_calls"] = prefix["client_calls"][:1]
    prefix["native_batches"] = [dict(prefix["native_batches"][0], end_at=0.)]
    final = f["part"]
    final["control_records"] = [dict(final["control_records"][-1], trace_sequence=3)]
    final["client_calls"] = final["client_calls"][-1:]
    final["native_batches"][0]["trace_sequence"] = 2
    final["native_batches"][-1]["trace_sequence"] = 4
    write_fixture(tmp_path, f)
    (tmp_path / "segments/0001.json.gz").write_bytes((tmp_path / "segments/0000.json.gz").read_bytes())
    (tmp_path / "segments/0000.json.gz").write_bytes(gzip.compress(json.dumps(prefix).encode()))
    def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
    def save(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return digest(path)
    f["manifest"]["shards"] = [{"path": f"segments/{i:04d}.json.gz", "sha256": digest(tmp_path / f"segments/{i:04d}.json.gz"),
        "counts": {k: len(p[k]) for k in ("control_records", "native_batches", "client_calls")},
        "status": "reached", "physical_time": float(50*i)} for i, p in enumerate((prefix, final))]
    f["manifest"]["segments"] = [{"status": "reached", "physical_time": float(50*i), "horizon": float(50*i),
        "cumulative_control_wall_seconds": .25 if i == 0 else 1.} for i in (0, 1)]
    f["manifest"]["counts"]["native_batches"] = 3
    f["manifest"]["final_state_shard"] = "segments/0001.json.gz"
    save("run_shards.json", f["manifest"])
    source_receipt_sha = save("resume_source/source_receipt_snapshot.json", {"source_before": {}})
    source_heartbeat_sha = save("resume_source/source_heartbeat_snapshot.json", {"physical_time": 0.})
    cut = {"schema": "g31.sparse_sealed_resume_cut.v1", "source_cut": 0, "physical_time": 0.,
        "owner_activations": 1, "binary_sha256": f["receipt"]["binary_sha256"],
        "input_sha256": digest(tmp_path / "input.json.gz"), "known_native_seal": "b" * 64,
        "controller_config": config, "shards": f["manifest"]["shards"][:1],
        "source_receipt_sha256": source_receipt_sha, "source_heartbeat_sha256": source_heartbeat_sha}
    cut_sha = save("resume_source/cut_manifest.json", cut)
    stop_sha = save("resume_source/stop_receipt.json", {"source_worker_stopped": True, "unchanged_policy": True,
        "cut_manifest_sha256": cut_sha})
    save("reconstruction.json", {"status": "verified_against_known_native_seal", "native_state_sha256": "b" * 64,
        "parts": 1, "physical_time": 0., "owners": 1, "native_boundaries": 1, "submissions": 1, "trace_records": 2})
    f["receipt"].update(schema="g31.sparse_sealed_resume_worker.v1", cut_manifest_sha256=cut_sha,
        status="hard_timeout", exit_code=None)
    f["receipt"]["command"] += ["--expected-cut-sha256", cut_sha, "--expected-stop-sha256", stop_sha]
    save("receipt.json", f["receipt"])
    return f, save


def test_sparse_resumed_prefix_and_all_raw_records_checked(tmp_path, monkeypatch):
    resume_fixture(tmp_path, monkeypatch)
    r = audit.audit_saved(tmp_path, 2, 50.)
    assert r["resume_proof"]["resumed"] is True
    assert r["resume_proof"]["prefix_parts"] == 1
    assert r["counts"] == {"control_records": 2, "native_batches": 3, "client_calls": 2}
    assert r["producer_receipt_status"] == "hard_timeout"


@pytest.mark.parametrize("defect", ["cut_hash", "stop_hash", "prefix_hash", "reconstruction_counts", "prefix_seal", "source_snapshot", "config"])
def test_sparse_resume_identity_and_prefix_fail_closed(tmp_path, monkeypatch, defect):
    f, save = resume_fixture(tmp_path, monkeypatch)
    if defect == "cut_hash":
        receipt = json.loads((tmp_path / "receipt.json").read_text())
        receipt["cut_manifest_sha256"] = "0" * 64
        save("receipt.json", receipt)
    elif defect == "stop_hash": save("resume_source/stop_receipt.json", {})
    elif defect == "source_snapshot": save("resume_source/source_heartbeat_snapshot.json", {})
    elif defect == "reconstruction_counts":
        r = json.loads((tmp_path / "reconstruction.json").read_text())
        r["native_boundaries"] += 1
        save("reconstruction.json", r)
    else:
        i = 1 if defect == "config" else 0
        path = tmp_path / f"segments/{i:04d}.json.gz"
        part = json.loads(gzip.decompress(path.read_bytes()))
        if defect == "config": part["controller_state"]["config"] = {"owners": ["X"]}
        elif defect == "prefix_seal": part["native_state_sha256"] = "c" * 64
        else: part["scope"] += " changed"
        path.write_bytes(gzip.compress(json.dumps(part).encode()))
        # Bind changed bytes in the final manifest, not the pinned prefix cut.
        manifest = json.loads((tmp_path / "run_shards.json").read_text())
        manifest["shards"][i]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        save("run_shards.json", manifest)
    with pytest.raises(ValueError): audit.audit_saved(tmp_path, 2, 50.)


def test_projection_explicitly_does_not_validate_skipped_subtree_syntax(tmp_path, monkeypatch):
    # Such input cannot have a genuine successful producer full-parse manifest.
    # This demonstrates the documented opaque-subtree limitation, not approval.
    f = fixture(tmp_path, monkeypatch)
    raw = json.dumps(f["part"]).encode()
    a = raw.index(b', "controller_state": ') + len(b', "controller_state": ')
    b = raw.index(b', "control_records": ')
    opaque_invalid = raw[:a] + b'{deliberately not JSON}' + raw[b:]
    assert decode_shard(opaque_invalid)["controller_state"] is None
    with pytest.raises(json.JSONDecodeError): decode_shard(opaque_invalid, final=True)
