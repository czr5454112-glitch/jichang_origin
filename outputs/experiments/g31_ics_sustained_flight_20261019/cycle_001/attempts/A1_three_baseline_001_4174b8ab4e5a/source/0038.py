"""Resident detached process: one active request plus one replaceable pending request.

The foreground takes a complete closed result body with get_nowait and an atomic
file read. No join, model call, waiting for readiness, or native authority occurs
in poll. Process warmup and shutdown are outside the native episode.
"""
from __future__ import annotations
import json
import multiprocessing
from pathlib import Path
import queue
import time
import traceback
from . import foundation_repeated_domain as model


def process(tasks, results, ready, folder):
    ready.set()
    while True:
        task = tasks.get()
        if task is None:
            return
        start, cpu = time.perf_counter_ns(), time.process_time_ns()
        result = {'request_id': task['request_id'], 'owner': task['owner'],
            'source_sha256': task['source_sha256'], 'execution_authority': False,
            'worker_started_ns': start, 'status': 'unknown_failed'}
        try:
            result['model_report'] = model.evaluate(task['evidence'], task['actions'])
            result['status'] = 'completed_detached_prediction'
        except Exception:
            result['exception'] = traceback.format_exc()
        result.update(worker_completed_ns=time.perf_counter_ns(),
            worker_wall_ms=(time.perf_counter_ns()-start)/1e6,
            worker_cpu_ms=(time.process_time_ns()-cpu)/1e6)
        path = Path(folder) / (task['request_id'] + '.json')
        temporary = path.with_suffix('.pending')
        temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf8')
        temporary.replace(path)
        results.put(task['request_id'])


class ResidentWorker:
    def __init__(self, owner, folder):
        model.require(owner in ('A', 'B'), 'resident_owner')
        self.owner, self.folder = owner, Path(folder)
        model.require(not self.folder.exists(), 'resident_fresh_output')
        self.folder.mkdir(parents=True)
        context = multiprocessing.get_context('spawn')
        self.tasks, self.results = context.Queue(1), context.Queue(1)
        self.ready = context.Event()
        self.process = context.Process(target=process, args=(self.tasks, self.results, self.ready, str(self.folder)))
        self.active, self.pending, self.sequence = None, None, 0
        self.records, self.timing = [], {}

    def start(self):
        start = time.perf_counter_ns()
        self.process.start()
        model.require(self.ready.wait(20), 'resident_ready_timeout')
        self.timing['cold_start_and_ready_wall_ms'] = (time.perf_counter_ns()-start)/1e6

    def submit(self, evidence, actions):
        start = time.perf_counter_ns()
        model.require(evidence['owner'] == self.owner and self.ready.is_set(), 'resident_same_owner_ready')
        self.sequence += 1
        request = {'request_id': f'{self.owner}-{self.sequence:05d}', 'owner': self.owner,
            'evidence': model.plain(evidence), 'source_sha256': model.digest(evidence),
            'actions': list(actions), 'enqueued_ns': time.perf_counter_ns()}
        disposition = 'enqueued'
        if self.active is None:
            self.tasks.put_nowait(request); self.active = request
        else:
            disposition = 'replaced_pending' if self.pending else 'pending'
            self.pending = request
        self.records.append({'request_id': request['request_id'], 'kind': disposition,
            'sim_time': evidence['at'], 'wall_ns': time.perf_counter_ns(),
            'foreground_pack_enqueue_wall_ms': (time.perf_counter_ns()-start)/1e6})
        return request['request_id']

    def poll(self, now):
        start = time.perf_counter_ns()
        try:
            identity = self.results.get_nowait()
        except queue.Empty:
            self.records.append({'kind': 'poll_not_ready', 'sim_time': now,
                'wall_ns': start, 'poll_wall_ms': (time.perf_counter_ns()-start)/1e6})
            return None
        model.require(self.active is not None and identity == self.active['request_id'], 'resident_result_identity')
        result = json.loads((self.folder / (identity + '.json')).read_text(encoding='utf8'))
        model.require(result['request_id'] == identity and result['owner'] == self.owner
            and result['source_sha256'] == self.active['source_sha256'] and result['execution_authority'] is False,
            'resident_closed_result_binding')
        self.active = None
        if self.pending is not None:
            self.tasks.put_nowait(self.pending); self.active, self.pending = self.pending, None
        self.records.append({'kind': 'result_body_collected', 'request_id': identity, 'sim_time': now,
            'wall_ns': start, 'poll_and_body_read_wall_ms': (time.perf_counter_ns()-start)/1e6})
        return result

    def close(self):
        start = time.perf_counter_ns()
        self.pending = None
        try:
            self.tasks.put_nowait(None)
            self.process.join(20)
        finally:
            if self.process.is_alive():
                self.process.terminate(); self.process.join(5)
            self.tasks.cancel_join_thread(); self.tasks.close()
            self.results.cancel_join_thread(); self.results.close()
        self.timing['after_native_shutdown_wall_ms'] = (time.perf_counter_ns()-start)/1e6
