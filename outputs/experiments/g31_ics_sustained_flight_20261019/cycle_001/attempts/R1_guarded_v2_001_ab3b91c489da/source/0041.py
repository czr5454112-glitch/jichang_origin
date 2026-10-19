"""Small scalar-only wall/simulation audit sink; no native or policy imports.

Milestones measure envelopes; overlapping activation/request/worker durations
must never be added. No timings are exposed as policy observations or authority.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

SCHEMA = 'g31.foundation.repeated_path_timing.v2'
STAGE_PAIRS = (
    ('collect', 'collect_start', 'collect_end'),
    ('all_candidate_evaluate', 'evaluate_start', 'evaluate_end'),
    ('mask', 'mask_start', 'mask_end'),
    ('public_observation', 'public_start', 'public_end'),
    ('inference', 'inference_start', 'inference_end'),
    ('ranking', 'ranking_start', 'ranking_end'),
    ('require_current', 'require_current_start', 'require_current_end'),
    ('route_dispatch_envelope', 'route_dispatch_start', 'route_dispatch_end'),
)


def require(value, reason):
    if not value:
        raise ValueError('path_timing:' + reason)


class Recorder:
    def __init__(self, *, clock=time.perf_counter_ns):
        self.clock = clock
        self.activations, self.requests, self.submits, self.ack_reads, self.native_advances = [], [], [], [], []

    def activation_start(self, owner, sim_at, *, started_ns=None, phase='owner_policy_continuation'):
        start = self.clock() if started_ns is None else started_ns
        record = {'owner': owner, 'entry_wall_ns': start, 'entry_sim_s': sim_at, 'status': 'open', 'phase': phase}
        self.activations.append(record)
        return record

    def activation_end(self, record, *, root_id, sim_at, status):
        end = self.clock()
        record.update(exit_wall_ns=end, exit_sim_s=sim_at, root_id=root_id, status=status)

    @contextmanager
    def owner_scope(self, client, owner, *, phase, started_ns=None):
        """Enclose existing owner work without creating/replacing a client root."""
        entry = self.clock() if started_ns is None else started_ns
        record = self.activation_start(owner, client.session.physical_time, started_ns=entry, phase=phase)
        prior_root = client.context['root_id'] if client.context else None
        ack_before = len(client.ack_handling)
        status = 'exception'
        try:
            yield record
            status = 'returned'
        finally:
            root = client.context
            identity = root['root_id'] if root and root['owner'] == owner and root['root_id'] != prior_root else None
            self.activation_end(record, root_id=identity, sim_at=client.session.physical_time, status=status)
            for index in range(ack_before, len(client.ack_handling)):
                row = client.ack_handling[index]; ack = row['ack']
                self.ack_read(request_id=row['request_id'], owner=row['owner'], sequence=ack['sequence'],
                    status=ack['status'], delivered_sim_s=ack['delivered_at'], started_ns=record['entry_wall_ns'],
                    ended_ns=record['exit_wall_ns'])

    def request_start(self, *, owner, phase, root_id, target_job, generation, traversal_id, sim_at, started_ns=None):
        start = self.clock() if started_ns is None else started_ns
        record = {'owner': owner, 'phase': phase, 'root_id': root_id, 'target_job': target_job,
            'generation': generation, 'traversal_id': traversal_id, 'open_wall_ns': start,
            'open_sim_s': sim_at, 'request_id': None, 'status': 'open', 'milestones_ns': {}}
        self.requests.append(record)
        return record

    def bind(self, record, request_id):
        require(record['request_id'] is None and type(request_id) is str, 'bind_actual_request_once')
        record['request_id'] = request_id

    def mark(self, record, name, *, sim_at=None):
        now = self.clock()
        require(record['status'] == 'open' and name not in record['milestones_ns'], 'unique_open_milestone')
        record['milestones_ns'][name] = now
        if sim_at is not None:
            record[name + '_sim_s'] = sim_at

    def request_end(self, record, *, status, sim_at, command_id=None, decision_id=None):
        end = self.clock()
        require(record['status'] == 'open', 'close_request_once')
        record.update(status=status, close_wall_ns=end, close_sim_s=sim_at,
            command_id=command_id, decision_id=decision_id)

    def submit(self, *, request_id, kind, owner, retry, started_ns, ended_ns, sim_at, status):
        # Called after the existing actual native submit returns; no payload copy.
        self.submits.append({'request_id': request_id, 'kind': kind, 'owner': owner, 'retry': retry,
            'start_wall_ns': started_ns, 'end_wall_ns': ended_ns, 'sim_s': sim_at, 'status': status,
            'scope': 'actual_native_submit_call_only'})

    def ack_read(self, *, request_id, owner, sequence, status, delivered_sim_s, started_ns, ended_ns):
        self.ack_reads.append({'request_id': request_id, 'owner': owner, 'sequence': sequence, 'status': status,
            'delivered_sim_s': delivered_sim_s, 'read_start_wall_ns': started_ns, 'read_end_wall_ns': ended_ns,
            'scope': 'owner_activation_envelope_contains_actual_delivered_ack_read'})

    def advance(self, *, started_ns, ended_ns, before_sim_s, after_sim_s, timestamp_complete):
        self.native_advances.append({'start_wall_ns': started_ns, 'end_wall_ns': ended_ns,
            'before_sim_s': before_sim_s, 'after_sim_s': after_sim_s, 'timestamp_complete': timestamp_complete})

    def audit(self):
        """Derive metrics only after the episode; never perform work in a guard."""
        activations, requests = [], []
        for row in self.activations:
            item = dict(row)
            item['processing_wall_ms'] = None if 'exit_wall_ns' not in row else (row['exit_wall_ns']-row['entry_wall_ns'])/1e6
            activations.append(item)
        for row in self.requests:
            item = {**row, 'milestones_ns': dict(row['milestones_ns'])}; marks = row['milestones_ns']
            ready = marks.get('ready_entry'); close = row.get('close_wall_ns')
            item['stage_wall_ms'] = {name: None if start not in marks or end not in marks else
                (marks[end]-marks[start])/1e6 for name, start, end in STAGE_PAIRS}
            item['logical_wait_to_ready_wall_ms'] = None if ready is None else (ready-row['open_wall_ns'])/1e6
            item['open_to_controller_done_wall_ms'] = None if close is None else (close-row['open_wall_ns'])/1e6
            item['ready_to_controller_done_wall_ms'] = None if ready is None or close is None else (close-ready)/1e6
            item['open_to_route_dispatch_return_wall_ms'] = None if 'route_dispatch_end' not in marks else (marks['route_dispatch_end']-row['open_wall_ns'])/1e6
            calls = [call for call in self.submits if call['request_id'] == row.get('command_id') and not call['retry']]
            item['actual_native_submit_wall_ms'] = (calls[0]['end_wall_ns']-calls[0]['start_wall_ns'])/1e6 if len(calls) == 1 else None
            item['open_to_native_submit_return_wall_ms'] = (calls[0]['end_wall_ns']-row['open_wall_ns'])/1e6 if len(calls) == 1 else None
            item['submit_to_ack_read_envelopes'] = [{**ack,
                'submit_return_to_read_end_wall_ms': (ack['read_end_wall_ns']-calls[0]['end_wall_ns'])/1e6}
                for ack in self.ack_reads if len(calls) == 1 and ack['request_id'] == row.get('command_id')]
            requests.append(item)
        return {'schema': SCHEMA, 'owner_activations': activations, 'requests': requests,
            'native_submits': [dict(row) for row in self.submits], 'ack_read_envelopes': [dict(row) for row in self.ack_reads],
            'native_advance_envelopes': [dict(row) for row in self.native_advances],
            'wall_and_sim_are_not_interchangeable': True, 'overlapping_envelopes_must_not_be_summed': True,
            'physical_effect_exact_wall_time_measured': False, 'instrumentation_has_policy_authority': False,
            'all_statuses_retained_in_denominator': True, 'deep_copy_in_timing_hot_path': False}
