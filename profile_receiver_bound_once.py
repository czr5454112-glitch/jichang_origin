"""One fixed diagnostic pass over saved-input A/B; no tuning or native."""
import time
BOOT=time.perf_counter()
from pathlib import Path
import argparse
import cProfile
import gc
import gzip
import hashlib
import json
import pstats
import sys
import traceback
from scripts.experiments.g31_ics_circulation import bounded_windows_job

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
ACCEPTED=OUT/'preference_receiver_bound_pair_001'
EXPECTED='745c9e64171e11f803537e3a577e6ee3c5e1af8c23aaf4bd433cb361912ad5e7'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def read(p):return json.loads(Path(p).read_bytes())
def worker(output,admission):
    if sys.stdin.readline().strip()!=admission:raise ValueError('job_admission')
    from scripts.experiments.g31_ics_circulation import measure_preference_receiver_bound_context as measurement
    if sha(ACCEPTED/'preregistered_protocol.json')!=EXPECTED:raise ValueError('wrong_accepted_source')
    oldplan=read(ACCEPTED/'preregistered_protocol.json');before={str(ROOT/name):digest for name,digest in oldplan['source_sha256'].items()}
    before[str(Path(__file__).resolve())]=admission
    for name,digest in before.items():
        if sha(name)!=digest:raise ValueError('source_changed_before')
    for name,digest in oldplan['source_sha256'].items():
        if sha(ACCEPTED/'source'/name)!=digest:raise ValueError('archive_changed')
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name:
            path=Path(name).resolve()
            if path.suffix=='.py' and path.is_relative_to(ROOT) and str(path) not in before:
                raise ValueError('unexpected_runtime_module:'+str(path))
    evidence={str(ACCEPTED/name):sha(ACCEPTED/name) for name in ('preregistered_protocol.json','ledger.json','receipt.json','external_process.json','external_application_wall.json')}
    ledger=read(ACCEPTED/'ledger.json')
    for case in oldplan['cases']:
        p=ACCEPTED/case['input']
        if sha(p)!=case['input_sha256']:raise ValueError('input_pin')
        evidence[str(p)]=sha(p)
        for sample in (0,1):
            row=next(r for r in ledger if r['case']==case['case'] and r['sample']==sample)
            p=ACCEPTED/row['raw']
            if sha(p)!=row['raw_sha256']:raise ValueError('oracle_pin')
            evidence[str(p)]=sha(p)
    plan={'status':'preregistered_before_fixed_pass','cases':[c['case'] for c in oldplan['cases']],
        'order':['A','B'],'passes':1,'batches':12,'queries_per_batch':32,'baseline_per_batch':1,
        'source_sha256':before,'accepted_evidence_sha256':evidence,'source_plan_sha256':EXPECTED,
        'profile_scope':'Full existing batch: context, full baseline,32queries,encoding; readback and profiling export in full job wall.',
        'limits':'Profiler and callback perturbation; no isolated or per-business timing claim. No GC disabling/collection/subtraction or parameter changes.',
        'owned_job_seconds':120,'native_calls':0}
    write(output/'preregistered_protocol.json',plan)
    (output/'profile_source.py').write_bytes(Path(__file__).read_bytes())
    samples=[];gcrows=[];active=None;gcstart=None
    def callback(phase,info):
        nonlocal gcstart
        stamp=time.perf_counter_ns()
        if phase=='start':gcstart=(stamp,active,info['generation'])
        elif phase=='stop' and gcstart is not None:
            gcrows.append({'start_ns':gcstart[0],'end_ns':stamp,'batch_at_start':gcstart[1],
                'batch_at_stop':active,'generation':gcstart[2],'collected':info['collected'],'uncollectable':info['uncollectable']});gcstart=None
    gc.callbacks.append(callback)
    try:
        for case in oldplan['cases']:
            bundle=read(ACCEPTED/case['input'])
            for arm,sample in (('A',0),('B',1)):
                identity=case['case']+'.'+arm;active=identity;prof=cProfile.Profile();start=time.perf_counter_ns();cpu=time.process_time_ns()
                try:
                    prof.enable();value=measurement.batch(bundle,arm)
                finally:
                    prof.disable();end=time.perf_counter_ns();cpuend=time.process_time_ns();active=None
                old=gzip.decompress((ACCEPTED/f"{case['case']}.{sample}.{arm}.json.gz").read_bytes())
                if value.encode('utf8')!=old:raise ValueError('exact_saved_output_mismatch:'+identity)
                prof.dump_stats(str(output/(identity+'.pstats')))
                stats=pstats.Stats(prof)
                functions=[{'file':key[0],'line':key[1],'name':key[2],'primitive_calls':v[0],'calls':v[1],
                    'exclusive_seconds':v[2],'cumulative_seconds':v[3]} for key,v in stats.stats.items()]
                functions.sort(key=lambda r:r['cumulative_seconds'],reverse=True)
                write(output/(identity+'.functions.json'),functions)
                samples.append({'case':case['case'],'arm':arm,'start_ns':start,'end_ns':end,'wall_ns':end-start,
                    'cpu_ns':cpuend-cpu,'exact_saved_output':True,'encoded_sha256':hashlib.sha256(old).hexdigest()})
                write(output/'ledger.json',samples);write(output/'gc.json',gcrows)
    finally:gc.callbacks.remove(callback)
    changed=[p for p,d in before.items() if sha(p)!=d];input_changed=[p for p,d in evidence.items() if sha(p)!=d]
    if changed or input_changed or len(samples)!=12:raise ValueError('incomplete_or_changed_profile')
    write(output/'receipt.json',{'status':'fixed12_profile_completed_exact_outputs','source_changed':changed,'input_changed':input_changed,
        'samples':samples,'gc':gcrows,'source_plan_sha256':EXPECTED,'native_calls':0,'new_projection_batches':12,
        'limits':plan['limits'],'complete_100ms_certified':False})


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true');p.add_argument('--admission');a=p.parse_args();out=a.output.resolve()
    if a.worker:
        try:worker(out,a.admission)
        except BaseException as error:
            write(out/'failure.json',{'status':'unknown_profile_error','error':repr(error),'traceback':traceback.format_exc()});raise
        return 0
    out.mkdir(parents=True,exist_ok=False);admission=sha(__file__)
    command=[sys.executable,'-m','profile_receiver_bound_once','--worker','--output',str(out),'--admission',admission]
    receipt={'status':'unknown_before_dispatch','command':command,'source_sha256':admission,'owned_job_seconds':120,'native_calls':0}
    try:
        remaining=120-(time.perf_counter()-BOOT)
        if remaining<=0:raise TimeoutError('setup_budget')
        with (out/'stdout.log').open('x',encoding='utf8') as stdout,(out/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=admission,cwd=ROOT)
        receipt.update(process=process,status='worker_exited_zero' if process['status']=='exited' and process['exitcode']==0 else 'failed_or_unknown')
    except BaseException as error:receipt.update(status='unknown_launcher_error',error=repr(error))
    finally:
        receipt.update(parent_post_interpreter_wall_seconds=time.perf_counter()-BOOT,evidence_sha256={str(p.relative_to(out)):sha(p) for p in out.iterdir() if p.is_file()})
        write(out/'external_process.json',receipt)
    print(json.dumps({'status':receipt['status'],'wall_seconds':receipt['parent_post_interpreter_wall_seconds']}))
    return 0 if receipt['status']=='worker_exited_zero' else 1
if __name__=='__main__':raise SystemExit(main())
