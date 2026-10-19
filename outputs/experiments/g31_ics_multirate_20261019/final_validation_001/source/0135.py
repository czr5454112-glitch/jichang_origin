"""Opt-in second successful B collection; observations are not extra actions.

The original protocol runs between collections. This probe neither edits old
commands nor pauses native physics, and it does not authorize cached execution.
"""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv:
        raise SystemExit('successful_refresh:missing_parent_admission')
    if sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission') + 1]:
        raise SystemExit('successful_refresh:missing_parent_admission')

import argparse
import gzip
import json
from pathlib import Path
import secrets
import traceback

from . import bounded_windows_job
from . import foundation_later_campaign as campaign
from . import foundation_later_control as control
from . import foundation_later_episode as episode
from . import foundation_later_seed as model
from . import foundation_native_environment as environment
from . import foundation_service_refresh as refresh
from . import live_obligation_recollection_policy as collection

ROOT = campaign.ROOT
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_successful_refresh_probe'
SCHEMA = 'g31.foundation.successful_refresh_probe.v1'
HARD_SECONDS = 150
BASELINE = ROOT / 'outputs/experiments/g31_ics_learning_next_20261017/later_episodes_001/guarded_default/episode/native'
PHYSICAL_EVENTS = ('BAG_ARRIVAL', 'LOAD_START', 'LOAD_COMPLETE', 'EDGE_ENTER', 'EDGE_EXIT',
    'STORAGE_ENTER', 'STORAGE_RELEASE', 'UNLOAD_START', 'UNLOAD_COMPLETE', 'HOLD_START', 'HOLD_COMPLETE', 'EMPTY_RECEIVED',
    'LEG_START', 'LEG_COMPLETE', 'EXPORT_GRANTED', 'MODULE_REQUEST_DELIVERED', 'RESOURCE_WAIT', 'RESOURCE_WAKE',
    'ROUTE_INTENT_updated', 'TRANSFER_REJECTED', 'PROTOCOL_ACK_DELIVERED')
COMMAND_ACK_EVENT = 'PROTOCOL_COMMAND_ACK_DELIVERED'
COMMUNICATION_KINDS = ('demand', 'planning_snapshot', 'planning_snapshot_v3')


def require(condition, reason):
    if not condition:
        raise ValueError('successful_refresh:' + reason)


def publication_identities(evidence):
    endpoints = evidence['information']['raw_endpoints']
    own = endpoints['command']['last_delivered_ack']['planning_snapshot_v3']
    selected = [item for item in endpoints['received'] if item['capture']['capture_v2']['local_capture']['message_id']
                == evidence['collection']['peer_message']]
    require(len(selected) == 1, 'exact_selected_peer_message')
    return {name: {field: envelope['capture']['capture_v2']['local_capture'][field]
                  for field in ('message_id', 'publication_sequence', 'captured_at')}
            for name, envelope in (('own', own), ('peer', selected[0]))}


class ProbeLaterControl(control.LaterControl):
    def __init__(self, *args, episode_id, **kwargs):
        super().__init__(*args, **kwargs)
        require(self.policy.owner == 'B' and self.mode == 'guarded', 'B_guarded_probe_only')
        require(type(episode_id) is str and bool(episode_id), 'explicit_episode_identity')
        self.episode_id = episode_id
        self.successful_observations = []
        self.followup_request = None
        self.refresh_result = None

    def collect(self, view):
        super().collect(view)
        if self.offer is None or self.offer['pending']['phase'] != 'first_reuse_route':
            return
        if self.followup_request is None:
            self.begin_successful_followup()
        else:
            self.finish_successful_followup()

    def snapshot(self):
        offer = self.offer
        require(offer is not None and self.adapter.is_native_collected(offer['handle'])
                and offer['actual_collection_supported'], 'genuine_successful_current_collection')
        require(offer['model_report']['status'] == 'conditional_current_seed', 'known_current_seed_required')
        defaults = [row for row in offer['actions'] if row['action_id'] == 'native_default']
        require(len(defaults) == 1 and defaults[0]['enabled'] is True
                and defaults[0]['guard_status'] == 'passed', 'protected_default_required')
        return control.plain({'evidence': offer['evidence'], 'observation': offer['observation'],
            'candidate_mask': offer['actions'], 'model_report': offer['model_report'],
            'initial_reference': offer['initial_reference'], 'initial_reference_sha256': self.reference_sha,
            'collection_through_offer_wall_ms': offer['collection_through_offer_wall_ms'],
            'model_and_guard_wall_ms': offer['model_and_guard_wall_ms'],
            'collection_segments': offer.get('collection_segments'),
            'publication_identities': publication_identities(offer['evidence']),
            'observation_only': True, 'action_or_transition_created': False})

    def begin_successful_followup(self):
        policy, offer = self.policy, self.offer
        require(not self.successful_observations and self.followup_request is None, 'single_followup_budget')
        snapshot = self.snapshot()
        pending = offer['pending']
        require(pending['phase'] == 'first_reuse_route' and pending.get('recollection_index') == 0,
                'unused_first_reuse_collection_budget')
        require(control.encoding(policy.pending) == control.encoding(pending), 'pending_identity_changed')
        now = policy.session.physical_time
        require(now == snapshot['observation']['at'] and policy.client.context['owner'] == 'B'
                and policy.client.context['accepted_at'] == now, 'current_B_admission_required')
        view = policy.session.observe_protocol('B')
        _, same = control.representation.equivalent_views(view, offer['handle']['raw_endpoints']['view'])
        require(same, 'current_owner_view_changed')
        require(control.encoding(control.plain(policy.client.owned('B')))
                == control.encoding(offer['evidence']['own_outbox']), 'owned_outbox_changed')
        collection.local_target(view, pending['trigger_tray'], pending['phase'])
        epochs = collection.sequential_epochs(now)
        bound = offer['handle']['bundle']['trays']['L']['service_ready_at']
        require(collection.finite(bound) and epochs['physical_wire'] < bound, 'insufficient_actual_service_window')
        for row in policy.client.owned('B').values():
            if row['kind'] in collection.PHYSICAL_KINDS:
                require(row['terminal'] is True and row.get('ack', {}).get('status') in collection.TERMINAL_BY_KIND[row['kind']],
                        'pending_physical_command')
        self.successful_observations.append(snapshot)
        causal = {'relation': 'replacement_replan', 'continuation_parent_roots': [pending['root']],
            'predecessor_protocol_id': pending['request_id'], 'delivered_peer_message_id': pending['peer_message'],
            'collection_phase': pending['phase'], 'probe_reason': 'one_successful_pair_followup_observation',
            'prior_collection_succeeded': True, 'prior_offer_executed': False}
        identity = policy.publication('successful-probe-first_reuse_route', causal)
        require(identity != pending['request_id'], 'new_publication_identity_required')
        deadline = min(now + collection.bound.COLLECTION_LIMIT, bound)
        policy.pending = {**control.plain(pending), 'at': now, 'deadline': deadline,
            'request_id': identity, 'peer_message': None, 'recollection_index': 1,
            'original_request_id': pending['request_id'], 'successful_followup_probe': True}
        policy.quiet_periods.append({'at': now, 'through': deadline, 'phase': pending['phase'],
            'reason': 'successful_pair_probe_pending', 'native_physics_paused': False})
        self.followup_request = {'request_id': identity, 'at': now, 'nominal_epochs': epochs,
            'retained_service_bound': bound, 'prior_request_id': pending['request_id'],
            'additional_physical_commands': 0, 'native_physics_paused': False}
        offer['attempt']['disposition'] = 'successful_observation_saved_not_executed_followup_requested'
        self.offer = None

    def finish_successful_followup(self):
        require(len(self.successful_observations) == 1, 'exactly_one_prior_successful_observation')
        current = self.snapshot()
        previous = self.successful_observations[0]
        pending = current['evidence']['collection']
        require(pending['request_id'] == self.followup_request['request_id']
                and pending.get('successful_followup_probe') is True, 'followup_request_binding')
        require(current['observation']['at'] > previous['observation']['at'], 'new_real_observation_epoch')
        for side in ('own', 'peer'):
            before, after = previous['publication_identities'][side], current['publication_identities'][side]
            require(after['message_id'] != before['message_id']
                    and after['publication_sequence'] > before['publication_sequence']
                    and after['captured_at'] > before['captured_at'], 'new_monotone_' + side + '_publication')
        self.successful_observations.append(current)
        self.offer['attempt']['successful_followup_observation_index'] = 1

    def audit_copy(self):
        result = super().audit_copy()
        result['successful_refresh_probe'] = control.plain({'episode_id': self.episode_id,
            'successful_observations': self.successful_observations, 'followup_request': self.followup_request,
            'refresh_result': self.refresh_result, 'first_observation_not_action': True,
            'local_suffix_reuse_authorized': False, 'rl_ready': False})
        return result


def make_factory(episode_id, controls):
    def factory(policy, reference, **kwargs):
        result = (ProbeLaterControl(policy, reference, episode_id=episode_id, **kwargs)
                  if policy.owner == 'B' else control.LaterControl(policy, reference, **kwargs))
        controls[policy.owner] = result
        return result
    return factory


def baseline_references():
    receipt = campaign.read(BASELINE / 'receipt.json')
    require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
            'closed_saved_baseline_required')
    require(receipt['raw_artifact']['sha256'] == campaign.sha(BASELINE / 'raw.json.gz'), 'baseline_raw_binding')
    return {name: campaign.reference(BASELINE / name) for name in ('receipt.json', 'raw.json.gz')}


def check_plan(plan):
    require(plan['schema'] == SCHEMA and plan['hard_seconds'] == HARD_SECONDS and plan['native_branches'] == 1
        and plan['automatic_retries'] == 0 and plan['case'] == 'mechanism' and plan['method'] == 'incumbent'
        and plan['horizon'] == 40. and plan['probe_owner'] == 'B' and plan['extra_successful_pairs'] == 1,
        'fixed_probe_protocol')
    require(plan['source_pins'] == campaign.source_pins(), 'source_set_or_bytes_changed')
    for item in list(plan['baseline'].values()) + plan['runtime_references']:
        require(campaign.sha(item['path']) == item['sha256'], 'reference_bytes_changed')


def prepare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and output != ROOT and not output.exists(), 'fresh_workspace_output')
    contract = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    semantic = contract.parent / 'native027_semantic_native_002/receipt.json'
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'hard_seconds': HARD_SECONDS,
        'native_branches': 1, 'automatic_retries': 0, 'case': 'mechanism', 'method': 'incumbent', 'horizon': 40.,
        'probe_owner': 'B', 'extra_successful_pairs': 1, 'episode_id': secrets.token_hex(24),
        'source_pins': campaign.source_pins(), 'baseline': baseline_references(),
        'runtime_references': [campaign.reference(path) for path in (contract, semantic,
            campaign.read(contract)['binary'], sys.executable)], 'physical_events_compared': list(PHYSICAL_EVENTS),
        'command_ACK_classification': 'retain route/transfer; only demand/planning_snapshot/planning_snapshot_v3 may differ',
        'unknown_event_or_command_kind': 'fail_closed',
        'first_observation_is_not_action': True, 'original_reference_refresh_allowed': False,
        'rl_ready': False, 'local_suffix_reuse_authorized': False, 'complete_request_100ms_certified': False,
        'scope': 'One genuine second successful collection; protocol differs, physical default trajectory must match.'}
    output.mkdir(parents=True, exist_ok=False)
    campaign.write_new(output / 'plan.json', plan)
    check_plan(plan)
    return plan


def physical_receipts(raw):
    rows = []
    for row in raw['result']['receipts']:
        if row['event'] in PHYSICAL_EVENTS:
            rows.append(row)
        else:
            require(row['event'] == COMMAND_ACK_EVENT, 'unclassified_native_event:' + row['event'])
            request_id = row['reason'].rsplit(':', 1)[0]
            kind = raw['outbox'][request_id]['kind']
            require(kind in ('route', 'transfer') + COMMUNICATION_KINDS, 'unclassified_command_ACK_kind:' + kind)
            if kind in ('route', 'transfer'):
                rows.append(row)
    return rows


def assess(raw, baseline, audit):
    observations = audit['successful_observations']
    require(len(observations) == 2 and audit['refresh_result']['status'] == 'full_refresh_required', 'two_successful_current_contexts')
    transitions = raw['later_transitions']
    require(len(transitions) == 2 and [row['executed_action_id'] for row in transitions] == ['return_now', 'native_default'],
            'only_original_two_default_actions')
    require([row['owner'] for row in transitions] == ['A', 'B'], 'original_owner_action_order')
    before, after = observations
    require(transitions[1]['observation'] == after['observation'] and transitions[0]['next_observation'] == after['observation']
            and transitions[1]['selected_at'] > before['observation']['at'], 'only_new_B_observation_becomes_action')
    require(transitions[1]['command_id'] is None and transitions[1]['command_ids'] == [] and transitions[1]['ACK'] is None
            and transitions[1]['ACK_status'] == 'not_applicable_no_command', 'default_has_no_command_or_fake_ACK')
    for transition in transitions:
        require(transition['conditional_protection_status'] == 'passed' and transition['actor_state_unchanged'] is True
            and transition['actual_physical_effect']['next_edge_enter'] is not None, 'guarded_actual_default_effect')
    require({row['event'] for row in raw['result']['receipts']} == {row['event'] for row in baseline['result']['receipts']},
            'baseline_event_vocabulary_changed')
    physical = [physical_receipts(value) for value in (baseline, raw)]
    actual = episode.compare_terminal(baseline, raw)
    parity = {'input': control.encoding(raw['input']) == control.encoding(baseline['input']),
        'physical_receipts_all_fields': control.encoding(physical[0]) == control.encoding(physical[1]),
        'physical_receipt_count': len(physical[1]),
        **{field: control.encoding(raw['result'][field]) == control.encoding(baseline['result'][field]) for field in ('jobs', 'trays')}}
    require(all(parity[field] for field in ('input', 'physical_receipts_all_fields', 'jobs', 'trays'))
            and all(value == 0 for value in actual['per_job_delta'].values()), 'default_physical_trajectory_changed')
    return {'physical_parity': parity, 'actual_terminal_comparison': actual,
        'protocol_receipts_equal': control.encoding(raw['result']['receipts']) == control.encoding(baseline['result']['receipts']),
        'observation_times': [row['observation']['at'] for row in observations],
        'additional_business_actions': 0, 'learning_gain_measured': False, 'rl_ready': False,
        'local_suffix_reuse_authorized': False, 'complete_request_100ms_certified': False}


def worker(output, expected_plan_sha):
    output = Path(output).resolve()
    plan = campaign.read(output / 'plan.json')
    controls = {}
    report = {'schema': SCHEMA, 'status': 'unknown_failed', 'native_execution_attempted': False}
    try:
        require(campaign.sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_before_worker')
        check_plan(plan)
        report['native_execution_attempted'] = True
        receipt = environment.run_baseline(output / 'native', later_choose=episode.fixed_choice({
            'first_return': 'return_now', 'first_reuse_route': 'native_default'}), later_model=model,
            later_mode='guarded', later_control_factory=make_factory(plan['episode_id'], controls))
        report['native_receipt'] = campaign.reference(output / 'native/receipt.json')
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
                'closed_native_run_required')
        raw_path = output / 'native/raw.json.gz'
        require(receipt['raw_artifact']['sha256'] == campaign.sha(raw_path), 'native_raw_binding')
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
        baseline = json.loads(gzip.decompress(Path(plan['baseline']['raw.json.gz']['path']).read_bytes()))
        report['native_raw'] = campaign.reference(raw_path)
        records = [refresh.make_record(row['evidence'], episode_id=report['native_raw']['sha256'],
            original_reference_sha256=row['initial_reference_sha256']) for row in controls['B'].successful_observations]
        require(len(records) == 2, 'two_successful_observations_before_refresh_audit')
        controls['B'].refresh_result = refresh.refresh_audit(records[0], records[1], audit_at=records[1]['evidence']['at'])
        campaign.write_new(output / 'refresh_audit.json', {'episode_binding': {'plan_episode_id': plan['episode_id'],
            'plan': campaign.reference(output / 'plan.json'), 'native_raw': report['native_raw'],
            'native_receipt': report['native_receipt']}, 'records': records, 'audit': controls['B'].refresh_result,
            'scope': 'Post-run supplied-data audit; caller-supplied episode identity is not promoted to native authority.'})
        report['refresh_audit'] = campaign.reference(output / 'refresh_audit.json')
        report.update(assess(raw, baseline, controls['B'].audit_copy()['successful_refresh_probe']))
        report['status'] = 'completed_successful_refresh_probe'
    except Exception:
        report['exception'] = traceback.format_exc()
    finally:
        campaign.write_new(output / 'probe_observations.json', {owner: current.audit_copy() for owner, current in controls.items()})
        report['probe_observations'] = campaign.reference(output / 'probe_observations.json')
        try:
            require(campaign.sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_during_worker')
            check_plan(plan)
            report['source_and_reference_exit_pins_passed'] = True
        except Exception:
            report['status'] = 'unknown_failed'
            report['exit_pin_exception'] = traceback.format_exc()
    campaign.write_new(output / 'worker_report.json', report)
    return report


def launch(output):
    output = Path(output).resolve()
    plan = campaign.read(output / 'plan.json')
    check_plan(plan)
    plan_sha = campaign.sha(output / 'plan.json')
    campaign.write_new(output / 'launch_started.json', {'plan_sha256': plan_sha, 'hard_seconds': HARD_SECONDS})
    admission = secrets.token_hex(24)
    receipt = {'schema': SCHEMA, 'status': 'unknown_failed', 'plan': campaign.reference(output / 'plan.json')}
    try:
        with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
            process = bounded_windows_job.run([sys.executable, '-m', MODULE, '--worker', '--output', str(output),
                '--plan-sha256', plan_sha, '--admission', admission], timeout=HARD_SECONDS,
                stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
        receipt['process'] = process
        report_path = output / 'worker_report.json'
        report = campaign.read(report_path) if report_path.exists() else {}
        receipt['worker_report'] = campaign.reference(report_path) if report_path.exists() else None
        check_plan(plan)
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed_after_worker')
        require(process['status'] == 'exited' and process['exitcode'] == 0
                and report.get('status') == 'completed_successful_refresh_probe'
                and report.get('source_and_reference_exit_pins_passed') is True, 'process_and_worker_success_required')
        for name in ('native_receipt', 'native_raw', 'probe_observations', 'refresh_audit'):
            require(campaign.sha(report[name]['path']) == report[name]['sha256'], 'worker_artifact_binding:' + name)
        native_receipt = campaign.read(report['native_receipt']['path'])
        require(native_receipt['status'] == 'assessed' and native_receipt['run_acceptance_status'] == 'closed_run_acceptance_passed'
                and native_receipt['raw_artifact'] == report['native_raw'], 'closed_native_artifact_binding')
        receipt['status'] = 'completed_successful_refresh_probe'
    except Exception:
        receipt['exception'] = traceback.format_exc()
    campaign.write_new(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--launch', action='store_true')
    action.add_argument('--worker', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--admission')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    result = prepare(args.output) if args.prepare else worker(args.output, args.plan_sha256) if args.worker else launch(args.output)
    print(json.dumps({'status': result['status']}))
    return 0 if result['status'] in ('prepared_unexecuted', 'completed_successful_refresh_probe') else 1


if __name__ == '__main__':
    raise SystemExit(main())
