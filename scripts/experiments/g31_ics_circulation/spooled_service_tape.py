"""Spool-only v2: fixed capture limits, original invocation, durable prefix.

The old pure comparison is immutable. JSON, UTF8 encoding and file flush remain
before each API return. Gzip level1 export and evidence hashing occur at close,
inside the measured child/campaign. Flush is not fsync or a power-loss promise.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import time
from . import deferred_service_tape as prior

MAX_BYTES, MAX_ROWS = prior.MAX_BYTES, prior.MAX_ROWS
CaptureFailure = prior.CaptureFailure


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): digest.update(chunk)
    return digest.hexdigest()


class SpoolSink(prior.EncodedSink):
    def __init__(self, path):
        super().__init__(path, mode='spool', max_bytes=MAX_BYTES, max_rows=MAX_ROWS)

    def close(self):
        if self.closed: return self.snapshot()
        failure = None
        handle = self._file
        if handle is not None:
            try:
                handle.flush()
            except BaseException as error:
                failure = error
                self.mark_failure('spool_final_flush_failed', error=repr(error))
            finally:
                try:
                    handle.close()
                except BaseException as error:
                    self.mark_failure('spool_final_close_failed', error=repr(error))
                    if failure is None: failure = error
                finally:
                    self._file = None
            if failure is not None:
                self.closed = True
                raise failure
        return super().close()


class SpoolServiceTape(prior.reference.ServiceTape):
    """Only begin/close storage changes; inherited invocation is untouched."""
    def __init__(self, native):
        super().__init__(native)
        self.capture_report = None

    def begin(self, path):
        if self.stream is not None or self.capture_report is not None:
            raise CaptureFailure('tape_already_started')
        self.stream = SpoolSink(path)

    def close(self):
        if self.stream is None: return
        active_error = sys.exception()
        sink = self.stream
        started = time.perf_counter_ns()
        error = None
        if self.count != sink.rows:
            sink.mark_failure('api_row_denominator_mismatch', api_calls=self.count, accepted_rows=sink.rows)
        try:
            sink.close()
            if not sink.snapshot()['evidence_complete']:
                raise CaptureFailure('incomplete_diagnostic_capture')
        except BaseException as caught:
            error = caught
        finally:
            self.stream = None
            report = sink.snapshot()
            report.update(schema='g31.spool_only_service_capture.v2', api_count=self.count,
                close_started_ns=started, close_export_finished_ns=time.perf_counter_ns(),
                original_inflight_error=None if active_error is None else repr(active_error),
                close_error=None if error is None else repr(error))
            try:
                report['artifact_sha256'] = {path.name: sha(path) for path in
                    (sink.path, sink.spool_path) if path.is_file()}
                report['close_hashes_finished_ns'] = time.perf_counter_ns()
                with sink.path.with_name('diagnostic_capture.json').open('x', encoding='utf8') as stream:
                    json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
            except BaseException as caught:
                sink.mark_failure('capture_receipt_failed', error=repr(caught))
                report.update(evidence_complete=False, failure=sink.snapshot()['failure'], receipt_error=repr(caught))
                if error is None: error = caught
            self.capture_report = report
        # The original exception, when unwinding a native/capture call, remains
        # primary. A normal close after a swallowed error still fails closed.
        if error is not None and active_error is None: raise error


def unchanged_invocation_proof():
    for name in ('__getattr__', 'role', 'observe_protocol_control_policy', 'observe_protocol_control_policy_recent'):
        assert getattr(SpoolServiceTape, name) is getattr(prior.reference.ServiceTape, name)
    return {'inherited_getattr_identical_function_and_bytecode': True,
        'fixed_max_bytes': MAX_BYTES, 'fixed_max_rows': MAX_ROWS, 'mode': 'spool',
        'json_utf8_flush_inside_api_return': True, 'no_native_execution': True,
        'scope': 'One diagnostic-pipeline sample; not an algorithmic speedup or historical subtraction.'}
