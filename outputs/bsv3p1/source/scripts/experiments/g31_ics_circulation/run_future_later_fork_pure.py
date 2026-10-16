"""Owned120 focused synthetic cuts only; no real model, native or C load."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
MODULE=__package__+'.run_future_later_fork_pure'
REFERENCE=OUT/'conditional_continuation_six_prepare_001/plan.json'
REFERENCE_SHA='dd91512a60cc6ef336842ab93a5341a47ebd90276470116b24e8cb4e90917c56'
TESTS=['tests/test_g31_circulation_future_later_fork.py',
       'tests/test_g31_circulation_conditional_continuation.py']
EXPECTED=62


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(value,reason):
    if not value:raise ValueError('future_pure:'+reason)


def files():
    from . import initial_owner_route_image as image
    require(sha(REFERENCE)==REFERENCE_SHA,'historical_plan_changed')
    old=json.loads(REFERENCE.read_bytes())
    entries=[MODULE,__package__+'.live_obligation_future_later_fork',
             'scripts.experiments.g31_ics_circulation.initial_owner_route_image',
             *[name[:-3].replace('/','.') for name in TESTS]]
    result=image.source_closure(ROOT,entries)
    for name,digest in old['source_sha256'].items():
        path=Path(name);path=path if path.is_absolute() else ROOT/path
        relative=path.relative_to(ROOT).as_posix();data=path.read_bytes()
        require(hashlib.sha256(data).hexdigest()==digest,'historical_live_source:'+relative)
        archived=REFERENCE.parent/old['source_archive'][name]
        require(sha(archived)==digest,'historical_archive_source:'+relative)
        require(relative not in result or result[relative]==data,'source_conflict')
        result[relative]=data
    return dict(sorted(result.items()))


def loaded(pins):
    result={}
    for module in tuple(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if not value:continue
        path=Path(value).resolve()
        if path.suffix=='.py' and path.is_relative_to(ROOT):
            key=path.relative_to(ROOT).as_posix();digest=sha(path)
            require(pins.get(key)==digest,'unlisted_loaded_source:'+key);result[key]=digest
    return dict(sorted(result.items()))


def worker(output,token):
    require(token and sys.stdin.readline()==token+'\n','admission')
    started=time.perf_counter();pins={};report={'status':'failed_or_unknown',
        'native_calls':0,'real_model_predictions':0,'actual_fixture_reads':0,'C_loads':0}
    try:
        sources=files();pins={name:hashlib.sha256(data).hexdigest() for name,data in sources.items()}
        for name,data in sources.items():
            path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        from . import live_obligation_future_later_fork as future
        proof=future.source_proof()
        plan={'schema':'g31.future_later_fork.pure.v1','status':'focused_pure_only',
            'source_sha256':pins,'source_archive':{name:'source/'+name for name in pins},
            'historical_reference':{'path':str(REFERENCE),'sha256':REFERENCE_SHA},
            'tests':TESTS,'expected_tests':EXPECTED,'owned_seconds':120.,
            'future_experiment':future.proposed_six_pair_plan(),
            'scope':'Synthetic source/control/cut tests; no real input/model/native execution. Private model instances are not native capabilities or arbitrary tamper-proof objects.'}
        write(output/'plan.json',plan);write(output/'source_proof.json',proof)
        report.update(plan_sha256=sha(output/'plan.json'),source_proof_sha256=sha(output/'source_proof.json'),
            source_sha256=pins,loaded_entry=loaded(pins))
        import pytest
        result=pytest.main(['-q',*TESTS,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        cases=ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        report.update(pytest_exitcode=int(result),tests=len(cases),expected_tests=EXPECTED,
            XML_sha256=sha(output/'tests.xml'))
        after={name:sha(ROOT/name) for name in pins}
        archive={name:sha(output/'source'/name) for name in pins}
        report['source_changed']=[name for name in pins if after[name]!=pins[name] or archive[name]!=pins[name]]
        report['loaded_exit']=loaded(pins)
        report['proof_unchanged']=future.source_proof()==proof
        require(sha(REFERENCE)==REFERENCE_SHA,'historical_plan_exit_changed')
        require(not any('czr005_circulation' in name or '_g31_complete_tree_normalizer' in name for name in sys.modules),'native_or_C_loaded')
        if (result==0 and len(cases)==EXPECTED and not report['source_changed'] and report['proof_unchanged']
            and not any(n.tag in ('failure','error','skipped') for row in cases for n in row)):
            report['status']='passed'
    except BaseException as error:report['error']=repr(error)
    finally:
        report['worker_before_receipt_seconds']=time.perf_counter()-started
        if pins:
            report['final_source_changed']=[name for name,digest in pins.items()
                if not (ROOT/name).is_file() or sha(ROOT/name)!=digest
                or not (output/'source'/name).is_file() or sha(output/'source'/name)!=digest]
            if report['final_source_changed']:report['status']='failed_or_unknown'
        write(output/'receipt.json',report)
    return 0 if report['status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission');args=parser.parse_args()
    output=args.output.resolve()
    if args.worker:return worker(output,args.admission)
    output.mkdir(parents=True,exist_ok=False);token=uuid.uuid4().hex
    report={'status':'failed_or_unknown','shared_seconds':120.,'native_calls':0,'real_model_predictions':0}
    try:
        remaining=120.-(time.monotonic()-BOOT)-1.
        require(remaining>0,'no_remaining_budget')
        command=[sys.executable,'-m',MODULE,'--output',str(output),'--worker','--admission',token]
        with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
            process=bounded_windows_job.run(command,timeout=remaining,admission=token,stdout=stdout,stderr=stderr,cwd=ROOT)
        report['process']=process
        if (output/'receipt.json').is_file():
            receipt=json.loads((output/'receipt.json').read_bytes());report['receipt_sha256']=sha(output/'receipt.json')
            if process['status']=='exited' and process['exitcode']==0 and receipt['status']=='passed':report['status']='passed'
    except BaseException as error:report['error']=repr(error)
    report['post_interpreter_before_final_export_seconds']=time.monotonic()-BOOT
    if report['post_interpreter_before_final_export_seconds']>120.:report['status']='failed_shared_budget'
    write(output/'bounded_parent_receipt.json',report);print(json.dumps(report))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
