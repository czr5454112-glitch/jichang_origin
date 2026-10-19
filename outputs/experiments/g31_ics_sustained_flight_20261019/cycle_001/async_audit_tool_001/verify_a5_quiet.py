"""Read-only actual A5 reply/return audit. No native/controller imports."""
import gzip
import json
from pathlib import Path
from audit_async import load_closed, one, read, reference, require

HERE = Path(__file__).resolve().parent
folder = HERE.parent/'A5_train_async_001'
raw, _, _ = load_closed(folder)
old, _, _ = load_closed(HERE.parent/'A4_train_async_001')
baseline_ref = read(folder/'plan.json')['original_reference']
baseline = json.loads(gzip.decompress(Path(baseline_ref['path']).read_bytes()))
audited = read(HERE/'A5_train_async_audit_001.json')
findings = []
previous_until = 0.
for row in raw['collection_policy_intervals']['A']:
    if 'reply_silence_contract' not in row:
        previous_until = max(previous_until, row['through'])
        continue
    identity = row['reply_request_id']; now = row['at']
    exchange = one([item for item in raw['exchanges']['A'] if item.get('request_id') == identity], 'actual_reply_exchange')
    envelope = exchange['message']; local = envelope['capture']['capture_v2']['local_capture']
    source = one([item for item in raw['outbox'].values() if (item.get('ack') or {}).get('result_id') == local['message_id']], 'actual_source_publication')
    require(source['request']['owner_id'] == 'B' and source['ack']['planning_snapshot_v3'] == envelope,
        'exchange_matches_native_source_publication_result')
    reply = raw['outbox'][identity]['request']
    call = one([item for item in raw['calls'] if item['request']['request_id'] == identity and not item['retry']], 'actual_reply_call')
    cause = raw['request_creations'][identity]['causal']['delivered_parent_message']
    require(call['at'] == now and call['request'] == reply and exchange['at'] == now
        and reply['owner_id'] == 'A' and reply['target_owner'] == 'B' and reply['kind'] == 'planning_snapshot_v3'
        and cause['message_id'] == row['message_id'] == local['message_id'] and local['source_owner'] == 'B'
        and local['target_owner'] == 'A' and local['captured_at'] <= envelope['delivered_at'] <= now
        and now-local['captured_at'] <= .05 and now < local['valid_until'], 'actual_current_reply_causality')
    coverage = local['coverage']
    require(coverage['complete_for_declared_local_scope'] is True and coverage['future_arrivals_included'] is False
        and coverage['tray_ids'] == [tray['tray_id'] for tray in local['trays']], 'actual_complete_local_tray_scope')
    loaded7 = any(tray['tray_id'] == 'L' and tray['mode'] == 'loaded' and tray['node'] == 7 for tray in local['trays'])
    expected = .08 if loaded7 else .02
    require(row['reply_silence_contract']['silence_s'] == expected and row['source_reply_identity_bound'] is True
        and row['reply_silence_contract']['execution_authority'] is False and row['native_physics_paused'] is False
        and row['worker_waited_for'] is False, 'declared_window_matches_actual_nonexecution_or_current_state')
    if not loaded7:
        require(reply['publication_delay'] == reply['message_delay'] == .01, 'actual_short_window_delays')
        own = raw['outbox'][identity]['ack']['planning_snapshot_v3']
        require(abs(own['capture']['capture_v2']['local_capture']['captured_at']-(now+.01)) < 1e-12
            and abs(own['delivered_at']-(now+.02)) < 1e-12, 'actual_reply_capture_delivery_inside_window')
    through = max(previous_until, now+expected)
    require(row['through'] == through and row['incremental_policy_silence_s'] == max(0., through-max(previous_until, now))
        and row['effective_policy_silence_s'] == through-now, 'actual_silence_cost_and_existing_window_preserved')
    previous_until = through
    findings.append({'reply': identity, 'source_message': local['message_id'], 'at_sim_s': now,
        'source_age_sim_s': now-local['captured_at'], 'source_L_loaded_at7': loaded7,
        'silence_sim_s': expected, 'incremental_silence_sim_s': row['incremental_policy_silence_s'], 'status': 'passed'})

def return_at(data):
    return one([item['at'] for item in data['calls'] if item['request']['request_id'] == 'live:1:A:return-1'
        and not item['retry']], 'actual_original_return_1')

require(return_at(raw) == return_at(baseline), 'original_return_timing_restored')
require(raw['input'] == baseline['input'] == old['input'], 'same_original_input')
delta = {key: value-baseline['summary']['completion'][key] for key, value in raw['summary']['completion'].items()}
require(set(delta) == {job['business_bag_id'] for job in raw['input']['jobs']} and all(value <= 0 for value in delta.values()),
    'all_original_business_no_harm_actual')
result = {'schema': 'g31.independent.a5_quiet_timing_audit.v1', 'status': 'passed_actual_silence_and_restored_return',
    'source': reference(__file__), 'raw': reference(folder/'raw.json.gz'), 'old_A4': reference(HERE.parent/'A4_train_async_001/raw.json.gz'),
    'baseline': baseline_ref, 'complete_chain_audit': reference(HERE/'A5_train_async_audit_001.json'), 'quiet_records': findings,
    'actual_return_1_sim_s': {'baseline': return_at(baseline), 'A4': return_at(old), 'A5': return_at(raw)},
    'actual_per_job_completion_delta_to_original': delta, 'actual_completion_sum': raw['summary']['completion_sum'],
    'actual_ranked_and_executed_body_count': audited['consumed_submitted_ack_edge_chains'],
    'worker_changes_choice_vs_current_only_rule_count': sum(row['async']['worker_order_changes_choice'] for row in audited['decisions']),
    'interpretation': 'Both complete bodies actually enter ranking among multiple current-authorized choices and both commands execute. Current-only scoring chooses the same actions, so this establishes consumption/concurrency, not marginal benefit of asynchronous advice.',
    'timings': [{'job': row['target_job'], 'worker_ms': row['async']['wall_milliseconds'],
        'current_ms': row['current_timing'], 'sim_s': row['async']['sim_seconds']} for row in audited['decisions']],
    'full_request_100ms_certified': False, 'native_started_by_this_audit': False, 'source_modified': False}
destination = HERE/'A5_quiet_and_timing_audit_001.json'
require(not destination.exists(), 'fresh_output_required')
destination.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf8')
print(json.dumps({'status': result['status'], 'quiet_records': len(findings), 'deltas': delta, 'return': result['actual_return_1_sim_s']}))
