"""Restricted later-state preference projection using source-authored v3 facts.

This is a new conditional model. The exact initial-state conformance corpus
is not evidence that these new seeds are correct. No native APIs or saved
outcomes are used by predict; authority remains the native collector's job.
"""
from __future__ import annotations
import copy
import heapq
import math
from . import public_native_preference_projection as initial
from . import public_preexisting_v3_model as captured
from .planning_capture_v2_contract import TERMINAL_BY_KIND

VERSION = 'public_native_later_preference_projection_v2'
contract, legacy = initial.contract, initial.legacy
ACTIONS = tuple({'return_delay': delay, 'later_action': action}
                for delay in (0., .5) for action in ('native_default', 'prefer_8'))


def revalidate(bundle):
    """Reapply every old v3 supplied-fact guard; never mint native authority."""
    if bundle.get('status') != 'conditional_model_input' or bundle.get('model_version') != captured.VERSION:
        return captured.unknown(['missing_validated_v3_later_input'])
    resources = bundle['resources']
    if any(type(key) not in (int, str) or isinstance(key, str) and (not key.isdecimal() or str(int(key)) != key)
           for key in resources):
        return captured.unknown(['invalid_resource_identity'])
    resources = {int(key): value for key, value in resources.items()}
    if len(resources) != len(bundle['resources']):
        return captured.unknown(['duplicate_resource_identity'])
    current = bundle.get('owner_current_action_facts', {})
    if (current.get('owner') not in ('A', 'B') or current.get('observed_at') != bundle['now']
            or current.get('pending_request_ids') != [] or bundle.get('owner_pending_tray_requests') != []):
        return captured.unknown(['missing_or_unresolved_current_owned_actions'])
    own = [r for r in bundle['source_records'] if r['owner'] == current['owner']]
    if len(own) != 1 or type(current.get('actions')) is not list:
        return captured.unknown(['missing_current_owned_action_coverage'])
    actions = current['actions']; ids = [row['request_id'] for row in actions]
    expected = [(row['request_id'], row['kind']) for row in own[0]['submitted_physical_actions']]
    if (len(ids) != len(set(ids)) or sorted((row['request_id'],row['kind']) for row in actions) != sorted(expected)):
        return captured.unknown(['current_owned_action_set_changed_after_capture'])
    floor = min(r['captured_at'] for r in bundle['source_records'])
    for row in actions:
        ack = row.get('last_delivered_ack', {})
        if (ack.get('status') not in TERMINAL_BY_KIND.get(row['kind'], ())
                or type(ack.get('sequence')) is not int or ack['sequence'] < 1
                or type(ack.get('delivered_at')) not in (int,float) or not math.isfinite(ack['delivered_at'])
                or not 0 <= ack['delivered_at'] < floor):
            return captured.unknown(['current_owned_action_not_terminal_before_capture_union'])
    checked = captured.assemble_later(bundle['contract'], bundle['jobs'], bundle['trays'], resources,
        now=bundle['now'], phase=bundle['phase'], source_records=bundle['source_records'],
        terminal_receipts=bundle['terminal_receipts'], owner_pending_tray_requests=bundle['owner_pending_tray_requests'],
        entry_receipts=list(bundle['entry_receipts'].values()), collection_contract=bundle['collection_contract'])
    if checked['status'] == 'conditional_model_input' and (
            bundle.get('completed_prefix') != checked['completed_prefix']
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in bundle['completed_prefix'].values())):
        return captured.unknown(['missing_or_changed_completed_prefix'])
    if checked['status'] == 'conditional_model_input':
        checked['owner_current_action_facts'] = copy.deepcopy(current)
        checked['owner_pending_tray_requests'] = []
    return checked


class LaterProjection(initial.Projection):
    def __init__(self, bundle, action):
        super().__init__(bundle, {'initial_action':'native_default', 'empty_departure':bundle['now'],
                                 **action})
        self.completed = copy.deepcopy(bundle['completed_prefix'])
        self.returns = 0 if bundle['phase'] == 'first_return' else 1

    def seed(self):
        # Full previous obligations remain in completed_prefix, authenticated
        # by destination-owned receipts in the actual adapter. No absent-job
        # inference or hidden checkpoint state is used by this pure seed.
        for key, tray in self.trays.items():
            if tray['mode'] == 'loading':
                tray['load_end'] = tray['service_ready_at']
                self.schedule(tray['load_end'], 'load_end', key)
            elif tray['mode'] == 'hold':
                self.schedule(tray['available_at'], 'hold', key)
            elif tray['mode'] == 'loaded' and tray['edge_to'] < 0:
                self.begin_leg(key, self.jobs[tray['job']]['destination'], ready=tray['service_ready_at'])
            elif tray['edge_to'] >= 0:
                row = self.b['entry_receipts'][key]; target = row['edge_to']
                tray['goal'] = self.jobs[tray['job']]['destination']
                tray['scheduled_incoming_node'] = target
                self.next_entry[row['edge_from'],target] = row['entered_at'] + self.edges[row['edge_from'],target]['entry_headway']
                if target != tray['goal']:
                    self.calendars[target].append((row['derived_edge_exit_at'],row['derived_edge_exit_at']+self.service[target]))
                self.schedule(row['derived_edge_exit_at'], 'arrive', key, target)
        if self.b['phase'] == 'first_return':
            self.returns = 1
            self.request('L',7,self.time+self.action['return_delay'])
        else:
            # Only the current reuse route is executable here. The first
            # return is already in the immutable prefix; the return_delay
            # coordinate is inactive at this phase. Second return stays0.
            self.choice_jobs.add('reuse1')
            if self.action['later_action'] == 'prefer_8': self.submit_preference('L',8)
        # Preserve the original global activation grid, not a fresh grid
        # shifted to whichever snapshot happened to be captured.
        for i in range(int((legacy.HORIZON-legacy.START)/legacy.PERIOD)+1):
            at=legacy.START+i*legacy.PERIOD
            if at >= self.time: self.schedule(at,'tick')

    def run(self):
        self.seed()
        count = 0
        while self.events:
            self.time, _, _, kind, args = heapq.heappop(self.events)
            if self.time > legacy.HORIZON:
                break
            count += 1
            if count > 20000:
                return {'status': 'unknown_event_budget', 'completion': self.completed}
            if kind == 'tick': self.tick()
            elif kind == 'owner_activation':
                self.activation_trace.append({'at': self.time, 'owner': args[0], 'reason': args[1]})
                self.tick(args[0])
            elif kind == 'ready':
                if self.ready_at.get(args[0]) == self.time:
                    self.ready_at.pop(args[0]); self.try_depart(args[0])
            elif kind == 'service_ready':
                key = args[0]; tray = self.trays[key]
                tray['scheduled_incoming_node'] = None
                tray['queued'] = tray['node'] != tray['goal']
                self.schedule(self.time, 'beacon', self.trays[key]['node'])
                self.schedule(self.time, 'ready', key)
            elif kind == 'beacon': self.beacon(args[0])
            elif kind == 'merge_commit': self.commit(*args)
            elif kind == 'edge_enter':
                key, source, target = args
                self.record('EDGE_ENTER', key, job=self.trays[key]['job'], source=source, target=target)
                for waiter, (to, reason) in list(self.wait_targets.items()):
                    if to == source and reason == 'receiving_full': self.wake_one(waiter, 'source_berth_departed')
            elif kind == 'command': self.execute_preference(args[0])
            elif kind == 'return_decision':
                self.returns += 1
                self.request('L', 7, self.time + self.action['return_delay'])
            elif kind == 'later_decision':
                if self.action['later_action'] == 'prefer_8': self.submit_preference('L', 8)
            elif kind == 'arrive':
                key, target = args; tray = self.trays[key]
                source = tray['edge_from']
                tray['node'], tray['edge_from'], tray['edge_to'] = target, -1, -1
                self.record('EDGE_EXIT', key, source=source, target=target)
                tray['ready'] = self.time + self.service[target]
                self.schedule(tray['ready'], 'service_ready', key)
                self.schedule(self.time, 'beacon', target)
                for waiter, (to, reason) in list(self.wait_targets.items()):
                    if (self.trays[waiter]['node'], to) == (source, target) and reason == 'edge_capacity':
                        self.wake_one(waiter, 'edge_capacity_released')
            elif kind == 'load_end':
                key = args[0]; tray = self.trays[key]; tray['mode'] = 'loaded'
                self.notify_nodes((tray['node'],), 'LOAD_COMPLETE')
                self.begin_leg(key, self.jobs[tray['job']]['destination'])
                self.notify_local_lifecycle(key)
            elif kind == 'storage_release':
                self.trays[args[0]]['mode'] = 'loaded'
                self.notify_nodes((self.trays[args[0]]['node'],), 'STORAGE_RELEASE')
                self.begin_leg(args[0], self.jobs['loaded']['destination'])
            elif kind == 'unload':
                tray = self.trays[args[0]]; self.completed[tray['job']] = self.time; tray['mode'] = 'hold'
                self.notify_nodes((tray['node'],), 'UNLOAD_COMPLETE')
                self.schedule(self.time + self.jobs[tray['job']]['hold_seconds'], 'hold', args[0])
            elif kind == 'hold':
                tray = self.trays[args[0]]; tray['mode'], tray['job'] = 'empty', None
                self.notify_nodes((tray['node'],), 'HOLD_COMPLETE')
                self.notify_local_lifecycle(args[0])
            elif kind == 'request_delivery':
                request = args[0]
                if request['physical_status'] == 'enqueued':
                    request['physical_status'] = 'pending'
                    if request['earliest'] <= self.time: self.grant(request)
                    else: self.schedule(request['earliest'], 'grant', request)
                self.schedule(self.time + .02, 'ack', request, request['physical_status'])
            elif kind == 'grant': self.grant(args[0])
            elif kind == 'ack':
                request, status = args
                self.notify_owner('B' if request['tray'] == 'E' else 'A', 'delivered_transfer_ack')
                if not request['terminal']:
                    request['ack'], request['ack_at'] = status, self.time
                    request['terminal'] = status in ('received', 'rejected')
                    if request['tray'] == 'L' and request['terminal']:
                        self.return_pending = False
            else:
                raise ValueError('unsupported_projection_event:' + kind)
        complete = set(self.completed) == contract.JOBS
        return {'status': 'conditional_prediction' if complete else 'unknown_unfinished_projection',
                'model_version': VERSION, 'completion': self.completed,
                'completion_sum': sum(self.completed.values()) if complete else None,
                'projected_commands': self.commands, 'projected_dispatches': self.dispatches,
                'physical_projection': self.receipts, 'resource_waits': self.waits, 'event_count': count,
                'projected_owner_activations': self.activation_trace,
                'projected_native_phases': self.phase_trace,
                'native_protection_certified': False, 'native_execution_certified': False,
                'online_information_delivered': False,
                'limits': ['Conditional normal-delivery projection; future collection validity is not proved.',
                           'No independently bounded model error or per-job physical protection certificate.',
                           'Native scorer/merge/event/controller notification semantics require all-case validation.']}


def predict(bundle, action):
    try:
        if (set(action) != {'return_delay','later_action'} or type(action['return_delay']) not in (int,float)
                or action not in ACTIONS):
            return {'status':'unknown_unsupported_action','completion':{},'native_protection_certified':False}
        checked=revalidate(bundle)
        if checked['status'] != 'conditional_model_input':
            return {'status':'unknown_missing_later_input','completion':{},'reasons':checked.get('reasons',[]),
                    'native_protection_certified':False,'online_information_delivered':False}
        return LaterProjection(checked,action).run()
    except (TypeError,ValueError,KeyError,OverflowError,AttributeError):
        return {'status':'unknown_malformed_later_input','completion':{},'native_protection_certified':False,
                'online_information_delivered':False}
