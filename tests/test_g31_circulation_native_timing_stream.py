"""Lossless native sidecar streaming: no simulator or generated performance data."""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import stream_native_request_timing as stream
from scripts.experiments.g31_ics_circulation.capture_native_request_timing import capture_session
from scripts.experiments.g31_ics_circulation.native_request_timing import analyze_native_timing
from scripts.experiments.g31_ics_circulation import profile_streamed_native_timing as profile


class Session:
    """Deterministic native ABI fake; raw output identity is independently kept."""
    physical_time = 2.
    def __init__(self):
        self.total, self.rows = 0, []
        self.response = {"owner_id": "A", "nested": {"status": "received"}}
        self.fail = False
        self.overflow = False
    def offline_request_timing_start(self, capacity, identity):
        self.identity = identity
    def offline_request_timing_take(self):
        batch = {"schema": "g31.native_request_timing.v1", "clock": "steady_clock_relative_nanoseconds",
            "coverage": "known_control_phases_and_unclassified_remainder", "physics_subtraction_authorized": False,
            "session_identity": self.identity, "trace_epoch": 4, "errors": int(self.overflow),
            "completed_outer_calls": self.total, "emitted_span_count": self.total,
            "rows": self.rows, "transfer_identities": [{"index": 0, "request_id": "t"}],
            "command_identities": [], "leg_identities": [], "job_identities": []}
        self.rows = []
        return batch
    def _record(self, method):
        self.total += 1
        self.rows.append({"span_id": self.total-1, "parent_span_id": -1,
            "start_ns": self.total*1000, "end_ns": self.total*1000+100,
            "phase": 0, "method": method, "trace_epoch": 4, "call_ordinal": self.total,
            "event_sequence": 0, "logical_time": 2., "attempt": 1,
            "identity_kind": 0, "identity_index": -1, "related_identity_kind": 0,
            "related_identity_index": -1, "ended": True, "exception_exit": self.fail})
        if self.fail:
            raise RuntimeError("native failure remains evidence")
        return self.response
    def advance_to(self, horizon): return self._record(12)
    def protocol_request(self, owner, request_id): return self._record(3)


class RecentSession(Session):
    def observe_protocol_control_policy(self, owner): return self._record(7)
    def observe_protocol_control_policy_recent(self, owner, validity): return self._record(8)


def clock():
    values = iter([value for i in range(100) for value in (10000+i*1000, 10105+i*1000)])
    return lambda: next(values)


def make_stream(tmp_path, *, failure=False, overflow=False):
    raw = RecentSession()
    captured = stream.streaming_capture_session(raw, stream_directory=tmp_path/"stream",
        session_identity=17, clock=clock())
    expected = {"batches": copy.deepcopy(captured.batches), "call_envelopes": [], "capture_errors": []}
    for index in range(3):
        raw.fail = failure and index == 1
        raw.overflow = overflow and index == 1
        try:
            assert captured.observe_protocol_control_policy_recent("A", 120.) is raw.response
        except RuntimeError:
            assert raw.fail
        captured.take_completed()
        expected["batches"].append(copy.deepcopy(captured.batches[-1]))
        expected["call_envelopes"].extend(copy.deepcopy(captured.envelopes))
        expected["capture_errors"].extend(captured.errors)
        captured.flush()
        assert not captured.batches and not captured.envelopes and not captured.errors
    return captured, captured.seal(), expected


def test_three_shards_reconstruct_exact_raw_namespace_tables_and_existing_validator(tmp_path):
    captured, reference, expected = make_stream(tmp_path)
    actual = stream.reconstruct_native_timing(reference)
    assert actual == expected
    assert captured.total_call_count == 3 and captured.total_batch_count == 4
    assert [e["call_ordinal"] for e in actual["call_envelopes"]] == [1, 2, 3]
    assert len(actual["batches"]) == 4 and actual["batches"][0]["rows"] == []
    assert all(b["transfer_identities"] == [{"index": 0, "request_id": "t"}] for b in actual["batches"])
    before = analyze_native_timing(expected["batches"], expected["call_envelopes"])
    assert stream.analyze_streamed_native_timing(reference) == before
    assert before["status"] == "validated_partial_native_phase_partition"
    assert before["unchanged_whole_native_envelope_ns"] == 315
    assert before["physics_subtracted_ns"] == 0


def test_streamed_and_retained_capture_exact_under_same_calls_and_clock(tmp_path):
    captured, reference, expected = make_stream(tmp_path)
    raw = RecentSession()
    retained = capture_session(raw, session_identity=17, clock=clock())
    for _ in range(3):
        assert retained.observe_protocol_control_policy_recent("A", 120.) is raw.response
        retained.take_completed()
    assert stream.reconstruct_native_timing(reference) == {
        "batches": retained.batches, "call_envelopes": retained.envelopes, "capture_errors": retained.errors}


@pytest.mark.parametrize("failure,overflow", [(True, False), (False, True)])
def test_exception_and_overflow_are_retained_verbatim_and_fail_closed(tmp_path, failure, overflow):
    _, reference, expected = make_stream(tmp_path, failure=failure, overflow=overflow)
    assert stream.reconstruct_native_timing(reference) == expected
    assert stream.analyze_streamed_native_timing(reference)["status"] == "unknown"


@pytest.mark.parametrize("defect", ["missing_middle", "missing_final", "changed_chunk", "changed_manifest",
    "duplicate_chunk", "open_manifest", "reordered_manifest", "reference_namespace"])
def test_missing_or_changed_stream_fails_closed(tmp_path, defect):
    captured, reference, _ = make_stream(tmp_path)
    directory = captured.stream.directory
    if defect == "missing_middle": (directory/"native_000001.json.gz").unlink()
    elif defect == "missing_final": (directory/"native_000002.json.gz").unlink()
    elif defect == "changed_chunk": (directory/"native_000000.json.gz").write_bytes(b"corrupt")
    elif defect == "changed_manifest": captured.stream.manifest_path.write_text("{}")
    elif defect == "duplicate_chunk": (directory/"native_000003.json.gz").write_bytes((directory/"native_000000.json.gz").read_bytes())
    elif defect == "open_manifest": reference["status"] = "open"
    elif defect == "reordered_manifest":
        manifest = json.loads(captured.stream.manifest_path.read_bytes())
        manifest["chunks"].reverse()
        captured.stream.manifest_path.write_text(json.dumps(manifest))
        reference["manifest_sha256"] = stream.file_sha256(captured.stream.manifest_path)
    else: reference["session_identity"] = 18
    report = stream.analyze_streamed_native_timing(reference)
    assert report["status"] == "unknown" and report["errors"]
    assert report["physics_subtracted_ns"] == 0
    assert report["complete_request_100ms_certified"] is False


def mutate_chunk(reference, index, mutate):
    """Rebind integrity hashes to test semantic checks independently of hashes."""
    path = Path(reference["manifest"])
    manifest = json.loads(path.read_bytes())
    descriptor = manifest["chunks"][index]
    chunk_path = path.parent/descriptor["file"]
    with gzip.open(chunk_path, "rt") as handle: chunk = json.load(handle)
    mutate(chunk)
    with gzip.open(chunk_path, "wt") as handle: json.dump(chunk, handle)
    descriptor["sha256"] = stream.file_sha256(chunk_path)
    path.write_text(json.dumps(manifest))
    reference["manifest_sha256"] = stream.file_sha256(path)


@pytest.mark.parametrize("defect", ["ordinal_reset", "batch_namespace", "chunk_namespace", "span_id",
    "envelope_missing", "batch_missing", "range_overlap", "mutated_identity", "final_leaf_missing"])
def test_rebound_hashes_do_not_hide_broken_identity_or_coverage(tmp_path, defect):
    _, reference, _ = make_stream(tmp_path)
    def mutate(chunk):
        if defect == "ordinal_reset": chunk["call_envelopes"][0]["call_ordinal"] = 1
        elif defect == "batch_namespace": chunk["batches"][0]["session_identity"] = 99
        elif defect == "chunk_namespace": chunk["trace_epoch"] = 99
        elif defect == "span_id": chunk["batches"][0]["rows"][0]["span_id"] = 100
        elif defect == "envelope_missing": chunk["call_envelopes"] = []
        elif defect == "batch_missing": chunk["batches"] = []
        elif defect == "range_overlap": chunk["batch_offset"] = 0
        elif defect == "mutated_identity": chunk["batches"][0]["transfer_identities"][0]["request_id"] = "changed"
        else: chunk["batches"][0]["rows"] = []
    mutate_chunk(reference, 2, mutate)
    assert stream.analyze_streamed_native_timing(reference)["status"] == "unknown"


def test_export_failure_preserves_buffers_and_prevents_silent_retry(tmp_path, monkeypatch):
    captured = stream.streaming_capture_session(Session(), stream_directory=tmp_path/"stream",
        session_identity=17, clock=clock())
    captured.advance_to(2.)
    captured.take_completed()
    before = copy.deepcopy((captured.batches, captured.envelopes, captured.errors))
    def fail(*args): raise OSError("disk failure")
    monkeypatch.setattr(stream, "_atomic_manifest", fail)
    with pytest.raises(OSError, match="disk failure"): captured.flush()
    assert (captured.batches, captured.envelopes, captured.errors) == before
    assert captured.stream.failed is True
    assert (tmp_path/"stream/native_000000.json.gz").exists()
    with pytest.raises(ValueError, match="stream_not_writable"): captured.flush()
    with pytest.raises(ValueError, match="capture_not_writable"): captured.advance_to(3.)
    with pytest.raises(ValueError, match="unflushed_records"): captured.seal()


def test_no_silent_reopen_or_unflushed_final_records(tmp_path):
    captured = stream.streaming_capture_session(Session(), stream_directory=tmp_path/"stream", session_identity=17)
    with pytest.raises(ValueError, match="unflushed_records"): captured.seal()
    captured.flush()
    reference = captured.seal()
    with pytest.raises(ValueError, match="capture_not_writable"): captured.advance_to(3.)
    with pytest.raises(FileExistsError): stream.NativeTimingStream(tmp_path/"stream", session_identity=17, trace_epoch=4)
    assert stream.analyze_streamed_native_timing(reference)["status"] == "unknown"  # no measured calls


def test_streaming_preserves_explicit_type_capability_and_query_argument(tmp_path):
    session = Session()
    captured = stream.streaming_capture_session(session, stream_directory=tmp_path/"stream", session_identity=17)
    assert getattr(type(captured), "observe_protocol_control_policy_recent", None) is None
    assert captured.protocol_request("A", "id:unaltered") is session.response
    assert captured.envelopes[0]["protocol_request_id"] == "id:unaltered"
    with pytest.raises(ValueError, match="unclassified_endpoint"): captured.untracked_native_method()


def test_driver_hook_cleanup_and_no_early_reconstruction(tmp_path, monkeypatch):
    args = SimpleNamespace(output=tmp_path, native_trace_capacity=10, stream_native_phase=True, record_gc=True)
    previous = profile.driver.BundleRecorder, profile.driver.analyze_bundles, profile.driver.SOURCE_NAMES
    settings = profile.PhaseStorageRecorder.instances, profile.PhaseStorageRecorder.output
    coarse = {"status": "complete_conservative_bundle_accounting", "requests": [{"complete_compute_upper_ns": 345}],
        "exclusive_controller_wall_ns": 999}
    monkeypatch.setattr(profile.bundles, "analyze_bundles", lambda ledger: copy.deepcopy(coarse))
    with pytest.raises(RuntimeError, match="stop"):
        with profile.installed_driver(args):
            assert profile.driver.BundleRecorder.stream_native_phase is True
            for ledger in ({"native_timing_stream": {}}, {"native_timing": {}}):
                result = profile.driver.analyze_bundles(ledger)
                assert result["requests"] == coarse["requests"]
                assert result["exclusive_controller_wall_ns"] == 999
                assert result["native_phase_partition"]["status"] == "deferred_until_offline_reconstruction"
            raise RuntimeError("stop")
    assert previous == (profile.driver.BundleRecorder, profile.driver.analyze_bundles, profile.driver.SOURCE_NAMES)
    assert settings == (profile.PhaseStorageRecorder.instances, profile.PhaseStorageRecorder.output)


def test_gc_callback_cleanup_and_timestamps_on_failed_controller(tmp_path, monkeypatch):
    args = SimpleNamespace(output=tmp_path, native_trace_capacity=10, stream_native_phase=False, record_gc=True)
    initial = list(profile.gc.callbacks)
    def fail(recorder, *args, **kwargs):
        callback = profile.gc.callbacks[-1]
        recorder.current_root = "owner-update-5"
        recorder._native_method = "observe_protocol_control_policy_recent"
        callback("start", {"generation": 2})
        callback("stop", {"generation": 2, "collected": 0, "uncollectable": 0})
        raise RuntimeError("controller failure")
    monkeypatch.setattr(profile.retained.NativePhaseBundleRecorder, "run", fail)
    with profile.installed_driver(args):
        recorder = profile.PhaseStorageRecorder(Session())
        with pytest.raises(RuntimeError, match="controller failure"): recorder.run([])
    assert profile.gc.callbacks == initial
    data = profile.driver.read_gzip(tmp_path/"gc_0001/window_000001.json.gz")
    row = data["rows"][0]
    assert row["root_request_id"] == "owner-update-5"
    assert row["native_method"] == "observe_protocol_control_policy_recent"
    assert row["end_ns"] >= row["start_ns"] and data["gc_time_subtracted"] is False


def test_default_new_driver_storage_is_retained():
    assert profile.PhaseStorageRecorder.stream_native_phase is False


def test_recorder_flushes_only_after_complete_controller_return(tmp_path, monkeypatch):
    args = SimpleNamespace(output=tmp_path, native_trace_capacity=10, stream_native_phase=True, record_gc=True)
    result = {"controller_state": {"unchanged": True}, "status": "control_budget_exhausted"}
    call_count = 0
    def controller(recorder, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Prior chunks have retired, while this call's raw envelope stays live
        # until the complete controller output returns through the wrapper.
        assert not recorder.native_capture.envelopes
        response = recorder.session.observe_protocol_control_policy_recent("A", 120.)
        assert response is recorder.native_capture._session.response
        assert len(recorder.native_capture.envelopes) == 1
        assert len(recorder.native_capture.stream.manifest["chunks"]) == call_count-1
        return result
    monkeypatch.setattr(profile.bundles.BundleRecorder, "run", controller)
    with profile.installed_driver(args):
        recorder = profile.PhaseStorageRecorder(RecentSession())
        for _ in range(3):
            assert recorder.run(["A"]) is result
            assert recorder.native_capture.envelopes == recorder.native_capture.batches == []
        ledger = recorder.ledger()
        assert "native_timing" not in ledger  # no cumulative reconstruction during control
        assert ledger["native_timing_stream"]["envelope_count"] == 3
        raw = stream.reconstruct_native_timing(recorder.native_capture.seal())
    assert [row["call_ordinal"] for row in raw["call_envelopes"]] == [1, 2, 3]
    assert len(raw["batches"]) == 4


def test_failed_controller_native_trace_is_exported_but_never_complete(tmp_path, monkeypatch):
    args = SimpleNamespace(output=tmp_path, native_trace_capacity=10, stream_native_phase=True, record_gc=True)
    callbacks = list(profile.gc.callbacks)
    def controller(recorder, *args, **kwargs):
        recorder.native_capture._session.fail = True
        recorder.session.advance_to(3.)
    monkeypatch.setattr(profile.bundles.BundleRecorder, "run", controller)
    with profile.installed_driver(args):
        recorder = profile.PhaseStorageRecorder(Session())
        with pytest.raises(RuntimeError, match="native failure"): recorder.run(["A"])
        reference = recorder.native_capture.stream.reference()
        assert reference["status"] == "open" and reference["capture_error_count"] == 1
        assert reference["envelope_count"] == 1
        assert stream.analyze_streamed_native_timing(reference)["status"] == "unknown"
    assert callbacks == profile.gc.callbacks


def test_original_identity_tables_do_not_alias_after_flush(tmp_path):
    captured = stream.streaming_capture_session(Session(), stream_directory=tmp_path/"stream",
        session_identity=17, clock=clock())
    captured.advance_to(2.)
    batch = captured.take_completed()
    captured.flush()
    batch["transfer_identities"][0]["request_id"] = "mutated caller alias after export"
    actual = stream.reconstruct_native_timing(captured.seal())
    assert actual["batches"][1]["transfer_identities"][0]["request_id"] == "t"


@pytest.mark.parametrize("defect", ["null_envelope", "null_batch", "non_list_rows", "unsupported025_identity"])
def test_malformed_containers_and_new_native_abi_fail_closed(tmp_path, defect):
    _, reference, _ = make_stream(tmp_path)
    def mutate(chunk):
        if defect == "null_envelope": chunk["call_envelopes"][0] = None
        elif defect == "null_batch": chunk["batches"][0] = None
        elif defect == "non_list_rows": chunk["batches"][0]["rows"] = 99
        else:
            chunk["batches"][0]["rows"][0].update(identity_kind=10, identity_index=0)
    mutate_chunk(reference, 2, mutate)
    report = stream.analyze_streamed_native_timing(reference)
    assert report["status"] == "unknown" and report["errors"]
    assert report["complete_request_100ms_certified"] is False


def test_failed_native_take_preserves_unexported_raw_for_error_prefix(tmp_path, monkeypatch):
    class FailedTake(Session):
        bad_take = False
        def offline_request_timing_take(self):
            if self.bad_take:
                raise OSError("native take failed")
            return super().offline_request_timing_take()
    args = SimpleNamespace(output=tmp_path, native_trace_capacity=10, stream_native_phase=True, record_gc=False)
    def controller(recorder, *args, **kwargs):
        recorder.session.advance_to(3.)
        return {"status": "control_budget_exhausted"}
    monkeypatch.setattr(profile.bundles.BundleRecorder, "run", controller)
    with profile.installed_driver(args):
        raw = FailedTake()
        recorder = profile.PhaseStorageRecorder(raw)
        recorder.run(["A"])
        raw.bad_take = True
        with pytest.raises(OSError, match="native take failed"): recorder.run(["A"])
        ledger = recorder.ledger()
        assert ledger["native_timing_stream"]["envelope_count"] == 1
        assert ledger["native_timing_unexported"]["call_envelopes"][0]["call_ordinal"] == 2
        assert len(ledger["native_timing_unexported"]["call_envelopes"]) == 1
        assert stream.analyze_streamed_native_timing(ledger["native_timing_stream"])["status"] == "unknown"
