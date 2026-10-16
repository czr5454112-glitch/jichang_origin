"""One180s owned process-tree saved audit, no native/prediction workers."""
import argparse,hashlib,json,sys,time,traceback,uuid
from pathlib import Path
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
RUN=OUT/'live_obligation_unloading_native_prepare_001'
DEST=OUT/'live_obligation_unloading_saved_audit_001'
HARD=180.
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(v,reason):
    if not v:raise ValueError('saved_audit_launcher:'+reason)

def prepare(expected_external):
    require(type(expected_external) is str and len(expected_external)==64 and all(ch in '0123456789abcdef' for ch in expected_external),'explicit_expected_external_sha256')
    require(sha(RUN/'external_application_wall.json')==expected_external,'closed_external_identity')
    actual=read(RUN/'external_process.json');producer=read(RUN/'receipt.json')
    require(actual['status']=='exited' and actual['exitcode']==0 and producer['status'] in ('complete96_assessed','completed_with_unknowns'),'closed_actual_run_required')
    DEST.mkdir(exist_ok=False)
    expected={str(ROOT/'scripts/experiments/g31_ics_circulation/audit_live_obligation_unloading.py'):'e12186e3646330ec9d52f233e30076b220fb9c8b811586641d1f6c34b0eb6681',
        str(ROOT/'tests/test_g31_circulation_unloading_saved_audit.py'):'ec3ae5382e44cd6ae2d6792660332b7f0509d20c9bb80933f35bb74a65027c69',
        str(OUT/'unloading_saved_audit_pure_002.xml'):'a87bc1111302336ddb864f091ccbf66f9d1eda2663b6f44418d8296a75fd7e38',
        str(RUN/'external_application_wall.json'):expected_external,
        str(RUN/'preregistered_protocol.json'):'6c82cc7ad10aae82f2f9d9059899dca20753e4bf0f5a78885d2e53e505199ecd'}
    plan=read(RUN/'preregistered_protocol.json')
    for p,d in plan['source_sha256'].items():expected[p]=d;expected[str(RUN/plan['source_archive'][p])]=d
    for name in ('receipt.json','branch_ledger.json','run_acceptance.json','external_process.json','prepare_receipt.json'):
        expected[str(RUN/name)]=sha(RUN/name)
    for p in (Path(__file__).resolve(),Path(bounded_windows_job.__file__).resolve(),
        ROOT/'scripts/experiments/g31_ics_circulation/audit_live_obligation_recollection_v2.py',
        ROOT/'scripts/experiments/g31_ics_circulation/audit_live_obligation_historical.py',
        DEST.parent/'invoke_unloading_saved_audit_001_measured.ps1'):
        expected[str(p)]=sha(p)
    write(DEST/'plan.json',{'schema':'g31.unloading_saved_audit_launch.v1','hard_timeout_seconds':HARD,
        'pins':expected,'run':str(RUN),'native_executions':0,'model_evaluations':0,
        'scope':'Child includes all entry pins, imports, complete saved96 audit and exit pins/output; outer application wall recorded separately.'})

def launch(expected_external):
    prepare(expected_external);token=uuid.uuid4().hex;started=time.perf_counter()
    planhash=sha(DEST/'plan.json')
    command=[sys.executable,'-m','scripts.experiments.g31_ics_circulation.launch_unloading_saved_audit',
             '--worker','--admission',token,'--plan-sha256',planhash]
    with (DEST/'stdout.log').open('w') as stdout,(DEST/'stderr.log').open('w') as stderr:
        result=bounded_windows_job.run(command,timeout=HARD,stdout=stdout,stderr=stderr,
            admission=token,cwd=str(ROOT))
    write(DEST/'external_process.json',{**result,'command':command,'plan_sha256':planhash,
        'parent_post_prepare_wall_seconds':time.perf_counter()-started,'native_executions':0,'model_evaluations':0})
    if result['status']!='exited' or result['exitcode']!=0 or not (DEST/'receipt.json').exists():raise SystemExit(1)

def worker(expected_plan):
    started=time.perf_counter();require(sha(DEST/'plan.json')==expected_plan,'plan_identity')
    plan=read(DEST/'plan.json');entry={p:sha(p) for p in plan['pins']}
    write(DEST/'entry_pins.json',entry);require(entry==plan['pins'],'entry_pins')
    import xml.etree.ElementTree as ET
    suite=ET.parse(OUT/'unloading_saved_audit_pure_002.xml').getroot().findall('testsuite')
    require(len(suite)==1 and int(suite[0].get('tests'))==22
        and all(int(suite[0].get(k))==0 for k in ('errors','failures','skipped')),'22_pure_gate')
    from . import audit_live_obligation_unloading as audit
    result=audit.audit()
    exitpins={p:sha(p) for p in plan['pins']};write(DEST/'exit_pins.json',exitpins)
    require(exitpins==entry,'exit_pins')
    write(audit.TARGET,result)
    receipt={'status':result['status'],'report':{'path':str(audit.TARGET),'sha256':sha(audit.TARGET)},
        'plan_sha256':expected_plan,'entry_pins_sha256':sha(DEST/'entry_pins.json'),
        'exit_pins_sha256':sha(DEST/'exit_pins.json'),'pin_count':len(entry),'source_changed':[],
        'worker_wall_seconds':time.perf_counter()-started,'counts':result['status_counts'],
        'independent_replay_errors':len(result['independent_replay_errors']),'native_executions':0,'model_evaluations':0}
    write(DEST/'receipt.json',receipt);print(json.dumps(receipt))
    summary=audit.compact_summary(result)
    summary['independent_report']={'path':str(audit.TARGET),'sha256':sha(audit.TARGET)}
    summary['bounded_audit_receipt']={'path':str(DEST/'receipt.json'),'sha256':sha(DEST/'receipt.json')}
    write(DEST/'terminal_summary.json',summary)
    require(not result['independent_replay_errors'],'saved_replay_failures_retained')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--admission');p.add_argument('--plan-sha256');p.add_argument('--expected-external-sha256')
    args=p.parse_args()
    if args.worker:
        require(args.admission and sys.stdin.readline().strip()==args.admission,'owned_job_admission')
        try:worker(args.plan_sha256)
        except Exception:
            write(DEST/'failure.json',{'status':'failed','error':traceback.format_exc(),'native_executions':0,'model_evaluations':0});raise
    else:launch(args.expected_external_sha256)
