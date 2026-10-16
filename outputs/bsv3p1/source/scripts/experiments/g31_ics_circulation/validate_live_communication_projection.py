"""Preregistered, bounded saved-data conformance; zero native executions.

The predictor receives only each owner's initial public endpoint evidence and
the declared candidate. Actual future endpoints/completions are read solely by
this verifier after prediction. All96 are retrospective regression targets.
"""
from __future__ import annotations
import argparse,copy,gzip,hashlib,json,math,sys,time,traceback,uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from . import bounded_windows_job
from . import live_obligation_delivered_context as context
from . import public_live_obligation_communication_projection as model

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
ACTUAL=OUT/'live_obligation_unloading_native_prepare_001'
CASES=('mechanism','no_overlap','insufficient_advance')
ORDER=[case+f'/vector_{i:02d}' for case in CASES for i in range(32)]
HARD=180.
EXPECTED_ACTUAL_RECEIPT='34a6d6d6d0b9008a9fbea2b0f8050d6afc2f69c3594dd22505f1c730ec859f3c'
EXPECTED_ACTUAL_PLAN='6c82cc7ad10aae82f2f9d9059899dca20753e4bf0f5a78885d2e53e505199ecd'
EXPECTED_ACTUAL_LEDGER='e8537e153dd0d1b402acfd63f1c6254b4597e23f7b8a442a623be0d4f6c6a6e1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(ok,why):
    if not ok:raise ValueError('communication_conformance:'+why)
def reference(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}

def pure_gate():
    suites=ET.parse(OUT/'live_communication_pure_004.xml').getroot().findall('testsuite')
    require(len(suites)==1 and int(suites[0].get('tests'))==38
        and all(int(suites[0].get(k))==0 for k in ('failures','errors','skipped')),'38_pure_gate')

def source_paths():
    return sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)})

def public_initial(raw,owner):
    ep=raw['initial_owners'][owner]['raw_endpoints'];key=ep['command']['request_id']
    calls=[c for c in raw['calls'] if c['at']<=.11 and c['request']['owner_id']==owner
           and c['request']['request_id']==key and c['retry'] is False]
    require(len(calls)==1,'unique_initial_immutable_publication')
    # No raw specification, continuation, result, future calls or target
    # outcome is copied into this input envelope.
    return {**copy.deepcopy(ep),'own_request':copy.deepcopy(calls[0]['request'])}

def future_context(raw,owner,entry):
    p=entry['collection'];ep=entry['information']['raw_endpoints']
    return context.later_context(**ep,retained=raw['retained_ledgers'][owner],
        own_calls=[c for c in raw['calls'][:entry['predecision_call_prefix_count']] if c['request']['owner_id']==owner],
        phase=entry['phase'],own_request_id=p['request_id'],peer_message_id=p['peer_message'],
        collection_started_at=p['at'],policy_quiet_since=p['policy_quiet_since'])

def exact_completion(predicted,actual):
    jobs={'loaded','receiver','reuse1','reuse2','blocker'}
    valid=lambda d:type(d) is dict and set(d)==jobs and all(type(t) is float and math.isfinite(t) and t>=0 for t in d.values())
    if not(valid(predicted) and valid(actual)):return False
    return all(type(predicted[k]) is type(actual[k]) and predicted[k].hex()==actual[k].hex() for k in jobs)

def actual_collection_rows(raw):
    result=[]
    for owner in ('A','B'):
        for row in raw['collection_attempts'][owner]:
            info=row['information'];p=row['collection']
            result.append({'at':row['at'],'owner':owner,'phase':row['phase'],'recollection_index':p['recollection_index'],
                'collection_started_at':p['at'],'known':info.get('native_delivery_verified') is True,
                'reasons':info.get('reasons',[]),'bundle_reasons':info.get('bundle',{}).get('reasons',[]),
                'retry_status':row['retry_admission']['status'],'disposition':row['disposition']})
    return sorted(result,key=lambda r:(r['at'],r['owner'],r['recollection_index']))

def projected_collection_rows(prediction):
    return sorted([{'at':r['at'],'owner':r['owner'],'phase':r['phase'],'recollection_index':r['recollection_index'],
        'collection_started_at':r['collection_started_at'],'known':r['information_status']=='conditional_validated_later_v3_data',
        'reasons':r['reasons'],'bundle_reasons':r['bundle_reasons'],'retry_status':r['retry_admission']['status'],
        'disposition':r['disposition']} for r in prediction.get('projected_collections',[])],
        key=lambda r:(r['at'],r['owner'],r['recollection_index']))

def prepare(output):
    output.mkdir(exist_ok=False)
    pure_gate()
    require(sha(ACTUAL/'receipt.json')==EXPECTED_ACTUAL_RECEIPT and sha(ACTUAL/'preregistered_protocol.json')==EXPECTED_ACTUAL_PLAN
        and sha(ACTUAL/'branch_ledger.json')==EXPECTED_ACTUAL_LEDGER,'closed_actual_identities')
    actual_plan=read(ACTUAL/'preregistered_protocol.json');ledger=read(ACTUAL/'branch_ledger.json')
    require(read(ACTUAL/'receipt.json')['status']=='complete96_assessed' and list(ledger)==ORDER,'complete_actual_order')
    actions=model.physics.previous.actions();require(len(actions)==32,'candidate_count')
    pins={};archives={}
    for p in source_paths():
        d=sha(p);pins[str(p)]=d;rel=Path('source')/p.relative_to(ROOT)
        (output/rel).parent.mkdir(parents=True,exist_ok=True);(output/rel).write_bytes(p.read_bytes());archives[str(p)]=str(rel)
    for name in ('test_g31_circulation_live_delivered_context.py','test_g31_circulation_live_communication_projection.py',
                 'test_g31_circulation_live_communication_conformance.py'):
        p=ROOT/'tests'/name;pins[str(p)]=sha(p);rel=Path('source')/p.relative_to(ROOT)
        (output/rel).parent.mkdir(parents=True,exist_ok=True);(output/rel).write_bytes(p.read_bytes());archives[str(p)]=str(rel)
    fixed={str(ACTUAL/name):sha(ACTUAL/name) for name in ('receipt.json','preregistered_protocol.json','branch_ledger.json',
        'external_application_wall.json','run_acceptance.json')}
    fixed[str(OUT/'live_obligation_unloading_native_saved_review_001.json')]=sha(OUT/'live_obligation_unloading_native_saved_review_001.json')
    fixed[str(OUT/'live_communication_pure_004.xml')]=sha(OUT/'live_communication_pure_004.xml')
    fixed[str(OUT/'live_communication_dependency_boundary_001.json')]=sha(OUT/'live_communication_dependency_boundary_001.json')
    for p,d in actual_plan['source_sha256'].items():
        require(sha(p)==d and sha(ACTUAL/actual_plan['source_archive'][p])==d,'actual93_sources_immutable')
        fixed[str(ACTUAL/actual_plan['source_archive'][p])]=d
    rows={k:{'action':copy.deepcopy(actions[i%32]),'actual_raw':ledger[k]['raw_artifact'],'status':'unknown_unexecuted'}
          for i,k in enumerate(ORDER)}
    plan={'schema':'g31.live_communication_conformance.v1','hard_timeout_seconds':HARD,'order':ORDER,'rows':rows,
        'source_sha256':pins,'source_archive':archives,'fixed_evidence_sha256':fixed,'native_executions':0,
        'maximum_model_evaluations':96,'initial_owner_data_checks':192,'expected_actual_collection_count':226,
        'rules':['All3 fixed cases, all32 actions in frozen order; no extra grid and no retuning.',
            'Prediction input contains one owner initial endpoints and its immutable initial publication only.',
            'Future actual records are comparison targets only, not inputs to simulated future messages.',
            'Current fixture initial underlying tray availability0 is a declared finite-domain assumption; loading observation is a typed future bound.',
            'Exact scalar types/float hex endpoints and ordered information attempts; no business epsilon.',
            'All missing/censored/unexecuted/unknown rows retained, conformance requires all96.',
            'Retrospective semantic debugging/regression targets, not statistically held-out validation.',
            'Entry pins/import/setup/all96 prediction/actual data replay/output/exit pins within one180s child JobObject.',
            'No online capability, execution, physical protection, 100ms or algorithm novelty is certified.']}
    write(output/'plan.json',plan);write(output/'rows.json',rows)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':reference(output/'plan.json'),
        'source_count':len(pins),'native_executions':0,'model_evaluations':0})
    return plan

def worker(output,expected):
    started=time.perf_counter();require(sha(output/'plan.json')==expected,'plan_sha')
    plan=read(output/'plan.json');require(plan['order']==ORDER and list(plan['rows'])==ORDER and len(ORDER)==96,'ordered_denominator')
    pins={**plan['source_sha256'],**plan['fixed_evidence_sha256']}
    for p,d in plan['source_sha256'].items():pins[str(output/plan['source_archive'][p])]=d
    entry={p:sha(p) for p in pins};write(output/'entry_pins.json',entry);require(entry==pins,'entry_pins')
    pure_gate()
    rows=read(output/'rows.json');predictions=0
    for index,key in enumerate(ORDER):
        row=rows[key];p=plan['rows'][key]['actual_raw'];row['execution_index']=index
        try:
            require(sha(p['path'])==p['sha256'],'actual_raw_sha')
            raw=json.loads(gzip.decompress(Path(p['path']).read_bytes()))
            action=plan['rows'][key]['action'];require(action==model.physics.previous.actions()[index%32],'fixed_action')
            contexts={o:context.initial_context(**public_initial(raw,o)) for o in ('A','B')}
            require(all(type(v) is context.SuppliedContext for v in contexts.values()),'actual_initial_context')
            # Each owner's physical sufficient facts must agree; this offline
            # check does not establish online atomic decision agreement.
            facts={o:context.initial_projection_bundle(v) for o,v in contexts.items()}
            require(all(context.encoded({'value':facts['A'][f]})==context.encoded({'value':facts['B'][f]})
                for f in ('jobs','trays','contract','now')),'independent_owner_initial_facts')
            start=time.perf_counter();prediction=model.predict(contexts['A'],action);predictions+=1
            elapsed=time.perf_counter()-start
            # Future actual data is used only below this line as a target.
            actual=raw['summary']['completion'];known_checks=[]
            for owner in ('A','B'):
                for attempt in raw['collection_attempts'][owner]:
                    supplied=future_context(raw,owner,attempt)
                    known=type(supplied) is context.SuppliedContext
                    known_checks.append({'owner':owner,'at':attempt['at'],'known':known,
                        'matches_saved':known==(attempt['information'].get('native_delivery_verified') is True)})
            projected=projected_collection_rows(prediction);actual_rows=actual_collection_rows(raw)
            path=output/key;path.parent.mkdir(parents=True,exist_ok=True);path=path.with_suffix('.json.gz')
            path.write_bytes(gzip.compress(json.dumps(prediction,allow_nan=False).encode(),compresslevel=1,mtime=0))
            exact=exact_completion(prediction.get('completion'),actual)
            chronology=context.encoded({'rows':projected})==context.encoded({'rows':actual_rows})
            row.update(status='exact_conformance' if exact and chronology and prediction['status']=='conditional_prediction'
                and all(c['matches_saved'] for c in known_checks) else 'unknown_conformance_difference',
                predictor_status=prediction['status'],prediction=reference(path),model_wall_seconds=elapsed,
                five_endpoints_exact=exact,predicted_completion=prediction.get('completion'),actual_completion=actual,
                ordered_information_attempts_exact=chronology,actual_collection_contexts=known_checks,
                projected_collection_rows=projected,actual_collection_rows=actual_rows,
                errors=prediction.get('reasons',[]))
        except Exception:row.update(status='unknown_error',error=traceback.format_exc())
        write(output/'rows.json',rows)
    exitpins={p:sha(p) for p in pins};write(output/'exit_pins.json',exitpins)
    require(entry==exitpins,'source_or_evidence_drift')
    counts={status:sum(r['status']==status for r in rows.values()) for status in sorted({r['status'] for r in rows.values()})}
    actual_checks=[c for row in rows.values() for c in row.get('actual_collection_contexts',[])]
    complete_target_contexts=len(actual_checks)==226 and sum(c['known'] for c in actual_checks)==192 and all(c['matches_saved'] for c in actual_checks)
    receipt={'schema':plan['schema'],'status':'exact_all96_conformance' if counts.get('exact_conformance')==96 and complete_target_contexts
        else 'completed_conformance_failed_unknowns_preserved','counts':counts,'model_evaluations':predictions,
        'actual_collection_data_checks':len(actual_checks),'actual_known_collection_data':sum(c['known'] for c in actual_checks),
        'complete_actual_collection_conformance':complete_target_contexts,
        'native_executions':0,'plan':reference(output/'plan.json'),'rows':reference(output/'rows.json'),
        'source_changed':[],'entry_pins':reference(output/'entry_pins.json'),'exit_pins':reference(output/'exit_pins.json'),
        'worker_wall_seconds':time.perf_counter()-started,'statistically_held_out':False,
        'used_for_retrospective_semantic_conformance':True,'online_executable':False,'native_protection_certified':False}
    write(output/'receipt.json',receipt);print(json.dumps(receipt))

def launch(output,expected):
    token=uuid.uuid4().hex;command=[sys.executable,'-m',__spec__.name,'--worker','--output',str(output),
        '--expected-plan',expected,'--admission',token]
    with (output/'stdout.log').open('w') as stdout,(output/'stderr.log').open('w') as stderr:
        result=bounded_windows_job.run(command,timeout=HARD,stdout=stdout,stderr=stderr,admission=token,cwd=str(ROOT))
    write(output/'external_process.json',{**result,'command':command,'native_executions':0})
    if result['status']!='exited' or result['exitcode']!=0:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--admission');p.add_argument('--expected-plan')
    a=p.parse_args()
    if a.worker:
        require(a.admission and sys.stdin.readline().strip()==a.admission,'owned_job_admission');worker(a.output,a.expected_plan)
    elif a.prepare:prepare(a.output)
    elif a.execute:require(sha(a.output/'plan.json')==a.expected_plan,'launch_plan_identity');launch(a.output,a.expected_plan)
    else:raise SystemExit('explicit prepare or execute required')
