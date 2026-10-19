"""Detached slow advice and conservative current-time screens, without authority.

The native event clock is not a wall-clock simulator. Process concurrency and
simulated deadlines are reported separately; this module never issues commands.
"""
from __future__ import annotations

import json
import math
import multiprocessing
from pathlib import Path
import time
import traceback

from . import foundation_later_control as control
from . import foundation_later_seed as model
from . import live_obligation_recollection_policy as collection

SCHEMA = 'g31.foundation.multirate_advice.v1'
SOURCE_TTL = .05  # Existing collection rule; not a general forecast lifetime.


def require(condition, reason):
    if not condition:
        raise ValueError('multirate:' + reason)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def advice_from_evidence(evidence, reference):
    require(evidence['owner'] == 'B' and evidence['phase'] == 'first_reuse_route', 'B_reuse_probe_only')
    endpoints = evidence['information']['raw_endpoints']
    own = endpoints['command']['last_delivered_ack']['planning_snapshot_v3']
    peer = [row for row in endpoints['received'] if row['capture']['capture_v2']['local_capture']['message_id']
            == evidence['collection']['peer_message']]
    require(len(peer) == 1, 'exact_delivered_peer')
    captures = [row['capture']['capture_v2']['local_capture'] for row in (own, peer[0])]
    source_at = min(row['captured_at'] for row in captures)
    now = evidence['at']
    require(finite(source_at) and source_at <= now and now - source_at <= SOURCE_TTL,
            'original_collection_freshness')
    tray = collection.local_target(endpoints['view'], evidence['collection']['trigger_tray'], evidence['phase'])
    service_at = evidence['information']['bundle']['trays']['L']['service_ready_at']
    require(finite(service_at) and now + .01 < service_at, 'original_future_route_window')
    identity = {'evidence_sha256': control.digest(evidence), 'reference_sha256': control.digest(reference),
                'owner': 'B', 'capture_sim_time': now}
    return {**identity, 'schema': SCHEMA, 'advice_id': control.digest(identity),
        'model_version': model.VERSION, 'source_captured_at': source_at,
        'source_collection_valid_through': source_at + SOURCE_TTL,
        'use_by': service_at - .01, 'use_by_exclusive': True,
        'deadline_derivation': 'existing strict route guard now + .01 < actual retained service_ready_at',
        'planned_handoff_time': service_at, 'tray_id': 'L', 'tray_generation': tray['generation'],
        'target': control.plain(tray), 'immutable_prefix_id': control.digest(tray['committed_prefix']),
        'continuation_id': evidence['collection']['root'],
        'dependency_scope': 'entire supported five-job domain; no local suffix reuse proof',
        'candidate_ids': list(control.PHASE_ACTIONS[evidence['phase']]),
        'original_reference': control.plain(reference), 'execution_authority': False,
        'native_protection_certified': False, 'current_capability_id': None}


def screen_current(advice, view, owned_rows):
    """Screen actual current local data; even success requires a new collection.

No submitted command, ACK, inventory or capability is inferred from a forecast.
Old-source expiry conservatively requests full refresh; it is never extended.
"""
    require(advice.get('schema') == SCHEMA and advice.get('execution_authority') is False,
            'detached_advice_required')
    now = view.get('now')
    require(finite(now) and now >= advice['capture_sim_time'], 'current_monotone_time')
    reasons = []
    if view.get('owner_id') != advice['owner']:
        reasons.append('wrong_current_owner')
    if now >= advice['use_by']:
        reasons.append('action_deadline_missed')
    current = [tray for tray in view.get('trays', []) if tray['tray_id'] == advice['tray_id']]
    if len(current) != 1:
        reasons.append('target_not_currently_owned')
    else:
        target = current[0]
        if target.get('generation') != advice['tray_generation']:
            reasons.append('tray_generation_changed')
        if any(target.get(field) != advice['target'].get(field) for field in collection.TARGET_FIELDS):
            reasons.append('target_or_immutable_prefix_changed')
    unresolved = [identity for identity, row in owned_rows.items() if row['kind'] in collection.PHYSICAL_KINDS
                  and (row.get('terminal') is not True or (row.get('ack') or {}).get('status')
                       not in collection.TERMINAL_BY_KIND[row['kind']]
                       or not finite((row.get('ack') or {}).get('delivered_at'))
                       or row['ack']['delivered_at'] > now)]
    if unresolved:
        reasons.append('physical_ACK_unknown_or_pending')
    source_expired = now - advice['source_captured_at'] > SOURCE_TTL
    if source_expired:
        reasons.append('old_collection_expired_full_refresh_required')
    hard_reject = any(reason != 'old_collection_expired_full_refresh_required' for reason in reasons)
    return {'advice_id': advice['advice_id'], 'checked_at_sim_time': now,
        'status': 'rejected' if hard_reject else 'full_refresh_required' if source_expired
                  else 'requires_fresh_current_admission_and_full_revalidation',
        'reasons': reasons, 'source_age_s': now - advice['source_captured_at'],
        'missed_action_deadline': now >= advice['use_by'], 'unresolved_physical_requests': unresolved,
        'old_collection_capability_reusable': False, 'execution_authority': False,
        'current_capability_id': None, 'new_physical_commands': 0,
        'predicted_inventory_promoted_to_actual': False}


def _predict_process(tasks, ready, started, done, output):
    ready.set()
    payload = tasks.get()
    if payload is None:
        return
    received = time.perf_counter_ns()
    cpu = time.process_time_ns()
    started.set()
    result = {'status': 'unknown_failed', 'worker_started_ns': received,
              'worker_queue_wall_ms': (received - payload['enqueued_ns']) / 1e6,
              'injected_delay_wall_ms': 0., 'simulated_delay_s': None}
    try:
        evidence = json.loads(payload['evidence_json'])
        prediction_start = time.perf_counter_ns()
        result['model_report'] = model.evaluate(evidence, tuple(payload['actions']))
        result['prediction_wall_ms'] = (time.perf_counter_ns() - prediction_start) / 1e6
        result['status'] = 'completed_detached_prediction'
    except Exception:
        result['exception'] = traceback.format_exc()
    result['worker_compute_end_ns'] = time.perf_counter_ns()
    result['worker_compute_cpu_ms'] = (time.process_time_ns() - cpu) / 1e6
    result['worker_compute_wall_ms'] = (result['worker_compute_end_ns'] - received) / 1e6
    path = Path(output)
    temporary = path.with_suffix('.pending.json')
    temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf8')
    temporary.replace(path)
    done.set()  # Output is closed before the fast path may read it.


class PredictionWorker:
    """One isolated request, prewarmed outside the native foreground loop."""
    def __init__(self, output):
        ctx = multiprocessing.get_context('spawn')
        self.tasks = ctx.Queue(maxsize=1)
        self.ready, self.started, self.done = (ctx.Event() for _ in range(3))
        self.output = Path(output)
        require(not self.output.exists(), 'fresh_prediction_output')
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.process = ctx.Process(target=_predict_process,
            args=(self.tasks, self.ready, self.started, self.done, str(self.output)))
        self.timing = {}
        self.submitted = False

    def start(self):
        start = time.perf_counter_ns()
        self.process.start()
        require(self.ready.wait(timeout=20), 'worker_cold_start_timeout')
        self.timing.update(cold_start_and_ready_wall_ms=(time.perf_counter_ns() - start) / 1e6,
                           worker_ready_ns=time.perf_counter_ns(), process_id=self.process.pid)

    def submit(self, evidence, actions):
        require(self.ready.is_set() and not self.submitted, 'single_ready_request')
        start, cpu = time.perf_counter_ns(), time.process_time_ns()
        payload = {'evidence_json': control.encoding(evidence), 'actions': list(actions),
                   'enqueued_ns': time.perf_counter_ns()}
        self.tasks.put_nowait(payload)
        self.submitted = True
        self.timing.update(foreground_serialize_enqueue_wall_ms=(time.perf_counter_ns() - start) / 1e6,
                           foreground_serialize_enqueue_cpu_ms=(time.process_time_ns() - cpu) / 1e6,
                           enqueued_ns=payload['enqueued_ns'], request_kind='first_resident_request')

    def finish(self):
        start = time.perf_counter_ns()
        if not self.submitted:
            self.tasks.put_nowait(None)
        self.process.join(timeout=20)
        require(not self.process.is_alive() and self.process.exitcode == 0, 'worker_exit_failed_or_timeout')
        self.timing['post_native_join_wall_ms'] = (time.perf_counter_ns() - start) / 1e6
        self.tasks.close()
        self.tasks.join_thread()
        return json.loads(self.output.read_text(encoding='utf8')) if self.submitted else None

    def terminate(self):
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5)
