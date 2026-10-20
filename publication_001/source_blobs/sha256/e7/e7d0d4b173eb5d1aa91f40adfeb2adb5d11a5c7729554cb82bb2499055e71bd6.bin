"""Owned120 source/functional gate; no model engine/native or cost experiment."""
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job, initial_owner_route_image as image
from . import profile_live_lazy_six as profile

ROOT,OUT=profile.ROOT,profile.OUT
TEST='tests/test_g31_circulation_scoped_public_inputs.py'
MODULE='scripts.experiments.g31_ics_circulation.run_scoped_public_inputs_pure'
FROZEN=OUT/'live_lazy_six_profile_prepare_001'


def sources():
    files=image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.')))
    plan=profile.read(FROZEN/'plan.json')
    assert profile.sha(FROZEN/'plan.json')=='222b1d66267921229866970bfd00ac843fa740e9e2a2695c786a3809887f7e85'
    for path,digest in plan['source_sha256'].items():
        assert profile.sha(path)==digest==profile.sha(FROZEN/plan['source_archive'][path])
        files[str(Path(path).relative_to(ROOT))]=Path(path).read_bytes()
    return files


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission');args=parser.parse_args()
    output=args.output.resolve()
    if args.worker:
        assert sys.stdin.readline()==args.admission+'\n'
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(exist_ok=False);files=sources()
    before={str(ROOT/p):hashlib.sha256(data).hexdigest() for p,data in files.items()}
    for relative,data in files.items():
        path=output/'source'/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    plan={'source_sha256':before,'fixed_previous_profile':profile.ref(FROZEN/'plan.json'),
        'test':TEST,'hard_application_seconds':120.,'native_calls':0,'model_engine_calls':0,'performance_runs':0}
    profile.write(output/'plan.json',plan);token=uuid.uuid4().hex
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--admission',token]
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        remaining=120-(time.monotonic()-BOOT)-1
        assert remaining>0
        process=bounded_windows_job.run(command,timeout=remaining,admission=token,stdout=out,stderr=err,cwd=str(ROOT))
    cases=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    changed=[p for p,d in before.items() if profile.sha(p)!=d]
    sources()
    failed=any(child.tag in ('failure','error','skipped') for case in cases for child in case)
    elapsed=time.monotonic()-BOOT
    status='passed' if len(cases)==16 and not failed and not changed and process['status']=='exited' and process['exitcode']==0 and elapsed<120 else 'failed_or_unknown'
    receipt={'status':status,'process':process,'tests':len(cases),'source_changed':changed,
        'plan':profile.ref(output/'plan.json'),'XML':profile.ref(output/'tests.xml') if cases else None,
        'whole_before_receipt_seconds':elapsed,'native_calls':0,'model_engine_calls':0,'performance_runs':0}
    profile.write(output/'receipt.json',receipt);print(json.dumps(receipt));return 0 if status=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
