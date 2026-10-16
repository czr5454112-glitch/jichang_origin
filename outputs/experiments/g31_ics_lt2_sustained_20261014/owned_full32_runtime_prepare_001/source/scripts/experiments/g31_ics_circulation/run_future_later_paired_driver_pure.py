"""Focused synthetic paired-driver tests; no actual model, native or C load."""
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
MODULE=__package__+'.run_future_later_paired_driver_pure'
TEST='tests/test_g31_circulation_future_later_paired_driver.py'
EXPECTED=22


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')


def worker(output,token):
    if not token or sys.stdin.readline()!=token+'\n':raise ValueError('future_driver_pure:admission')
    report={'status':'failed_or_unknown','native_calls':0,'real_model_predictions':0,'actual_fixture_decodes':0,'C_loads':0}
    started=time.perf_counter();pins={}
    try:
        from . import validate_future_later_paired_suffix as driver
        files=driver.source_files();pins={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        for name,data in files.items():
            path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        report.update(source_sha256=pins,loaded_entry=driver.loaded_sources(pins))
        write(output/'plan.json',{'schema':'g31.future_later_driver.pure.v1','source_sha256':pins,
            'source_archive':{name:'source/'+name for name in pins},'tests':[TEST],'expected_tests':EXPECTED,
            'shared_seconds':120.,'scope':'Synthetic engine/fork control, output retention, full alias-graph-only delta and exact JSON output audit. No real supplied context/model run.'})
        report['plan_sha256']=sha(output/'plan.json')
        import pytest
        result=pytest.main(['-q',TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        cases=ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        report.update(pytest_exitcode=int(result),tests=len(cases),expected_tests=EXPECTED,XML_sha256=sha(output/'tests.xml'))
        report['loaded_exit']=driver.loaded_sources(pins)
        report['source_changed']=[name for name,digest in pins.items() if sha(ROOT/name)!=digest or sha(output/'source'/name)!=digest]
        if any('czr005_circulation' in name or '_g31_complete_tree_normalizer' in name for name in sys.modules):
            raise ValueError('future_driver_pure:native_or_C_loaded')
        if (result==0 and len(cases)==EXPECTED and not report['source_changed']
            and not any(n.tag in ('failure','error','skipped') for row in cases for n in row)):report['status']='passed'
    except BaseException as error:report['error']=repr(error)
    report['worker_before_receipt_seconds']=time.perf_counter()-started
    if pins:
        report['source_changed']=[name for name,digest in pins.items()
            if not (ROOT/name).is_file() or sha(ROOT/name)!=digest or not (output/'source'/name).is_file() or sha(output/'source'/name)!=digest]
        if report['source_changed']:report['status']='failed_or_unknown'
    write(output/'receipt.json',report);return 0 if report['status']=='passed' else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true');p.add_argument('--admission')
    args=p.parse_args();output=args.output.resolve()
    if args.worker:return worker(output,args.admission)
    output.mkdir(parents=True,exist_ok=False);token=uuid.uuid4().hex
    report={'status':'failed_or_unknown','shared_seconds':120.,'native_calls':0,'real_model_predictions':0}
    try:
        remaining=120.-(time.monotonic()-BOOT)-1.
        if remaining<=0:raise TimeoutError('future_driver_pure:no_remaining_budget')
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
