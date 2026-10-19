"""Conditional current-state seeding from revalidated delivered v3 data.

This module has no native session, fork, delivery capability or result input.
The caller must separately bind the evidence to a still-current collection.
Only the inherited physical loop's initial seeding statements are replaced.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import math
import textwrap

from . import live_obligation_delivered_context as delivered
from . import live_obligation_domain_guard as guard
from . import public_live_obligation_event_projection_v2 as physics

VERSION = 'g31.foundation.later_seed.v1'
EVIDENCE_SCHEMA = 'g31.foundation.later_evidence.v1'
ACTIONS = {'first_return': ('return_now', 'return_not_before_7_84'),
           'first_reuse_route': ('native_default', 'prefer_8')}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def unknown(reason):
    return {'status': 'unknown', 'reasons': [str(reason)], 'model_version': VERSION,
            'completion': {}, 'native_delivery_verified': False,
            'native_protection_certified': False, 'native_execution_certified': False,
            'online_executable': False}


def digest(value):
    return hashlib.sha256(delivered.encoded(value).encode()).hexdigest()


def retained_preferences(bundle, own_calls, owner):
    """Retain applicable delivered commands; default never removes a command."""
    submissions = delivered.history.submission_history(own_calls, owner, bundle['now'])
    current = {row['request_id']: row for row in bundle['owner_current_action_facts']['actions']}
    preferences = {}
    history = []
    for source in bundle['source_records']:
        for action in source['submitted_physical_actions']:
            acknowledgment = action['last_delivered_ack']
            if action['kind'] != 'route' or acknowledgment['status'] != 'updated':
                continue
            request_id = action['request_id']
            require(source['owner'] == owner and request_id in submissions,
                    'missing_retained_route_payload:' + request_id)
            kind, encoded = submissions[request_id]
            request = json.loads(encoded)
            require(kind == 'route', 'retained_route_kind:' + request_id)
            tray = bundle['trays'].get(request['tray_id'])
            require(tray is not None, 'retained_route_tray:' + request_id)
            applicable = (request['business_bag_id'] == tray['business_bag_id']
                and request['expected_generation'] == tray['generation']
                and request['expected_traversal'] == tray['traversal_id']
                and request['from'] == tray['node'] and tray['edge_to'] < 0
                and request['expiry'] >= bundle['now'])
            history.append({'request_id': request_id, 'request': request,
                            'last_delivered_ack': copy.deepcopy(acknowledgment),
                            'applicable_to_current_prefix': applicable})
            if applicable:
                executed_at = current.get(request_id, {}).get('last_delivered_ack', {}).get('executed_at')
                require(type(executed_at) in (int, float) and math.isfinite(executed_at)
                        and 0 <= executed_at <= acknowledgment['delivered_at'],
                        'missing_retained_route_execution_epoch:' + request_id)
                previous = preferences.get(request['tray_id'])
                require(previous is None or previous['executed_at'] != executed_at,
                        'ambiguous_retained_route_order:' + request['tray_id'])
                candidate = {'id': request_id, 'tray': request['tray_id'],
                    'job': request['business_bag_id'], 'from': request['from'],
                    'next': request['next'], 'prefix': tray['traversal_id'],
                    'expiry': request['expiry'], 'ack_delivered_at': acknowledgment['delivered_at'],
                    'executed_at': executed_at}
                if previous is None or candidate['executed_at'] > previous['executed_at']:
                    preferences[request['tray_id']] = candidate
    return preferences, history


def build_seed(evidence):
    """A detached evidence dictionary is data, never current execution authority."""
    try:
        delivered.encoded(evidence)
        require(evidence['schema'] == EVIDENCE_SCHEMA, 'evidence_schema')
        phase, owner = evidence['phase'], evidence['owner']
        require(phase in ACTIONS and owner == ('A' if phase == 'first_return' else 'B'),
                'owner_phase_mismatch')
        endpoints = evidence['information']['raw_endpoints']
        collection = evidence['collection']
        require(endpoints['view']['owner_id'] == owner and endpoints['view']['now'] == evidence['at'],
                'current_owner_or_epoch_mismatch')
        context = delivered.later_context(view=endpoints['view'], command=endpoints['command'],
            received=endpoints['received'], retained=evidence['retained'], own_calls=evidence['own_calls'],
            phase=phase, own_request_id=collection['request_id'], peer_message_id=collection['peer_message'],
            collection_started_at=collection['at'], policy_quiet_since=collection['policy_quiet_since'])
        require(type(context) is delivered.SuppliedContext, 'later_context:' + str(context))
        validated = delivered.revalidate(context)
        require(validated['status'] == 'conditional_validated_later_v3_data',
                'later_context_revalidation:' + str(validated))
        bundle = copy.deepcopy(validated['bundle'])
        contract = guard.model.public_contract(endpoints['view'])
        contract['native_semantics'] = copy.deepcopy(guard.model.SUPPORTED_NATIVE_SEMANTICS)
        case = guard.identify_public_case(contract, bundle['jobs'], later=True)
        entries = [copy.deepcopy(entry) for envelope in validated['envelopes'].values()
                   for entry in envelope['capture']['extension']['source_observed_inflight']]
        entry_by_tray = {entry['tray_id']: entry for entry in entries}
        moving = {name for name, tray in bundle['trays'].items() if tray['edge_to'] >= 0}
        require(set(entry_by_tray) == moving and len(entry_by_tray) == len(entries),
                'missing_or_duplicate_observed_entry')
        travel = {(start, end): max(.001, length / speed)
                  for start, end, length, speed in contract['edge_records']}
        for edge in contract['edge_contracts']:
            if edge['entry_headway'] <= travel[edge['from'], edge['to']]:
                continue
            require((edge['from'], edge['to']) == (5, 1), 'missing_exited_edge_headway_history')
            receiver = bundle['jobs']['receiver']
            bound = receiver['loaded_at']
            if bundle['trays']['E']['mode'] == 'loading':
                bound = guard.latest_possible_start(bundle['trays']['E']['load_complete_at'],
                                                    receiver['load_seconds'])
            require(bound >= 0 and bound + edge['entry_headway'] <= bundle['now'],
                    'unexpired_unobserved_supply_edge_headway')
        preferences, preference_history = retained_preferences(bundle, evidence['own_calls'], owner)
        bundle.update(contract=contract, owner_pending_tray_requests=[],
                      protocol=copy.deepcopy(physics.previous.PROTOCOL))
        result = {'schema': VERSION, 'status': 'conditional_current_seed', 'owner': owner,
            'phase': phase, 'at': evidence['at'], 'case_from_public_contract': case,
            'bundle': bundle, 'entry_receipts': entries,
            'retained_preferences': preferences, 'retained_route_history': preference_history,
            'context_sha256': context.audit_copy()['sha256'],
            'evidence': copy.deepcopy(evidence), 'action_ids': list(ACTIONS[phase]),
            'native_delivery_verified': False, 'native_protection_certified': False,
            'native_execution_certified': False, 'online_executable': False,
            'conditional_scope': 'stable finite population; no pending physical requests; normal retained continuation',
            'fifo_seed': 'no current ready/queued carrier in validated stable lifecycle; waiting jobs retain source arrival order',
            'headway_seed': 'exited headways expire by exit or observed receiver loading bound; current edge epochs retained',
            'continuation': {'first_reuse_action': 'native_default',
                'second_return': 'immediate', 'second_reuse_action': 'prefer_3',
                'future_delivery': 'conditional_normal_delivery_not_observed'}}
        result['seed_sha256'] = digest(result)
        return result
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
        return unknown('seed:' + str(error))


def revalidate_seed(seed):
    require(type(seed) is dict and seed.get('status') == 'conditional_current_seed', 'seed_status')
    rebuilt = build_seed(seed['evidence'])
    require(rebuilt.get('status') == 'conditional_current_seed', 'seed_evidence_no_longer_valid')
    require(delivered.encoded(seed) == delivered.encoded(rebuilt), 'mutated_or_unreproducible_seed')
    return rebuilt


class Projection(physics.Projection):
    def __init__(self, seed, action_id):
        action = {'initial_action': 'native_default', 'empty_departure': .11,
                  'return_delay': .5 if action_id == 'return_not_before_7_84' else 0.,
                  'later_action': 'prefer_8' if action_id == 'prefer_8' else 'native_default'}
        super().__init__(seed['bundle'], action)
        self.seed = seed
        self.action_id = action_id

    def seed_current(self):
        self.completed = copy.deepcopy(self.b['completed_prefix'])
        self.returns = 0 if self.seed['phase'] == 'first_return' else 1
        self.collecting.add('first_return')
        self.choice_jobs = {'reuse1'} if self.returns else set()
        self.storage_passed = {name for name, job in self.jobs.items() if job['storage_released_at'] >= 0}
        entries = {entry['tray_id']: entry for entry in self.seed['entry_receipts']}
        bounds = {row['tray_id']: row['next_bound'] for row in self.b['stability']}
        for name, tray in self.trays.items():
            tray['projection_prefix'] = tray['traversal_id']
            tray['preference'] = copy.deepcopy(self.seed['retained_preferences'].get(name))
            mode, job = tray['mode'], tray['job']
            if name in entries:
                entry = entries[name]
                edge = entry['edge_from'], entry['edge_to']
                tray['goal'] = self.jobs[job]['destination']
                tray['scheduled_incoming_node'] = edge[1]
                self.next_entry[edge] = entry['entered_at'] + self.edges[edge]['entry_headway']
                arrival = entry['derived_edge_exit_at']
                if edge[1] != tray['goal']:
                    self.calendars[edge[1]].append((arrival, arrival + self.service[edge[1]]))
                self.schedule(arrival, 'arrive', name, edge[1])
            elif mode == 'loading':
                tray['load_end'] = tray['load_complete_at']
                self.schedule(tray['load_end'], 'load_end', name)
            elif mode == 'storage':
                self.storage_pending[name] = job
                self.schedule(bounds[name], 'storage_release', name)
            elif mode == 'loaded':
                tray['goal'], tray['ready'] = self.jobs[job]['destination'], bounds[name]
                require(tray['ready'] > self.time, 'missing_future_committed_service:' + name)
                if len(tray['committed_prefix']) > 1:
                    tray['scheduled_incoming_node'] = tray['node']
                if tray['node'] != tray['goal']:
                    self.calendars[tray['node']].append((self.time, tray['ready']))
                self.schedule(tray['ready'], 'service_ready', name)
            elif mode == 'unloading':
                self.schedule(bounds[name], 'unload', name)
            elif mode == 'hold':
                self.schedule(bounds[name], 'hold', name)
            else:
                require(mode == 'empty' and bounds[name] is None, 'unsupported_seed_mode:' + name)
        for node in self.nodes:
            self.beacon(node)
        if self.seed['phase'] == 'first_return':
            self.returns = 1
            self.request('L', 7, self.time)
        elif self.action_id == 'prefer_8':
            self.submit_preference('L', 8)
        for index in range(int((40. - .11) / .05) + 1):
            epoch = .11 + index * .05
            if epoch > self.time:
                self.schedule(epoch, 'tick')


def current_run():
    physics.check_sources()
    original = physics.previous.original.Projection.run
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    function = tree.body[0]
    count_index = next(index for index, node in enumerate(function.body)
                       if isinstance(node, ast.Assign) and ast.unparse(node) == 'count = 0')
    require(count_index == 5, 'unreviewed_inherited_initial_seeding')
    function.body[:count_index] = ast.parse('self.seed_current()').body
    ast.fix_missing_locations(tree)
    namespace = dict(original.__globals__)
    exec(compile(tree, '<foundation_current_state_physical_loop>', 'exec'), namespace)
    return namespace['run']


Projection.run = current_run()


def predict(seed, action_id):
    try:
        checked = revalidate_seed(seed)
        require(type(action_id) is str and action_id in ACTIONS[checked['phase']], 'unsupported_action_id')
        engine = Projection(checked, action_id)
        result = engine.run()
        require(all(math.isfinite(value) for value in result.get('completion', {}).values()),
                'nonfinite_prediction')
        result.update(model_version=VERSION, seed_sha256=checked['seed_sha256'],
            current_state_at=checked['at'], action_id=action_id,
            projected_transfers=copy.deepcopy(engine.requests),
            retained_preferences=copy.deepcopy(checked['retained_preferences']),
            conditional_operation_guards=engine.operation_guards,
            native_delivery_verified=False, native_execution_certified=False,
            native_protection_certified=False, online_executable=False,
            complete_request_100ms_certified=False,
            comparison_scope='current_state_conditional_forecast_not_protection_reference',
            continuation=copy.deepcopy(checked['continuation']))
        result.setdefault('limits', []).extend([
            'Actual collection authority belongs only to the separate current native adapter.',
            'Normal retained future controller behavior is conditional, not future delivered information.',
            'Original established per-job references must remain separate and unchanged.'])
        return result
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
        return unknown('prediction:' + str(error))


def evaluate(evidence, action_ids):
    """Fresh request data only; shared validated state never leaves as authority."""
    from . import foundation_request_context as request_context
    request = None
    result = {'status': 'unknown', 'seed': unknown('evaluation_not_started'), 'candidate_results': {}}
    try:
        require(type(action_ids) in (list, tuple) and 0 < len(action_ids) <= 2
                and all(type(action) is str for action in action_ids)
                and len(set(action_ids)) == len(action_ids), 'evaluation_action_ids')
        require(type(evidence) is dict and evidence.get('schema') == EVIDENCE_SCHEMA, 'evaluation_evidence_required')
        request = request_context.RequestContext()
        checked = request.build_seed(build_seed, evidence)
        result.update(status=checked['status'], seed=checked)
        if checked['status'] != 'conditional_current_seed':
            return result
        require(all(action in ACTIONS[checked['phase']] for action in action_ids), 'unsupported_action_id')
        encoding = delivered.encoded(checked)
        def request_checked(candidate):
            require(candidate is checked and delivered.encoded(candidate) == encoding,
                    'request_local_seed_changed')
            return checked
        namespace = dict(predict.__globals__)
        namespace['revalidate_seed'] = request_checked
        conditional_predict = request_context.clone_function(predict, namespace)
        for action in action_ids:
            result['candidate_results'][action] = conditional_predict(checked, action)
        require(delivered.encoded(checked) == encoding, 'request_local_seed_changed_after_prediction')
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError) as error:
        result.update(status='unknown', seed=unknown('evaluation:' + str(error)), candidate_results={})
    finally:
        if request is not None:
            try:
                result['evaluation'] = request.close()
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError) as error:
                result.update(status='unknown', candidate_results={},
                    evaluation={'status': 'unknown', 'reason': str(error), 'source_exit_pins_passed': False})
    return result
