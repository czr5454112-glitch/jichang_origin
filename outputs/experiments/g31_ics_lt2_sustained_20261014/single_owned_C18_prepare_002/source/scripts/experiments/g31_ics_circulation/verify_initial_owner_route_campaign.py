"""Saved endpoint replay and full physical outcome audit; no predictor/native.

This does not call every internal query again, mint collection capabilities,
or infer future participant policy from a planning message identity.
"""
from __future__ import annotations
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from . import initial_owner_route_campaign as c
from . import native_preexisting_initial_adapter as initial

require = c.require


def exact(a, b):
    return json.dumps(a, ensure_ascii=False, allow_nan=False, separators=(',', ':')) == \
           json.dumps(b, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def endpoint_replay(record):
    e, information = record['endpoints'], record['information']
    require(e['owner'] in ('A', 'B') and e['at'] == .11 and
            e['view']['owner_id'] == e['owner'] and e['view']['now'] == .11,
            'initial_endpoint_owner_or_epoch')
    command = e['command']
    require(command['request_id'] == e['request_id'] and command['kind'] == 'planning_snapshot',
            'initial_endpoint_command_identity')
    value = initial.validate_pair(e['view'], command.get('last_delivered_ack', {}), e['received'])
    if value['status'] == 'conditional_validated_data':
        require(information.get('native_delivery_verified') is True and
                information.get('status') == 'conditional_native_delivered_model_input', 'initial_native_origin_shape')
        original = copy.deepcopy(information)
        native_read = original.pop('native_read')
        require(native_read['owner'] == e['owner'] and native_read['at'] == .11 and
                native_read['own_request_id'] == e['request_id'], 'initial_read_binding')
        original['status'] = 'conditional_validated_data'
        original['native_delivery_verified'] = False
        require(exact(original, value), 'initial_endpoint_data_mismatch')
        require(record['ledger'] is not None and record['ledger']['owner'] == e['owner'], 'initial_ledger_owner')
    else:
        require(information.get('native_delivery_verified') is not True and record['ledger'] is None,
                'unknown_endpoint_promoted')
        require(exact(information.get('initial'), {**value, 'native_read': information['initial']['native_read']}),
                'unknown_endpoint_changed')
    return value['status']


def immutable_calls(calls, outbox):
    seen, previous = {}, -math.inf
    for call in calls:
        at, payload = call['at'], call['request']
        require(type(at) in (int, float) and math.isfinite(at) and previous <= at <= 40., 'call_time')
        previous = at
        identity = payload['request_id']
        require(payload['owner_id'] in ('A', 'B') and identity.startswith('live:1:' + payload['owner_id'] + ':'),
                'owner_namespace')
        require(type(call['retry']) is bool, 'retry_boolean')
        if identity not in seen:
            require(not call['retry'], 'retry_without_creation')
            seen[identity] = payload
        else:
            require(call['retry'] and exact(payload, seen[identity]), 'immutable_retry_payload')
        require(identity in outbox and exact(payload, outbox[identity]['request']) and
                call['kind'] == outbox[identity]['kind'], 'outbox_identity')
    require(set(seen) == set(outbox), 'outbox_denominator')
    return len(seen), len(calls)


def root_replay(raw):
    records = raw['root_records']
    if not records:
        require(raw['failure'] and raw['root_constructed'] is False, 'missing_root_without_failure')
        return {'status': 'unknown_constructor_failure', 'closed': False, 'warm_ms': None}
    require(len(records) == 1, 'root_denominator')
    record = records[0]
    root = record['value']['evidence']
    start, cutoff, deadline = (root[k] for k in ('root_started_ns', 'decision_cutoff_ns', 'root_deadline_ns'))
    require(all(type(t) is int and t >= 0 for t in (start, cutoff, deadline, record['outside_return_ns'])) and
            cutoff == start + 60_000_000 and deadline == start + 100_000_000, 'root_budget')
    require(start <= record['value']['body_finished_ns'] <= record['outside_return_ns'] and
            record['warm_caller_elapsed_ns'] == record['outside_return_ns'] - start, 'caller_tail_clock')
    encoded = c.image.artifact_encode(root)
    require(hashlib.sha256(encoded).hexdigest() == record['ledger']['evidence_sha256'] and
            len(encoded) == record['ledger']['bytes'] and
            c.image.artifact_decode(record['return_codec'].encode()) == record['ledger'], 'root_codec_ledger')
    require(root['root_id'] == raw['key'].replace('/', ':') and root['owner'] == 'A', 'root_identity')
    if 'initial_endpoint_records' in raw:
        require(exact(root.get('initial_endpoint_records'),raw['initial_endpoint_records']), 'endpoint_codec_outside_root')
    events = root['events']
    previous = start
    local = None
    sticky = None
    final_verdict = None
    replies=[e for e in events if e['stage']=='two_choice_reply']
    require(len(replies)<=1,'multiple_initial_choices')
    check_choice=replies[0]['value']['payload']['selection']['choice'] if replies else None
    for index,event in enumerate(events):
        require(type(event['wall_ns']) is int and previous <= event['wall_ns'] <= record['outside_return_ns'],
                'root_event_clock')
        previous = event['wall_ns']
        if event['stage']=='predeclared_default_control':
            check_choice='native_default'
        if event['stage']=='decision_return_overrun_default_incumbent':
            require(check_choice=='prefer_2' and event['wall_ns']>=cutoff,'invalid_decision_overrun')
            check_choice='native_default'
        if event['stage']=='pre_submit_root_overrun_default_incumbent':
            require(check_choice=='prefer_2' and event['wall_ns']>=deadline,'invalid_submit_overrun')
            check_choice='native_default'
        if event['stage'] == 'final_local_and_receiver_check':
            view, verdict = event['value']['view'], event['value']['verdict']
            pair = raw['initial_endpoint_records']['A'][-1]['information']
            require(exact(c.contract.validate_final_local(view, pair['bundle'], check_choice), verdict),
                    'final_local_replay')
            if verdict['status'] == 'fresh_local_precondition_checked':
                local = verdict['source']
        if event['stage'] in ('continuation', 'post_drain_observation'):
            value = event['value']
            require(local is not None and value['view']['now'] == event['at'] and
                    value['view']['owner_id'] == 'A' and value['command_query_owner'] == 'A' and
                    value['command_query_id'] == root['command_id'], 'root_endpoint_identity')
            observed = c.contract.observed_first_hop(value['view'], local)
            if sticky is None and observed is not None:
                sticky = observed
            if event['stage'] == 'continuation':
                require(exact(sticky, value['hop']), 'physical_proof_not_observed')
            else:
                require(index > 0 and events[index-1]['stage'] == 'mandatory_drain' and
                        c.request.native_boundary_complete(events[index-1]['value'], event['at']),
                        'actual_complete_drain')
                final_verdict = c.contract.closure(root['choice'], sticky, value['command'],
                    queried_owner=value['command_query_owner'], request_id=value['command_query_id'],
                    now=event['at'], timestamp_complete=True)
                require(exact(final_verdict, value['verdict']), 'closure_endpoint_replay')
    closed = root['state'].startswith('closed_')
    require(check_choice==root['choice'],'root_choice_history')
    require(record['closed'] is closed, 'closed_label')
    if closed:
        require(final_verdict is not None and final_verdict['closed'] and
                final_verdict['status'] == root['state'] and exact(sticky, root['hop']), 'false_terminal')
    if raw['specification']['method'] == 'fixed_default':
        require(not any(e['stage'] == 'two_choice_reply' for e in events), 'fixed_control_uses_solver')
    if root['command_id']:
        payload = raw['outbox'][root['command_id']]['request']
        require(local is not None and all(payload.get(k) == v for k, v in {
            'owner_id': 'A', 'kind': 'route', 'tray_id': 'L', 'business_bag_id': 'loaded',
            'from': 0, 'next': 2, 'expected_generation': local['generation'],
            'expected_traversal': local['traversal_id'], 'message_delay': .01, 'expiry': 5.}.items()),
            'initial_route_payload')
    return {'status': root['state'], 'closed': closed, 'warm_ms': record['warm_caller_elapsed_ns']/1e6,
            'observed_within_100ms': closed and record['outside_return_ns'] <= deadline,
            'cold_excludes_nothing_by_amortization': False, 'full32_or_universal_100ms_certificate': False}


def rpc_replay(sample, raw):
    """Rebind saved real RPC to live-origin endpoints; no new prediction."""
    root=raw['root_records'][0]['value']['evidence']
    packet=sample['request']['snapshot']
    reply=sample['response']
    payload=reply['payload']
    require(sample['request_id']==root['root_id'] and sample['request']['request_id']==root['root_id'] and
        reply['request_id']==root['root_id'] and sample['request']['sequence']==sample['sequence']==reply['sequence'],
        'RPC_root_identity')
    pair=raw['initial_endpoint_records']['A'][0]['information']
    require(exact(packet['bundle'],pair['bundle']) and packet['root_started_ns']==root['root_started_ns'] and
        packet['root_deadline_ns']==root['root_deadline_ns'] and packet['decision_cutoff_ns']==root['decision_cutoff_ns'] and
        packet['participation_contract_sha256']==c.contract.contract_sha256(), 'RPC_not_actual_initial_bundle')
    require(payload['snapshot_sha256']==c.image.sha_bytes(c.image.encode(packet['bundle'])) and
        payload['native_authority'] is False and payload['full_32_search_performed'] is False and
        payload['participation_contract_sha256']==c.contract.contract_sha256(), 'RPC_payload_binding')
    budget=payload['budget'];counts=payload['counts']
    require(all(budget[k]==packet[k] for k in ('root_started_ns','root_deadline_ns','decision_cutoff_ns')) and
        sample['caller_admitted_ns']>=root['root_started_ns'] and
        sample['caller_admitted_ns']<=sample['caller_decoded_ns']<=sample['caller_body_finished_ns']<=
        raw['root_records'][0]['outside_return_ns'], 'RPC_clock_binding')
    require(all(type(n) is int for n in counts.values()) and counts['logical_choices']==2 and counts['baseline_evaluation_calls'] in (0,1) and
            counts['complete_baselines'] in (0,1) and counts['additional_candidate_calls'] in (0,1), 'RPC_count_domain')
    if counts['baseline_evaluation_calls']==0:
        require(payload['baseline'] is None and counts['additional_candidate_calls']==0 and
            payload['selection']['choice'] is None and payload['selection']['status']=='unknown_no_baseline_budget' and
            budget['worker_started_ns']>=root['decision_cutoff_ns'], 'unexecuted_baseline_promoted')
    else:
        baseline=payload['baseline']
        require(counts['complete_baselines']==int(c.contract.completion(baseline) is not None), 'baseline_complete_count')
        if payload['actions']:
            require(payload['actions']==[dict(initial_action=choice,empty_departure=.11,return_delay=0.,later_action='native_default')
                for choice in ('native_default','prefer_2')] and len(payload['predictions'])==2 and
                exact(payload['predictions'][0],baseline), 'two_original_actions')
            candidate=payload['predictions'][1]
        else:
            require(not payload['predictions'] and counts['additional_candidate_calls']==0, 'unknown_action_promoted')
            candidate={'status':'unknown_unexecuted_budget','completion':{},'native_protection_certified':False}
        expected=c.contract.select(baseline,candidate,decision_budget_expired=budget['atomic_overrun'])
        require(expected==payload['selection'], 'RPC_selection_changed')
    events=[e for e in root['events'] if e['stage']=='two_choice_reply']
    require(len(events)==1 and exact(events[0]['value'],reply), 'RPC_reply_not_root_event')
    choice=payload['selection']['choice']
    overrides=[e for e in root['events'] if e['stage'] in (
        'decision_return_overrun_default_incumbent','pre_submit_root_overrun_default_incumbent')]
    if root['choice']!=choice:
        require(choice=='prefer_2' and root['choice']=='native_default' and overrides, 'unexplained_selection_override')
    return counts


def verify_branch(raw, row, key):
    require(raw['schema'] == c.SCHEMA and raw['key'] == key and raw['specification'] == row and
            exact(raw['input'], c.scene(row)), 'branch_binding')
    if raw['native_state_sha256'] is None:
        require(raw['failure'], 'missing_seal_without_failure')
    else:
        require(type(raw['native_state_sha256']) is str and len(raw['native_state_sha256']) == 64 and
                all(t in '0123456789abcdef' for t in raw['native_state_sha256']), 'native_seal_shape')
    for owner, records in raw['initial_endpoint_records'].items():
        require(owner in ('A', 'B') and len(records) <= (2 if owner == 'A' else 1), 'initial_endpoint_count')
        for record in records:
            require(record['endpoints']['owner'] == owner, 'endpoint_record_owner')
            endpoint_replay(record)
    calls, count = immutable_calls(raw['calls'], raw['outbox'])
    stage_names = [s['stage'] for s in raw['participation_stages']]
    if raw['failure'] is None:
        require(stage_names[:2] == ['A_collection', 'fixed_B_first_action'] and
                raw['participation_stages'][1]['at'] == .11, 'B_first_action_before_advance')
    if raw['initial_B'] and raw['initial_B']['request_id']:
        first = raw['outbox'][raw['initial_B']['request_id']]['request']
        require(all(first.get(k) == v for k, v in {'owner_id':'B','tray_id':'E','source':5,
            'destination':1,'earliest_departure':.11,'message_delay':.01,'expiry':39.}.items()), 'fixed_B_contract')
    if raw['decisions']:
        require(set(raw['decisions']) == {'A', 'B'} and stage_names[2:] == ['both_fixed_continuation_owners'],
                'missing_fixed_participant')
        for rows in raw['decisions'].values():
            for d in rows:
                selected = d['decision'].get('selected_action')
                require(selected in (None, {'return_delay':0.,'later_action':'native_default'}), 'changed_fixed_continuation')
    previous = .11
    for batch in raw['native_batches']:
        response = batch['response']
        require(type(batch['deadline']) in (int,float) and previous <= response['physical_time'] <= batch['deadline'] <= 40.,
                'native_boundary_order')
        previous = response['physical_time']
    if raw['result'] is None:
        require((raw['failure'] or raw['continuation']['status']!='finished') and
                raw['outcome']['status']=='unknown_assessor_failure', 'missing_result_promoted')
        replay={'status':'unknown_missing_result'}
    else:
        replay = c.full_outcome(raw['input'], raw['result'], SimpleNamespace(rows=raw['outbox'], calls=raw['calls']),
                               raw['continuation'], raw['root_records'][0]['value']['evidence']['choice'] if raw['root_records'] else None)
        require(exact(replay, raw['outcome']), 'full_five_job_audit_changed')
    root = root_replay(raw)
    require(raw['diagnostic_physical_time_before']==raw['diagnostic_physical_time_after'], 'diagnostic_advanced_partial_cut')
    if raw['root_records'] and raw['root_records'][0]['value']['evidence']['hop'] is not None and raw['result'] is not None:
        hop=raw['root_records'][0]['value']['evidence']['hop']
        entries=[r for r in raw['result']['receipts'] if r['event']=='EDGE_ENTER' and
            r.get('tray_id')=='L' and r.get('business_bag_id')=='loaded' and r.get('from')==0]
        require(len(entries)==1 and entries[0]['to']==hop['to'] and entries[0]['time']<=hop['observed_at'],
                'firsthop_missing_actual_physical_receipt')
    return {'root': root, 'business': replay, 'immutable_requests': calls, 'submit_retry_calls': count,
            'initial_endpoints': sum(len(v) for v in raw['initial_endpoint_records'].values()),
            'native_state_sha256': raw['native_state_sha256'], 'native_reexecution': False}


def pair_comparison(control, trial):
    a, b = control['business'], trial['business']
    known = a.get('status') == b.get('status') == 'assessed'
    return {'status': 'assessed_finite_actual_pair' if known else 'unknown_incomplete_or_invalid_pair',
        'request_pair_completed':bool(control.get('root',{}).get('closed') and trial.get('root',{}).get('closed')),
        'all_five_strict_nonregression': all(b['completion'][j] <= a['completion'][j]
            for j in c.contract.JOBS) if known else None,
        'per_job_delta': {j:b['completion'][j]-a['completion'][j] for j in sorted(c.contract.JOBS)} if known else None,
        'full32_optimization': False, 'model_protection_certificate': False}


def verify_saved(output, expected):
    output = Path(output).resolve()
    plan = c.verify_plan(output, expected)
    ledger = c.read(output/'branch_ledger.json')
    require(list(ledger) == plan['row_order'], 'branch_denominator_or_order')
    accepted = c.read(output/'run_acceptance.json')
    require(accepted['status'] == 'closed_run_acceptance_passed' and accepted['active'] is False and
            accepted['invalid'] == [] and accepted['branch_keys'] == sorted(plan['rows']) and
            accepted['run_reference'] == c.reference(output/'campaign.json'), 'run_not_closed')
    require(all(c.sha(p) == h for p,h in accepted['evidence_sha256'].items()), 'accepted_file_drift')
    life = c.read(output/'predictor_lifetime.json')
    samples={sample['request_id']:sample for sample in life['ledger']}
    require(len(samples)==len(life['ledger']) and [s['sequence'] for s in life['ledger']]==list(range(1,len(samples)+1)),
            'RPC_denominator_or_sequence')
    used=set()
    results = {}
    for key in plan['row_order']:
        row = ledger[key]
        require(all(row[f] == plan['rows'][key][f] for f in ('case','method','fault')), 'row_specification')
        if row['status'] != 'raw_saved':
            results[key] = {'root': {'status': row['status'], 'closed': False, 'warm_ms': None},
                            'business': {'status':'unknown_missing_raw'}, 'failure':row.get('exception')}
            continue
        path = output/'raw'/(key+'.json.gz')
        require(row['raw'] == c.reference(path), 'raw_hash')
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            raw = json.load(stream)
        results[key] = verify_branch(raw, plan['rows'][key], key)
        root_id=key.replace('/',':')
        events=raw['root_records'][0]['value']['evidence']['events'] if raw['root_records'] else []
        if root_id in samples:
            require(plan['rows'][key]['method']=='budget_two', 'RPC_in_fixed_control')
            results[key]['prediction_counts']=rpc_replay(samples[root_id],raw)
            used.add(root_id)
        else:
            require(not any(e['stage']=='two_choice_reply' for e in events), 'missing_actual_RPC_sample')
    require(used==set(samples),'unaccounted_RPC_or_failed_branch_prefix')
    require({k:life['ready'][k] for k in plan['expected_READY']} == plan['expected_READY'], 'saved_READY_closure_or_proof')
    require(life['ready']['version'] == plan['image']['version'] and life['ready']['mode'] == 'initial_A_two' and
            life['close']['reply']['source_unchanged'] is True and life['close']['process_exit_code'] == 0 and
            life['close']['reply']['requests'] == len(life['ledger']) and
            life['started_ns'] <= life['ready_ns'] <= life['close']['close_admitted_ns'] <=
            life['close']['close_finished_ns'] <= life['cleanup_finished_ns'], 'predictor_lifetime')
    require(len(life['ledger']) <= 9 and len({r['request_id'] for r in life['ledger']}) == len(life['ledger']),
            'predictor_request_domain')
    pairs = {}
    for key, row in plan['rows'].items():
        if row['method'] == 'budget_two':
            base = key.rsplit('/',1)[0] + '/fixed_default'
            pairs[key] = pair_comparison(results[base], results[key])
    return {'schema':c.SCHEMA, 'status':'passed_saved_finite_endpoint_and_physical_audit',
        'campaign_sha256':expected, 'rows':results, 'pairs':pairs, 'branches':18,
        'closed_roots':sum(r['root']['closed'] for r in results.values()),
        'open_or_unknown_roots':sum(not r['root']['closed'] for r in results.values()),
        'predictor_requests':len(life['ledger']),
        'prediction_counts':{field:sum(r.get('prediction_counts',{}).get(field,0) for r in results.values())
            for field in ('baseline_evaluation_calls','complete_baselines','additional_candidate_calls')},
        'predictor_startup_ms':(life['ready_ns']-life['started_ns'])/1e6,
        'predictor_close_with_cleanup_ms':(life['cleanup_finished_ns']-life['close']['close_admitted_ns'])/1e6,
        'cold_charge':'Retain full startup, acceptance, native setup, shutdown, export and verification; external whole campaign is charged in full per sensitivity, never divided among roots.',
        'scope':'Endpoint replay, immutable calls, native boundaries and complete five-job physical audit. No all-internal-query replay, new native seal replay or full32/100ms certificate.'}
