"""Closed callback header/order binding and wall-cost audit; no native calls."""
from collections import Counter
import json

from audit import BRANCH, HERE, RUN, load, save, sha
from scripts.experiments.g31_ics_circulation.foundation_airport_observations_v2 import members


def main():
    raw, receipt = load(BRANCH/'raw.json.gz'), load(RUN/'receipt.json')
    expected, segments = [], []
    for item in raw['segments']:
        segment = load(item['raw']['path'])
        native_ms = sum(x['wall_ms'] for x in segment['native_batches'])
        prepare_ms = sum(x['preparation_compute_ms'] for x in segment['control_records'])
        decision_ms = sum(x['compute_ms'] for t in segment['control_records'] for x in t['owner_decisions'])
        segments.append({'index':item['index'],'start':item['start_at'],'end':item['actual_clock'],
            'segment_wall_seconds':segment['wall_seconds'],
            'elapsed_including_segment_archive_seconds':item['elapsed_wall_seconds'],
            'native_advance_wall_seconds':native_ms/1000,'preparation_seconds':prepare_ms/1000,
            'decision_loop_seconds_including_recording':decision_ms/1000})
        for tick in segment['control_records']:
            if not 43200 <= tick['at'] <= 59400:
                continue
            for owner in tick['owner_decisions']:
                attempts = owner['attempts']
                base = {'now':tick['at'],'owner':owner['owner_id'],'tick':tick['tick'],
                    'segment':item['index']}
                expected.append({**base,'prefix':f"protocol:{tick['tick']}",
                    'prior_pending_request':None,
                    'next_attempt_request':attempts[0]['request_id'] if attempts else None})
                for i,attempt in enumerate(attempts):
                    if attempt['reply']['status'] == 'pending':
                        expected.append({**base,'prefix':f"protocol:{tick['tick']}:residual",
                            'prior_pending_request':attempt['request_id'],
                            'next_attempt_request':attempts[i+1]['request_id'] if i+1 < len(attempts) else None})
    count = 0
    for count, payload in enumerate(members(BRANCH/'policy_observations.jsonl.gz'), start=1):
        row = json.loads(payload)
        ref = expected[count-1]
        assert row['sequence'] == count-1 and row['now'] == ref['now'] and row['owner_id'] == ref['owner']
        option = row['policy_options']['fields']['request_prefix']
        assert option['kind'] == 'inline' and option['value'] == ref['prefix']
    assert count == len(expected)
    calls = load(BRANCH/'client_calls.json.gz')
    call_ids = Counter(c['request']['request_id'] for c in calls if c['kind']=='transfer')
    referenced = {r['next_attempt_request'] for r in expected if r['next_attempt_request'] is not None}
    assert all(r in call_ids for r in referenced)
    recorder = load(BRANCH/'policy_observation_receipt.json')
    last = raw['segments'][-1]
    previous, full = raw['segments'][-3:-1]
    cost = full['elapsed_wall_seconds']-previous['elapsed_wall_seconds']
    interval = full['actual_clock']-previous['actual_clock']
    remaining = 59400-raw['final_physical_time']
    estimate = last['elapsed_wall_seconds'] + cost*remaining/interval
    report = {'schema':'g31.airport_closed_callback_order_and_cost.v1',
        'native_sessions':0,'record_header_count':count,
        'callback_order_owner_time_prefix_exactly_matches_closed_control_records':True,
        'distinct_next_attempt_request_ids':len(referenced),
        'all_next_attempts_have_immutable_client_calls':True,
        'payload_binding_scope':'Header/order join only; full action payload equality and offline outcome labels need separate validation.',
        'actor_private_fields_added':False,'receiver_ledger_completeness_inferred':False,
        'training_scope':'One censored trajectory development prefix only; no independent train/dev/test or unvisited candidate labels.',
        'capture_seconds':recorder['capture_seconds'],'segments':segments,
        'estimate':{'last_complete_interval_seconds':interval,'last_complete_interval_wall_seconds':cost,
            'actual_soft_stop':raw['final_physical_time'],'remaining_simulated_seconds':remaining,
            'projected_remaining_wall_seconds':cost*remaining/interval,
            'projected_complete_loop_wall_seconds':estimate,'outer_closure_allowance_seconds':31,
            'projected_with_allowance_seconds':estimate+31,
            'prior_child_wall_seconds':receipt['process']['wall_seconds'],
            'recommended_soft_inner_outer_seconds':[600,660,720],'completion_guarantee':False}}
    save('callback_order_binding.json',expected)
    save('binding_and_cost.json',report)
    print(json.dumps({'callback_count':count,'request_ids':len(referenced),'estimate':report['estimate']}))


if __name__ == '__main__':
    main()
