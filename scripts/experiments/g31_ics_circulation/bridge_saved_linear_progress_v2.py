"""Bounded progress correction only; frozen linear001 semantics stay intact.

Only the two shared whole-document reads have individual decode stages. The
bootstrap's ordinary row reads are counted every256, never cached or skipped.
The first instrumentation failure is sticky even if a policy catches it.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
from pathlib import Path
import time
from . import bridge_saved_linear_core as old

base, r, original, require, full = old.base, old.r, old.original, old.require, old.full
source_proof, ordered_equal, semantic_equal = old.source_proof, old.ordered_equal, old.semantic_equal
transformed, observer_result, replay_type = old.transformed, old.observer_result, old.replay_type
native_host = old.native_host


class Progress(old.Progress):
    LIMIT = 1024
    def __init__(self, directory, clock=time.perf_counter_ns):
        super().__init__(directory, clock)
        self.first_error = None
        self.first_failure = None
        self.last_success = None
        self.closed = False
        self.reporting_original_error = None

    def remember(self, error, event, fields):
        if self.first_error is None:
            self.first_error = error
            self.first_failure = {'record_count': self.count, 'event': event,
                'fields': dict(fields), 'error_type': type(error).__name__,
                'error': str(error), 'last_success': self.last_success}
        self.failed = True

    def check(self):
        if self.first_error is not None:
            raise self.first_error

    def emit(self, event, **fields):
        self.check()
        try:
            require(not self.closed and self.count < self.LIMIT, 'linear_progress_budget_or_failure')
            value = {'record': self.count, 'at_ns': self.clock(), 'event': event, **fields}
            text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n'
            require(len(text.encode('utf8')) <= 4096, 'linear_progress_row_limit')
            require(self.stream.write(text) == len(text), 'linear_progress_short_write')
            self.stream.flush()
            self.count += 1
            self.last_success = {'record': value['record'], 'event': event, **fields}
        except BaseException as error:
            self.remember(error, event, fields)
            raise

    @contextmanager
    def stage(self, name):
        self.check()
        start = self.clock()
        self.emit('stage_start', stage=name)
        try:
            yield
        except BaseException as error:
            if error is self.reporting_original_error:
                raise
            if self.first_error is not None:
                if error is self.first_error:
                    raise
                raise self.first_error from error
            # An ordinary checker exception retains priority over any failure
            # encountered while trying to report it.
            try:self.emit('stage_failed', stage=name, error_type=type(error).__name__)
            except BaseException:self.reporting_original_error = error
            raise
        else:
            self.check()
            self.emit('stage_end', stage=name, elapsed_ns=self.clock()-start)

    def close(self):
        if self.closed:
            self.check()
            return
        try:
            try:self.stream.flush()
            except BaseException as error:self.remember(error, 'close_flush', {})
        finally:
            try:self.stream.close()
            except BaseException as error:self.remember(error, 'close_handle', {})
            self.closed = True
        self.check()


class SharedReads(old.SharedReads):
    def __init__(self, directory, progress, loader=base.gzread):
        super().__init__(directory, progress, loader)
        self.other_reads = 0

    def read(self, path):
        self.progress.check()
        path = Path(path).resolve()
        if path not in self.allowed:
            value = self.loader(path)
            self.progress.check()
            self.other_reads += 1
            if self.other_reads % 256 == 0:
                self.progress.emit('bootstrap_other_read_progress', completed=self.other_reads)
            return value
        self.requests[path] = self.requests.get(path, 0)+1
        if path in self.values:
            self.progress.emit('shared_decoded_read', path=path.name, logical_reads=self.requests[path])
            return self.values[path]
        with self.progress.stage('decode:'+str(path)):
            value = self.loader(path)
        self.decodes[path] = self.decodes.get(path, 0)+1
        self.values[path] = value
        return value

    def finish(self):
        self.progress.check()
        result = super().finish()
        self.progress.emit('bootstrap_other_read_complete', completed=self.other_reads)
        return result


def bind(plan, redirect, progress):
    # Same function code and every original substitution/guard; only the
    # progress-aware loader class resolves differently in this private scope.
    function = r.original.clone(old.bind, {**old.bind.__globals__, 'SharedReads': SharedReads})
    require(function.__code__ is old.bind.__code__, 'linear_progress_changed_bind')
    return function(plan, redirect, progress)


def progress_contract():
    return {'schema': 'g31.bridge.linear_progress.v2', 'record_limit': 1024,
        'row_interval': 256, 'individual_decode_stages': ['raw_final.json.gz', 'input.json.gz'],
        'other_reads': 'Every original read still happens; no caching, per-row stage or guard removal. One counter event per256 completed ordinary reads.',
        'first_failure': 'First progress capacity/write/flush/close exception stays sticky; outer verifier cannot certify success after it. Original non-instrumentation failure remains primary if reporting that failure also fails.',
        'frozen_semantics': 'Original linear001 bind code and original hash, ordered actual arguments, actor copy, readonly observer and physical checks are unchanged.'}
