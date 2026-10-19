"""Stepable native027 baseline, not a new physical simulator or RL action gate.

Initial dispatch remains unchanged; optional later choices use real collections.
The actor API returns actual own endpoints; evaluator records are separate.
Python object privacy is an API discipline, not an adversarial sandbox.
"""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
import time
import traceback

from . import research_live_obligation_initial_methods as online
from . import foundation_later_control as later

SCHEMA = 'g31.foundation.native_environment.v1'
ROOT = Path(__file__).resolve().parents[3]
OWNERS = ('A', 'B')
HORIZON = 40.
CAPABILITIES = {
    'single_native_truth': True,
    'owner_local_observation': True,
    'repeated_retained_policy_activations': True,
    'initial_conditional_nondefault_R2': True,
    'new_later_R1_R2_choice': False,
    'full_joint_R1_R2_authority': False,
    'rl_ready': False,
    'missing_capabilities': [
        'fresh later candidate generation and current legal collection for each learned action',
        'later learned-action submission authority preserving receiving rights and component compatibility',
        'paired native evaluation of newly chosen later actions',
        'new shortage/shared-capacity/conflicting-proposal learning trajectories',
    ],
}


def require(condition, reason):
    if not condition:
        raise ValueError('foundation_native_environment:' + reason)


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8')


def validate_owner_snapshot(owner, view, received):
    require(view['owner_id'] == owner, 'native_observation_owner')
    local_nodes = {row['node'] for row in view['node_contracts'] if row['resource_owner'] == owner}
    require(all(not {'occupancy', 'actual_available'}.intersection(row)
                for row in view['node_contracts'] if row['resource_owner'] != owner), 'foreign_dynamic_node_state')
    require(all(row['node'] in local_nodes for row in view['trays']), 'foreign_dynamic_tray_state')
    carried = {row['business_bag_id'] for row in view['trays']}
    require(all(row['origin'] in local_nodes or row['business_bag_id'] in carried for row in view['jobs']),
            'foreign_unreleased_job_state')
    require(all(row['capture']['target_owner'] == owner and row['delivered_at'] <= view['now']
                for row in received), 'undelivered_or_wrong_target_planning_message')
    return {'owner': owner, 'at': view['now'], 'local_tray_ids': [row['tray_id'] for row in view['trays']],
            'delivered_planning_count': len(received), 'foreign_dynamic_state_absent': True}


class FoundationNativeEnvironment:
    """One admitted session; no implicit reset, fork, checkpoint or future read."""

    def __init__(self, native, accepted_run, branch_key, contract_reference, *, initial_evaluator=None,
                 later_model=None, later_mode=None, later_phases=tuple(later.PHASE_ACTIONS)):
        self._native = native
        self._run = accepted_run
        self._key = branch_key
        self._contract = contract_reference
        self._initial_evaluator = initial_evaluator
        self._session = None
        self._progress = {}
        self._audit = []
        self._shadows = []
        self._pending = []
        self._epoch = 0
        self._status = 'uninitialized'
        self._outcome = None
        self._advice = {}
        self._observations = []
        self._later_mode, self._later_model, self._later_phases = later_mode, later_model, tuple(later_phases)
        self._later_controls = {}

    def reset(self):
        require(self._session is None, 'reset_requires_fresh_admitted_environment')
        require(type(self._run) is online.old.run_admission.RunAcceptance and self._run.active_for(self._key),
                'active_native_run_required')
        self._row = self._run.branch_specification(self._key)
        require(self._row == online.rows().get(self._key), 'declared_online_case_and_method')
        runtime = self._run.contract_copy(self._key)
        require(runtime['reference'] == self._contract and
                runtime['contract']['binary_sha256'] == self._native._g31_native_artifact_identity['sha256'],
                'accepted_binary_identity')
        self._data = online.old.native_scene(self._row['case'], self._row.get('fault'))
        self._progress.update(specification=self._row, input=self._data, stage='native_session_constructor')
        self._session = self._native.NativeSession(self._data)
        self._progress.update(session=self._session, stage='runtime_admission')
        admission, self._accepted = online.old.adapter.bind_native027(
            self._native, self._session, self._contract, accepted_run=self._run, branch_key=self._key)
        require(self._accepted is not None, 'native_admission_rejected:' + str(admission))
        self._client = online.old.LocalTransport(self._session)
        self._channels, self._planning, self._ledgers, self._initial, self._policies = {}, {}, {}, {}, {}
        self._batches, self._cursors, self._tick, self._activations = [], dict.fromkeys(OWNERS, 0), 0, 0
        self._progress.update(client=self._client, ledgers=self._ledgers, initial_owners=self._initial,
                              policies=self._policies, native_batches=self._batches)
        self._session.advance_to(.05)
        for owner, peer in (('A', 'B'), ('B', 'A')):
            self._client.activate(owner, {'kind': 'initial_public_epoch', 'at': .05})
            self._channels[owner] = self._client.submit(owner, 'demand', 'seed-demand', target_owner=peer,
                                                       message_delay=.01, publication_delay=.01)
            self._planning[owner] = self._client.submit(owner, 'planning_snapshot', 'initial-planning',
                target_owner=peer, message_delay=.01, publication_delay=.01, expiry=.21)
        for owner in OWNERS:
            observation = self.observe(owner)
            require(not observation['delivered_planning_snapshots'], 'message_visible_before_delivery')
        self._session.advance_to(online.old.v1.START)
        self._phase = 'initial'
        self._status = 'running'
        self._pending = list(OWNERS)
        self._triggers = {owner: {'kind': 'initial_decision_epoch', 'at': online.old.v1.START} for owner in OWNERS}
        return self._boundary(0.)

    def _boundary(self, delta):
        return {'schema': SCHEMA, 'status': self._status, 'event_time_s': self._session.physical_time,
                'delta_sim_time_s': delta, 'decision_epoch': self._epoch,
                'due_owners': list(self._pending), 'phase': self._phase,
                'timing_mode': 'offline_sync', 'capabilities': copy.deepcopy(CAPABILITIES)}

    def observe(self, owner):
        require(self._session is not None and owner in OWNERS, 'known_owner_and_reset_required')
        control = self._later_controls.get(owner)
        if control is not None and control.offer is not None:
            return control.observation()
        view = self._session.observe_protocol(owner)
        received = self._session.protocol_planning_snapshots(owner)
        self._observations.append(validate_owner_snapshot(owner, view, received))
        result = {'kind': 'OwnerObservation', 'owner': owner, 'event_time_s': self._session.physical_time,
                'decision_epoch': self._epoch, 'native_local_view': plain(view),
                'delivered_planning_snapshots': plain(received),
                'own_outbox': plain(self._client.owned(owner)),
                'actor_information_scope': 'own native observation, actual delivered peer messages, own outbox',
                'guard_information_scope': 'existing current own endpoints and delivered capture stability contract; native executes receiving checks',
                'privileged_evaluator_state_included': False}
        if self._later_mode is not None:
            result['delivered_planning_snapshots_v3'] = later.v3_messages(
                self._session.protocol_planning_snapshots_v3(owner), owner, view['now'])
        return result

    def candidates(self, owner):
        require(owner in OWNERS and self._status == 'running', 'running_known_owner_required')
        due = owner in self._pending
        control = self._later_controls.get(owner)
        if control is not None and control.offer is not None:
            return {'owner': owner, 'decision_epoch': self._epoch, 'scope': 'new_current_later_choices',
                'actions': control.candidates(), 'later_free_action_mask': {'enabled': True},
                'timing_mode': 'offline_sync', 'rl_ready': False}
        action = self._row['method'] if self._phase == 'initial' else 'activate_retained_policy'
        if self._phase != 'initial' and self._later_mode is not None:
            action = 'advance_collection_protocol'
        return {'owner': owner, 'decision_epoch': self._epoch,
                'scope': 'registered initial method' if self._phase == 'initial' else 'fixed retained policy; not fresh R1/R2 alternatives',
                'actions': [{'candidate_id': f'{self._epoch}:{owner}:{action}', 'action': action,
                             'enabled': due, 'reason': None if due else 'owner_not_due'}],
                'supported_initial_methods': list(online.dispatch.ARMS),
                'initial_nondefault_R2_disabled': False,
                'later_free_action_mask': {'enabled': False, 'reason': 'missing_fresh_later_collection_and_submission_contract'}}

    def submit(self, owner, candidate_id, *, shadow=False):
        require(self._pending and self._pending[0] == owner, 'ordered_current_owner_required')
        matches = [row for row in self.candidates(owner)['actions'] if row['candidate_id'] == candidate_id]
        require(len(matches) == 1 and matches[0]['enabled'], 'stale_or_unauthorized_candidate')
        candidate = matches[0]
        started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
        if shadow:
            before = self._session.offline_state_sha256()
            row = {'owner': owner, 'candidate_id': candidate_id, 'event_time_s': self._session.physical_time,
                   'kind': 'ForecastAdvice', 'authority': False, 'native_state_before': before}
            self._shadows.append(row)
            row['native_state_after'] = self._session.offline_state_sha256()
            require(row['native_state_after'] == before, 'shadow_mutated_native_state')
            row['compute_wall_ms'] = (time.perf_counter_ns() - started) / 1e6
            row['compute_cpu_ms'] = (time.process_time_ns() - cpu_started) / 1e6
            return plain(row)
        before_calls = len(self._client.calls)
        before_time = self._session.physical_time
        control = self._later_controls.get(owner)
        if control is not None and control.offer is not None:
            transition = control.submit(candidate_id)
            require(self._session.physical_time == before_time, 'later_submit_must_not_advance_native_time')
            row = {'kind': 'LaterSubmission', 'owner': owner, 'candidate_id': candidate_id,
                'event_time_s': before_time, 'decision_epoch': self._epoch, 'phase': transition['phase'],
                'transition': transition, 'calls': plain(self._client.calls[before_calls:]),
                'submitted_is_not_physical_success': True}
            self._audit.append(row)
            self._pending.pop(0)
            return plain(row)
        self._progress['stage'] = self._phase + '_owner_activation'
        if self._phase == 'initial':
            self._client.activate(owner, self._triggers[owner])
            self._client.refresh_owner(owner, retry=False)
            if self._initial_evaluator is not None:
                decision = online.dispatch.origin.collect_initial_decision(self._native, self._session, owner,
                    self._planning[owner], self._client, self._accepted)
                require(type(decision) is online.dispatch.origin.InitialDecision, 'actual_initial_callback_context')
                before = self._session.offline_state_sha256()
                self._advice[owner] = plain(self._initial_evaluator(decision))
                online.dispatch.origin.require_current(decision)
                require(self._session.offline_state_sha256() == before, 'initial_evaluator_changed_native_truth')
            online.start_owner(self._native, self._session, self._client, owner, self._planning[owner],
                self._channels[owner], self._accepted, arm=self._row['method'], incumbent=online.incumbent_index(),
                progress=self._initial, ledgers=self._ledgers, policies=self._policies)
            require(owner in self._policies, 'missing_admitted_retained_policy')
            if self._later_mode is not None:
                self._later_controls[owner] = later.LaterControl(self._policies[owner],
                    later.initial_reference(self._initial[owner]), model=self._later_model,
                    mode=self._later_mode, phases=self._later_phases)
        else:
            self._policies[owner].activate(self._triggers[owner])
            self._activations += 1
        require(self._session.physical_time == before_time, 'policy_must_not_advance_native_time')
        calls = plain(self._client.calls[before_calls:])
        row = {'owner': owner, 'candidate_id': candidate_id, 'event_time_s': before_time,
               'decision_epoch': self._epoch, 'phase': self._phase,
               'compute_wall_ms': (time.perf_counter_ns() - started) / 1e6,
               'compute_cpu_ms': (time.process_time_ns() - cpu_started) / 1e6,
               'calls': calls, 'submitted_is_not_physical_success': True,
               'action_contract': 'initial_conditional_component' if self._phase == 'initial' else 'retained_policy_current_local_guards'}
        self._audit.append(row)
        for current in self._later_controls.values():
            current.update_ack()
        control = self._later_controls.get(owner)
        if control is not None and control.offer is not None:
            next_observation = control.observation()
            for current in self._later_controls.values():
                for transition in current.transitions:
                    if transition['next_observation'] is None:
                        transition['next_observation'] = plain(next_observation)
                        transition['delta_sim_time_s'] = next_observation['at'] - transition['selected_at']
            row['later_decision_ready'] = True
        else:
            self._pending.pop(0)
        return plain(row)

    def choose_later(self, owner, choose):
        require(self._status == 'running' and owner in self._pending and callable(choose), 'current_later_actor_required')
        control = self._later_controls[owner]
        require(control.offer is not None, 'current_later_offer_required')
        started = time.perf_counter_ns()
        before_time = self._session.physical_time
        before = self._session.offline_state_sha256()
        actor_started = time.perf_counter_ns()
        try:
            chosen = choose(control.observation(), control.candidates())
        finally:
            actor_ms = (time.perf_counter_ns() - actor_started) / 1e6
            after = self._session.offline_state_sha256()
            after_time = self._session.physical_time
            unchanged = before == after and before_time == after_time
            control.offer.update(actor_state_unchanged=unchanged,
                actor_state_check={'native_state_before': before, 'native_state_after': after,
                    'physical_time_before': before_time, 'physical_time_after': after_time,
                    'scope': 'new callback isolation evidence only; hashes are not actor inputs'},
                actor_inference_wall_ms=actor_ms, actor_choose_wall_ms=(time.perf_counter_ns() - started) / 1e6)
            require(unchanged, 'later_actor_changed_native_state_or_clock')
        return chosen

    def advance_to_next_decision(self):
        require(self._status == 'running' and not self._pending, 'consume_current_owner_decisions_first')
        before = self._session.physical_time
        self._phase = 'retained'
        if self._activations >= online.old.MAX_ACTIVATIONS:
            self._status = 'unknown_activation_budget'
            return self._boundary(0.)
        if before >= HORIZON:
            self._status = 'finished'
            return self._boundary(0.)
        deadline = min(HORIZON, online.old.v1.START + self._tick * online.old.v1.PERIOD,
            *(max(policy.pending['deadline'], policy.peer_quiet_until)
              for policy in self._policies.values() if policy.pending))
        require(deadline >= before, 'missed_native_deadline')
        response = self._session.advance_until_owner_notification(list(OWNERS), self._cursors, deadline, max_events=100000)
        self._batches.append({'deadline': deadline, 'response': plain(response)})
        if response['status'] not in {'notified', 'horizon_reached'} or response.get('timestamp_complete') is not True:
            self._status = 'unknown_native_boundary'
            return self._boundary(self._session.physical_time - before)
        now = self._session.physical_time
        due_tick = now == online.old.v1.START + self._tick * online.old.v1.PERIOD
        if due_tick:
            self._tick += 1
        notices = response.get('notifications', {})
        self._pending = sorted(owner for owner, policy in self._policies.items()
            if due_tick or owner in notices or policy.pending and now >= policy.pending['deadline'])
        for owner, notice in notices.items():
            self._cursors[owner] = notice['sequence']
        self._triggers = {owner: {'native_notification': copy.deepcopy(notices.get(owner)),
            'periodic_tick': due_tick,
            'collection_deadline': bool(self._policies[owner].pending and now >= self._policies[owner].pending['deadline'])}
            for owner in self._pending}
        self._epoch += 1
        return self._boundary(now - before)

    def outcome(self):
        """Terminal evaluator-only record; never callable from an actor window."""
        require(self._status == 'finished' and not self._pending, 'terminal_evaluator_only')
        if self._outcome is not None:
            return plain(self._outcome)
        for owner in OWNERS:
            self._client.activate(owner, {'kind': 'final_outbox_collection', 'at': self._session.physical_time})
            self._client.refresh_owner(owner, retry=False)
        continuation = {'status': 'finished', 'route_choices': self._policies['B'].choices,
            'returns': self._policies['A'].returns, 'supply_lineage': self._policies['B'].supplies,
            'recovery_decisions': self._policies['B'].recovery, 'missing_owner_policies': []}
        result = self._session.result_at(self._session.physical_time)
        self._progress['result'] = result
        decisions = {owner: policy.decisions for owner, policy in self._policies.items()}
        if not self._later_controls:
            summary = online.completed_summary(self._data, result, self._client, continuation, self._initial, decisions)
        else:
            effective = online.retrospective_vector(self._initial)
            transitions = [transition for control in self._later_controls.values() for transition in control.transitions]
            for control in self._later_controls.values():
                control.update_ack()
            for transition in transitions:
                if transition['phase'] == 'first_return':
                    effective['return_delay'] = transition['actual_action']['return_delay']
                else:
                    effective['later_action'] = transition['action_id']
                enters = [receipt for receipt in result['receipts'] if receipt['event'] == 'EDGE_ENTER'
                    and receipt['tray_id'] == 'L' and receipt['time'] >= transition['selected_at']
                    and receipt['from'] == (6 if transition['phase'] == 'first_return' else 7)]
                transition['actual_physical_effect'] = {'next_edge_enter': plain(enters[0]) if enters else None,
                    'scope': 'terminal evaluator only; no physical receipts used by actor or guard'}
                transition['terminal_completion'] = {job['business_bag_id']: job['completed_at'] for job in result['jobs']}
                if transition['next_observation'] is None:
                    transition['delta_sim_time_s'] = self._session.physical_time - transition['selected_at']
                    transition['next_state_kind'] = 'terminal_no_next_effective_decision'
            summary = online.old.assess_cell(self._data, result, self._client, continuation, effective)
            for transition in transitions:
                transition['truncated'] = summary['status'] != 'assessed'
                transition['terminated'] = summary['status'] == 'assessed' and transition['next_observation'] is None
            summary.update(later_current_choices_enabled=True, behavior_mode=self._later_mode,
                later_effective_decision_count=len(transitions), effective_vector_evaluator_only=effective,
                initial_reference_refresh_allowed=False, strict_protected=None, rl_ready=False,
                native_model_protection_certified=False, complete_request_100ms_certified=False,
                scope='Actual later submissions and terminal physical assessment; multi-step protected RL not certified.')
        self._outcome = plain({'kind': 'EvaluatorRecord', 'schema': SCHEMA, 'input': self._data, 'result': result,
            'summary': summary, 'specification': self._row, 'initial_owners': self._initial,
            'decisions': decisions, 'continuation': continuation, 'calls': self._client.calls,
            'outbox': self._client.rows, 'request_creations': self._client.creations,
            'owner_activation_admissions': self._client.roots, 'ack_handling': self._client.ack_handling,
            'native_batches': self._batches, 'activation_records': self._audit, 'shadow_records': self._shadows,
            'initial_evaluator_advice': self._advice, 'capabilities': CAPABILITIES,
            'later_transitions': sorted([plain(transition) for control in self._later_controls.values()
                for transition in control.transitions], key=lambda transition: transition['selected_at']),
            'later_collection_failures': {owner: plain(control.collection_failures) for owner, control in self._later_controls.items()},
            'owner_observation_checks': self._observations,
            'native027_acceptance': self._accepted.audit_copy(),
            'retained_ledgers': {owner: ledger.audit_copy() for owner, ledger in self._ledgers.items()}})
        return plain(self._outcome)


def _saved_baseline_comparison(raw, case, method):
    directory = online.old.OUT / 'compatible_initial_native_20261017_004' / case
    path = directory / (method + '.raw.json.gz')
    if not path.exists():
        return {'status': 'unavailable_no_saved_same_method_baseline', 'trajectory_equivalence': None}
    cell = online.old.read(directory / (method + '.cell.json'))
    require(cell['status'] == 'assessed' and online.old.sha(path) == cell['raw_artifact']['sha256'], 'saved_baseline_binding')
    baseline = json.loads(gzip.decompress(path.read_bytes()))
    acceptance = online.old.read(directory / (method + '.acceptance.json'))
    require(acceptance['status'] == 'closed_run_acceptance_passed', 'saved_baseline_closed_acceptance')
    fields = ('receipts', 'jobs', 'trays')
    same = raw['input'] == baseline['input'] and all(raw['result'][field] == baseline['result'][field] for field in fields)
    return {'status': 'exact_saved_baseline_trajectory' if same else 'trajectory_difference',
            'reference': online.old.reference(path), 'input_exact': raw['input'] == baseline['input'],
            'compared_native_result_fields': list(fields), 'all_fields_exact': same,
            'trajectory_equivalence': same,
            'scope': 'same input and method against prior closed native execution; no new paired execution or general shadow proof'}


def run_baseline(output_dir, *, case='mechanism', method='incumbent', initial_evaluator=None,
                 later_choose=None, later_model=None, later_mode=None, later_phases=tuple(later.PHASE_ACTIONS)):
    """One native branch; caller MUST provide a process-level hard timeout.

Output is immutable. Admission validates the existing built binary and saved
closed gates at entry and exit. No build or other native branch is launched.
The optional evaluator gets a genuine current InitialDecision, not raw truth;
its JSON advice never enters dispatch. Import callback modules before calling.
"""
    output = Path(output_dir).resolve()
    require(not output.exists(), 'fresh_output_required')
    key = case + '/' + method
    require(key in online.rows(), 'supported_case_and_method')
    output.mkdir(parents=True)
    contract_path = online.old.OUT / 'native027_accepted_contract_001.json'
    semantic_path = online.old.OUT / 'native027_semantic_native_002/receipt.json'
    contract = online.old.read(contract_path)
    plan = {'schema': SCHEMA, 'rows': {key: online.rows()[key]}, 'branch_order': [key],
        'native_branch_budget': 1, 'horizon': HORIZON, 'timing_mode': 'offline_sync',
        'native_contract_reference': online.old.reference(contract_path),
        'semantic_gate_reference': online.old.reference(semantic_path), 'binary': online.old.reference(contract['binary']),
        'source_sha256': {}, 'source_archive': {}, 'input_file_sha256': {},
        'capabilities': CAPABILITIES, 'initial_evaluator_enabled': initial_evaluator is not None,
        'later_control': {'mode': later_mode, 'phases': list(later_phases), 'enabled': later_mode is not None}}
    for source in online.old.bound.imported_sources():
        archive = output / 'source' / source.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(source.read_bytes())
        plan['source_sha256'][str(source)] = online.old.sha(source)
        plan['source_archive'][str(source)] = str(archive.relative_to(output))
    input_path = output / 'inputs' / (key + '.json')
    write(input_path, online.old.native_scene(case))
    plan['input_file_sha256'][key] = online.old.sha(input_path)
    write(output / 'preregistered_protocol.json', plan)
    campaign = online.old.reference(output / 'preregistered_protocol.json')
    accepted, environment = None, None
    started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
    receipt = {'status': 'unknown_unexecuted', 'native_session_attempted': False, 'plan': campaign,
               'complete_request_100ms_certified': False, 'capabilities': CAPABILITIES}
    try:
        accepted = online.old.run_admission.open_run(plan['native_contract_reference'], plan['semantic_gate_reference'], campaign)
        native = online.old.native_host.load_native(Path(plan['binary']['path']))
        accepted.enter_branch(key, campaign)
        environment = FoundationNativeEnvironment(native, accepted, key, plan['native_contract_reference'],
            initial_evaluator=initial_evaluator, later_model=later_model, later_mode=later_mode, later_phases=later_phases)
        receipt['native_session_attempted'] = True
        boundary = environment.reset()
        boundaries, shadowed = [boundary], set()
        while boundary['status'] == 'running':
            for owner in boundary['due_owners']:
                while owner in environment._pending:
                    observation = environment.observe(owner)
                    require(observation['owner'] == owner and not observation['privileged_evaluator_state_included'], 'actor_observation_scope')
                    candidates = environment.candidates(owner)['actions']
                    if observation.get('schema') == later.ACTOR_SCHEMA:
                        require(any(candidate['enabled'] for candidate in candidates), 'all_later_candidates_unknown_or_rejected')
                        require(later_choose is not None, 'explicit_later_actor_required')
                        chosen = environment.choose_later(owner, later_choose)
                    else:
                        chosen = candidates[0]['candidate_id']
                        shadow_key = (owner, boundary['phase'])
                        if shadow_key not in shadowed:
                            environment.submit(owner, chosen, shadow=True)
                            shadowed.add(shadow_key)
                    environment.submit(owner, chosen)
            boundary = environment.advance_to_next_decision()
            boundaries.append(boundary)
        require(boundary['status'] == 'finished', 'incomplete_native_rollout:' + boundary['status'])
        raw = environment.outcome()
        raw['decision_boundaries'] = boundaries
        raw['saved_baseline_comparison'] = _saved_baseline_comparison(raw, case, method)
        raw_path = output / 'raw.json.gz'
        raw_path.write_bytes(gzip.compress(json.dumps(raw, allow_nan=False).encode(), compresslevel=1, mtime=0))
        receipt.update(status=raw['summary']['status'], summary=raw['summary'], raw_artifact=online.old.reference(raw_path),
                       saved_baseline_comparison=raw['saved_baseline_comparison'],
                       actual_owner_activation_count=len(raw['activation_records']), native_boundary_count=len(boundaries),
                       shadow_count=len(raw['shadow_records']))
        accepted.finish_branch(key)
    except Exception:
        receipt.update(status='unknown_failed', exception=traceback.format_exc())
        if environment is not None:
            partial = online.old.capture_partial(environment._progress, receipt['exception'])
            partial['later_control'] = {owner: control.audit_copy() for owner, control in environment._later_controls.items()}
            write(output / 'partial.json', partial)
            receipt['partial_artifact'] = online.old.reference(output / 'partial.json')
    finally:
        if accepted is not None:
            closed = accepted.close()
            write(output / 'acceptance.json', closed)
            receipt['run_acceptance_status'] = closed['status']
            if closed['status'] != 'closed_run_acceptance_passed':
                receipt['status'] = 'unknown_invalidated_runtime_evidence'
        receipt['compute_wall_ms'] = (time.perf_counter_ns() - started) / 1e6
        receipt['compute_cpu_ms'] = (time.process_time_ns() - cpu_started) / 1e6
        write(output / 'receipt.json', receipt)
    return receipt
