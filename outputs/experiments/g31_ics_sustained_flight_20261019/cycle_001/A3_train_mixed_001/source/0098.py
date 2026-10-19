"""Restricted public conditional simulator with native preference semantics.

The new projection deliberately does not edit the accepted historical model.
No native session, saved outcome, case-key lookup or outcome-calibrated offset
is used here. Native protection and collection readiness remain unproved.
"""
from __future__ import annotations

import copy
import heapq
import math

from . import public_reuse_model as legacy
from . import public_preexisting_model as contract
from . import public_route_preference_model as preference
from . import public_executable_preference_actions as vocabulary
from scripts.eval.run_g4irsf28_service_potential import service_aware_potential

VERSION = 'public_native_preference_projection_v2'
def planning_decision_epoch(start):
    """Conditional normal exchange, preserving each actual wire addition."""
    own_capture = start + .01
    invitation_delivered = own_capture + .01
    own_ack_delivered = invitation_delivered + .02
    peer_capture = invitation_delivered + .01
    peer_delivered = peer_capture + .01
    return max(own_ack_delivered, peer_delivered)


def earliest_calendar_start(intervals, at, duration):
    current = at
    for start, stop in sorted(intervals):
        if current + duration <= start + 1e-9:
            break
        if current < stop - 1e-9 and start < current + duration - 1e-9:
            current = stop
    return current


class Projection(legacy.DiscreteProjection):
    def __init__(self, bundle, action):
        super().__init__(bundle, {'initial_next': 1, 'departure': action['empty_departure'], 'later_mode': 'native_keep'})
        self.action = copy.deepcopy(action)
        self.commands, self.dispatches = [], []
        self.collecting = set()
        self.serial = 0
        self.potential = {}
        self.score_potential, self.score_potential_contract = service_aware_potential(
            bundle['contract']['node_records'], bundle['contract']['edge_records'],
            minimum_service_seconds=.001)
        self.owner_boundaries = set()
        self.activation_trace = []
        self.ready_at = {}
        self.wait_targets = {}
        self.ranking_subscriptions = {}
        self.beacon_state = {}
        self.phase_trace = []
        self.incoming_degree = {node: sum(to == node for _, to in self.edges) for node in self.nodes}
        for tray in self.trays.values():
            tray['projection_prefix'] = 0
            tray['preference'] = None
            tray['queued'] = False
            tray['dispatch_pending'] = False
            tray['scheduled_incoming_node'] = None

    def schedule(self, when, kind, *args):
        if kind == 'ready':
            key = args[0]
            if self.ready_at.get(key, math.inf) <= when:
                return
            self.ready_at[key] = when
        ranks = {'arrive': 2, 'service_ready': 3, 'beacon': 5, 'ready': 8,
                 'command': 6, 'load_end': 6, 'storage_release': 6, 'unload': 6,
                 'hold': 6, 'request_delivery': 6, 'grant': 6, 'ack': 6,
                 'merge_commit': 9, 'edge_enter': 10, 'owner_activation': 99,
                 'return_decision': 99, 'later_decision': 99}
        if kind in ranks:
            # The native notification API returns only after the physical
            # timestamp has drained. Owner code therefore runs after dispatch,
            # never between reservation publication and EDGE_ENTER.
            self.sequence += 1
            heapq.heappush(self.events, (when, ranks[kind], self.sequence, kind, args))
        else:
            super().schedule(when, kind, *args)

    def notify_owner(self, owner, reason):
        identity = self.time, owner
        if identity not in self.owner_boundaries:
            self.owner_boundaries.add(identity)
            self.schedule(self.time, 'owner_activation', owner, reason)

    def notify_nodes(self, nodes, reason):
        for node in nodes:
            if node in self.nodes:
                self.notify_owner(self.nodes[node]['resource_owner'], reason)

    def record(self, event, tray, **extra):
        super().record(event, tray, **extra)
        # These are the corresponding local_physical circulation receipts;
        # RESOURCE_WAIT and TRANSFER_REJECTED deliberately do not notify here.
        if event in ('EDGE_ENTER', 'EDGE_EXIT', 'LOAD_START', 'EMPTY_RECEIVED', 'STORAGE_ENTER'):
            self.notify_nodes((self.trays[tray]['node'], extra.get('source'), extra.get('target')), event)

    def grant(self, request):
        before = request['physical_status']
        super().grant(request)
        if before == 'pending' and request['physical_status'] == 'dispatching':
            self.notify_nodes((self.trays[request['tray']]['node'],), 'EXPORT_GRANTED')

    def remaining(self, node, goal):
        """Static positive-capacity travel potential, from public graph only."""
        if (node, goal) in self.potential:
            return self.potential[node, goal]
        distances, queue = {goal: 0.}, [(0., goal)]
        while queue:
            distance, target = heapq.heappop(queue)
            if distance != distances[target]:
                continue
            for (source, end), edge in self.edges.items():
                if end != target or edge['capacity'] <= 0:
                    continue
                candidate = distance + self.travel[source, end]
                if candidate < distances.get(source, math.inf):
                    distances[source] = candidate
                    heapq.heappush(queue, (candidate, source))
        value = distances.get(node, math.inf)
        self.potential[node, goal] = value
        return value

    def candidate_rows(self, key):
        tray = self.trays[key]
        result = []
        for target in self.outgoing[tray['node']]:
            # S4 retains every outgoing candidate, including a statically
            # unreachable one with the public preprocessing sentinel. Static
            # legal-suffix rejection is a separate route-command contract.
            potential = self.score_potential[target][tray['goal']]
            travel = self.travel[tray['node'], target]
            queued = sum(t['node'] == target and t['edge_to'] < 0 and t['queued']
                         for t in self.trays.values())
            incoming = sum(t['scheduled_incoming_node'] == target for t in self.trays.values())
            target_start = self.time + travel
            # R3 has no corridor calendar. Native S4 hides merge-node calendar
            # pressure unless its separate visibility option is enabled; this
            # finite supported contract keeps that option disabled.
            if target != tray['goal'] and self.incoming_degree[target] <= 1:
                target_start = earliest_calendar_start(self.calendars[target], target_start, self.service[target])
            score = travel + potential + queued + incoming + max(0., target_start - (self.time + travel))
            reason = self.blocked(key, target)
            if (tray['preference'] is not None and tray['preference']['prefix'] == tray['projection_prefix']
                    and self.time <= tray['preference']['expiry'] and target == tray['preference']['next'] and reason is None):
                score -= preference.PREFERENCE_SCORE_BONUS
            result.append({'next': target, 'score': score, 'allowed': reason is None,
                           'reason': reason or 'allowed', 'queue': queued, 'incoming': incoming,
                           'target_calendar_start': target_start})
        return sorted(result, key=lambda row: (row['score'], row['next']))

    def choose_next(self, key):
        rows = self.candidate_rows(key)
        if not rows:
            raise ValueError('projection:no_static_suffix')
        # Ordinary loaded dispatch waits for the best-ranked candidate even
        # when another candidate is currently allowed. No best-allowed hack.
        self.dispatches.append({'at': self.time, 'tray': key, 'job': self.trays[key]['job'],
                                'from': self.trays[key]['node'], 'ranked': copy.deepcopy(rows)})
        return rows[0]['next']

    def try_depart(self, key):
        tray = self.trays[key]
        if (tray['edge_to'] >= 0 or tray['goal'] is None or tray['dispatch_pending']
                or tray['ready'] > self.time + 1e-9): return
        if tray['node'] == tray['goal']:
            self.waiting.pop(key, None); tray['queued'] = False
            self.complete_leg(key)
            return
        if self.last_arbitration.get(tray['node']) == self.time:
            return
        target = self.choose_next(key)
        reason = self.blocked(key, target)
        self.last_arbitration[tray['node']] = self.time
        self.phase_trace.append({'at': self.time, 'phase': 'source_arbitration', 'tray': key,
                                 'from': tray['node'], 'target': target, 'blocked': reason})
        if reason:
            if key not in self.waiting:
                self.fifo += 1; self.waiting[key] = self.fifo
                self.waits.append({'at': self.time, 'tray': key, 'node': tray['node'], 'to': target, 'reason': reason})
            self.wait_targets[key] = target, reason
            rows = self.candidate_rows(key)
            if len(rows) > 1 and reason in ('headway', 'edge_capacity', 'receiving_full') and all(
                    r['target_calendar_start'] <= self.time + self.travel[tray['node'], r['next']] + 1e-9 for r in rows):
                self.ranking_subscriptions[key] = {r['next'] for r in rows}
            if reason == 'headway': self.schedule(self.next_entry[tray['node'], target], 'ready', key)
            if reason == 'service_calendar':
                times = [b - self.travel[tray['node'], target] for a, b in self.calendars[target]
                         if b - self.travel[tray['node'], target] > self.time + 1e-9]
                if times: self.schedule(min(times), 'ready', key)
            return
        tray['dispatch_pending'] = True
        # Native R3 exempts the goal from the destination service/merge grant.
        # Its ordinary source dispatch commits before later source arbitrations
        # at this timestamp; non-goal proposals wait for destination phase9.
        if target == tray['goal'] or self.incoming_degree[target] <= 1:
            self.commit(key, target)
        else:
            # jit_destination_merge_ready_time preserves (now+travel)-travel;
            # algebraically replacing it with now changes exact double order.
            travel = self.travel[tray['node'], target]
            arrival = self.time + travel
            service_start = earliest_calendar_start(self.calendars[target], arrival, self.service[target])
            ready = max(self.time, service_start - travel)
            self.schedule(ready, 'merge_commit', key, target)

    def begin_leg(self, key, goal, *, ready=None):
        tray = self.trays[key]
        tray['goal'] = goal
        tray['ready'] = self.time + self.service[tray['node']] if ready is None else ready
        tray['queued'] = False
        self.calendars[tray['node']].append((self.time, tray['ready']))
        self.schedule(tray['ready'], 'service_ready', key)

    def wake_one(self, key, reason):
        if key not in self.waiting: return
        self.wait_targets.pop(key, None); self.ranking_subscriptions.pop(key, None)
        delay = self.minimum if self.last_arbitration.get(self.trays[key]['node']) == self.time else 0.
        self.phase_trace.append({'at': self.time, 'phase': 'resource_wake', 'tray': key,
                                 'reason': reason, 'next_arbitration': self.time + delay})
        self.schedule(self.time + delay, 'ready', key)

    def beacon(self, node):
        snapshot = (sum(t['node'] == node and t['edge_to'] < 0 and t['queued'] for t in self.trays.values()),
                    sum(t['scheduled_incoming_node'] == node for t in self.trays.values()))
        if self.beacon_state.get(node) == snapshot: return
        self.beacon_state[node] = snapshot
        for key, nodes in list(self.ranking_subscriptions.items()):
            if node in nodes: self.wake_one(key, 'candidate_score_state_changed')

    def commit(self, key, target):
        tray = self.trays[key]; tray['dispatch_pending'] = False
        reason = self.blocked(key, target)
        if reason:
            self.schedule(self.time + self.minimum, 'ready', key)
            return
        self.waiting.pop(key, None); self.wait_targets.pop(key, None); self.ranking_subscriptions.pop(key, None)
        source, edge = tray['node'], (tray['node'], target)
        self.next_entry[edge] = self.time + self.edges[edge]['entry_headway']
        tray['edge_from'], tray['edge_to'], tray['queued'] = source, target, False
        # Native scheduled_incoming survives physical EDGE_EXIT and is removed
        # only by process_arrive after target service finishes (or goal release).
        tray['scheduled_incoming_node'] = target
        tray['projection_prefix'] += 1
        arrival = self.time + self.travel[edge]
        if target != tray['goal']:
            self.calendars[target].append((arrival, arrival + self.service[target]))
        self.phase_trace.append({'at': self.time, 'phase': 'destination_merge_commit', 'tray': key,
                                 'from': source, 'target': target})
        self.notify_nodes((source, target), 'reservation_published')
        self.schedule(self.time, 'beacon', source); self.schedule(self.time, 'beacon', target)
        self.schedule(self.time, 'edge_enter', key, source, target)
        self.schedule(arrival, 'arrive', key, target)

    def submit_preference(self, key, target, *, expiry=None):
        tray = self.trays[key]
        self.serial += 1
        record = {'id': self.serial, 'issued_at': self.time, 'tray': key, 'job': tray['job'],
                  'from': tray['node'], 'next': target, 'prefix': tray['projection_prefix'],
                  'expiry': self.time + 5. if expiry is None else expiry}
        self.schedule(self.time + .01, 'command', record)

    def execute_preference(self, record):
        tray = self.trays[record['tray']]
        reason = 'allowed'
        if (tray['edge_to'] >= 0 or tray['goal'] is None or tray['node'] != record['from']
                or tray['job'] != record['job'] or tray['projection_prefix'] != record['prefix']):
            reason = 'stale_executed_prefix'
        elif not self.jobs[tray['job']]['allow_suffix_reroute']:
            reason = 'service_obligation_disallows_reroute'
        elif record['next'] not in self.outgoing[tray['node']]:
            reason = 'not_a_directed_edge'
        elif not math.isfinite(self.remaining(record['next'], tray['goal'])):
            reason = 'no_static_legal_suffix'
        else:
            reason = self.blocked(record['tray'], record['next']) or 'allowed'
        if reason == 'allowed':
            tray['preference'] = copy.deepcopy(record)
            if record['tray'] in self.waiting:
                self.wake_one(record['tray'], 'route_intent_updated')
        self.commands.append({**record, 'executed_at': self.time, 'ack_delivered_at': self.time + .02,
                              'status': 'updated' if reason == 'allowed' else 'rejected', 'reason': reason,
                              'reserves_receiving_capacity': False})

    def notify_local_lifecycle(self, key):
        """Normal-delivery finite policy contract, not observed readiness proof.

        First return and first loaded reuse wait one planning exchange. Actual
        per-owner v3 validation remains outside this conditional simulator.
        Second return/reuse follows the same declared direct continuation.
        """
        if key != 'L':
            return
        tray = self.trays[key]
        if tray['mode'] == 'empty' and tray['node'] == 6 and self.returns < 2 and not self.return_pending:
            if self.returns == 0 and 'first_return' not in self.collecting:
                self.collecting.add('first_return')
                self.schedule(planning_decision_epoch(self.time), 'return_decision')
            elif self.returns == 1:
                self.returns += 1
                self.request('L', 7, self.time)
        if tray['mode'] == 'loaded' and tray['node'] == 7 and tray['job'] not in self.choice_jobs:
            self.choice_jobs.add(tray['job'])
            if tray['job'] == 'reuse1':
                self.schedule(planning_decision_epoch(self.time), 'later_decision')
            else:
                self.submit_preference('L', 3)

    def tick(self, owner=None):
        for request in self.requests[:]:
            if owner is not None and owner != ('B' if request['tray'] == 'E' else 'A'):
                continue
            if not request['terminal'] and self.time >= request['next_retry']:
                request['next_retry'] = self.time + .5
                self.schedule(self.time + .01, 'request_delivery', request)
        request = self.last_supply
        tray = self.trays['E']
        if (owner in (None, 'B') and request and request['terminal'] and request['ack'] == 'rejected'
                and self.time >= request['ack_at'] + .5
                and len([r for r in self.requests if r['tray'] == 'E']) < 16
                and tray['mode'] == 'empty' and tray['node'] == 5):
            self.request('E', 1, self.time)

    def run(self):
        self.begin_leg('L', self.jobs['loaded']['storage_node'], ready=self.jobs['loaded']['loaded_at'] + self.service[0])
        self.schedule(self.trays['P']['load_end'], 'load_end', 'P')
        self.request('E', 1, self.action['empty_departure'])
        if self.action['initial_action'] == 'prefer_2':
            self.submit_preference('L', 2, expiry=5.)
        for i in range(int((legacy.HORIZON - legacy.START) / legacy.PERIOD) + 1):
            self.schedule(legacy.START + i * legacy.PERIOD, 'tick')
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


def _predict(bundle, action):
    """Revalidate the supported initial facts; labels alone are not guards."""
    if bundle.get('status') != 'conditional_model_input' or bundle.get('model_version') != contract.VERSION:
        return {'status': 'unknown_unvalidated_initial_contract', 'completion': {}, 'native_protection_certified': False}
    expected = contract.supported_contract()
    expected.pop('native_semantics')
    if (contract._canonical(bundle.get('contract')) != contract._canonical(expected)
            or bundle.get('now') != legacy.START or set(bundle.get('trays', {})) != {'L', 'E', 'P'}):
        return {'status': 'unknown_static_or_initial_scope', 'completion': {}, 'native_protection_certified': False}
    case = contract.infer_case(bundle['jobs'])
    if case is None:
        return {'status': 'unknown_population', 'completion': {}, 'native_protection_certified': False}
    declared_jobs = contract.domain.make_bundle(case)['jobs']
    if any(contract._canonical({f: bundle['jobs'][key][f] for f in contract.CONTRACT_FIELDS}) !=
           contract._canonical({f: declared_jobs[key][f] for f in contract.CONTRACT_FIELDS}) for key in contract.JOBS):
        raise ValueError('invalid_typed_obligation_contract')
    resources = bundle['resources']
    if any(type(key) not in (int, str) or isinstance(key, str) and (not key.isdecimal() or str(int(key)) != key)
           for key in resources):
        raise ValueError('invalid_resource_identity')
    normalized = {int(key): value for key, value in resources.items()}
    if len(normalized) != len(resources) or set(normalized) != {n['node'] for n in expected['node_contracts']}:
        raise ValueError('missing_or_duplicate_resource_coverage')
    numeric = lambda value: type(value) in (int, float) and math.isfinite(value)
    for key, node, mode, job in (('L', 0, 'loaded', 'loaded'), ('E', 5, 'empty', ''), ('P', 1, 'loading', 'blocker')):
        tray = bundle['trays'][key]
        if ((tray.get('node'), tray.get('mode'), tray.get('business_bag_id')) != (node, mode, job)
                or type(tray.get('node')) is not int or tray.get('tray_id') != key
                or any(type(tray.get(field)) is not int or tray[field] != -1 for field in ('edge_from', 'edge_to', 'reception_node'))
                or type(tray.get('generation')) is not int or tray['generation'] != (0 if key == 'E' else 1)
                or type(tray.get('traversal_id')) is not int or tray['traversal_id'] != 0
                or tray.get('committed_prefix') != [node]
                or any(type(v) is not int for v in tray['committed_prefix'])):
            return {'status': 'unknown_initial_lifecycle', 'completion': {}, 'native_protection_certified': False}
        if (tray.get('service_ready_known') is not True
                or any(not numeric(tray.get(field)) for field in ('available_at','service_ready_at','load_complete_at'))):
            raise ValueError('unknown_or_invalid_initial_service')
    l, e, p = (bundle['trays'][key] for key in ('L', 'E', 'P'))
    if (not 0 <= e['available_at'] == e['service_ready_at'] <= bundle['now']
            or e['ready_kind'] != 'empty_available_at' or e['load_complete_at'] != -1.
            or l['ready_kind'] != 'observed_load_completion'
            or l['service_ready_at'] != .1 or l['load_complete_at'] != .1
            or not 0 <= l['available_at'] <= bundle['now']
            or p['ready_kind'] != 'observed_load_completion'
            or not bundle['now'] < p['available_at'] == p['service_ready_at'] == p['load_complete_at'] == case['blocker_load']):
        raise ValueError('unsupported_initial_ready_or_availability_epoch')
    for node, resource in normalized.items():
        if (type(resource.get('node')) is not int or resource['node'] != node
                or type(resource.get('occupancy')) is not int or type(resource.get('actual_available')) is not int
                or resource['occupancy'] != sum(t['node'] == node for t in bundle['trays'].values())
                or resource['actual_available'] != sum(t['node'] == node and t['mode'] == 'empty'
                    and t['available_at'] <= bundle['now'] for t in bundle['trays'].values())):
            raise ValueError('unrepresented_initial_occupancy_or_stock')
    if (type(bundle['trays']['P'].get('load_end')) not in (int, float)
            or bundle['trays']['P']['load_end'] != case['blocker_load']
            or type(bundle['jobs']['loaded'].get('loaded_at')) not in (int, float)
            or bundle['jobs']['loaded']['loaded_at'] != .1
            or bundle['jobs']['loaded'].get('status') != 'in_transit'
            or bundle['jobs']['blocker'].get('status') != 'loading'
            or any(bundle['jobs'][job].get('status') != 'waiting_for_tray' for job in ('receiver','reuse1','reuse2'))
            or any(bundle['jobs'][job].get('loaded_at') != -1. for job in contract.JOBS - {'loaded'})
            or any(bundle['jobs'][job].get('protected_service') is not True for job in contract.JOBS)
            or any(bundle['jobs'][job].get(field) != -1. for job in contract.JOBS
                   for field in ('storage_entered_at','storage_released_at'))):
        return {'status': 'unknown_initial_service_epoch', 'completion': {}, 'native_protection_certified': False}
    if bundle.get('owner_pending_tray_requests', []) != []:
        raise ValueError('unresolved_initial_owned_action')
    windows = contract.domain.domain(case)['public_derivation']['supply_windows']
    if (set(action) != {'initial_action','empty_departure','return_delay','later_action'}
            or any(not numeric(action.get(key)) for key in ('empty_departure','return_delay'))
            or action not in vocabulary.domain(windows)['actions']):
        return {'status': 'unknown_action', 'completion': {}, 'native_protection_certified': False}
    return Projection(bundle, action).run()


def predict(bundle, action):
    try:
        return _predict(bundle, action)
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError):
        return {'status': 'unknown_malformed_or_unsupported_projection_input', 'completion': {},
                'native_protection_certified': False, 'online_information_delivered': False}
