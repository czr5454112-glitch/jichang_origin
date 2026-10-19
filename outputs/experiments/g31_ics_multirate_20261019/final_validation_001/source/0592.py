"""Lossless, opt-in native diagnostic streaming outside controller windows.

Only exported native sidecar objects are retired from memory. No policy state,
coarse request associations, native phase, or measured interval is discarded.
The externally pinned sealed manifest is required for complete reconstruction;
an open prefix is useful evidence but cannot establish complete coverage.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import time
import zlib

from .capture_native_request_timing import API_METHODS, NativeTimingCapture
from .native_request_timing import METHODS, analyze_native_timing


SCHEMA = "g31.native_timing_stream.v1"
CHUNK_SCHEMA = "g31.native_timing_stream_chunk.v1"


def _json(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _atomic_manifest(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_json(value))
    temporary.replace(path)


def _uint(value):
    return type(value) is int and value >= 0


def _require(condition, message):
    if not condition:
        raise ValueError("native_timing_stream:" + message)


class NativeTimingStream:
    """One namespace/epoch, append-only chunks and prefix manifests.

    A failed write poisons this stream. The caller retains its in-memory buffer;
    orphan/partial files remain forensic evidence and are never overwritten.
    The small manifest index grows with controller calls, not native span count.
    """
    def __init__(self, directory, *, session_identity, trace_epoch):
        _require(type(session_identity) is int and 0 < session_identity < 2**64, "invalid_namespace")
        _require(type(trace_epoch) is int and trace_epoch > 0, "invalid_epoch")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.manifest_path = self.directory / "manifest_000000.json"
        self.manifest = {"schema": SCHEMA, "status": "open", "session_identity": session_identity,
            "trace_epoch": trace_epoch, "chunks": [], "batch_count": 0, "envelope_count": 0,
            "span_row_count": 0, "capture_error_count": 0,
            "chunk_prepare_write_hash_ns": 0,
            "chunk_timing_scope": "Chunk preparation, serialization, write and hash only; excludes manifest commit, seal, later reads and final reconstruction. Whole process wall is separate.",
            "coverage_scope": "native_phase_sidecar_only",
            "coarse_request_ledger_streamed": False, "physics_subtracted": False}
        self.failed = False
        _atomic_manifest(self.manifest_path, self.manifest)

    def append(self, batches, envelopes, errors):
        _require(not self.failed and self.manifest["status"] == "open", "stream_not_writable")
        _require(bool(batches), "missing_export_batch")
        started = time.perf_counter_ns()
        index = len(self.manifest["chunks"])
        name = f"native_{index:06d}.json.gz"
        chunk = {"schema": CHUNK_SCHEMA, "index": index,
            "session_identity": self.manifest["session_identity"], "trace_epoch": self.manifest["trace_epoch"],
            "batch_offset": self.manifest["batch_count"], "envelope_offset": self.manifest["envelope_count"],
            "span_row_offset": self.manifest["span_row_count"],
            "capture_error_offset": self.manifest["capture_error_count"],
            "batches": batches, "call_envelopes": envelopes, "capture_errors": errors}
        try:
            # Exclusive creation makes prior evidence immutable, including an
            # orphan from a failed manifest commit. No retry overwrites it.
            with (self.directory/name).open("xb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                    compressed.write(_json(chunk))
            descriptor = {"index": index, "file": name, "sha256": file_sha256(self.directory/name),
                "batch_offset": chunk["batch_offset"], "envelope_offset": chunk["envelope_offset"],
                "span_row_offset": chunk["span_row_offset"], "capture_error_offset": chunk["capture_error_offset"],
                "batch_count": len(batches), "envelope_count": len(envelopes),
                "span_row_count": sum(len(batch["rows"]) for batch in batches), "capture_error_count": len(errors)}
            updated = {**self.manifest, "chunks": [*self.manifest["chunks"], descriptor]}
            for name in ("batch_count", "envelope_count", "span_row_count", "capture_error_count"):
                updated[name] += descriptor[name]
            updated["chunk_prepare_write_hash_ns"] += time.perf_counter_ns()-started
            # New prefix filename avoids replacing even the prior manifest.
            # A crash leaves the last externally referenced prefix intact.
            next_manifest = self.directory/f"manifest_{index+1:06d}.json"
            _require(not next_manifest.exists(), "manifest_already_exists")
            _atomic_manifest(next_manifest, updated)
            self.manifest_path = next_manifest
            self.manifest = updated
        except BaseException:
            self.failed = True
            raise
        return descriptor

    def seal(self, *, expected_call_count, expected_batch_count):
        _require(not self.failed and self.manifest["status"] == "open", "stream_not_sealable")
        _require(_uint(expected_call_count) and _uint(expected_batch_count), "invalid_final_counts")
        _require(expected_call_count == self.manifest["envelope_count"] and
                 expected_batch_count == self.manifest["batch_count"], "unexported_records")
        _require(bool(self.manifest["chunks"]), "empty_stream")
        updated = {**self.manifest, "status": "sealed", "expected_call_count": expected_call_count,
            "expected_batch_count": expected_batch_count}
        try:
            sealed_path = self.directory/"manifest_sealed.json"
            _require(not sealed_path.exists(), "manifest_already_exists")
            _atomic_manifest(sealed_path, updated)
            self.manifest_path = sealed_path
        except BaseException:
            self.failed = True
            raise
        self.manifest = updated
        return self.reference()

    def reference(self):
        return {"schema": SCHEMA, "manifest": str(self.manifest_path.resolve()),
            "manifest_sha256": file_sha256(self.manifest_path), "status": self.manifest["status"],
            "session_identity": self.manifest["session_identity"], "trace_epoch": self.manifest["trace_epoch"],
            "chunk_count": len(self.manifest["chunks"]), "envelope_count": self.manifest["envelope_count"],
            "batch_count": self.manifest["batch_count"], "span_row_count": self.manifest["span_row_count"],
            "capture_error_count": self.manifest["capture_error_count"], "failed": self.failed}


class StreamingNativeTimingCapture(NativeTimingCapture):
    """Same public forwarding contract, with ordinals independent of buffers."""
    def __init__(self, session, *, stream_directory, **kwargs):
        super().__init__(session, **kwargs)
        self.total_call_count = 0
        self.total_batch_count = len(self.batches)
        self.stream = NativeTimingStream(stream_directory, session_identity=self.session_identity,
                                        trace_epoch=self.trace_epoch)

    def _invoke(self, name, method, *args, **kwargs):
        _require(not self.stream.failed and self.stream.manifest["status"] == "open", "capture_not_writable")
        self.total_call_count += 1
        envelope = {"session_identity": self.session_identity, "trace_epoch": self.trace_epoch,
            "call_ordinal": self.total_call_count, "method": METHODS.index(API_METHODS[name])}
        if name.startswith("submit_protocol_"):
            payload = args[0] if args else kwargs.get("request", {})
            envelope["protocol_request_id"] = payload.get("request_id")
        elif name in {"protocol_request", "protocol_command"}:
            envelope["protocol_request_id"] = args[1] if len(args) > 1 else kwargs.get("request_id")
        envelope["start_ns"] = self._clock()
        try:
            return method(*args, **kwargs)
        except BaseException as exc:
            self.errors.append(type(exc).__name__ + ":" + str(exc))
            raise
        finally:
            envelope["end_ns"] = self._clock()
            self.envelopes.append(envelope)

    def take_completed(self):
        batch = super().take_completed()
        self.total_batch_count += 1
        return batch

    def flush(self):
        """Only after full controller return/output, never inside service work."""
        descriptor = self.stream.append(self.batches, self.envelopes, self.errors)
        # Commit has succeeded; buffers can now retire without losing evidence.
        self.batches, self.envelopes, self.errors = [], [], []
        return descriptor

    def seal(self):
        _require(not self.batches and not self.envelopes and not self.errors, "unflushed_records")
        return self.stream.seal(expected_call_count=self.total_call_count,
                                expected_batch_count=self.total_batch_count)


class PolicyStreamingNativeTimingCapture(StreamingNativeTimingCapture):
    def observe_protocol_control_policy(self, owner):
        return self._invoke("observe_protocol_control_policy", self._session.observe_protocol_control_policy, owner)


class RecentStreamingNativeTimingCapture(PolicyStreamingNativeTimingCapture):
    def observe_protocol_control_policy_recent(self, owner, forecast_validity):
        return self._invoke("observe_protocol_control_policy_recent",
            self._session.observe_protocol_control_policy_recent, owner, forecast_validity)


def streaming_capture_session(session, **kwargs):
    if getattr(type(session), "observe_protocol_control_policy_recent", None) is not None:
        cls = RecentStreamingNativeTimingCapture
    elif getattr(type(session), "observe_protocol_control_policy", None) is not None:
        cls = PolicyStreamingNativeTimingCapture
    else:
        cls = StreamingNativeTimingCapture
    return cls(session, **kwargs)


def reconstruct_native_timing(reference):
    """Return the exact retained-mode native_timing object or fail closed.

    A hash in an independently saved final ledger binds the final manifest. It
    prevents an omitted final shard being presented as a shorter complete run.
    Phase validity is checked separately: error/overflow records stay verbatim.
    """
    path = Path(reference["manifest"])
    _require(reference.get("schema") == SCHEMA and reference.get("status") == "sealed" and
             reference.get("failed") is False, "unsealed_reference")
    _require(file_sha256(path) == reference["manifest_sha256"], "manifest_hash_mismatch")
    manifest = json.loads(path.read_bytes())
    _require(manifest.get("schema") == SCHEMA and manifest.get("status") == "sealed", "unsealed_manifest")
    _require(manifest.get("coverage_scope") == "native_phase_sidecar_only" and
             manifest.get("coarse_request_ledger_streamed") is False and
             manifest.get("physics_subtracted") is False, "scope_changed")
    for name in ("session_identity", "trace_epoch", "batch_count", "envelope_count", "span_row_count", "capture_error_count"):
        _require(_uint(manifest.get(name)) and manifest[name] == reference.get(name), "reference_mismatch:"+name)
    _require(manifest["session_identity"] > 0 and manifest["trace_epoch"] > 0, "invalid_namespace")
    _require(reference.get("chunk_count") == len(manifest["chunks"]) > 0, "chunk_count_mismatch")
    _require(manifest.get("expected_call_count") == manifest["envelope_count"] and
             manifest.get("expected_batch_count") == manifest["batch_count"], "final_counts_mismatch")
    result = {"batches": [], "call_envelopes": [], "capture_errors": []}
    counts = {"batch": 0, "envelope": 0, "span_row": 0, "capture_error": 0}
    expected_files = {f"native_{index:06d}.json.gz" for index in range(len(manifest["chunks"]))}
    _require({p.name for p in path.parent.glob("native_*.json.gz")} == expected_files, "unlisted_or_missing_chunks")
    for index, descriptor in enumerate(manifest["chunks"]):
        name = f"native_{index:06d}.json.gz"
        _require(descriptor.get("index") == index and descriptor.get("file") == name, "chunk_order_mismatch")
        chunk_path = path.parent/name
        _require(file_sha256(chunk_path) == descriptor["sha256"], "chunk_hash_mismatch")
        with gzip.open(chunk_path, "rt", encoding="utf-8") as stream:
            chunk = json.load(stream)
        _require(chunk.get("schema") == CHUNK_SCHEMA and chunk.get("index") == index, "chunk_identity_mismatch")
        for name in ("session_identity", "trace_epoch"):
            _require(chunk.get(name) == manifest[name], "chunk_namespace_mismatch")
        actual = {"batch": len(chunk["batches"]), "envelope": len(chunk["call_envelopes"]),
            "span_row": sum(len(batch["rows"]) for batch in chunk["batches"]),
            "capture_error": len(chunk["capture_errors"])}
        _require(actual["batch"] > 0, "missing_export_batch")
        for name, value in actual.items():
            _require(_uint(descriptor.get(name+"_count")) and value == descriptor[name+"_count"] and
                     chunk.get(name+"_offset") == descriptor.get(name+"_offset") == counts[name], "chunk_range_mismatch")
            counts[name] += value
        for key in result:
            result[key].extend(chunk[key])
    for key, value in counts.items():
        _require(value == manifest[key+"_count"], "total_count_mismatch")
    # Validate namespace/ordinal continuity here even before the complete phase
    # validator; never silently repair, sort, or deduplicate raw evidence.
    for ordinal, envelope in enumerate(result["call_envelopes"], 1):
        _require(envelope.get("call_ordinal") == ordinal and
            all(envelope.get(key) == manifest[key] for key in ("session_identity", "trace_epoch")), "envelope_identity_mismatch")
    for batch in result["batches"]:
        _require(all(batch.get(key) == manifest[key] for key in ("session_identity", "trace_epoch")), "batch_namespace_mismatch")
    return result


def analyze_streamed_native_timing(reference):
    """Use the existing validator unchanged; missing/tampered data is unknown."""
    try:
        native = reconstruct_native_timing(reference)
        report = analyze_native_timing(native["batches"], native["call_envelopes"])
        if native["capture_errors"]:
            report["status"] = "unknown"
            report["errors"].extend(native["capture_errors"])
        return report
    except (OSError, ValueError, KeyError, TypeError, EOFError, AttributeError, IndexError, OverflowError, zlib.error) as error:
        return {"status": "unknown", "errors": [str(error)], "physics_subtracted_ns": 0,
            "complete_request_100ms_certified": False, "refined_per_request_totals_available": False}
