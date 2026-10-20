"""Synchronous bounded JSON RPC, owning only its own predictor process tree."""
from __future__ import annotations
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from . import bounded_windows_job
from . import json_prediction_image as codec


class Client:
    def __init__(self, image, version, mode, *, timeout, stderr):
        if type(timeout) not in (int, float) or not 0 < timeout < float('inf'):
            raise ValueError('invalid_lifetime_timeout')
        self.image, self.version, self.mode = Path(image).resolve(), version, mode
        self.started_ns = time.perf_counter_ns()
        self.deadline = time.monotonic() + timeout
        self.job = bounded_windows_job.Job()
        self.job_lock = threading.Lock()
        self.expired = threading.Event()
        self.watchdog = None
        self.process = None
        self.reader = None
        self.messages = queue.Queue(maxsize=2)
        self.stopping = threading.Event()
        self.sequence = 0
        self.ids = set()
        self.closed = False
        self.ledger = []
        admission = uuid.uuid4().hex
        self.command = [sys.executable, '-I', '-S', str(self.image/'scripts/experiments/g31_ics_circulation/json_prediction_worker.py'),
            '--image', str(self.image), '--version', version, '--mode', mode, '--admission', admission]
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=stderr, cwd=self.image)
            self.job.assign(self.process)
            # The watchdog closes this owned process tree even if a pipe write
            # blocks. The enclosing 120s Job also includes Popen/assignment.
            self.watchdog = threading.Timer(max(0., self.deadline-time.monotonic()), self._expire)
            self.watchdog.daemon = True
            self.watchdog.start()
            self.reader = threading.Thread(target=self._reader, daemon=True)
            self.reader.start()
            self.process.stdin.write((admission+'\n').encode('ascii'))
            self.process.stdin.flush()
            self.ready = self._next()
            if (self.ready.get('kind') != 'ready' or self.ready.get('version') != version
                    or self.ready.get('mode') != mode or self.ready.get('native_authority') is not False):
                raise ValueError('worker_READY_identity')
            self.ready_ns = time.perf_counter_ns()
        except BaseException:
            self.abort()
            raise

    def _reader(self):
        def publish(value):
            while not self.stopping.is_set():
                try:
                    self.messages.put(value, timeout=.05)
                    return
                except queue.Full:
                    pass
        try:
            while True:
                value = codec.read_frame(self.process.stdout)
                publish((value, None))
                if value is None:
                    return
        except BaseException as error:
            publish((None, error))

    def _next(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.expired.is_set():
            raise TimeoutError('RPC_lifetime_timeout')
        try:
            value, error = self.messages.get(timeout=remaining)
        except queue.Empty as error:
            raise TimeoutError('RPC_lifetime_timeout') from error
        if self.expired.is_set():
            raise TimeoutError('RPC_lifetime_timeout')
        if error is not None:
            raise error
        if value is None:
            raise ValueError('RPC_unexpected_EOF')
        return value

    def _close_job(self):
        with self.job_lock:
            self.job.close()

    def _expire(self):
        self.expired.set()
        self._close_job()

    def predict(self, request_id, snapshot):
        # Caller-side admission precedes schema validation and serialization.
        start = time.perf_counter_ns()
        if self.closed:
            raise ValueError('RPC_closed')
        request = {'kind': 'predict', 'version': self.version, 'sequence': self.sequence+1,
                   'request_id': request_id, 'snapshot': snapshot}
        try:
            raw = codec.encode(request)
            self.process.stdin.write(raw)
            self.process.stdin.flush()
            result = self._next()
            if (result.get('kind') != 'prediction' or result.get('version') != self.version
                    or result.get('sequence') != self.sequence+1 or result.get('request_id') != request_id
                    or result.get('native_authority') is not False or result.get('complete_100ms_certified') is not False):
                raise ValueError('RPC_reply_identity')
            self.sequence += 1
            decoded = time.perf_counter_ns()
            sample = {'sequence': self.sequence, 'request_id': request_id,
                'caller_admitted_ns': start, 'caller_decoded_ns': decoded,
                'request': codec.decode(raw), 'response': result}
            self.ledger.append(sample)
            end = time.perf_counter_ns()
            sample.update(caller_body_finished_ns=end, caller_elapsed_ns=end-start,
                caller_bookkeeping_ns=end-decoded,
                cold_through_reply_ns=end-self.started_ns if self.sequence == 1 else None)
            # The campaign additionally timestamps outside this function call,
            # retaining these final field writes and the actual return tail.
            return result
        except BaseException:
            self.abort()
            raise

    def close(self):
        start = time.perf_counter_ns()
        if self.closed:
            raise ValueError('RPC_already_closed')
        try:
            self.process.stdin.write(codec.encode({'kind':'close', 'version':self.version, 'sequence':self.sequence+1}))
            self.process.stdin.flush()
            self.process.stdin.close()
            result = self._next()
            if (result.get('kind') != 'closed' or result.get('version') != self.version
                    or result.get('requests') != self.sequence or result.get('source_unchanged') is not True):
                raise ValueError('RPC_invalid_shutdown')
            self.process.wait(timeout=max(.001, self.deadline-time.monotonic()))
            if self.process.returncode != 0:
                raise ValueError('RPC_nonzero_shutdown')
            # Any extra JSON response or non-JSON stdout after CLOSED is a failure.
            self.reader.join(timeout=max(.001, self.deadline-time.monotonic()))
            if self.reader.is_alive():
                raise TimeoutError('RPC_reader_shutdown')
            trailer, error = self.messages.get_nowait()
            if trailer is not None or error is not None or not self.messages.empty():
                raise ValueError('RPC_extra_output')
            self.shutdown = {'reply': result, 'close_admitted_ns': start,
                'protocol_closed_ns': time.perf_counter_ns(), 'process_exit_code': self.process.returncode}
        finally:
            self.abort()
        if self.expired.is_set():
            raise TimeoutError('RPC_lifetime_timeout')
        self.shutdown['close_finished_ns'] = time.perf_counter_ns()
        return self.shutdown

    def abort(self):
        self.closed = True
        self.stopping.set()
        if self.watchdog is not None:
            self.watchdog.cancel()
        try:
            self._close_job()
        finally:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.kill()  # only this unreleased/owned child
                self.process.wait()
                for stream in (self.process.stdin, self.process.stdout):
                    if stream is not None and not stream.closed:
                        try:
                            stream.close()
                        except OSError:
                            pass
            if self.reader is not None:
                self.reader.join(timeout=1.)
            if self.watchdog is not None and self.watchdog is not threading.current_thread():
                self.watchdog.join(timeout=1.)
                if self.watchdog.is_alive():
                    self.expired.set()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, trace):
        if not self.closed:
            if kind is None:
                self.close()
            else:
                self.abort()
