"""Three native sessions/six owner initial seams; no model or physical submit.

Preparation is separate. Execution requires a reviewed hash and owned launcher.
The source/session origin is tested at run time; saved guards certify only the
recorded data. Neither outcome tables nor later snapshots enter this experiment.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from . import live_obligation_initial_recorded_adapter as recorded
from . import prepare_live_initial_decision_seam as seam
from . import research_live_obligation_native_domain as fixture
from . import initial_owner_route_image as image

ROOT,OUT=seam.ROOT,seam.OUT
MODULE=__package__+'.research_live_initial_six_seam'
SCHEMA='g31.live_initial_six_seam.v1'
CASES=('mechanism','no_overlap','insufficient_advance')
KEYS=tuple(case+'/initial' for case in CASES)
DOMAIN=tuple(case+'/'+owner for case in CASES for owner in ('A','B'))
PURE=OUT/'live_initial_six_seam_pure_001'
SEAM=OUT/'live_initial_decision_seam_prepare_001'
OLD=OUT/'live_obligation_unloading_native_prepare_001'
TESTS=('tests/test_g31_circulation_live_initial_recorded_adapter.py',)
EXPECTED_TESTS=36
LIMIT=120.
sha,read,write,reference=fixture.sha,fixture.read,fixture.write,fixture.reference
origin=recorded.original


def require(ok,reason):
    if not ok:raise ValueError('initial_six:'+reason)


def encoded(value):return origin.history.payload_encoding(value)
def data(value):return json.loads(encoded({'value':value}))['value']


def declaration():
    action=fixture.construction.actions()[16]
    require(action=={'initial_action':'prefer_2','empty_departure':.11,'return_delay':0.,'later_action':'native_default'},'fixed_action16')
    return {key:{'case':case,'vector':copy.deepcopy(action),'method':'initial_seam_only','fault':None,
        'status':'unknown_unexecuted'} for key,case in zip(KEYS,CASES,strict=True)}


def owner_row(owner):
    return {'owner':owner,'status':'unknown_unexecuted','native_protection_certified':False,
        'dispatch_authorized':False,'model_predictions':0,'physical_requests_submitted':0}


def run_case(native,specification,input_data,contract_ref,*,accepted_run,branch_key):
    """Own scope, real endpoints and exact client; no provider or native result."""
    raw={'schema':SCHEMA,'specification':data(specification),'input':data(input_data),
        'owners':{o:owner_row(o) for o in ('A','B')},'status':'unknown_partial',
        'native_protection_certified':False,'model_predictions':0,'physical_requests_submitted':0}
    session=None;client=None
    try:
        require(accepted_run.active_for(branch_key),'active_branch')
        require(all(accepted_run.branch_specification(branch_key).get(k)==specification.get(k)
            for k in ('case','vector','method','fault')),'declared_specification')
        session=native.NativeSession(input_data)
        admission,handle=origin.native_gate.bind_native027(native,session,contract_ref,
            accepted_run=accepted_run,branch_key=branch_key)
        raw['native_admission']=data(admission);require(handle is not None,'runtime_admission')
        session.advance_to(.05)
        client=origin.history.fixture.LocalTransport(session);publication={}
        for owner,peer in (('A','B'),('B','A')):
            client.activate(owner,{'kind':'initial_public_epoch','at':.05})
            client.submit(owner,'demand','seed-demand',target_owner=peer,message_delay=.01,publication_delay=.01)
            publication[owner]=client.submit(owner,'planning_snapshot','initial-planning',target_owner=peer,
                message_delay=.01,publication_delay=.01,expiry=.21)
        session.advance_to(.11)
        for owner in ('A','B'):
            row=raw['owners'][owner];journal=recorded.EndpointJournal();started=time.perf_counter_ns()
            try:
                client.activate(owner,{'kind':'initial_decision_epoch','at':.11});client.refresh_owner(owner,retry=False)
                row.update(admission=data(client.context),own_publication_id=publication[owner])
                decision=recorded.collect_initial_decision(native,session,owner,publication[owner],client,handle,journal=journal)
                if type(decision) is not origin.InitialDecision:
                    row.update(status='unknown_initial_collection',collection_result=data(decision));continue
                origin.require_current(decision)
                row['initial_decision']=decision.audit_copy()
                context=origin.supplied_snapshot(decision)
                require(type(context) is origin.supplied.SuppliedContext,'supplied_context')
                row['supplied_context']=context.audit_copy()
                proposal=recorded.revalidate_first_component(decision,specification['vector'],journal=journal)
                row['local_proposal']=data(proposal)
                row['status']='initial_seam_validated' if proposal.get('status')=='fresh_local_component_proposal' else 'unknown_fresh_current_guard'
                origin.require_current(decision)
            except Exception:row.update(status='unknown_owner_exception',exception=traceback.format_exc())
            finally:
                row['journal']=journal.audit_copy();row['finished_ns']=time.perf_counter_ns();row['started_ns']=started
                row['calls_at_owner_exit']=data(client.calls);row['owned_rows_at_owner_exit']=data(client.owned(owner))
                row['own_request_order_at_owner_exit']=list(client.owned(owner))
                row['owner_exit_physical_time']=session.physical_time
        require(session.physical_time==.11,'no_physical_advance_in_seams')
        require(len(client.calls)==4 and all(c['kind'] in ('demand','planning_snapshot') and c['retry'] is False for c in client.calls),
            'only_four_seed_publications')
        raw['status']='complete_six_scope_case' if all(r['status']=='initial_seam_validated' for r in raw['owners'].values()) else 'completed_case_with_unknowns'
    except Exception:raw.update(status='unknown_case_exception',exception=traceback.format_exc())
    finally:
        if session is not None:raw['physical_time']=session.physical_time
        if client is not None:
            raw['calls']=data(client.calls);raw['outbox']=data(client.rows);raw['roots']=data(client.roots)
    return raw


def verify_journal(value):
    require(value.get('schema')==recorded.SCHEMA and value.get('saved_copy_has_authority') is False,'journal_schema')
    require(type(value.get('monitor_failed')) is bool and type(value.get('monitor_errors')) is list,'monitor_status')
    failed=value['monitor_failed'];require(failed or value['monitor_errors']==[],'monitor_failure_not_hidden')
    records=value['records'];require(type(records) is list and len(records)<=2,'maximum_two_collections')
    previous=-1
    for i,entry in enumerate(records):
        require(entry['collection']==('initial','fresh_current')[i] and entry['owner'] in ('A','B'),'journal_phase_owner')
        require(type(entry['request_id']) is str and entry['request_id'],'journal_request')
        start,end=entry.get('started_ns'),entry.get('finished_ns')
        require(all(type(t) is int and t>=0 for t in (start,end) if t is not None),'journal_clock_types')
        require(failed or start is not None and end is not None,'journal_clock_present')
        if start is not None:require(previous<=start,'journal_clock_order')
        if start is not None and end is not None:require(start<=end,'journal_clock')
        if end is not None:previous=end
        rows=entry['endpoints'];require(type(rows) is list and len(rows)<=3,'getter_maximum')
        before=start
        for j,row in enumerate(rows):
            begin,finish=row.get('started_ns'),row.get('finished_ns')
            require(row['endpoint']==recorded.ORDER[j] and all(type(t) is int and t>=0 for t in (begin,finish) if t is not None),'getter_clock_type_order')
            require(failed or begin is not None and finish is not None,'getter_clock_present')
            if before is not None and begin is not None:require(before<=begin,'getter_before')
            if begin is not None and finish is not None:require(begin<=finish,'getter_clock_order')
            if finish is not None and end is not None:require(finish<=end,'getter_after')
            before=finish
            require(row['status'] in ('returned','raised') or failed and row['status']=='in_progress','terminal_getter')
            if row['status']=='raised':require(j==len(rows)-1 and type(row.get('error_type')) is str and 'value' not in row,'exception_terminal_prefix')
            elif row.get('evidence_status')=='unknown_export_error':require('value' not in row and type(row.get('export_error')) is str,'export_failure')
            elif 'value' in row:recorded.endpoint_data(row['endpoint'],row['value'])
            else:require(failed,'missing_return_value')
        require(entry['status'] in ('returned','raised') or failed and entry['status']=='in_progress','terminal_collection')
        if entry['status']=='raised':require(type(entry.get('error_type')) is str,'collection_exception_type')
        if entry['status']=='returned' and any(e['status']=='raised' for e in rows):
            require(failed or entry.get('returned_status')=='unknown','captured_exception_must_return_unknown')
    return records


def verify_owner(row,action):
    require(row['owner'] in ('A','B') and row['native_protection_certified'] is False and row['dispatch_authorized'] is False
        and row['model_predictions']==row['physical_requests_submitted']==0,'owner_scope')
    if 'journal' not in row:
        require(row['status']=='unknown_unexecuted','missing_journal_unknown');return {'status':'unknown_unexecuted'}
    records=verify_journal(row['journal'])
    require(type(row['started_ns']) is int and type(row['finished_ns']) is int
        and 0<=row['started_ns']<=row['finished_ns'],'owner_wall')
    require(all(row['started_ns']<=r[k]<=row['finished_ns'] for r in records for k in ('started_ns','finished_ns') if k in r),'owner_journal_envelope')
    if row['status']!='initial_seam_validated':return {'status':'unknown_preserved','reason':row['status'],'recorded_collections':len(records)}
    require(row['journal']['monitor_failed'] is False,'recording_failed_not_success')
    require(len(records)==2 and all(len(r['endpoints'])==3 and all(e['status']=='returned' and 'evidence_status' not in e
        for e in r['endpoints']) for r in records),'six_successful_getters')
    owner=row['owner'];decision=row['initial_decision'];public=decision['public'];key=row['own_publication_id']
    require(decision['owner']==owner and decision['own_publication_id']==key and decision['at']==.11
        and decision['saved_copy_has_authority'] is False,'decision_identity')
    require(hashlib.sha256(encoded(public).encode()).hexdigest()==decision['public_sha256'],'public_digest')
    for r in records:
        require(r['owner']==owner and r['request_id']==key,'collection_owner_identity')
        actual={e['endpoint']:e['value'] for e in r['endpoints']}
        require(encoded(actual)==encoded({k:public[k] for k in recorded.ORDER}),'exact_same_endpoint_data')
    history=origin.history.submission_history(row['calls_at_owner_exit'],owner,.11)
    rows=row['owned_rows_at_owner_exit'];require(list(history)==row['own_request_order_at_owner_exit']
        and set(history)==set(rows),'complete_own_rows')
    for request_id,(kind,payload) in history.items():
        require(rows[request_id]['kind']==kind and encoded(rows[request_id]['request'])==payload,'immutable_row')
    require(rows[key]['request']==public['own_request'] and rows[key]['kind']=='planning_snapshot','own_request')
    admission=row['admission'];require(admission['owner']==owner and admission['accepted_at']==.11
        and row['owner_exit_physical_time']==.11,'owner_admission_clock')
    context=origin.supplied.initial_context(**public)
    require(type(context) is origin.supplied.SuppliedContext and context.audit_copy()==row['supplied_context'],'supplied_full_guard_replay')
    proposal=row['local_proposal'];require(proposal['status']=='fresh_local_component_proposal' and proposal['owner']==owner
        and proposal['at']==.11 and proposal['public_sha256']==decision['public_sha256']
        and proposal['native_request_submitted'] is False and proposal['dispatch_authorized'] is False
        and proposal['native_protection_certified'] is False,'proposal_scope')
    view=public['view'];tray=next(t for t in view['trays'] if t['tray_id']==('L' if owner=='A' else 'E'))
    require(tray['edge_to']<0 and tray['edge_from']<0,'uncommitted_local_tray')
    if owner=='A':
        target=[n for n in view['node_contracts'] if n['node']==2 and n['resource_owner']=='A']
        require(tray['mode']=='loaded' and tray['node']==0 and tray['business_bag_id']=='loaded'
            and tray['service_ready_known'] is True and type(tray['service_ready_at']) is float
            and math.isfinite(tray['service_ready_at']) and .11+.01<tray['service_ready_at']
            and len(target)==1 and target[0]['occupancy']<target[0]['capacity'],'A_current_guard')
        expected={'kind':'route','tray_id':'L','business_bag_id':'loaded','from':0,'next':2,
            'expected_generation':tray['generation'],'expected_traversal':tray['traversal_id'],'expiry':5.,'message_delay':.01}
    else:
        require(tray['mode']=='empty' and tray['node']==5 and not tray['business_bag_id'] and tray['available_at']<=.11,'B_current_guard')
        expected={'kind':'transfer','tray_id':'E','source':5,'destination':1,'earliest_departure':action['empty_departure'],
            'expiry':39.,'message_delay':.01}
    require(encoded(proposal['component'])==encoded(expected),'exact_local_proposal')
    return {'status':'saved_initial_seam_validated','collections':2,'getters':6,'supplied_data_only':True,
        'native_authority_reconstructed':False,'complete_request_100ms_certified':False}


def verify_saved(raw,specification,input_data):
    require(raw['schema']==SCHEMA and raw['specification']==specification and raw['input']==input_data,'raw_binding')
    require(list(raw['owners'])==['A','B'] and raw['model_predictions']==raw['physical_requests_submitted']==0
        and raw['native_protection_certified'] is False,'fixed_owner_scope')
    output={o:verify_owner(row,specification['vector']) for o,row in raw['owners'].items()}
    if 'calls' in raw:
        require(all(c['kind'] in ('demand','planning_snapshot') and c['retry'] is False for c in raw['calls'])
            and len(raw['calls'])<=4,'no_extra_or_physical_submission')
    known=sum(r['status']=='saved_initial_seam_validated' for r in output.values())
    if known==2:require(raw['physical_time']==.11 and len(raw['calls'])==4,'complete_seed_clock')
    return {'owners':output,'known_initial_domains':known,'unknown_initial_domains':2-known,
        'saved_data_guards_only':True,'model_predictions':0,'native_protection_certified':False}


def source_files():
    files=seam.source_files()
    for name,blob in image.source_closure(ROOT,[MODULE,__package__+'.launch_live_initial_six_seam',
        __package__+'.run_live_initial_six_seam_pure',TESTS[0][:-3].replace('/','.')]).items():
        require(name not in files or files[name]==blob,'source_conflict');files[name]=blob
    return dict(sorted(files.items()))


def source_gate():
    saved=read(SEAM/'plan.json');require(sha(SEAM/'plan.json')=='b99c0e61d308dec0ca803eb06cd058b54f8a1b8abef86f9ff5b5c550e427a8ff','frozen168plan')
    for name,digest in saved['source_sha256'].items():require(sha(ROOT/name)==sha(SEAM/saved['source_archive'][name])==digest,'frozen168source')
    old=read(OLD/'preregistered_protocol.json')
    for name,digest in old['source_sha256'].items():require(sha(name)==sha(OLD/old['source_archive'][name])==digest,'frozen93source')
    return old


def verify_plan(output,plan):
    require(plan['schema']==SCHEMA and plan['rows']==declaration() and plan['branch_order']==list(KEYS)
        and plan['initial_domain_order']==list(DOMAIN) and plan['hard_application_seconds']==LIMIT,'fixed_declared_domain')
    require(plan['source_proof']==recorded.source_proof(),'collector_proof')
    for name,digest in plan['source_sha256'].items():require(sha(name)==sha(output/plan['source_archive'][name])==digest,'source_identity')
    for key in KEYS:require(sha(output/'inputs'/(key+'.json'))==plan['input_file_sha256'][key],'input_identity')
    for ref in plan['references'].values():require(sha(ref['path'])==ref['sha256'],'reference_identity')
    for key in KEYS:
        require(read(output/'inputs'/(key+'.json'))==read(plan['references']['original_input_'+plan['rows'][key]['case']]['path']),
            'same_original_physical_input_and_notification_overlay')
    require(sha(plan['binary']['path'])==plan['binary']['sha256'] and sha(sys.executable)==plan['interpreter']['sha256'],'runtime_identity')


def loaded_source_pins(plan):
    relative={Path(name).relative_to(ROOT).as_posix():digest for name,digest in plan['source_sha256'].items()}
    return seam.prior.paired.loaded_sources(relative)


def evidence_pins(output,plan):
    expected={**plan['source_sha256']}
    expected.update({str(output/plan['source_archive'][p]):v for p,v in plan['source_sha256'].items()})
    expected.update({str(output/'inputs'/(k+'.json')):v for k,v in plan['input_file_sha256'].items()})
    for ref in (*plan['references'].values(),plan['binary'],plan['interpreter'],plan['native_contract_reference'],plan['semantic_gate_reference']):
        require(ref['path'] not in expected or expected[ref['path']]==ref['sha256'],'conflicting_evidence')
        expected[ref['path']]=ref['sha256']
    actual={p:sha(p) for p in expected};require(actual==expected,'evidence_hash');return actual


def prepare(output):
    old=source_gate();pure=read(PURE/'receipt.json');cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(EXPECTED_TESTS>0 and pure['status']=='passed' and pure['tests']==len(cases)==EXPECTED_TESTS
        and pure['source_changed']==[] and not any(n.tag in ('failure','error','skipped') for r in cases for n in r),'pure_gate')
    bounded=read(PURE/'bounded_parent_receipt.json');external=read(PURE/'external_application_wall.json')
    require(sha(PURE/'tests.xml')==pure['XML_sha256'] and bounded['status']=='passed'
        and bounded['receipt_sha256']==sha(PURE/'receipt.json') and external['exitcode']==0
        and 0<=external['external_application_seconds']<=120.,'pure_execution_bindings')
    files=source_files()
    for name,digest in pure['source_sha256'].items():require(sha(ROOT/name)==sha(PURE/'source'/name)==digest,'pure_source_pin')
    output.mkdir(parents=True,exist_ok=False);archives={};pins={}
    for name,blob in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
        pins[str(ROOT/name)]=hashlib.sha256(blob).hexdigest();archives[str(ROOT/name)]=str(path.relative_to(output))
    plan={'schema':SCHEMA,'rows':declaration(),'branch_order':list(KEYS),'initial_domain_order':list(DOMAIN),
        'source_sha256':pins,'source_archive':archives,'source_proof':recorded.source_proof(),'input_file_sha256':{},
        'binary':old['binary'],'interpreter':reference(sys.executable),'native_contract_reference':old['native_contract_reference'],
        'semantic_gate_reference':old['semantic_gate_reference'],'hard_application_seconds':LIMIT,
        'references':{label:reference(path) for label,path in {'frozen_seam168':SEAM/'plan.json',
            'frozen_unloading93':OLD/'preregistered_protocol.json','pure_receipt':PURE/'receipt.json','pure_XML':PURE/'tests.xml',
            'pure_external':PURE/'external_application_wall.json','pure_bounded':PURE/'bounded_parent_receipt.json',
            **{'original_input_'+case:OLD/'inputs'/(case+'/vector_16.json') for case in CASES}}.items()},
        'scope':'3 actual native sessions /6 independent owner domains /12 triplets; first collection plus immediate fresh local proposal.0 model/provider/physical submit.',
        'failure':'All6 domains retained. Endpoint returns/throws/export failures recorded in original order without extra calls or native session proxy. Saved JSON never mints authority.',
        'budget_basis':{'prior_nine_initial_delivery_whole_seconds_range':[18.,23.], 'fixed_shared_seconds':120.,
            'scope':'Boot/import/pins/full44+21 entry and exit/3 sessions/saved guards/all export share one owned120. No product100ms claim.'},
        'native_workers_maximum':1,'model_predictions':0,'physical_requests_submitted':0,'complete_request_100ms_certified':False}
    for key,spec in plan['rows'].items():
        input_data=fixture.native_scene(spec['case']);path=output/'inputs'/(key+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        require(input_data==read(OLD/'inputs'/(spec['case']+'/vector_16.json')),'unchanged_frozen_input')
        write(path,input_data);plan['input_file_sha256'][key]=sha(path)
    write(output/'plan.json',plan);verify_plan(output,plan)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':reference(output/'plan.json'),'sources':len(files),
        'initial_domains':6,'native_executions':0,'model_predictions':0,
        'execute_command':[sys.executable,'-m',__package__+'.launch_live_initial_six_seam','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def worker(output,expected):
    started=time.perf_counter();require(sha(output/'plan.json')==expected,'worker_plan');plan=read(output/'plan.json')
    rows={key:{'status':'unknown_unexecuted','owners':{o:owner_row(o) for o in ('A','B')}} for key in KEYS}
    write(output/'ledger.json',rows);verify_plan(output,plan);campaign_ref=reference(output/'plan.json')
    entry=evidence_pins(output,plan);write(output/'entry_pins.json',entry);write(output/'loaded_entry.json',loaded_source_pins(plan))
    accepted=fixture.run_admission.open_run(plan['native_contract_reference'],plan['semantic_gate_reference'],campaign_ref)
    try:
        native=fixture.bound.load_native(Path(plan['binary']['path']))
        for key in KEYS:
            row=rows[key];row['status']='unknown_in_progress';write(output/'ledger.json',rows)
            try:
                accepted.enter_branch(key,campaign_ref)
                spec=plan['rows'][key];input_data=read(output/'inputs'/(key+'.json'))
                raw=run_case(native,spec,input_data,plan['native_contract_reference'],accepted_run=accepted,branch_key=key)
                path=output/'raw'/(key+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(encoded(raw).encode(),compresslevel=1,mtime=0));row['raw']=reference(path)
                saved=json.loads(gzip.decompress(path.read_bytes()));row['saved_audit']=verify_saved(saved,spec,input_data)
                row['owners']={o:{'status':v['status']} for o,v in row['saved_audit']['owners'].items()}
                row['status']='saved_case_verified' if row['saved_audit']['known_initial_domains']==2 else 'unknown_case_domains'
            except Exception:row.update(status='unknown_branch_exception',exception=traceback.format_exc())
            finally:
                if accepted.active_for(key):
                    try:accepted.finish_branch(key)
                    except Exception:row.update(status='unknown_acceptance_failure',acceptance_error=traceback.format_exc())
                write(output/'ledger.json',rows)
    finally:
        closed=accepted.close();write(output/'run_acceptance.json',closed)
    verify_plan(output,plan)
    after=evidence_pins(output,plan);require(after==entry,'exit_evidence_changed')
    write(output/'exit_pins.json',after);write(output/'loaded_exit.json',loaded_source_pins(plan))
    known=sum(r.get('saved_audit',{}).get('known_initial_domains',0) for r in rows.values()
        if r['status'] in ('saved_case_verified','unknown_case_domains'))
    valid=closed['status']=='closed_run_acceptance_passed'
    write(output/'receipt.json',{'schema':SCHEMA,'status':'six_actual_initial_seams_validated' if valid and known==6 else 'completed_unknowns_preserved',
        'initial_domains':6,'known_initial_domains':known if valid else 0,'unknown_initial_domains':6-known if valid else 6,
        'ledger':reference(output/'ledger.json'),'run_acceptance':reference(output/'run_acceptance.json'),
        'run_acceptance_status':closed['status'],'source_changed':[],'plan':reference(output/'plan.json'),
        'entry_pins':reference(output/'entry_pins.json'),'exit_pins':reference(output/'exit_pins.json'),
        'loaded_entry':reference(output/'loaded_entry.json'),'loaded_exit':reference(output/'loaded_exit.json'),
        'worker_seconds':time.perf_counter()-started,'model_predictions':0,'physical_requests_submitted':0,
        'native_protection_certified':False,'complete_request_100ms_certified':False})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    prepare(args.output.resolve());return 0


if __name__=='__main__':raise SystemExit(main())
