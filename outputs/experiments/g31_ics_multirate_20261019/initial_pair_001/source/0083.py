"""Bounded, lossless diagnostic sinks; no native policy or clock substitution.

JSON serialization remains inside the inherited ServiceTape invocation. RAM is
a diagnostic comparison only: hard kill loses its prefix. Spool preserves the
immediately flushed UTF8 prefix under the same non-fsync contract as reference.
Compression/export is deferred to close and remains real campaign work.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
from . import probe_original_route_update as reference

MAX_BYTES = 256 * 1024 * 1024
MAX_ROWS = 160000
MODES = ('ram', 'spool')


class CaptureFailure(RuntimeError):
    pass


class EncodedSink:
    def __init__(self, path, *, mode, max_bytes=MAX_BYTES, max_rows=MAX_ROWS):
        if mode not in MODES or type(max_bytes) is not int or type(max_rows) is not int or min(max_bytes,max_rows) <= 0:
            raise ValueError('invalid_fixed_capture_limits')
        self.path = Path(path); self.spool_path = Path(str(path) + '.spool.jsonl')
        if self.path.exists() or (mode == 'spool' and self.spool_path.exists()):
            raise FileExistsError('preserve_existing_capture')
        self.mode, self.max_bytes, self.max_rows = mode, max_bytes, max_rows
        self.rows = self.encoded_bytes = self.flushed_rows = self.write_attempts = 0
        self.failure = None; self.closed = False; self.export_attempted = False
        self._pending = False; self._digest = hashlib.sha256(); self._chunks = []
        self._file = self.spool_path.open('xb') if mode == 'spool' else None

    def _fail(self, reason, **extra):
        if self.failure is None: self.failure = {'reason': reason, **extra}
        raise CaptureFailure(reason)

    def _guard(self):
        if self.closed: raise CaptureFailure('capture_closed')
        if self.failure is not None: raise CaptureFailure('sticky_capture_failure:' + self.failure['reason'])

    def mark_failure(self, reason, **extra):
        if self.failure is None: self.failure = {'reason': reason, **extra}

    def write(self, text):
        self._guard(); self.write_attempts += 1
        if self._pending: self._fail('previous_row_not_flushed')
        if type(text) is not str or not text.endswith('\n') or '\n' in text[:-1] or '\r' in text:
            self._fail('not_one_complete_json_text_line')
        try:
            # gzip.open(...,'wt',newline=None) on the host performs the same
            # newline translation. Preserve literal Unicode and strict UTF8.
            encoded = text.replace('\n', os.linesep).encode('utf8', errors='strict')
        except UnicodeError as error:
            self.mark_failure('utf8_encoding_failed', error=repr(error)); raise
        if self.rows == self.max_rows or len(encoded) > self.max_bytes-self.encoded_bytes:
            self._fail('fixed_capacity_exceeded', rejected_encoded_bytes=len(encoded),
                rejected_sha256=hashlib.sha256(encoded).hexdigest(),
                failed_call_row_not_retained=True)
        if self.mode == 'ram':
            try: self._chunks.append(encoded)
            except MemoryError:
                self.mark_failure('allocation_failed'); raise
        else:
            try:
                written = self._file.write(encoded)
                if written != len(encoded): self._fail('short_spool_write', expected=len(encoded), returned=written)
            except BaseException as error:
                self.mark_failure('spool_write_failed', error=repr(error)); raise
        self._digest.update(encoded); self.encoded_bytes += len(encoded); self.rows += 1
        self._pending = True
        return len(text)

    def flush(self):
        self._guard()
        if self.mode == 'spool':
            try: self._file.flush()
            except BaseException as error:
                self.mark_failure('spool_flush_failed', error=repr(error)); raise
        self.flushed_rows = self.rows; self._pending = False

    def snapshot(self):
        return {'schema': 'g31.deferred_service_capture.v1', 'mode': self.mode,
            'max_bytes': self.max_bytes, 'max_rows': self.max_rows,
            'rows': self.rows, 'flushed_rows': self.flushed_rows, 'encoded_bytes': self.encoded_bytes,
            'write_attempts': self.write_attempts, 'accepted_encoded_sha256': self._digest.hexdigest(),
            'failure': None if self.failure is None else dict(self.failure),
            'closed': self.closed, 'export_attempted': self.export_attempted,
            'evidence_complete': self.closed and self.failure is None and self.flushed_rows == self.rows,
            'hardkill_prefix_durability': 'none' if self.mode == 'ram' else 'flushed_uncompressed_spool_no_fsync_or_powerloss_guarantee',
            'gzip_path': str(self.path), 'spool_path': str(self.spool_path) if self.mode == 'spool' else None}

    def close(self):
        if self.closed: return self.snapshot()
        if self.export_attempted:
            self.closed = True
            return self.snapshot()
        # A failed call has already raised. Still preserve its accepted prefix
        # on an ordinary error unwind; do not relabel partial evidence complete.
        if self._file is not None:
            try: self._file.flush(); self._file.close()
            except BaseException as error:
                self.mark_failure('spool_final_flush_failed', error=repr(error))
                self.closed = True
                raise
        elif self._pending:
            self.flushed_rows = self.rows; self._pending = False
        self.export_attempted = True
        try:
            with self.path.open('xb') as raw:
                with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=1) as compressed:
                    if self.mode == 'ram':
                        for chunk in self._chunks: compressed.write(chunk)
                    else:
                        with self.spool_path.open('rb') as source:
                            for chunk in iter(lambda: source.read(1024*1024), b''): compressed.write(chunk)
        except BaseException as error:
            self.mark_failure('gzip_export_failed', error=repr(error)); raise
        finally:
            self.closed = True
        # Keep failed RAM chunks for inspection if export failed; after success
        # the immutable gzip artifact is the canonical diagnostic capture.
        self._chunks.clear()
        return self.snapshot()


class DeferredServiceTape(reference.ServiceTape):
    """Original call/role/clock/JSON code, only begin/close storage differs."""
    def __init__(self, native, *, mode='spool', max_bytes=MAX_BYTES, max_rows=MAX_ROWS):
        super().__init__(native)
        self._capture_options = {'mode': mode, 'max_bytes': max_bytes, 'max_rows': max_rows}
        self.capture_report = None

    def begin(self, path):
        if self.stream is not None or self.capture_report is not None:
            raise CaptureFailure('tape_already_started')
        self.stream = EncodedSink(path, **self._capture_options)

    def close(self):
        if self.stream is None: return
        sink = self.stream
        if self.count != sink.rows:
            sink.mark_failure('api_row_denominator_mismatch', api_calls=self.count, accepted_rows=sink.rows)
        try:
            report = sink.close()
            self.capture_report = report
            # Do not replace an in-flight native/serialization/capacity error.
            # If a caller swallowed that error, normal close still fails closed.
            if not report['evidence_complete'] and sys.exception() is None:
                raise CaptureFailure('incomplete_diagnostic_capture')
        finally:
            self.capture_report = sink.snapshot()
            self.stream = None


def unchanged_invocation_proof():
    assert DeferredServiceTape.__getattr__ is reference.ServiceTape.__getattr__
    assert DeferredServiceTape.role is reference.ServiceTape.role
    assert DeferredServiceTape.observe_protocol_control_policy is reference.ServiceTape.observe_protocol_control_policy
    assert DeferredServiceTape.observe_protocol_control_policy_recent is reference.ServiceTape.observe_protocol_control_policy_recent
    return {'original_source_sha256': hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
        'inherited_getattr_identical_function_and_bytecode': True,
        'json_before_api_return': True, 'native_execution': False,
        'scope': 'Diagnostic-storage candidate only; no historical cost subtraction or speed certification.'}
