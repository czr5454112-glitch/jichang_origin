"""Pure audit counterexamples; fixtures do not assert a repeat native execution."""
from copy import deepcopy
from functools import lru_cache
import json
import pytest
from scripts.experiments.g31_ics_circulation import review_original_low_wip_repeat_saved as r


def outcome_fixture():
    jobs = [{'business_bag_id':f'j{i}', 'arrival':i*10, 'origin':1, 'destination':4} for i in range(3)]
    trays = [{'tray_id':'token'}, {'tray_id':'parked'}]
    data = {'jobs':jobs, 'trays':trays}
    first = {'request_id':'s1', 'at':0., 'choice':{'job':jobs[0]}}
    second = {'request_id':'s2', 'at':10., 'choice':{'job':jobs[1]}}
    receipts = [{'event':event, 'business_bag_id':'j0', 'tray_id':'token', 'time':i+1.,
        'node':1 if i<2 else 4} for i,event in enumerate(('LOAD_START','LOAD_COMPLETE','UNLOAD_COMPLETE','HOLD_COMPLETE'))]
    raw = {'physical_time':15., 'owners':[{'supply':first,'repeated':[second]}], 'result':{
        'jobs':[{**j, 'status':'completed' if i==0 else 'waiting_for_tray'} for i,j in enumerate(jobs)],
        'trays':[{'tray_id':name,'node':node,'mode':'empty','job':-1,'edge_to':-1,'reception_node':-1,'available_at':4.}
            for name,node in [('token',4),('parked',6)]], 'receipts':receipts}}
    plan = {'parking_plan':{'token_tray_id':'token','parking':[
        {'tray_id':'token','destination':2},{'tray_id':'parked','destination':6}]}}
    return data, raw, plan


def test_pending_second_keeps_all_offered_and_only_one_other_parked():
    data, raw, plan = outcome_fixture()
    result = r.independent_outcomes(data, raw, plan, offered=3, trays=2)
    assert result['completed']==['j0'] and result['unfinished_offered']==2 and result['arrived']==2
    assert result['total_tray_identities']==result['startup_parking_request_count']==2
    assert result['expected_other_parked_trays']==1 and result['other_trays_stationary_at_declared_parking']==['parked']
    assert result['actual_supplies']==2 and len(result['physical_lifecycles'])==1


@pytest.mark.parametrize('change', ['missing_job','duplicate_job','missing_tray','duplicate_load','wrong_token',
    'wrong_destination','before_hold','completed_without_receipt','unselected_completion'])
def test_outcome_tampering_fails_closed(change):
    data, raw, plan = outcome_fixture()
    if change=='missing_job': raw['result']['jobs'].pop()
    elif change=='duplicate_job': raw['result']['jobs'][-1]=deepcopy(raw['result']['jobs'][0])
    elif change=='missing_tray': raw['result']['trays'].pop()
    elif change=='duplicate_load': raw['result']['receipts'].append(deepcopy(raw['result']['receipts'][0]))
    elif change=='wrong_token': raw['result']['receipts'][0]['tray_id']='parked'
    elif change=='wrong_destination': raw['result']['receipts'][-1]['node']=99
    elif change=='before_hold': raw['owners'][0]['repeated'][0]['at']=3.
    elif change=='completed_without_receipt': raw['result']['jobs'][1]['status']='completed'
    else:
        raw['result']['jobs'][-1]['status']='completed'
        raw['result']['receipts'].append({'event':'UNLOAD_COMPLETE','business_bag_id':'j2','tray_id':'token','time':10.,'node':4})
    with pytest.raises(ValueError): r.independent_outcomes(data, raw, plan, offered=3, trays=2)


@lru_cache(maxsize=1)
def old_fixture():
    directory = r.p.OUT/'original_low_wip_third_prepare_001'
    return r.p.base.gzread(directory/'input.json.gz'), r.p.base.gzread(directory/'raw_final.json.gz')


def test_actual_closed_protocol_calls_keep_identity_inside_payload():
    _,raw=old_fixture()
    rows=[row for owner in raw['owners'] for row in owner['calls']]
    assert rows and all('request_id' not in row and 'request_id' in row['request'] for row in rows)
    parks={row['request']['request_id'] for row in rows if row['kind']=='transfer'}
    for row in rows: r.check_actual_call(row,parks,'unused-token')


@pytest.mark.parametrize('change',['missing_payload_id','conflicting_top_id','negative_cost','other_tray'])
def test_actual_call_schema_correction_fails_closed(change):
    row={'at':1.,'retry':False,'kind':'transfer','request':{'request_id':'actual-id','tray_id':'token'},
        'reply':{'status':'accepted'},'submit_compute_ms':.2}
    if change=='missing_payload_id': del row['request']['request_id']
    elif change=='conflicting_top_id': row['request_id']='wrong'
    elif change=='negative_cost': row['submit_compute_ms']=-.1
    else: row['request']['tray_id']='parked'
    with pytest.raises((ValueError,KeyError)): r.check_actual_call(row,set(),'token')


def frame_fixture():
    data, raw = deepcopy(old_fixture())
    owner = next(o for o in raw['owners'] if o.get('third_supply'))
    third = owner['third_supply']; old = third['return_proof']; who = owner['owner']; token = third['request']['tray_id']
    own = old['own_delivered_self_copy']; peer = third['choice']['delivered_message']
    permit = {'receipt':old['terminal_receipt'], 'self_copy':own,
        'current_token':old['current_token'], 'observed_at':third['at']}
    view = {'owner_id':who, 'now':third['at'], 'trays':[old['current_token']]}
    physical, queries = {}, {}
    for source in raw['owners']:
        for rid, item in source['outbox']['outbox'].items():
            if item['kind']!='transfer' or rid==third['request_id']: continue
            physical[rid] = item['payload']
            queries[source['owner'],rid]={'result':item['client_view']}
    queries[who,own['request_id']]={'result':{'last_delivered_ack':own['ack']}}
    selection = {**third,'return_permit':permit,'physical_barrier':{
        'known_supply_count':2,'received_request_ids':list(physical),
        'peer_message_id':peer['capture']['local_capture']['message_id']}}
    return data, selection, who, owner['second_supply'], view, [peer], queries, physical, third['at']


def test_old_actual_third_public_facts_validate_generic_frame_only():
    result = r.validate_repeat_frame(*frame_fixture())
    assert result['source_completion']['business_bag_id']=='projected:1x:6'
    assert result['selected_job']=='projected:1x:8' and result['selected_origin']==49
    assert result['known_received_physical_requests']==24


def test_actual_native_action_ack_may_have_newer_duplicate_sequence():
    args=list(frame_fixture()); peer=args[5][0]
    peer['capture']['extension']['submitted_physical_actions'][0]['last_delivered_ack']['sequence']+=1
    peer['payload_sha256']=r.p.base.capture_digest_v2(peer['capture'])
    assert r.validate_repeat_frame(*args)['selected_origin']==49


@pytest.mark.parametrize('late_only', [False, True])
def test_historical_received_read_not_overwritten_by_later_duplicate(late_only):
    args=list(frame_fixture()); peer=args[5][0]; local=peer['capture']['local_capture']; history={}
    for action in peer['capture']['extension']['submitted_physical_actions']:
        key=action['source_owner'],action['request_id']
        earlier=deepcopy(args[6][key]); earlier['before']=local['captured_at']+(1 if late_only else 0)
        history[key]=[earlier]
        # The latest query is deliberately after the historical capture.
        args[6][key]['result']['last_delivered_ack']['delivered_at']=args[-1]+1
    if late_only:
        with pytest.raises(ValueError,match='source_received_before_relay_capture'):
            r.validate_repeat_frame(*args,received_history=history)
    else:
        assert r.validate_repeat_frame(*args,received_history=history)['selected_origin']==49


@pytest.mark.parametrize('change', [None, 'wrong_unload', 'hold_after_return', 'missing_received'])
def test_source_return_also_binds_actual_physical_unload_hold(change):
    data, raw, plan=outcome_fixture(); outcomes=r.independent_outcomes(data,raw,plan,offered=3,trays=2)
    frame={'previous_job':'j0','source_completion':{'completed_at':3.},'current_empty_available_at':4.,'at':10.}
    api={'repeat_handoffs':[frame],'actual_received_queries':{'s1':{}}}
    if change=='wrong_unload': frame['source_completion']['completed_at']=2.9
    elif change=='hold_after_return': frame['current_empty_available_at']=3.9
    elif change=='missing_received': api['actual_received_queries'].clear()
    if change is None: r.bind_physical_returns(outcomes,api)
    else:
        with pytest.raises(ValueError): r.bind_physical_returns(outcomes,api)


@pytest.mark.parametrize('change', ['wrong_owner','future_available','receipt_other_job','missing_physical',
    'peer_missing','self_not_delivered','peer_pending','choose_nonhead','newer_self'])
def test_actual_public_frame_guards(change):
    args = list(frame_fixture()); data, selected, who, previous, view, messages, queries, physical, now = args
    own = selected['return_permit']['self_copy']; peer = messages[0]
    if change=='wrong_owner': view['owner_id']='foreign'
    elif change=='future_available': view['trays'][0]['available_at']=now+1
    elif change=='receipt_other_job': selected['return_permit']['receipt']['business_bag_id']='unknown'
    elif change=='missing_physical': selected['physical_barrier']['received_request_ids'].pop()
    elif change=='peer_missing': messages.clear()
    elif change=='self_not_delivered': queries[who,own['request_id']]['result']['last_delivered_ack']['status']='expired'
    elif change=='peer_pending':
        peer['capture']['extension']['submitted_physical_actions'][0]['last_delivered_ack']['status']='departed'
        peer['payload_sha256']=r.p.base.capture_digest_v2(peer['capture'])
    elif change=='choose_nonhead': selected['choice']['job']=deepcopy(previous['choice']['job'])
    else:
        q=deepcopy(queries[who,own['request_id']]); q['result']['last_delivered_ack']['planning_snapshot_v2']['capture']['local_capture']['publication_sequence']+=100
        queries[who,'newer'] = q
    with pytest.raises((ValueError,KeyError)): r.validate_repeat_frame(*args)


def test_terminal_gate_rejects_in_progress_before_opening_case_files(tmp_path):
    (tmp_path/'external_launch_receipt.json').write_text(json.dumps({'status':'unknown_before_dispatch'}))
    with pytest.raises(ValueError, match='campaign_not_terminal'): r.terminal_inventory(tmp_path)


def test_terminal_gate_keeps_both_cases_even_timeout(tmp_path):
    campaign=tmp_path/'campaign.json'; campaign.write_text('{}')
    digest=r.p.base.sha(campaign)
    (tmp_path/'ready.json').write_text(json.dumps({'campaign_sha256':digest}))
    (tmp_path/'external_launch_receipt.json').write_text(json.dumps({'status':'unknown_campaign_process',
        'campaign_sha256':digest,'whole_dispatch_wall_seconds':2400.1}))
    ledger={'cap3':{'status':'completed_saved_case'},'cap8':{'status':'unknown_in_progress'}}
    (tmp_path/'branch_ledger.json').write_text(json.dumps(ledger))
    _, actual=r.terminal_inventory(tmp_path)
    assert actual==ledger
    del ledger['cap8']; (tmp_path/'branch_ledger.json').write_text(json.dumps(ledger))
    with pytest.raises(ValueError,match='missing_case_denominator'): r.terminal_inventory(tmp_path)
