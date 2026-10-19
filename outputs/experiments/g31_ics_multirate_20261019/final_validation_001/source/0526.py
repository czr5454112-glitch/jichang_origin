"""One owned120s pure harness gate; zero native and no predictor evaluation."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT=Path(__file__).resolve().parents[3]
TEST='tests/test_g31_circulation_initial_owner_route_campaign.py'


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission')
    a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=a.admission+'\n':raise ValueError('pure_job_admission')
        os.environ['G31_INITIAL_CAMPAIGN_PURE_OUTPUT']=str(output)
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(ROOT/'outputs'/('initial_campaign_'+output.name)),
                           '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    files=image.source_closure(ROOT,(__package__+'.run_initial_owner_route_campaign_pure',
        __package__+'.prepare_initial_owner_route_campaign',__package__+'.launch_initial_owner_route_campaign',
        __package__+'.verify_initial_owner_route_campaign','tests.test_g31_circulation_initial_owner_route_campaign'))
    before={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
    for name,data in files.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_initial_owner_route_campaign_pure','--output',str(output),
             '--worker','--admission',token]
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.monotonic()-BOOT)),
            admission=token,stdout=out,stderr=err,cwd=ROOT)
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    changed=[k for k,h in before.items() if hashlib.sha256((ROOT/k).read_bytes()).hexdigest()!=h]
    bad=any(n.tag in ('failure','error','skipped') for r in rows for n in r)
    report={'status':'passed' if process['status']=='exited' and process['exitcode']==0 and rows and not bad and not changed else 'failed_or_unknown',
        'process':process,'source_sha256':before,'source_changed':changed,'tests':len(rows),
        'XML_sha256':hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'native_calls':0,'predictor_evaluations':0,'performance_runs':0,
        'startup_sha256':hashlib.sha256((output/'image_startup.json').read_bytes()).hexdigest() if (output/'image_startup.json').exists() else None,
        'post_interpreter_before_receipt_seconds':time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
