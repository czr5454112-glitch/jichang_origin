"""Diagnostic streaming must preserve bytes' meaning and restore instrumentation."""
import gc
import gzip
import json
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import profile_lt2_streaming as profile


@pytest.mark.parametrize("level", [0, 1, 9])
def test_bulk_gzip_keeps_every_json_field_and_unicode(tmp_path, level):
    value = {"requests": [{"id": "完整记录", "attempt": i, "payload": [i, None, False]} for i in range(30)]}
    target = tmp_path / "trace.json.gz"
    profile.gz(target, value, compresslevel=level)
    with gzip.open(target, "rt", encoding="utf-8") as stream:
        assert json.load(stream) == value
    assert not target.with_suffix(".gz.tmp").exists()
    # Compression is allowed to change only container bytes, never the UTF-8
    # JSON representation (including order, Unicode, spaces and number forms).
    assert gzip.decompress(target.read_bytes()).decode("utf-8") == json.dumps(value, ensure_ascii=False, allow_nan=False)


def test_controller_failure_restores_gc_and_owner_hooks_and_keeps_error_evidence(tmp_path, monkeypatch):
    binary = tmp_path / "identity-only.bin"
    binary.write_bytes(b"not-loaded")
    session = SimpleNamespace(physical_time=0.)
    monkeypatch.setattr(profile, "load_native", lambda _: SimpleNamespace(NativeSession=lambda data: session))
    previous_hook = profile.controller_module._activate_owner
    previous_callbacks = list(gc.callbacks)

    def fail(*args, **kwargs):
        assert profile.controller_module._activate_owner is not previous_hook
        gc.collect(2)
        raise RuntimeError("injected_controller_failure")

    monkeypatch.setattr(profile, "run_event_protocol_control", fail)
    args = SimpleNamespace(binary=binary, expected_binary_sha256=profile.sha(binary), suite="synthetic",
        output=tmp_path, cprofile=False, trace_gc=True, retain_trace_in_memory=False,
        horizon=50., segment_seconds=10., event_budget=1000, max_activations=20,
        activation_shard_budget=10, policy="joint")
    with pytest.raises(RuntimeError, match="injected_controller_failure"):
        profile.worker(args)
    assert gc.callbacks == previous_callbacks
    assert profile.controller_module._activate_owner is previous_hook
    assert "injected_controller_failure" in (tmp_path / "error.txt").read_text(encoding="utf-8")
    with gzip.open(tmp_path / "gc_events.json.gz", "rt", encoding="utf-8") as stream:
        events = json.load(stream)
    assert any(event["generation"] == 2 and event["inside_controller"] for event in events)


def saved_shard(root, number, sequences, state):
    folder = root / "segments"
    folder.mkdir(exist_ok=True)
    value = {"control_records": [{"trace_sequence": seq, "payload": ["保留", seq]} for seq in sequences[::2]],
             "native_batches": [{"trace_sequence": seq} for seq in sequences[1::2]],
             "client_calls": [{"id": str(number)}], "controller_state": state,
             "status": "reached", "control_continuation": {"physical_time": float(number + 1)}}
    path = folder / f"{number:04d}.json.gz"
    profile.gz(path, value)
    return path, value


def test_shard_manifest_preserves_raw_history_and_separates_intermediate_horizon(tmp_path):
    first, first_data = saved_shard(tmp_path, 0, [0, 1, 2], {"generation": 1})
    second, second_data = saved_shard(tmp_path, 1, [3, 4], {"generation": 2, "timer_heap": [(5., 1, "A")]})
    before = [first.read_bytes(), second.read_bytes()]
    run = {"controller_state": second_data["controller_state"], "status": "control_budget_exhausted",
           "segments": [{"horizon": 1.}, {"horizon": 2.}], "wall_seconds": .5}
    manifest = profile.shard_manifest(tmp_path, run, 3)
    assert manifest["counts"] == {"control_records": 3, "native_batches": 2, "client_calls": 2}
    assert manifest["status"] == "control_budget_exhausted" and manifest["last_shard_status"] == "reached"
    assert manifest["all_raw_records_retained"] and not manifest["cross_process_native_checkpoint"]
    assert [first.read_bytes(), second.read_bytes()] == before
    assert manifest["shards"][1]["sha256"] == profile.sha(second)
    assert json.loads((tmp_path / "run_shards.json").read_text(encoding="utf-8")) == manifest
    assert list(profile.shard_calls(tmp_path)) == first_data["client_calls"] + second_data["client_calls"]


@pytest.mark.parametrize("defect", ["gap", "duplicate", "missing_owner", "wrong_final"])
def test_shard_manifest_fails_closed_on_incomplete_or_mismatched_trace(tmp_path, defect):
    saved_shard(tmp_path, 0, [0, 1], {"generation": 1})
    sequence = 3 if defect == "gap" else 1 if defect == "duplicate" else 2
    saved_shard(tmp_path, 1, [sequence], {"generation": 2})
    run = {"controller_state": {"generation": 3 if defect == "wrong_final" else 2},
           "status": "reached", "segments": [], "wall_seconds": .5}
    with pytest.raises(ValueError, match="stream_manifest:"):
        profile.shard_manifest(tmp_path, run, 3 if defect == "missing_owner" else 2)
    assert not (tmp_path / "run_shards.json").exists()
