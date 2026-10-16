"""Independent terminal-artifact audit; never starts or restores NativeSession."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from . import research_original_low_wip_repeat as p
from . import verify_original_low_wip_repeat as frozen
from .review_original_low_wip_reuse_saved import independent_fifo_choice


def require(ok, why):
    if not ok:
        raise ValueError('repeat_saved_review:' + why)


def ordered(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def check_actual_call(row, parking_ids, token):
    # ProtocolClient._send stores immutable identity inside the payload. The
    # frozen first verifier erroneously expected a top-level request_id.
    require(finite(row['submit_compute_ms']), 'invalid_submit_clock')
    request=row['request'];rid=request['request_id']
    require(type(rid) is str and bool(rid), 'invalid_call_request_identity')
    if 'request_id' in row: require(row['request_id']==rid, 'conflicting_call_identity')
    if row['kind']=='transfer' and rid not in parking_ids:
        require(request['tray_id']==token,'parked_tray_reused')


def verify_case_corrected(directory):
    """Separate saved-only correction, never rewrites old verifier/results."""
    plan=p.base.read(directory/'preregistered_protocol.json');p.verify_pins(directory,plan)
    with p.installed(): replay=p.base.verify_saved(directory)
    data=p.base.gzread(directory/'input.json.gz');raw=p.base.gzread(directory/'raw_final.json.gz')
    source_ids=[j['business_bag_id'] for j in data['jobs']];actual_ids=[j['business_bag_id'] for j in raw['result']['jobs']]
    require(len(source_ids)==len(set(source_ids))==len(actual_ids)==len(set(actual_ids))==28506
        and set(source_ids)==set(actual_ids),'all_offered_ids')
    require(len(raw['result']['trays'])==22 and {t['tray_id'] for t in raw['result']['trays']}=={t['tray_id'] for t in data['trays']},'all_trays')
    selected=p.supplies(raw);token=plan['parking_plan']['token_tray_id'];parks={x['request_id'] for x in plan['parking_plan']['parking']}
    require(len(selected)<=plan['supply_cap'],'supply_cap')
    for owner in raw['owners']:
        require(len(owner['repeat_publications'])<=p.MAX_PUBLICATIONS
            and len(owner['consumed'])==len(set(owner['consumed']))==len(owner['repeated']),'permit_publication_denominator')
        for row in owner['calls']: check_actual_call(row,parks,token)
    require(len(raw['native_state_sha256'])==64 and all(c in '0123456789abcdef' for c in raw['native_state_sha256']),'native_seal')
    old=Path(plan['bootstrap_reference']);old_raw=p.base.gzread(old/'raw_final.json.gz')
    first=next(o['supply'] for o in old_raw['owners'] if o['supply'])
    if selected:
        require(selected[0]==first,'first_supply_difference');startup=frozen.prefix(old,directory,first['at']+p.base.PERIOD)
    else: startup={'status':'unknown_bootstrap_incomplete','compared_api_rows':0}
    return {'schema':p.SCHEMA,'status':'passed_saved_policy_replay','replay':replay,'startup_exact':startup,
        'all_offered':28506,'trays':22,'assessment':p.assess(raw,plan),'producer_native_seal':raw['native_state_sha256'],
        'evidence_sha256':{str(directory/name):p.base.sha(directory/name) for name in
            ('preregistered_protocol.json','input.json.gz','raw_final.json.gz','assessment.json','api/manifest.jsonl')},
        'reviewer_source_sha256':p.base.sha(__file__),'native_executions':0,'strict_protection':'not_assessed',
        'complete_100ms_certified':False,'correction':'Separate verifier reads actual ProtocolClient.calls[].request.request_id; old failing verifier and original failure receipts are unchanged.'}


def terminal_inventory(output):
    """Do not open mutable case files until the whole Job has returned."""
    outer = p.base.read(output/'external_launch_receipt.json')
    require(outer.get('status') in {'campaign_process_exited', 'unknown_campaign_process',
        'unknown_launcher_error', 'unknown_shared_budget_overrun'}, 'campaign_not_terminal')
    require(finite(outer.get('whole_dispatch_wall_seconds')), 'outer_clock')
    ready = p.base.read(output/'ready.json')
    require(outer['campaign_sha256'] == ready['campaign_sha256'] == p.base.sha(output/'campaign.json'), 'campaign_binding')
    for relative, digest in outer.get('artifact_sha256', {}).items():
        path = (output/relative).resolve()
        require(path.is_relative_to(output.resolve()) and p.base.sha(path) == digest, 'outer_artifact_changed')
    ledger = p.base.read(output/'branch_ledger.json')
    require(set(ledger) == set(p.CAPS), 'missing_case_denominator')
    return outer, ledger


def independent_outcomes(data, raw, plan, *, offered=28506, trays=22):
    source = {j['business_bag_id']: j for j in data['jobs']}
    jobs = {j['business_bag_id']: j for j in raw['result']['jobs']}
    require(len(source) == len(data['jobs']) == len(jobs) == len(raw['result']['jobs']) == offered
        and source.keys() == jobs.keys(), 'offered_denominator')
    initial = {t['tray_id'] for t in data['trays']}
    final = {t['tray_id']: t for t in raw['result']['trays']}
    require(len(initial) == len(data['trays']) == len(final) == len(raw['result']['trays']) == trays
        and initial == final.keys(), 'tray_denominator')
    token = plan['parking_plan']['token_tray_id']; selected = p.supplies(raw)
    selected_ids = [s['choice']['job']['business_bag_id'] for s in selected]
    require(len(selected_ids) == len(set(selected_ids)), 'job_selected_twice')
    receipts = raw['result']['receipts']; witnesses = []
    events = ('LOAD_START', 'LOAD_COMPLETE', 'UNLOAD_COMPLETE', 'HOLD_COMPLETE')
    for supply in selected:
        jid = supply['choice']['job']['business_bag_id']; job = source[jid]
        rows = {event: [r for r in receipts if r.get('event') == event and r.get('business_bag_id') == jid]
            for event in events}
        require(all(len(v) <= 1 for v in rows.values()), 'duplicate_lifecycle_receipt')
        require(all(r['tray_id'] == token for rs in rows.values() for r in rs), 'different_token_lifecycle')
        if not all(rows.values()):
            require(jobs[jid]['status'] != 'completed' or bool(rows['UNLOAD_COMPLETE']), 'completed_without_unload')
            continue
        load, loaded, unload, hold = [rows[event][0] for event in events]
        require(all(finite(r['time']) for r in (load, loaded, unload, hold))
            and supply['at'] <= load['time'] <= loaded['time'] <= unload['time'] <= hold['time'] <= raw['physical_time']
            and load['node'] == loaded['node'] == job['origin']
            and unload['node'] == hold['node'] == job['destination']
            and jobs[jid]['status'] == 'completed', 'lifecycle_clock_node_or_state')
        witnesses.append({'job': jid, 'request_id': supply['request_id'], 'at': supply['at'],
            'origin': job['origin'], 'destination': job['destination'],
            'load': load, 'loaded': loaded, 'unload': unload, 'hold': hold})
    completed = [jid for jid, row in jobs.items() if row['status'] == 'completed']
    unloaded = {r['business_bag_id'] for r in receipts if r.get('event') == 'UNLOAD_COMPLETE'}
    require(set(completed) == unloaded and unloaded <= set(selected_ids), 'completed_scope')
    actual_loads = [r for r in receipts if r.get('event') == 'LOAD_START']
    require(all(r['tray_id'] == token and r['business_bag_id'] in selected_ids for r in actual_loads)
        and len({r['business_bag_id'] for r in actual_loads}) == len(actual_loads), 'unselected_or_duplicate_load')
    for previous, nxt in zip(selected, selected[1:]):
        old = [w for w in witnesses if w['request_id'] == previous['request_id']]
        require(len(old) == 1 and old[0]['hold']['time'] <= nxt['at'], 'next_supply_before_actual_hold')
    parking = plan['parking_plan']['parking']
    require(len(parking) == trays and {r['tray_id'] for r in parking} == initial, 'startup_parking_domain')
    stationary = []
    for row in parking:
        if row['tray_id'] == token: continue
        tray = final[row['tray_id']]
        if (tray['node'] == row['destination'] and tray['mode'] == 'empty' and tray['job'] == -1
                and tray['edge_to'] < 0 and tray.get('reception_node', -1) < 0
                and finite(tray['available_at']) and tray['available_at'] <= raw['physical_time']):
            stationary.append(tray['tray_id'])
    return {'offered': offered, 'arrived': sum(j['arrival'] <= raw['physical_time'] for j in data['jobs']),
        'completed': completed, 'unfinished_offered': offered-len(completed), 'status_counts': dict(Counter(j['status'] for j in jobs.values())),
        'total_tray_identities': trays, 'startup_parking_request_count': len(parking),
        'other_trays_stationary_at_declared_parking': stationary, 'expected_other_parked_trays': trays-1,
        'actual_supplies': len(selected), 'same_token': token, 'physical_lifecycles': witnesses,
        'final_token': final[token], 'strict_protection': 'unknown_unfinished_offered_jobs'}


def validate_repeat_frame(data, selected, source, previous, view, messages, queries, physical, now,
        received_history=None):
    """Only supplied public rows establish an online handoff; IDs are opaque."""
    permit = selected['return_permit']; current = permit['current_token']; token = selected['request']['tray_id']
    nodes = {r['node']: r for r in data['node_contracts']}; own = permit['self_copy']; receipt = permit['receipt']
    require(now == selected['at'] == permit['observed_at'] == view['now'] and view['owner_id'] == source,
        'fresh_actual_owner_view')
    require([t for t in view['trays'] if t['tray_id'] == token] == [current]
        and current['mode'] == 'empty' and not current['business_bag_id'] and current['edge_to'] < 0
        and current['reception_node'] < 0 and finite(current['available_at']) and current['available_at'] <= now
        and current['node'] == selected['request']['source'] and nodes[current['node']]['resource_owner'] == source,
        'actual_owned_return')
    own_query = queries[(source, own['request_id'])]['result']['last_delivered_ack']
    require(own_query == own['ack'] and own_query['status'] == 'delivered'
        and own_query['planning_snapshot_v2'] == own['envelope'] and own_query['delivered_at'] <= now,
        'actual_self_ack')
    env = own['envelope']; local = env['capture']['local_capture']; ext = env['capture']['extension']
    require(env['payload_sha256'] == p.base.capture_digest_v2(env['capture'])
        and local['source_owner'] == source and env['status'] == 'conditional'
        and receipt in ext['terminal_receipts'] and local['captured_at'] <= now < local['valid_until'], 'self_capture')
    candidate_receipts = [r for r in ext['terminal_receipts'] if r['tray_id'] == token]
    require(receipt == max(candidate_receipts, key=lambda r: r['source_local_sequence'])
        and receipt['source_owner'] == source and receipt['event'] == 'UNLOAD_COMPLETE'
        and receipt['status'] == 'completed' and receipt['business_bag_id'] == previous['choice']['job']['business_bag_id']
        and receipt['destination'] == current['node'] == previous['choice']['job']['destination']
        and finite(receipt['completed_at']) and receipt['completed_at'] <= local['captured_at']
        and receipt['completed_at'] <= current['available_at'], 'previous_source_completion')
    own_captures = [q['result']['last_delivered_ack']['planning_snapshot_v2']['capture']['local_capture']
        for (owner, _), q in queries.items() if owner == source
        and (q['result'].get('last_delivered_ack') or {}).get('planning_snapshot_v2')]
    require(local['publication_sequence'] == max(c['publication_sequence'] for c in own_captures), 'stale_self_revision')
    peer = selected['choice']['delivered_message']; peer_local = peer['capture']['local_capture']
    require(messages == [peer] and peer['payload_sha256'] == p.base.capture_digest_v2(peer['capture'])
        and peer['status'] == 'conditional' and peer_local['target_owner'] == source
        and peer_local['source_owner'] != source and local['captured_at'] <= peer_local['captured_at']
        and peer['delivered_at'] <= now < peer_local['valid_until'], 'actual_latest_peer')
    choice, considered = independent_fifo_choice(data, peer, current['node'])
    require(choice == selected['choice']['job'] and selected['request']['destination'] == choice['origin'], 'independent_fifo_choice')
    barrier = selected['physical_barrier']; barrier_ids = barrier['received_request_ids']
    require(len(barrier_ids) == len(set(barrier_ids)) and set(barrier_ids) == set(physical), 'complete_prior_physical_barrier')
    own_ids = {rid for rid, row in physical.items() if row['owner_id'] == source}
    peer_ids = set(physical)-own_ids
    for rid in own_ids:
        ack = queries[(source, rid)]['result']['last_delivered_ack']
        require(ack['status'] == 'received' and ack['delivered_at'] <= now, 'actual_own_physical_ack')
    actions = peer['capture']['extension']['submitted_physical_actions']
    require(len(actions) == len(peer_ids) and {a['request_id'] for a in actions} == peer_ids, 'peer_physical_coverage')
    for action in actions:
        ack = action['last_delivered_ack']; who = action['source_owner']
        require(who == peer_local['source_owner'] and action['kind'] == 'transfer'
            and ack['status'] == 'received' and ack['delivered_at'] <= peer_local['captured_at'], 'peer_received_ack')
        # The actually returned native capture is the action-ACK authority.
        # When scanning the tape, separately prove that source policy had read
        # a received ACK before this capture. Never overwrite that historical
        # evidence with a newer duplicate from a later query.
        if received_history is not None:
            earlier = received_history.get((who, action['request_id']), [])
            require(any(q['before'] <= peer_local['captured_at']
                and q['result']['last_delivered_ack']['delivered_at'] <= q['before'] for q in earlier),
                'source_received_before_relay_capture')
    require(barrier['known_supply_count'] == len(physical)-len(data['trays'])
        and barrier['peer_message_id'] == peer_local['message_id'], 'barrier_identity_or_count')
    return {'at': now, 'source_owner': source, 'previous_job': receipt['business_bag_id'],
        'source_completion': receipt, 'current_empty_node': current['node'], 'current_empty_available_at': current['available_at'],
        'self_message_id': local['message_id'], 'self_capture_at': local['captured_at'], 'self_ack_at': own_query['delivered_at'],
        'peer_owner': peer_local['source_owner'], 'peer_message_id': peer_local['message_id'],
        'peer_capture_at': peer_local['captured_at'], 'peer_delivery_at': peer['delivered_at'],
        'selected_job': choice['business_bag_id'], 'selected_origin': choice['origin'],
        'independent_fifo_considered': considered, 'known_received_physical_requests': len(physical)}


def scan_api(directory, data, raw):
    selected = p.supplies(raw); by_id = {s['request_id']: (i, s) for i, s in enumerate(selected)}
    views, messages, queries, physical, seen_commands, frames, received, history = {}, {}, {}, {}, {}, [], {}, {}
    manifest = frozen.manifest(directory)
    for index, item in enumerate(manifest):
        row = p.base.gzread(directory/'api'/item['path'])
        require(row['ordinal'] == index and finite(row['before']) and finite(row['after']) and row['before'] <= row['after'], 'api_ordinal_or_clock')
        endpoint, args = row['endpoint'], row['args']
        if endpoint == 'observe_protocol_control_policy_recent': views[args[0]] = row
        elif endpoint == 'protocol_planning_snapshots_v2': messages[args[0]] = row
        elif endpoint in ('protocol_request', 'protocol_command'):
            queries[tuple(args)] = row
            ack = row['result'].get('last_delivered_ack') or {}
            if endpoint == 'protocol_request' and ack.get('status') == 'received':
                require(finite(ack['delivered_at']) and ack['delivered_at'] <= row['before'], 'received_clock')
                received[args[1]] = {'ordinal': index, 'queried_at': row['before'], 'ack': ack}
                history.setdefault(tuple(args), []).append(row)
        elif endpoint == 'submit_protocol_command':
            payload = args[0]; rid = payload['request_id']
            require(rid not in seen_commands or seen_commands[rid] == payload, 'mutable_command_retry')
            seen_commands[rid] = payload
        elif endpoint == 'submit_protocol_transfer':
            payload = args[0]; rid = payload['request_id']; source = payload['owner_id']
            if rid in physical:
                require(physical[rid] == payload, 'mutable_transfer_retry'); continue
            if rid in by_id:
                i, selection = by_id[rid]
                require({k:v for k,v in payload.items() if k not in ('owner_id','request_id')} == selection['request'], 'actual_supply_payload')
                if i:
                    require(views[source]['before'] == row['before'] and messages[source]['before'] == row['before'], 'choice_api_clock')
                    frame = validate_repeat_frame(data, selection, source, selected[i-1], views[source]['result'],
                        messages[source]['result'], queries, physical, row['before'], received_history=history)
                    frames.append({**frame, 'request_id': rid, 'submit_ordinal': index,
                        'own_view_ordinal': views[source]['ordinal'], 'peer_read_ordinal': messages[source]['ordinal']})
            physical[rid] = payload
    require(all(s['request_id'] in physical for s in selected) and len(frames) == max(0, len(selected)-1), 'missing_supply_submit')
    return {'api_rows': len(manifest), 'unique_physical_requests': len(physical), 'repeat_handoffs': frames,
        'actual_received_queries': received, 'physical_payloads': physical}


def bind_physical_returns(outcomes, api):
    by_job = {w['job']: w for w in outcomes['physical_lifecycles']}
    for frame in api['repeat_handoffs']:
        previous = by_job.get(frame['previous_job'])
        require(previous is not None and frame['source_completion']['completed_at'] == previous['unload']['time']
            and previous['hold']['time'] <= frame['current_empty_available_at'] <= frame['at'],
            'captured_return_not_bound_to_actual_unload_hold')
    for witness in outcomes['physical_lifecycles']:
        require(witness['request_id'] in api['actual_received_queries'], 'completion_without_actual_received_query')


def review(output, expected_ready):
    require(p.base.sha(output/'ready.json') == expected_ready, 'ready_changed')
    outer, ledger = terminal_inventory(output); p.verify_campaign(output)
    cases = {}; evidence = {}; raws = {}
    for name in p.CAPS:
        case = output/name; entry = ledger[name]
        for path in case.rglob('*'):
            if path.is_file() and ('source_archive' not in path.parts and 'compiled_source_archive' not in path.parts):
                evidence[str(path.relative_to(output))] = p.base.sha(path)
        finished = entry.get('execution', {}).get('exit_code') == 0 and (case/'raw_final.json.gz').is_file()
        if not finished:
            cases[name] = {'status': 'unknown_incomplete_case', 'ledger': entry, 'registered_offered': 28506,
                'registered_trays': 22, 'completion_comparison': 'unknown'}
            continue
        replay = verify_case_corrected(case); data = p.base.gzread(case/'input.json.gz'); raw = p.base.gzread(case/'raw_final.json.gz')
        outcomes = independent_outcomes(data, raw, p.base.read(case/'preregistered_protocol.json'))
        api = scan_api(case, data, raw); raws[name] = raw
        bind_physical_returns(outcomes, api)
        cases[name] = {'status': 'passed_saved_case_review', 'original_process_ledger':entry,
            'replay': replay, 'independent_outcomes': outcomes, 'actual_api': api}
    pair = {'status': 'unknown_incomplete_case_denominator', 'extra_observed_completions': None}
    if len(raws) == len(p.CAPS):
        assessments={name:item['replay']['assessment'] for name,item in cases.items()}
        thirds=[a['completion_witnesses'][2]['hold_complete']['time'] if len(a['completion_witnesses'])>=3 else None for a in assessments.values()]
        through=thirds[0] if all(t is not None for t in thirds) else min(raw['physical_time'] for raw in raws.values())
        if all(t is not None for t in thirds): require(thirds[0]==thirds[1],'third_completion_changed')
        prefix=frozen.prefix(output/'cap3',output/'cap8',through) if through>0 else {'status':'unknown_no_complete_boundary'}
        closed=all(a['status']=='complete_finite_policy_evidence' for a in assessments.values())
        counts={name:len(item['independent_outcomes']['completed']) for name,item in cases.items()}
        pair={'status':'assessed_finite_pair' if closed else 'unknown_incomplete_policy_pair','completion_counts':counts,
            'exact_common_prefix':prefix,'extra_observed_completions':counts['cap8']-counts['cap3'] if closed else None}
    for file in ('ready.json','campaign.json','branch_ledger.json','external_launch_receipt.json','receipt.json','comparison.json','powershell_launch_receipt.json'):
        if (output/file).is_file(): evidence[file] = p.base.sha(output/file)
    return {'schema': 'g31.repeat_policy.independent_saved_review.v1', 'status': 'completed_saved_review',
        'campaign_outcome': pair['status'], 'cases': cases, 'pair': pair, 'outer_launcher': outer,
        'registered_cases': list(p.CAPS), 'all_offered_each': 28506, 'total_trays_each': 22,
        'startup_parking_requests_each': 22, 'other_parked_trays_after_token_circulates': 21,
        'native_executions_by_reviewer': 0, 'new_native_hidden_state_reconstruction': False,
        'evidence_sha256': evidence, 'reviewer_source_sha256': p.base.sha(__file__),
        'reviewer_dependency_sha256': {str(path): p.base.sha(path) for path in
            (Path(__file__), Path(frozen.__file__), Path(__file__).with_name('review_original_low_wip_reuse_saved.py'))},
        'strict_protection': 'unknown_unfinished_offered_jobs', 'complete_100ms_certified': False,
        'scope': 'Saved policy/API and actual native receipt audit. Two finite cumulative-supply caps, both WIP1; no throughput optimality or full-completion claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-ready-sha256', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(); require(not args.report.exists(), 'report_exists')
    try:
        result = review(args.output.resolve(), args.expected_ready_sha256)
    except Exception as error:
        p.base.write(args.report, {'status': 'review_failed_or_evidence_unconfirmed', 'error': repr(error),
            'reviewer_source_sha256': p.base.sha(__file__), 'native_executions_by_reviewer': 0})
        raise
    p.base.write(args.report, result)
    print(json.dumps({'status': result['status'], 'campaign_outcome': result['campaign_outcome'],
        'sha256': p.base.sha(args.report)}))


if __name__ == '__main__': main()
