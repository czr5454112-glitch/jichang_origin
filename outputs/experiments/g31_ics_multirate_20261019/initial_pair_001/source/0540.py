"""Owned 120s functional gate only; never a performance or native campaign."""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
ROOT = Path(__file__).resolve().parents[3]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    if args.worker:
        if sys.stdin.readline().strip()!=args.admission:raise ValueError('no_job_admission')
        os.environ['G31_JSON_FUNCTIONAL_OUTPUT']=str(output)
        import pytest
        return pytest.main(['-q','tests/test_g31_circulation_json_prediction_worker.py',
            'tests/test_g31_circulation_json_prediction_campaign.py','--basetemp='+str(ROOT/'outputs'/('jpt_'+output.name[-3:])),
            '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    names=('json_prediction_image.py','json_prediction_worker.py','json_prediction_client.py',
           'measure_json_prediction_service.py','run_json_prediction_pure.py')
    paths=[ROOT/'scripts/experiments/g31_ics_circulation'/name for name in names]
    paths.extend(ROOT/'tests'/name for name in ('test_g31_circulation_json_prediction_worker.py',
                                               'test_g31_circulation_json_prediction_campaign.py'))
    before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    admission=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_json_prediction_pure','--worker','--output',str(output),'--admission',admission]
    with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=admission,stdout=stdout,stderr=stderr,cwd=ROOT)
    changed=[name for name,digest in before.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    cases=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    bad=any(child.tag in ('failure','error','skipped') for case in cases for child in case)
    report={'schema':'g31.json_prediction_functional_gate.v1','process':process,'command':command,
        'source_sha256':before,'source_changed':changed,'native_calls':0,'performance_campaign_executed':False,
        'tests':len(cases),'XML_sha256':hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if cases else None,
        'startup_attestations':{mode:{'path':str(output/f'startup_{mode}.json'),
            'sha256':hashlib.sha256((output/f'startup_{mode}.json').read_bytes()).hexdigest()}
            for mode in ('reference','compiled') if (output/f'startup_{mode}.json').is_file()},
        'post_interpreter_wall_seconds':time.perf_counter()-BOOT,
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed and cases and not bad else 'failed_or_unknown'}
    (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
