"""One180s owned process-tree saved audit, no native/prediction workers."""
import argparse,hashlib,json,sys,time,traceback,uuid
from pathlib import Path
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
RUN=OUT/'live_obligation_historical_native_prepare_001'
DEST=OUT/'live_obligation_historical_saved_audit_001'
HARD=180.
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(v,reason):
    if not v:raise ValueError('saved_audit_launcher:'+reason)

def prepare():
    DEST.mkdir(exist_ok=False)
    expected={str(ROOT/'scripts/experiments/g31_ics_circulation/audit_live_obligation_historical.py'):'14361464b301ad89cf2a18632804f802b1d4578e0d5bcf49b239274cf02ba8a6',
        str(ROOT/'tests/test_g31_circulation_historical_saved_audit.py'):'69db77f2f38235193c59ad1b140fd1e75fa489c9e1df5dd24229a8d9779785b8',
        str(OUT/'historical_saved_audit_pure_001.xml'):'9ec1fd6dbdffab541dc106eb93a4bdc1943701e3da1e772539078cbe74f7ddf3',
        str(RUN/'external_application_wall.json'):'c56a630b1fa7ad34f0799967ed3a6e28260b5767f2cb41c0b292c95c2d83a0f4',
        str(RUN/'preregistered_protocol.json'):'bc3bc04e8c81e496120cfd7760e83c6274bd7e92f287fe68ba8d1e206737fcd5'}
    plan=read(RUN/'preregistered_protocol.json')
    for p,d in plan['source_sha256'].items():expected[p]=d;expected[str(RUN/plan['source_archive'][p])]=d
    for name in ('receipt.json','branch_ledger.json','run_acceptance.json','external_process.json','prepare_receipt.json'):
        expected[str(RUN/name)]=sha(RUN/name)
    for p in (Path(__file__).resolve(),Path(bounded_windows_job.__file__).resolve(),
        ROOT/'scripts/experiments/g31_ics_circulation/audit_live_obligation_recollection_v2.py',
        DEST.parent/'invoke_historical_saved_audit_001_measured.ps1'):
        expected[str(p)]=sha(p)
    write(DEST/'plan.json',{'schema':'g31.historical_saved_audit_launch.v1','hard_timeout_seconds':HARD,
        'pins':expected,'run':str(RUN),'native_executions':0,'model_evaluations':0,
        'scope':'Child includes all entry pins, imports, complete saved96 audit and exit pins/output; outer application wall recorded separately.'})

def launch():
    prepare();token=uuid.uuid4().hex;started=time.perf_counter()
    planhash=sha(DEST/'plan.json')
    command=[sys.executable,'-m','scripts.experiments.g31_ics_circulation.launch_historical_saved_audit',
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
    suite=ET.parse(OUT/'historical_saved_audit_pure_001.xml').getroot().findall('testsuite')
    require(len(suite)==1 and int(suite[0].get('tests'))==16
        and all(int(suite[0].get(k))==0 for k in ('errors','failures','skipped')),'16_pure_gate')
    from . import audit_live_obligation_historical as audit
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
    require(not result['independent_replay_errors'],'saved_replay_failures_retained')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--admission');p.add_argument('--plan-sha256')
    args=p.parse_args()
    if args.worker:
        require(args.admission and sys.stdin.readline().strip()==args.admission,'owned_job_admission')
        try:worker(args.plan_sha256)
        except Exception:
            write(DEST/'failure.json',{'status':'failed','error':traceback.format_exc(),'native_executions':0,'model_evaluations':0});raise
    else:launch()
