"""Owned120s functional/source gate only; no native, predictor or benchmark."""
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
from . import initial_owner_route_image as image

ROOT=Path(__file__).resolve().parents[3]
TESTS=('tests/test_g31_circulation_initial_owner_route_observation_gate.py',
    'tests/test_g31_circulation_initial_owner_route_gate_adapter.py',
    'tests/test_g31_circulation_initial_owner_route_outbox_trace_v2.py',
    'tests/test_g31_circulation_initial_owner_route_gate_campaign_v2.py')


def modules():
    return tuple(__package__+'.'+name for name in ('run_initial_owner_route_gate_pure_v2',
        'prepare_initial_owner_route_gate_campaign_v2','launch_initial_owner_route_gate_campaign_v2',
        'initial_owner_route_gate_campaign_v2','verify_initial_owner_route_gate_campaign_v2'))+tuple(
            path[:-3].replace('/','.') for path in TESTS)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission');a=p.parse_args()
    output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=a.admission+'\n':raise ValueError('gate_pure_job_admission')
        import pytest
        return pytest.main(['-q',*TESTS,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    files=image.source_closure(ROOT,modules());before={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
    for name,data in files.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_initial_owner_route_gate_pure_v2','--output',str(output),
        '--worker','--admission',token]
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.monotonic()-BOOT)),
            admission=token,stdout=out,stderr=err,cwd=ROOT)
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    changed=[k for k,h in before.items() if hashlib.sha256((ROOT/k).read_bytes()).hexdigest()!=h]
    bad=any(n.tag in ('failure','error','skipped') for row in rows for n in row)
    report={'status':'passed' if process['status']=='exited' and process['exitcode']==0 and rows and not bad and not changed else 'failed_or_unknown',
        'process':process,'source_sha256':before,'source_changed':changed,'tests':len(rows),
        'XML_sha256':hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'native_calls':0,'predictor_evaluations':0,'performance_runs':0,
        'post_interpreter_before_receipt_seconds':time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
