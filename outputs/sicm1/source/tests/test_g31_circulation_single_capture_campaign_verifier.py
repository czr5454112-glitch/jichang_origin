"""Source-bound saved verifier tests; synthetic data, no model/native/raw scan."""
import copy
import gzip
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_single_capture_campaign as v
from test_g31_circulation_single_capture_endpoint_dispatch import records, transport, incomplete, failed, reported, ENVELOPE


def campaign():
    return SimpleNamespace(**{**vars(v.previous.c), 'scene': lambda row: {'synthetic_input': True}})


def minimal_raw():
    c = campaign(); key = 'synthetic/fixed_default'; row = {'method': 'fixed_default'}
    admission = {'status': 'unknown_root_failure', 'closed': False, 'root_id': key.replace('/', ':'),
        'attempt_started_ns': 1, 'root_started_ns': 2, 'outside_return_ns': 10, 'elapsed_ns': 8}
    encoded = c.image.artifact_encode({k: value for k, value in admission.items()
        if k not in ('encoded_sha256', 'encoded_bytes', 'outside_return_ns', 'elapsed_ns')})
    admission.update(encoded_sha256=c.image.sha_bytes(encoded), encoded_bytes=len(encoded))
    raw = {'schema': c.SCHEMA, 'key': key, 'specification': row, 'input': c.scene(row),
        'native_state_sha256': None, 'failure': 'synthetic retained failure',
        'initial_endpoint_records': {'A': [], 'B': []}, 'calls': [], 'outbox': {},
        'participation_stages': [], 'initial_B': None, 'decisions': {}, 'native_batches': [],
        'result': None, 'continuation': {'status': 'unknown'}, 'outcome': {'status': 'unknown_assessor_failure'},
        'root_records': [], 'root_constructed': False, 'failed_root_admission': admission,
        'diagnostic_physical_time_before': .11, 'diagnostic_physical_time_after': .11,
        'owner_activation_admissions': [], 'request_creations': {}, 'ack_handling': [],
        'observation_gate_audit': None, 'outbox_query_trace': {
            'schema': 'g31.initial_root.outbox_query_trace.v2', 'reads': [], 'ack_bodies': [], 'refreshes': [], 'invalid': None}}
    return c, raw, row, key


def test_factory_preserves_full_namespaces_inverse_AST_and_both_root_layers():
    c = campaign(); bound = v.make_namespace(c); proof = bound.source_proof()
    assert proof['endpoint_loop_inverse_AST_exact'] and proof['fallback_partition_inverse_AST_exact']
    assert proof['attempt_RPC_inverse_AST_exact'] and proof['explicit_validated_attempt_envelope']
    assert all(not names for names in proof['recursive_LOAD_GLOBAL_missing'].values())
    root = bound.functions['root_replay']; original = bound.functions['original_root_replay']
    assert root.__code__ is v.previous.root_replay.__code__
    assert original.__code__ is v.previous.original.root_replay.__code__
    assert root.__globals__['c'] is original.__globals__['c'] is c
    assert root.__globals__['old'].root_replay is original
    assert bound.namespace['verify_branch'] is bound.verify_branch


def test_real_unchanged_checks_accept_structurally_valid_failed_prefix():
    c, raw, row, key = minimal_raw(); before = copy.deepcopy(raw)
    result = v.make_namespace(c).verify_branch(raw, row, key, branch_envelope=ENVELOPE)
    assert result['audit_status'] == 'passed_with_retained_unknown'
    assert result['reported_root']['status'] == 'unknown_root_failure'
    assert result['original_root_replay_verified'] and not result['root']['closed']
    assert result['business'] == {'status': 'unknown_missing_result'}
    assert result['query_replay']['status'] == 'passed_complete_actual_refresh_outbox_replay'
    assert result['original_checks']['original_branch_and_query_gate']['status'] == 'passed'
    assert raw == before


@pytest.mark.parametrize('defect', ['root_codec', 'diagnostic', 'immutable', 'physical', 'binding'])
def test_original_check_failures_keep_independent_facts_without_fabricated_root(defect):
    c, raw, row, key = minimal_raw()
    if defect == 'root_codec': raw['failed_root_admission']['encoded_bytes'] += 1
    elif defect == 'diagnostic': raw['diagnostic_physical_time_after'] = 1.
    elif defect == 'immutable': raw['outbox']['uncreated'] = {'request': {}, 'kind': 'route'}
    elif defect == 'physical': raw['outcome']['status'] = 'invented_success'
    else: raw['input'] = {'synthetic_input': False}
    result = v.make_namespace(c).verify_branch(raw, row, key, branch_envelope=ENVELOPE)
    assert result['audit_status'] == 'invalid' and not result['root']['closed']
    assert result['raw_root_diagnostic_hash']['status'] == 'passed'
    assert all(name in result['original_checks'] for name in ('binding','immutable','continuation','physical','root','diagnostic','query','gate'))
    if defect == 'root_codec':
        assert result['reported_root'] is None and not result['original_root_replay_verified']
        assert result['business'] == {'status': 'unknown_missing_result'}
    else: assert result['reported_root']['status'] == 'unknown_root_failure'


def synthetic_flow(rows=None, core_error=None, query_error=None):
    calls, outbox = transport()
    raw = {'initial_endpoint_records': records() if rows is None else rows, 'calls': calls,
        'outbox': outbox, 'root_records': [], 'failed_root_admission': None,
        'observation_gate_audit': {'calls':[]}, 'failure': None, 'native_state_sha256': None,
        'native_batches':[], 'owner_activation_admissions':[]}
    expected = reported(); business = {'status': 'assessed', 'completion': {'loaded': 1.}}
    seen = []
    def core(*args):
        seen.append('core')
        if core_error: raise core_error
        return {'root': copy.deepcopy(expected), 'business': copy.deepcopy(business)}
    def query(*args):
        seen.append('query')
        if query_error: raise query_error
        return {'status': 'passed_complete_actual_refresh_outbox_replay'}
    def root(*args):
        seen.append('root_replay')
        if core_error: raise core_error
        return copy.deepcopy(expected)
    fallback = {'binding':lambda *a: True,'immutable':lambda *a: {},'continuation':lambda *a: True,
        'physical':lambda *a: copy.deepcopy(business),'root':root,'diagnostic':lambda *a: True}
    namespace = {**v.previous._namespace, 'complete_query_replay':query,
        'chain_verifier':SimpleNamespace(verify=lambda *a:{'status':'passed_source_bound_chain_data'})}
    result = v._branch(raw, {}, 'synthetic', branch_envelope=ENVELOPE, namespace=namespace,
        core=core, fallback=fallback, gate_check=lambda *a: {'status': 'synthetic_passed'})
    return result, expected, business, seen


def test_complete_synthetic_conjunction_preserves_original_replay_conclusion():
    result, expected, business, seen=synthetic_flow()
    assert result['audit_status']=='passed' and result['root']['closed']
    assert result['reported_root']==expected and result['business']==business
    assert result['root']['observed_within_100ms'] and not result['root']['complete_100ms_certified']
    assert result['endpoint_status']=='verified_complete' and seen==['core','query']


def test_nonthrowing_B_failure_cannot_certify_reported_closed_root():
    rows = records(); rows['B'][0] = incomplete('B')
    result, expected, business, seen = synthetic_flow(rows)
    assert result['reported_root'] == expected and result['reported_root']['closed']
    assert result['business'] == business
    assert result['endpoint_status'] == 'verified_unknown'
    assert not result['root']['closed'] and not result['root']['observed_within_100ms']
    assert result['endpoint_audit']['records'][2]['status'] == 'verified_unknown_capture'
    assert seen == ['core','query']


def test_invalid_single_record_continues_other_records_and_original_subsystems():
    rows = records(); rows['A'][0] = failed(1)
    rows['A'][0]['capture_failure']['started'][0]['started_ns'] = True
    result, expected, business, seen = synthetic_flow(rows)
    assert result['audit_status'] == 'invalid' and not result['root']['closed']
    assert [r['status'] for r in result['endpoint_audit']['records']] == [
        'invalid','verified_conditional_endpoints','verified_conditional_endpoints']
    assert result['reported_root'] == expected and result['business'] == business
    assert seen == ['core','query']


@pytest.mark.parametrize('error', [MemoryError('resource'), RuntimeError('unexpected')])
def test_audit_error_is_not_legal_unknown_or_raw_reported_root(error):
    result, _, business, _ = synthetic_flow(core_error=error)
    assert result['audit_status'] == 'audit_error'
    assert result['reported_root'] is None and not result['original_root_replay_verified']
    assert result['business'] == business and not result['root']['closed']


def test_late_query_failure_retains_successful_original_core_without_rerunning_it():
    result, expected, business, seen = synthetic_flow(query_error=ValueError('bad query'))
    assert result['audit_status'] == 'invalid' and not result['root']['closed']
    assert result['reported_root'] == expected and result['business'] == business
    assert seen.count('core') == 1 and 'root_replay' not in seen


@pytest.mark.parametrize('envelope', [None, {}, {'attempt_started_ns':True,'attempt_finished_ns':100},
    {'attempt_started_ns':101,'attempt_finished_ns':100}])
def test_missing_or_malformed_explicit_envelope_never_uses_root_clock(envelope):
    c, raw, row, key = minimal_raw()
    result = v.make_namespace(c).verify_branch(raw,row,key,branch_envelope=envelope)
    assert result['audit_status'] == 'invalid' and not result['root']['closed']
    assert result['reported_root']['warm_ms'] == 8/1e6
    assert result['endpoint_audit']['problems'][0]['stage'] == 'branch_envelope'


def test_saved_entry_executes_with_Path_and_reaches_real_plan_guard(tmp_path):
    seen=[]
    def plan(output, expected):
        seen.append((output,expected));raise ValueError('sentinel_bound_plan')
    c=campaign();c.verify_plan=plan
    with pytest.raises(ValueError,match='sentinel_bound_plan'):
        v.make_namespace(c).verify_saved(tmp_path,'expected')
    assert seen == [(tmp_path.resolve(),'expected')]


@pytest.mark.parametrize('name', ['Path','gzip','json','_checked_rpc_scope','verify_branch'])
def test_missing_globals_detected_recursively_in_saved_template(name):
    bound=v.make_namespace(campaign()); fn=bound.functions['saved_template']
    namespace=dict(fn.__globals__);namespace.pop(name)
    broken=v.shared(fn,namespace)
    assert name in v.previous.previous.missing_globals(broken)


def test_factories_do_not_share_mutable_namespaces_or_change_old_module():
    first=v.make_namespace(campaign());second=v.make_namespace(campaign())
    assert first.namespace is not second.namespace
    first.namespace['c']='local_only'
    assert second.namespace['c'] is not first.namespace['c']
    assert v.previous.root_replay.__globals__['c'] is v.previous.c
    assert v.previous.verify_saved.__globals__['verify_branch'] is v.previous.verify_branch


def saved_fixture(tmp_path):
    """Tiny failed branches exercise the real v3 saved loop and explicit clocks.

Only the pre-validated campaign/source identity is stubbed. No saved native
fixture, capability, complete prediction or invented successful root is used.
"""
    c=campaign(); rows={}; ledger={}; times={}
    for n in range(9):
        for method in ('fixed_default','budget_two'):
            key=f'synthetic{n}/{method}'
            row={'case':str(n),'method':method,'fault':'synthetic'};rows[key]=row
            _,raw,_,_=minimal_raw();raw.update(key=key,specification=row,input=c.scene(row))
            start=10+len(ledger)*30;end=start+20;times[key]=(start,end)
            admission=raw['failed_root_admission']
            admission.update(root_id=key.replace('/',':'),attempt_started_ns=start,
                root_started_ns=start+1,outside_return_ns=start+5,elapsed_ns=4)
            encoded=c.image.artifact_encode({k:value for k,value in admission.items()
                if k not in ('encoded_sha256','encoded_bytes','outside_return_ns','elapsed_ns')})
            admission.update(encoded_sha256=c.image.sha_bytes(encoded),encoded_bytes=len(encoded))
            path=tmp_path/'raw'/(key+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
            with gzip.open(path,'wt',encoding='utf8') as stream:json.dump(raw,stream)
            ledger[key]={**row,'status':'raw_saved','raw':c.reference(path),
                'attempt_started_ns':start,'export_started_ns':start+6,'export_finished_ns':start+10,
                'attempt_finished_ns':end}
    plan={'row_order':list(rows),'rows':rows,'expected_READY':{'mode':'initial_A_two','version':'synthetic'},
        'image':{'version':'synthetic'}}
    (tmp_path/'campaign.json').write_text(json.dumps(plan),encoding='utf8')
    accepted={'status':'closed_run_acceptance_passed','active':False,'invalid':[],
        'branch_keys':sorted(rows),'run_reference':c.reference(tmp_path/'campaign.json'),'evidence_sha256':{}}
    life={'worker_setup_started_ns':0,'construction_attempt_started_ns':1,'started_ns':2,'ready_ns':3,
        'close_attempt_started_ns':1000,'cleanup_finished_ns':1005,'ledger':[],
        'ready':plan['expected_READY'],'status':'closed_protocol','process_exit_code':0,
        'close':{'close_admitted_ns':1001,'close_finished_ns':1002,'process_exit_code':0,
            'reply':{'source_unchanged':True,'requests':0}}}
    for name,value in [('branch_ledger.json',ledger),('run_acceptance.json',accepted),('predictor_lifetime.json',life)]:
        (tmp_path/name).write_text(json.dumps(value),encoding='utf8')
    c.verify_plan=lambda path,expected:plan
    return c,plan,ledger,times


def test_saved18_real_loop_passes_verified_attempts_not_root_clocks_and_retains_unknowns(tmp_path):
    c,plan,ledger,times=saved_fixture(tmp_path)
    bound=v.make_namespace(c);report=bound.verify_saved(tmp_path,'synthetic-only')
    assert report['status']=='passed_saved_with_complete_unknown_denominator'
    assert report['branches']==18 and len(report['rows'])==18 and len(report['pairs'])==9
    assert report['closed_roots']==report['reported_closed_roots']==0
    assert report['open_or_unknown_roots']==18 and report['predictor_requests']==0
    for key,row in report['rows'].items():
        start,end=times[key]
        assert row['endpoint_audit']['branch_envelope']=={'attempt_started_ns':start,'attempt_finished_ns':end}
        assert row['branch_attempt']['started_ns']==start
        assert row['reported_root']['warm_ms']==4/1e6
        assert row['RPC_audit']['status']=='passed' and not row['root']['closed']


def test_one_invalid_saved_branch_does_not_erase_other17_or_become_passed(tmp_path):
    c,plan,ledger,times=saved_fixture(tmp_path)
    key=plan['row_order'][0];path=tmp_path/'raw'/(key+'.json.gz')
    with gzip.open(path,'rt',encoding='utf8') as stream:raw=json.load(stream)
    raw['failed_root_admission']['encoded_bytes']+=1
    with gzip.open(path,'wt',encoding='utf8') as stream:json.dump(raw,stream)
    ledger[key]['raw']=c.reference(path)
    (tmp_path/'branch_ledger.json').write_text(json.dumps(ledger),encoding='utf8')
    report=v.make_namespace(c).verify_saved(tmp_path,'synthetic-only')
    assert report['status']=='failed_saved_audit' and report['invalid_or_error_branches']=={key:'invalid'}
    assert len(report['rows'])==18 and report['rows'][key]['reported_root'] is None
    assert sum(r['audit_status']=='passed_with_retained_unknown' for r in report['rows'].values())==17
    assert report['pairs']['synthetic0/budget_two']['status']=='unknown_invalid_audit_pair'


def test_unexecuted_denominator_stays_unknown_without_fake_attempt_or_reported_root(tmp_path):
    c,plan,ledger,_=saved_fixture(tmp_path);key=plan['row_order'][-1]
    ledger[key]={**plan['rows'][key],'status':'unknown_unexecuted'}
    (tmp_path/'branch_ledger.json').write_text(json.dumps(ledger),encoding='utf8')
    report=v.make_namespace(c).verify_saved(tmp_path,'synthetic-only');row=report['rows'][key]
    assert report['status']=='passed_saved_with_complete_unknown_denominator' and len(report['rows'])==18
    assert row['reported_root'] is None and row['endpoint_audit'] is None and not row['root']['closed']
    assert row['branch_attempt']['status']=='not_attempted'


def test_RPC_partial_mutation_is_retained_but_excluded_from_verified_subtotal():
    def failing_rpc(results,key,plan,samples,raw,used):
        results[key]['prediction_counts']={'baseline_evaluation_calls':999,'additional_candidate_calls':7}
        raise ValueError('injected_after_partial_count_write')
    fake_factory=v.private(v.make_namespace,{'_rpc_checker':lambda ns:(failing_rpc,'synthetic AST')})
    bound=fake_factory(campaign());key='sample/budget_two'
    result={'root':{'closed':True,'observed_within_100ms':True,'reasons':[]},'reported_root':reported(),
        'audit_status':'passed'}
    results={key:result};used=set()
    bound.namespace['_checked_rpc_scope'](results,key,{}, {key.replace('/',':'):{}}, {},used)
    assert used=={key.replace('/',':')} and result['RPC_audit']['status']=='invalid'
    assert result['reported_unverified_prediction_counts']['baseline_evaluation_calls']==999
    assert 'prediction_counts' not in result and not result['root']['closed']
    assert result['reported_root']['closed'] is True
