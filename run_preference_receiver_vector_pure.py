"""120-second owned pure-test worker, preserving full external wall."""
import time
BOOT=time.perf_counter()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from scripts.experiments.g31_ics_circulation import bounded_windows_job

ROOT=Path(__file__).resolve().parent
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def pins():
    paths={Path(__file__).resolve(),ROOT/'tests/test_g31_circulation_receiver_vector_context.py',
        ROOT/'tests/test_g31_circulation_measure_receiver_vector_context.py'}
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            path=Path(file).resolve()
            if path.suffix=='.py' and path.is_relative_to(ROOT): paths.add(path)
    return {str(path.relative_to(ROOT)):sha(path) for path in sorted(paths)}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args(); output=args.output.resolve()
    if args.worker:
        if sys.stdin.readline().rstrip('\n')!=args.admission or sha(__file__)!=args.admission: raise ValueError('job_admission')
        output.mkdir(parents=True,exist_ok=False)
        sys.path.insert(0,str(ROOT/'tests'))
        import test_g31_circulation_receiver_vector_context
        import test_g31_circulation_measure_receiver_vector_context
        import pytest
        before=pins()
        evidence=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_static_context_pair_001/worker'
        inputs={str(evidence/name):sha(evidence/name) for name in ('supplied_inputs.json','plan.json')}
        comparison=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_receiver_bound_pair_001'
        selected=['preregistered_protocol.json','ledger.json','external_process.json','receipt.json','external_application_wall.json']
        selected += [f'block{b}_load{r}.{suffix}' for b in range(2) for r in range(3) for suffix in ('input.json','1.B.json.gz')]
        inputs.update({str(comparison/name):sha(comparison/name) for name in selected})
        for name in before:
            target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
        write(output/'plan.json',{'status':'pure_tests_before_execution','source_sha256':before,'input_sha256':inputs,
            'native_executions':0,'proof_scope':'Only immutable five-time certificate reference replaces full-baseline copies; all full/partial outputs exact frozen receiver-bound context, no performance claim.'})
        code=pytest.main(['-q','tests/test_g31_circulation_receiver_vector_context.py',
            'tests/test_g31_circulation_measure_receiver_vector_context.py',
            '--basetemp',str(output/'tmp'),'--junitxml',str(output/'tests.xml')])
        changed=[name for name,digest in before.items() if sha(ROOT/name)!=digest]
        input_changed=[name for name,digest in inputs.items() if sha(name)!=digest]
        write(output/'report.json',{'status':'passed_pure_cut_guard_tests' if code==0 and not changed and not input_changed else 'failed_or_unknown',
            'pytest_exit_code':code,'source_changed':changed,'input_changed':input_changed,'native_executions':0,
            'six_case_cut_rows':test_g31_circulation_receiver_vector_context.ROWS,
            'method_scope':'Same32 predictions byte-exact; no search policy change.'})
        return int(code) if code else int(bool(changed or input_changed))
    output.mkdir(parents=True,exist_ok=False); admission=sha(__file__)
    command=[sys.executable,'-m','run_preference_receiver_vector_pure','--output',str(output/'worker'),'--worker','--admission',admission]
    receipt={'status':'unknown_before_dispatch','command':command,'launcher_sha256':admission,'owned_job_seconds':120.,'native_executions':0}
    try:
        remaining=120.-(time.perf_counter()-BOOT)
        if remaining<=0: raise TimeoutError('setup_budget')
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=admission,cwd=ROOT)
        receipt.update(process=process,status='child_passed' if process['status']=='exited' and process['exitcode']==0 else 'failed_or_unknown')
    except BaseException as error: receipt.update(status='unknown_launcher_error',error=repr(error))
    finally:
        receipt['evidence_sha256']={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}
        receipt['dispatch_through_evidence_hash_wall_seconds']=time.perf_counter()-BOOT
        receipt['outer_startup_and_final_export']='External PowerShell Stopwatch retains complete launch-to-exit; internal BOOT omits interpreter startup.'
        write(output/'receipt.json',receipt)
    print(json.dumps({'status':receipt['status'],'wall_seconds':receipt['dispatch_through_evidence_hash_wall_seconds']}))
    return 0 if receipt['status']=='child_passed' else 1
if __name__=='__main__':raise SystemExit(main())

