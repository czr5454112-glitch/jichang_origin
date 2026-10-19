"""Versioned, finite repeated-cycle domain on the unchanged native small graph.

Old domain validators remain untouched. The new arrival cases change only one
exogenous arrival. All five contracts must have actually become known before a
full-domain prediction is available; unknown future business is never invented.
"""
from __future__ import annotations

import copy
from types import FunctionType, SimpleNamespace

from . import foundation_later_control as control
from . import foundation_later_seed as old_seed
from . import live_obligation_domain_guard as old_guard
from . import live_obligation_lifecycle_state_v2 as lifecycle
from . import research_live_obligation_native_domain as legacy
from . import public_native_preference_projection as physical_loop

VERSION = 'g31.foundation.repeated_domain.v1'
EVIDENCE_SCHEMA = 'g31.foundation.repeated_evidence.v1'
OBSERVATION_SCHEMA = 'g31.foundation.repeated_observation.v1'
TRANSITION_SCHEMA = 'g31.foundation.repeated_transition.v1'
CASES = {'legacy_mechanism': 0., 'late_blocker_11_1': 11.1,
         'late_blocker_12_1': 12.1, 'late_blocker_12_5': 12.5,
         'three_reuse_blocker_11_1': 11.1, 'four_reuse_blocker_12_5': 12.5}
REUSE_COUNTS = {'three_reuse_blocker_11_1': 3, 'four_reuse_blocker_12_5': 4}
PHASES = ('cycle_return', 'cycle_route', 'preview_next_route')
ACTIONS = {'cycle_return': ('return_now', 'return_delay_0_5'),
           'cycle_route': ('native_default', 'prefer_3', 'prefer_8'),
           'preview_next_route': ('native_default', 'prefer_3', 'prefer_8')}
require, finite = old_guard.require, old_guard.finite
plain, digest = control.plain, control.digest


def scene(case):
    require(case in CASES, 'unregistered_repeated_case')
    data = legacy.native_scene('mechanism')
    data['model_scope'] = VERSION + ':' + case
    next(row for row in data['jobs'] if row['business_bag_id'] == 'blocker')['arrival'] = CASES[case]
    template = next(row for row in data['jobs'] if row['business_bag_id'] == 'reuse2')
    for index in range(3, REUSE_COUNTS.get(case, 2) + 1):
        data['jobs'].append({**copy.deepcopy(template), 'business_bag_id': f'reuse{index}', 'arrival': .01 * (index + 1)})
    return data


def manifest(case):
    data = scene(case)
    physical = {key: value for key, value in data.items() if key not in ('jobs', 'model_scope')}
    return {'schema': VERSION, 'case': case, 'input_sha256': digest(data),
        'physical_sha256': digest(physical), 'business_ids': sorted(row['business_bag_id'] for row in data['jobs']),
        'tray_ids': ['E', 'L', 'P'], 'horizon': 40., 'last_arrival': max(row['arrival'] for row in data['jobs']),
        'changed_external_input': {'blocker.arrival': CASES[case],
            'reuse_count': REUSE_COUNTS.get(case, 2), 'extra_reuse_arrivals': [.01 * (index+1) for index in range(3, REUSE_COUNTS.get(case, 2)+1)]},
        'reference_policy': 'fixed_original_incumbent_with_immutable_retry_and_receiving_full_recovery',
        'source_age_limit_s': .05, 'strict_protection_tolerance': 0.,
        'future_arrivals_are_not_actor_observations': True,
        'scope': 'Finite registered 5/6/7-job circulation variation; no airport or unknown-demand generalization.'}


def validate_scene(data, declared):
    require(declared == manifest(declared['case']) and data == scene(declared['case']),
            'repeated_registered_input_changed')
    return plain(declared)


def identify(contract, jobs):
    require(old_guard.canonical(contract) == old_guard.canonical(old_guard.supported_contract(later=True)),
            'repeated_fixed_physical_contract_changed')
    matches = []
    for case in CASES:
        expected = {row['business_bag_id']: {**row, 'protected_service': True} for row in scene(case)['jobs']}
        if set(jobs) == set(expected) and all(all(jobs[key][field] == expected[key][field]
                for field in old_guard.CONTRACT_FIELDS) for key in jobs):
            matches.append(case)
    require(len(matches) == 1, 'repeated_business_contract_not_registered')
    return matches[0]


def opportunity(episode_id, owner, phase, tray, now, causal_operation_id, *, service_ready_at=None):
    require(type(episode_id) is str and episode_id and phase in PHASES and owner in ('A', 'B'),
            'repeated_opportunity_identity')
    require(finite(now) and now >= 0 and type(causal_operation_id) is str and causal_operation_id,
            'repeated_opportunity_time_or_cause')
    require(tray['tray_id'] == 'L' and all(type(tray[key]) is int and tray[key] >= 0
            for key in ('generation', 'traversal_id')), 'repeated_target_identity')
    kind = 'transfer' if phase == 'cycle_return' else 'route'
    identity = {'episode_id': episode_id, 'owner': owner, 'operation_kind': kind,
        'tray_id': tray['tray_id'], 'generation': tray['generation'], 'traversal_id': tray['traversal_id'],
        'causal_operation_id': causal_operation_id}
    return {**identity, 'opportunity_id': digest(identity), 'phase': phase, 'observed_at': now,
        'target': plain(tray), 'service_ready_at': service_ready_at,
        'use_by': 39. if kind == 'transfer' else None if service_ready_at is None else service_ready_at - .01,
        'unexecuted_suffix_only': True, 'execution_authority': False}


def later_bundle(contract, jobs, trays, resources, *, now, phase, source_records, terminal_receipts,
                 owner_pending_tray_requests, entry_receipts, collection_contract, terminal_trays):
    """Conservative stable arbitrary job/tray pairing, not an E/P role alias.

Every carrier's next autonomous boundary must lie strictly after now. Unknown
ready queues, leases, crossing events and omitted resources fail closed.
"""
    try:
        case = identify(contract, jobs)
        require(phase in PHASES and finite(now) and set(trays) == {'L', 'E', 'P'}, 'repeated_phase_or_population')
        require(len(source_records) == 2 and {row['owner'] for row in source_records} == {'A', 'B'}, 'source_domain')
        floor = min(row['captured_at'] for row in source_records)
        require(0 <= floor <= now and all(job['arrival'] <= floor for job in jobs.values()), 'future_uncaptured_population')
        require(owner_pending_tray_requests == [] and collection_contract == {
            'schema': 'g31.conditional_collection_quiescence.v1', 'physical_admissions_quiesced_from': floor,
            'through': now, 'future_python_actions_certified_by_native': False}, 'quiet_contract')
        owners = {row['node']: row['resource_owner'] for row in contract['node_contracts']}
        records = {row['owner']: row for row in source_records}
        require(set(resources) == set(owners), 'full_resource_coverage')
        for row in source_records:
            require(row['known_faults'] == [] and row['unresolved_tray_request_ids'] == [], 'unresolved_source_action_or_fault')
            actions = row['submitted_physical_actions']
            require(row['submitted_physical_request_ids'] == [action['request_id'] for action in actions]
                    and len({action['request_id'] for action in actions}) == len(actions), 'complete_action_ids')
            require(set(row['node_ids']) == {node for node, owner in owners.items() if owner == row['owner']},
                    'owner_node_coverage')
            for action in actions:
                ack = action.get('last_delivered_ack') or {}
                require(action['source_owner'] == row['owner'] and action['kind'] in old_guard.PHYSICAL_KINDS
                        and type(ack.get('sequence')) is int and ack['sequence'] > 0
                        and ack.get('status') in old_guard.TERMINAL_BY_KIND[action['kind']]
                        and finite(ack.get('delivered_at')) and 0 <= ack['delivered_at'] < floor,
                        'physical_action_not_delivered_terminal_before_capture_union')
        completed, latest_by_tray = {}, {}
        for row in terminal_receipts:
            key = row['business_bag_id']; owner = row['source_owner']
            require(key in jobs and key not in completed and jobs[key]['status'] == row['status'] == 'completed'
                    and owner == owners[jobs[key]['destination']] and finite(row['completed_at'])
                    and 0 <= row['completed_at'] <= floor
                    and row['capture_message_id'] == records[owner]['identity']
                    and row['captured_at'] == records[owner]['captured_at']
                    and row['delivered_at'] == records[owner]['delivered_at'], 'terminal_destination_identity')
            tray_id = terminal_trays[row['identity']]
            require(tray_id in trays, 'terminal_tray_identity')
            completed[key] = row['completed_at']
            if tray_id not in latest_by_tray or row['completed_at'] > latest_by_tray[tray_id]['completed_at']:
                latest_by_tray[tray_id] = row
        require(set(completed) == {key for key, job in jobs.items() if job['status'] == 'completed'},
                'complete_delivered_prefix')
        moving = {key: tray for key, tray in trays.items() if tray['edge_to'] >= 0}
        entries = {row['tray_id']: row for row in entry_receipts}
        require(set(entries) == set(moving) and len(entries) == len(entry_receipts), 'observed_entry_coverage')
        travel = {(a, b): max(.001, length / speed) for a, b, length, speed in contract['edge_records']}
        service = {row[0]: max(.001, row[2]) for row in contract['node_records']}
        stability = []
        active_jobs = set()
        for key, tray in trays.items():
            require(all(type(tray[field]) is int and tray[field] >= 0 for field in ('generation', 'traversal_id'))
                    and tray['reception_node'] == -1 and finite(tray['available_at']) and tray['available_at'] >= 0,
                    'carrier_identity_or_unmodeled_lease')
            mode, job_id = tray['mode'], tray['business_bag_id']
            require(mode in ('empty', 'loading', 'loaded', 'storage', 'unloading', 'hold'), 'unsupported_carrier_queue_state')
            if job_id:
                require(job_id in jobs and job_id not in active_jobs, 'duplicate_or_unknown_loaded_job')
                active_jobs.add(job_id)
            bound = None
            if key in moving:
                entry, edge = entries[key], (tray['edge_from'], tray['edge_to'])
                require(mode == 'loaded' and job_id and jobs[job_id]['status'] == 'in_transit'
                        and tray['node'] == edge[0] and edge in travel
                        and all(entry[field] == tray[field] for field in ('tray_id', 'business_bag_id', 'generation',
                                                                       'traversal_id', 'edge_from', 'edge_to')),
                        'moving_carrier_job_identity')
                require(entry['source_owner'] == owners[tray['node']] and entry['receipt_event'] == 'EDGE_ENTER'
                        and 0 <= jobs[job_id]['loaded_at'] <= entry['entered_at'] <= floor
                        and entry['static_edge_travel_seconds'] == travel[edge]
                        and entry['derived_edge_exit_at'] == entry['entered_at'] + travel[edge]
                        and now < entry['derived_edge_exit_at'] and tray['available_at'] <= floor,
                        'moving_stability_interval')
                require(tray['committed_prefix'] and tray['committed_prefix'][-1] == tray['node'], 'moving_prefix')
                bound = entry['derived_edge_exit_at']
            else:
                require(tray['edge_from'] == -1 and tray['service_ready_known'] is True
                        and all(finite(tray[field]) for field in ('service_ready_at', 'load_complete_at')),
                        'stationary_known_epoch')
                bound = tray['service_ready_at']
                if mode == 'empty':
                    require(not job_id and tray['ready_kind'] == 'empty_available_at'
                            and bound == tray['available_at'] <= floor
                            and tray['committed_prefix'] == [tray['node']], 'stable_empty')
                    if key in latest_by_tray:
                        prior = latest_by_tray[key]
                        require(tray['node'] == jobs[prior['business_bag_id']]['destination']
                                and bound == prior['completed_at'] + jobs[prior['business_bag_id']]['hold_seconds'],
                                'empty_release_receipt_binding')
                    bound = None
                elif mode == 'hold':
                    prior = latest_by_tray[key]
                    require(prior['business_bag_id'] == job_id and jobs[job_id]['status'] == 'completed'
                            and tray['node'] == jobs[job_id]['destination']
                            and tray['ready_kind'] == 'observed_hold_completion'
                            and bound == tray['available_at'] == completed[job_id] + jobs[job_id]['hold_seconds']
                            and bound > now, 'stable_hold')
                elif mode == 'loading':
                    job = jobs[job_id]
                    require(job['status'] == 'loading' and job['loaded_at'] == -1.
                            and tray['node'] == job['origin'] and tray['ready_kind'] == 'observed_load_completion'
                            and bound == tray['available_at'] == tray['load_complete_at'] > now
                            and old_guard.latest_possible_start(bound, job['load_seconds']) <= floor, 'stable_loading')
                elif mode == 'unloading':
                    job = jobs[job_id]
                    require(job['status'] == 'unloading' and tray['node'] == job['destination']
                            and tray['ready_kind'] == 'observed_unload_completion'
                            and bound == tray['available_at'] > now
                            and old_guard.latest_possible_start(bound, job['unload_seconds']) <= floor, 'stable_unloading')
                elif mode == 'storage':
                    job = jobs[job_id]
                    require(job['status'] == 'storage' and tray['node'] == job['storage_node']
                            and tray['ready_kind'] == 'observed_storage_release_bound'
                            and 0 <= job['storage_entered_at'] <= floor and job['storage_released_at'] == -1.
                            and bound == max(job['storage_release_at'], job['storage_entered_at'] + job['storage_min_dwell'])
                            and bound > now and tray['available_at'] <= floor, 'stable_storage')
                else:
                    job = jobs[job_id]
                    require(job['status'] == 'in_transit' and 0 <= job['loaded_at'] <= floor
                            and tray['available_at'] <= floor and tray['ready_kind'] == 'committed_local_service_end'
                            and bound > now and old_guard.latest_possible_start(bound, service[tray['node']]) <= floor
                            and tray['committed_prefix'] and tray['committed_prefix'][-1] == tray['node'],
                            'stable_committed_local_service')
            stability.append({'tray_id': key, 'source_owner': owners[tray['node']], 'floor': floor,
                              'now': now, 'next_bound': bound})
        for node, resource in resources.items():
            occupants = [key for key, tray in trays.items()
                         if (tray['edge_to'] if tray['edge_to'] >= 0 else tray['node']) == node]
            local = sum(owners[trays[key]['node']] == owners[node] for key in occupants)
            available = sum(tray['node'] == node and tray['edge_to'] < 0 and tray['mode'] == 'empty'
                            and tray['available_at'] <= now for tray in trays.values())
            require(all(type(resource[field]) is int for field in ('occupancy', 'actual_available', 'unrepresented_occupancy'))
                    and resource['occupancy'] == len(occupants) and resource['actual_available'] == available
                    and resource['unrepresented_occupancy'] == len(occupants) - local, 'OR_receiving_occupancy')
        for owner, row in records.items():
            require(row['unrepresented_occupancy'] == sum(resources[node]['unrepresented_occupancy']
                    for node, value in owners.items() if value == owner), 'source_occupancy_coverage')
        target = trays['L']
        if phase == 'cycle_return':
            require((target['node'], target['mode'], target['business_bag_id']) == (6, 'empty', ''), 'return_target')
        if phase == 'cycle_route':
            require(target['node'] == 7 and target['mode'] == 'loaded' and target['edge_to'] < 0
                    and target['business_bag_id'].startswith('reuse'), 'route_target')
        return {'status': 'conditional_model_input', 'domain_version': VERSION, 'case': case, 'phase': phase,
            'now': now, 'contract': plain(contract), 'jobs': plain(jobs), 'trays': plain(trays),
            'resources': plain(resources), 'stability': stability, 'completed_prefix': completed,
            'source_records': plain(source_records), 'terminal_receipts': plain(terminal_receipts),
            'conditional_stability_only': True, 'native_protection_certified': False}
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return old_guard.unknown('repeated_lifecycle:' + str(error))


def validate_endpoints(view, command, received, **kwargs):
    """Reuse the full original endpoint gate with only the new downstream domain."""
    terminal_trays = {}
    try:
        envelopes = [command['last_delivered_ack']['planning_snapshot_v3'],
            next(row for row in received if row['capture']['capture_v2']['local_capture']['message_id'] == kwargs['peer_message_id'])]
        for envelope in envelopes:
            for row in envelope['capture']['capture_v2']['extension']['terminal_receipts']:
                require(row['receipt_id'] not in terminal_trays, 'duplicate_terminal_identity')
                terminal_trays[row['receipt_id']] = row['tray_id']
    except (KeyError, TypeError, ValueError, StopIteration) as error:
        return old_guard.unknown('repeated_missing_terminal_identity:' + str(error))
    def bundle(*args, **kw):
        return later_bundle(*args, **kw, terminal_trays=terminal_trays)
    namespace = dict(vars(old_guard)); namespace['later_bundle'] = bundle
    # A new endpoint contract allows only a registered complete job population;
    # the downstream identify() still compares every exact immutable contract.
    # The original validator module and its five-job model are not modified.
    namespace['model'] = SimpleNamespace(**{**vars(old_guard.model), 'JOBS': set(kwargs['retained']['contracts'])})
    pair = FunctionType(old_guard.validate_later_pair.__code__, namespace,
                        old_guard.validate_later_pair.__name__, old_guard.validate_later_pair.__defaults__)
    namespace['validate_later_pair'] = pair
    validate = FunctionType(old_guard.validate_collected_endpoints.__code__, namespace,
                            old_guard.validate_collected_endpoints.__name__, old_guard.validate_collected_endpoints.__defaults__)
    return validate(view, command, received, **kwargs)


def build_seed(evidence):
    require(evidence['schema'] == EVIDENCE_SCHEMA, 'repeated_evidence_schema')
    endpoints, pending = evidence['information']['raw_endpoints'], evidence['collection']
    require(evidence['owner'] == endpoints['view']['owner_id'] and evidence['at'] == endpoints['view']['now'],
            'repeated_evidence_owner_time')
    validated = validate_endpoints(endpoints['view'], endpoints['command'], endpoints['received'],
        retained=evidence['retained'], own_actions=sorted((key, row['kind']) for key, row in evidence['own_outbox'].items()
            if row['kind'] in old_guard.PHYSICAL_KINDS), phase=evidence['phase'],
        own_request_id=pending['request_id'], peer_message_id=pending['peer_message'],
        collection_started_at=pending['at'], policy_quiet_since=pending['policy_quiet_since'],
        own_request=evidence['own_outbox'][pending['request_id']]['request'])
    require(validated['status'] == 'conditional_validated_later_v3_data', 'repeated_current_data:' + str(validated.get('reasons'))
            + ':' + str(validated.get('bundle', {}).get('reasons')))
    bundle = validated['bundle']
    # Edge5->1 has a headway longer than its travel time. An exited carrier
    # alone cannot prove that entry clock expired. B's actual immutable E
    # transfer and terminal received ACK provide a conservative upper bound.
    require(evidence['owner'] == 'B', 'short_edge_headway_requires_B_owned_transfer_history')
    floor = min(row['captured_at'] for row in bundle['source_records'])
    for row in evidence['own_outbox'].values():
        if row['kind'] == 'transfer':
            request, ack = row['request'], row.get('ack', {})
            require(request['tray_id'] == 'E' and request['source'] == 5 and request['destination'] == 1,
                    'repeated_B_fixed_supply_scope')
            require(ack.get('status') == 'rejected' or ack.get('status') == 'received'
                    and ack['delivered_at'] + .5 < floor, 'short_edge_entry_headway_not_proven_expired')
    bundle.update(owner_pending_tray_requests=[], protocol=plain(old_seed.physics.previous.PROTOCOL))
    entries = [entry for envelope in validated['envelopes'].values()
               for entry in envelope['capture']['extension']['source_observed_inflight']]
    preferences, history = old_seed.retained_preferences(bundle, evidence['own_calls'], evidence['owner'])
    seed = {'schema': VERSION, 'status': 'conditional_current_seed', 'at': evidence['at'],
        'phase': evidence['phase'], 'owner': evidence['owner'], 'bundle': bundle,
        'entry_receipts': entries, 'retained_preferences': preferences, 'retained_route_history': history,
        'evidence_sha256': digest(evidence), 'source_captured_at': min(row['captured_at'] for row in bundle['source_records']),
        'action_ids': list(ACTIONS[evidence['phase']]), 'online_executable': False,
        'native_protection_certified': False}
    seed['seed_sha256'] = digest(seed)
    return seed


class Projection(old_seed.Projection):
    def __init__(self, seed, action_id):
        super().__init__(seed, action_id)
        self.action['return_delay'] = 0.

    def submit_preference(self, key, target, *, expiry=None):
        tray = self.trays[key]
        if tray['job'] in ('loaded', 'reuse1', 'reuse2'):
            return super().submit_preference(key, target, expiry=expiry)
        require(key == 'L' and tray['mode'] == 'loaded' and tray['job'] in self.jobs
            and tray['job'] in ('reuse3', 'reuse4') and tray['edge_to'] < 0, 'new_registered_route_lifecycle')
        expires = self.time + 5. if expiry is None else expiry
        require(self.time + .01 <= expires, 'new_route_expiry_before_wire')
        self.operation_guards.append({'at': self.time, 'kind': 'route', 'tray': key,
            'source_owner': self.nodes[tray['node']]['resource_owner'], 'source': tray['node'],
            'job': tray['job'], 'prefix': tray['projection_prefix'], 'next': target, 'expiry': expires,
            'conditional_local_state_only': True})
        return physical_loop.Projection.submit_preference(self, key, target, expiry=expiry)

    def seed_current(self):
        self.completed = plain(self.b['completed_prefix'])
        self.returns = sum(key.startswith('reuse') and job['status'] != 'waiting_for_tray' for key, job in self.jobs.items())
        self.choice_jobs = {key for key, job in self.jobs.items() if key.startswith('reuse') and job['status'] != 'waiting_for_tray'}
        self.reuse_count = sum(key.startswith('reuse') for key in self.jobs)
        self.collecting.add('first_return')
        self.storage_passed = {key for key, job in self.jobs.items() if job['storage_released_at'] >= 0}
        entries = {row['tray_id']: row for row in self.seed['entry_receipts']}
        bounds = {row['tray_id']: row['next_bound'] for row in self.b['stability']}
        for key, tray in self.trays.items():
            tray['projection_prefix'] = tray['traversal_id']
            tray['preference'] = copy.deepcopy(self.seed['retained_preferences'].get(key))
            mode, job = tray['mode'], tray['job']
            if key in entries:
                entry = entries[key]; edge = entry['edge_from'], entry['edge_to']
                tray['goal'] = self.jobs[job]['storage_node'] if self.jobs[job]['storage_node'] >= 0 and job not in self.storage_passed else self.jobs[job]['destination']
                tray['scheduled_incoming_node'] = edge[1]
                self.next_entry[edge] = entry['entered_at'] + self.edges[edge]['entry_headway']
                arrival = entry['derived_edge_exit_at']
                if edge[1] != tray['goal']:
                    self.calendars[edge[1]].append((arrival, arrival + self.service[edge[1]]))
                self.schedule(arrival, 'arrive', key, edge[1])
            elif mode == 'loading':
                tray['load_end'] = tray['load_complete_at']; self.schedule(tray['load_end'], 'load_end', key)
            elif mode == 'storage':
                self.storage_pending[key] = job; self.schedule(bounds[key], 'storage_release', key)
            elif mode == 'loaded':
                tray['goal'] = self.jobs[job]['storage_node'] if self.jobs[job]['storage_node'] >= 0 and job not in self.storage_passed else self.jobs[job]['destination']
                tray['ready'] = bounds[key]
                if len(tray['committed_prefix']) > 1:
                    tray['scheduled_incoming_node'] = tray['node']
                if tray['node'] != tray['goal']:
                    self.calendars[tray['node']].append((self.time, tray['ready']))
                self.schedule(tray['ready'], 'service_ready', key)
            elif mode == 'unloading':
                self.schedule(bounds[key], 'unload', key)
            elif mode == 'hold':
                self.schedule(bounds[key], 'hold', key)
            else:
                require(mode == 'empty' and bounds[key] is None, 'repeated_seed_empty')
        for node in self.nodes:
            self.beacon(node)
        if self.seed['phase'] == 'cycle_return':
            self.returns += 1
            self.request('L', 7, self.time + (.5 if self.action_id == 'return_delay_0_5' else 0.))
        elif self.seed['phase'] == 'cycle_route' and self.action_id != 'native_default':
            self.submit_preference('L', 3 if self.action_id == 'prefer_3' else 8)
        for index in range(int((40. - .11) / .05) + 1):
            epoch = .11 + index * .05
            if epoch > self.time:
                self.schedule(epoch, 'tick')

    def notify_local_lifecycle(self, key):
        tray = self.trays[key]
        if key == 'L' and self.returns >= 2:
            if tray['mode'] == 'empty' and tray['node'] == 6 and self.returns < self.reuse_count and not self.return_pending:
                self.returns += 1; self.request('L', 7, self.time)
            if tray['mode'] == 'loaded' and tray['node'] == 7 and tray['job'] not in self.choice_jobs:
                self.choice_jobs.add(tray['job']); self.submit_preference(key, 3)
            return
        if key == 'L' and self.seed['phase'] == 'preview_next_route':
            tray = self.trays[key]
            if tray['mode'] == 'loaded' and tray['node'] == 7 and tray['job'] == 'reuse2' and 'reuse2' not in self.choice_jobs:
                self.choice_jobs.add('reuse2')
                if self.action_id != 'native_default':
                    self.submit_preference(key, 3 if self.action_id == 'prefer_3' else 8)
                return
        return super().notify_local_lifecycle(key)

    def run(self):
        original = old_seed.Projection.run
        namespace = dict(original.__globals__)
        namespace['contract'] = SimpleNamespace(**{**vars(namespace['contract']), 'JOBS': set(self.jobs)})
        execute = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__)
        return execute(self)


def evaluate(evidence, action_ids):
    try:
        old_seed.physics.check_sources()
        seed = build_seed(evidence)
        require(type(action_ids) in (list, tuple) and 0 < len(action_ids) <= 3
                and len(set(action_ids)) == len(action_ids) and all(action in seed['action_ids'] for action in action_ids),
                'repeated_action_budget')
        before = digest(seed); results = {}
        for action_id in action_ids:
            engine = Projection(seed, action_id)
            result = engine.run()
            require(digest(seed) == before, 'repeated_candidate_mutated_seed')
            require(result['status'] == 'conditional_prediction' and set(result.get('completion', {})) == set(seed['bundle']['jobs'])
                    and all(finite(value) and value >= 0 for value in result['completion'].values()),
                    'repeated_full_completion_prediction_required')
            results[action_id] = {**result, 'action_id': action_id, 'online_executable': False,
                'native_protection_certified': False, 'model_version': VERSION,
                'projected_commands': plain(engine.commands), 'projected_transfers': plain(engine.requests)}
        return {'status': 'conditional_current_seed', 'seed': seed, 'candidate_results': results,
                'model_version': VERSION, 'execution_authority': False}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return {'status': 'unknown', 'reasons': [str(error)], 'candidate_results': {},
                'model_version': VERSION, 'execution_authority': False}
