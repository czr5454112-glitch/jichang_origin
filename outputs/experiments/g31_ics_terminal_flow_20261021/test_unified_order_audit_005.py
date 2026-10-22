"""Pure guards and malformed-record cases; no native or real ACK files opened."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

path = Path(__file__).with_name('unified_order_audit_005.py')
spec = importlib.util.spec_from_file_location('unified005',path)
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
science = audit.dependency()


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.suffix == '.gz':
        with gzip.open(path,'wt',encoding='utf8') as out: json.dump(value,out)
    else: path.write_text(json.dumps(value),encoding='utf8')
    return science.bind(path)


def records(method='TF-B1-300'):
    payload = dict(request_id='request',tray_id='tray',source=0,destination=2,owner_id='A',
        issued_at=10.,expiry=90.,earliest_departure=12.,message_delay=2.,transfer_scope='cross_zone',
        control_reason='observed_source_queue')
    ledger = {k:v for k,v in payload.items() if k in audit.LEDGER_ROW_FIELDS}
    ledger.update(status='received',received_at=49.,reason='received',status_scope='own_payload_and_last_delivered_ack_only')
    ack = dict(request_id='request',sequence=1,attempt=1,observed_at=49.,delivered_at=50.,
        status='received',reason='received',received_at=49.,delivered_copies=1)
    view = dict(schema='g31.owner_protocol_observation.v1',now=60.,owner_id='A',scope='own messages',
        delivered_transfer_acks=[ack],client_transfer_ledger=[ledger])
    view['evidence_scope'] = dict(schema='g31.airport_joint_campaign.v1.transfer_ack_subset.v1',
        complete_owner_protocol_view=False,full_transfer_ack_history_preserved=True,
        full_client_transfer_ledger_preserved=True,owner_protocol_fields_retained=list(audit.ACK_FIELDS),
        owner_protocol_fields_omitted=['client_commands'],original_owner_protocol_scope=view['scope'],online_actor_input=False)
    order = dict(order_id='order',request_id='request',reason='REAL_DEMAND_SUPPLY')
    return dict(plan=dict(method=method,horizon=60.),checkpoint=dict(policy_state=dict(empty_transport_orders=dict(orders={'order':order}))),
        call_rows=[dict(kind='transfer',retry=False,request=payload)],
        terminal=dict(transfers=[dict(request_id='request',status='received',received_at=49.)],
            receipts=[dict(event='PROTOCOL_ACK_DELIVERED',reason='request:1',time=50.)]),
        ack_views={'A':view},frozen_audit=dict(violations=[],request_sets_equal=True,
            by_reason={'REAL_DEMAND_SUPPLY':dict(orders=1,submitted=1,accepted=1,received=1,failed_at_export=0)}))


def test_valid_instrumented_records_preserve_all_four_denominators():
    result = audit.audit_rows(**records())
    assert result['passed'] and set(result['by_reason']) == set(audit.REASONS)
    assert result['by_reason']['NECESSARY_CLEARING']['received_per_submitted'] is None
    assert result['actual_nonretry_requests'] == 1


def test_unsubmitted_orders_are_retained_in_their_reason_denominator():
    r=records();r['checkpoint']['policy_state']['empty_transport_orders']['orders']['planned']=dict(
        order_id='planned',request_id=None,reason='FORECAST_REPOSITION')
    result=audit.audit_rows(**r)
    assert result['by_reason']['FORECAST_REPOSITION']['all_order_records']==1
    assert result['by_reason']['FORECAST_REPOSITION']['unsubmitted_order_records']==1
    assert result['by_reason']['FORECAST_REPOSITION']['submitted']==0
    aggregate=audit.aggregate_denominators([result])
    assert aggregate['serialized_unified_order_book']['by_reason']['FORECAST_REPOSITION']['received_per_submitted'] is None


@pytest.mark.parametrize('mutation,reason', [
    ('duplicate_call','duplicate_nonretry_submission'), ('duplicate_native','duplicate_native_request_identity'),
    ('bad_order_id','order_book_key_or_identity_mismatch'), ('duplicate_order_request','duplicate_order_request_identity'),
    ('bad_expiry','request_payload_evidence_mismatch'), ('bad_ack_owner','ack_without_same_owner_submission'),
    ('bad_delivery','ack_physical_delivery_receipts_mismatch'), ('bad_sequence','ack_sequence_duplicate_or_invalid'),
    ('bad_attempt','ack_attempt_invalid'), ('future_ack','ack_delivery_time_invalid'),
    ('unknown_reason','unknown_order_reason'), ('wrong_reason','order_reason_payload_category_mismatch'),
])
def test_raw_record_violations_survive_dict_join(mutation,reason):
    r=records()
    if mutation=='duplicate_call': r['call_rows'].append(copy.deepcopy(r['call_rows'][0]))
    if mutation=='duplicate_native': r['terminal']['transfers'].append(copy.deepcopy(r['terminal']['transfers'][0]))
    if mutation=='bad_order_id': r['checkpoint']['policy_state']['empty_transport_orders']['orders']['order']['order_id']='wrong'
    if mutation=='duplicate_order_request': r['checkpoint']['policy_state']['empty_transport_orders']['orders']['second']=dict(order_id='second',request_id='request',reason='REAL_DEMAND_SUPPLY')
    if mutation=='bad_expiry': r['ack_views']['A']['client_transfer_ledger'][0]['expiry']=91.
    if mutation=='bad_ack_owner': r['call_rows'][0]['request']['owner_id']='B'
    if mutation=='bad_delivery': r['terminal']['receipts'][0]['time']=51.
    if mutation=='bad_sequence': r['ack_views']['A']['delivered_transfer_acks'][0]['sequence']=0
    if mutation=='bad_attempt': r['ack_views']['A']['delivered_transfer_acks'][0]['attempt']=0
    if mutation=='future_ack': r['ack_views']['A']['delivered_transfer_acks'][0]['delivered_at']=61.
    if mutation=='unknown_reason': r['checkpoint']['policy_state']['empty_transport_orders']['orders']['order']['reason']='UNKNOWN'
    if mutation=='wrong_reason': r['call_rows'][0]['request']['control_reason']='ordinary_return_to_loader'
    result=audit.audit_rows(**r)
    assert not result['passed'] and any(v['reason']==reason for v in result['violations'])


def test_retry_payload_and_soft_fields_are_checked_even_without_matching_order():
    r=records('C00');r['checkpoint']={}
    retry=copy.deepcopy(r['call_rows'][0]);retry['retry']=True;retry['request']['target_by']=123.
    r['call_rows'].append(retry)
    reasons={v['reason'] for v in audit.audit_rows(**r)['violations']}
    assert {'retry_changed_or_missing_first_payload','soft_order_times_in_any_transfer_payload'} <= reasons


def test_baseline_optional_is_separate_and_never_synthesizes_upper_order_identity():
    r=records('C00');r['checkpoint']={};r['call_rows'][0]['request']['control_reason']='joint_optional_reposition'
    result=audit.audit_rows(**r)
    assert result['passed'] and result['instrumentation']=='upper_order_book_not_instrumented'
    assert result['by_reason']['FORECAST_REPOSITION']['submitted']==0
    assert result['by_reason']['baseline_optional_inventory_reposition']['submitted']==1
    assert result['all_order_records']==0
    assert result['request_chains'][0]['actual_submission']['control_reason']=='joint_optional_reposition'


def test_baseline_unknown_payload_reason_remains_unclassified():
    r=records('C10');r['checkpoint']={};r['call_rows'][0]['request'].pop('control_reason')
    result=audit.audit_rows(**r)
    assert result['by_reason']['unclassified']['submitted']==1


@pytest.mark.parametrize('bad', ['outer_history','inner_history','nested_reason','scope_flag','owner_roster','time','retained_fields'])
def test_subset_schema_rejects_full_or_changed_history(tmp_path,bad):
    views=records()['ack_views'];view=views['A']
    if bad=='outer_history':view['client_commands']=[{'large':'history'}]
    if bad=='inner_history':view['delivered_transfer_acks'][0]['owner_history']=[]
    if bad=='nested_reason':view['delivered_transfer_acks'][0]['reason']={'owner_history':[]}
    if bad=='scope_flag':view['evidence_scope']['complete_owner_protocol_view']=True
    if bad=='owner_roster':views['B']=copy.deepcopy(view)
    if bad=='time':view['now']=59.
    if bad=='retained_fields':view['evidence_scope']['owner_protocol_fields_retained']=[]
    path=tmp_path/'ack.json.gz';save(path,views)
    with pytest.raises(ValueError,match='unified_order_audit:'):
        audit.read_subset(path,owners=['A'],horizon=60.)


def test_valid_subset_and_decompression_size_guard(tmp_path,monkeypatch):
    path=tmp_path/'ack.json.gz';views=records()['ack_views'];save(path,views)
    assert audit.read_subset(path,owners=['A'],horizon=60.)==views
    monkeypatch.setattr(audit,'ACK_JSON_BYTES_LIMIT',100)
    with pytest.raises(ValueError,match='inflated_json_limit'):
        audit.read_subset(path,owners=['A'],horizon=60.)


def test_duplicate_json_keys_are_rejected_before_field_roster_can_hide_history(tmp_path):
    path=tmp_path/'ack.json.gz'
    with gzip.open(path,'wt',encoding='utf8') as out:
        out.write('{"A":{},"A":{}}')
    with pytest.raises(ValueError,match='duplicate_ack_json_key'):
        audit.read_subset(path,owners=['A'],horizon=60.)


def test_compressed_size_limit_is_checked_before_gzip_open(tmp_path,monkeypatch):
    path=tmp_path/'ack.gz';path.write_bytes(b'not gzip')
    monkeypatch.setattr(audit,'ACK_BYTES_LIMIT',path.stat().st_size)
    monkeypatch.setattr(audit.gzip,'open',lambda *a,**k:pytest.fail('must not open rejected ACK'))
    with pytest.raises(ValueError,match='below_30MB'):
        audit.read_subset(path,owners=['A'],horizon=60.)


def fixture_rows(tmp_path):
    source=save(tmp_path/'terminal_flow_runtime_005/source_manifest.json',dict(worker_evidence_contract=audit.CONTRACT))
    directory=tmp_path/'run';save(directory/'delivered_ack_evidence.json.gz',{})
    save(directory/'worker_report.json',dict(delivered_ack_evidence_scope='complete transfer ACK history and transfer ledger; owner protocol subset',
        delivered_ack_evidence=dict(gzip_bytes=(directory/'delivered_ack_evidence.json.gz').stat().st_size)))
    rows={(i,'TF-current'):dict(directory=directory,plan=dict(source_bundle=source,worker_evidence_contract=audit.CONTRACT)) for i in range(28)}
    return rows,source


def test_pending_preflight_never_stats_or_opens_ack(tmp_path,monkeypatch):
    rows,source=fixture_rows(tmp_path)
    for row in rows.values():row['directory']=tmp_path/'missing'
    monkeypatch.setattr(audit.gzip,'open',lambda *a,**k:pytest.fail('no ACK reads in pending check'))
    assert audit.preflight(rows,dict(status='pending'),source,science)['status']=='pending'


@pytest.mark.parametrize('bad', ['old_runtime','source_contract','plan_contract','worker_scope','worker_size','fewer_runs'])
def test_source_plan_and_export_guards_before_ack_read(tmp_path,monkeypatch,bad):
    rows,source=fixture_rows(tmp_path)
    if bad=='old_runtime':source=save(tmp_path/'terminal_flow_runtime_003/source_manifest.json',dict(worker_evidence_contract=audit.CONTRACT))
    if bad=='source_contract':source=save(Path(source['path']),dict(worker_evidence_contract='full_owner_history'))
    if bad=='plan_contract':next(iter(rows.values()))['plan']['worker_evidence_contract']='legacy'
    if bad=='worker_scope':save(tmp_path/'run/worker_report.json',dict(delivered_ack_evidence_scope='full_history'))
    if bad=='worker_size':save(tmp_path/'run/worker_report.json',dict(delivered_ack_evidence_scope='complete transfer ACK history and transfer ledger; owner protocol subset',delivered_ack_evidence=dict(gzip_bytes=0)))
    if bad=='fewer_runs':rows.pop(next(iter(rows)))
    monkeypatch.setattr(audit.gzip,'open',lambda *a,**k:pytest.fail('no ACK reads in metadata guard'))
    with pytest.raises(ValueError,match='unified_order_audit:'):
        audit.preflight(rows,dict(status='ready'),source,science)


def test_pending_execute_creates_no_output(tmp_path):
    with pytest.raises(ValueError,match='all_28_closed'):
        audit.execute({},dict(status='pending'),{},{},{},science,tmp_path/'report',[])
    assert not (tmp_path/'report').exists()


def test_frozen_join_reads_the_validated_subset_once_and_restores_reader(tmp_path):
    views=records()['ack_views']
    original=lambda p:pytest.fail('ACK must not be decoded a second time')
    flow=SimpleNamespace(read=original)
    def join(directory):
        assert flow.read(directory/'delivered_ack_evidence.json.gz') is views
        raise RuntimeError('join failure')
    flow.audit_unified_order_book=join
    with pytest.raises(RuntimeError,match='join failure'):
        audit.frozen_book_audit(flow,tmp_path,views)
    assert flow.read is original


def test_producer_change_prevents_complete_marker(tmp_path,monkeypatch):
    rows,source=fixture_rows(tmp_path)
    producer=tmp_path/'driver.py';producer.write_text('original',encoding='utf8');binding=science.bind(producer)
    registration=save(tmp_path/'registration.json',{})
    status=dict(status='ready',blocks=[])
    wrapper=SimpleNamespace(**{name:getattr(science,name) for name in ('bound_read','read','bind','verify_bindings','fresh')},
        verify_sources=lambda ref:None,inspect_blocks=lambda *args:(rows,status))
    def changed(row,h,s):
        producer.write_text('changed',encoding='utf8')
        return dict(task_id='task',full_request_audit=dict(instrumentation='serialized_unified_order_book',violations=[],passed=True))
    monkeypatch.setattr(audit,'run_audit',changed)
    with pytest.raises(ValueError,match='producer_dependency_or_artifact_changed'):
        audit.execute(rows,status,source,registration,{},wrapper,tmp_path/'report',[binding])
    assert (tmp_path/'report/pending.json').exists() and not (tmp_path/'report/COMPLETE.json').exists()


def test_complete_marker_requires_final_bound_artifacts_and_preserves_independent_scope(tmp_path,monkeypatch):
    rows,source=fixture_rows(tmp_path)
    producer=tmp_path/'driver.py';producer.write_text('original',encoding='utf8');binding=science.bind(producer)
    registration=save(tmp_path/'registration.json',{})
    status=dict(status='ready',blocks=[])
    wrapper=SimpleNamespace(**{name:getattr(science,name) for name in ('bound_read','read','bind','verify_bindings','fresh')},
        verify_sources=lambda ref:None,inspect_blocks=lambda *args:(rows,status))
    monkeypatch.setattr(audit,'run_audit',lambda *args:dict(task_id='synthetic',evidence={},
        full_request_audit=audit.audit_rows(**records())))
    audit.execute(rows,status,source,registration,{},wrapper,tmp_path/'report',[binding])
    marker=science.read(tmp_path/'report/COMPLETE.json');report=science.bound_read(marker['summary'])
    assert marker['all_request_audits_passed'] and report['registered_runs']==28
    assert report['compact_transfer_ack_subset_read'] is True and report['full_owner_history_opened'] is False
    assert report['scientific_service_improvement_claimed'] is False
    assert 'request_chains' not in report['run_reports'][0]
    with pytest.raises(ValueError,match='fresh_output_required'):
        audit.execute(rows,status,source,registration,{},wrapper,tmp_path/'report',[binding])
