"""Owned120 fake-predictor tests, no model/native or actual raw decoding."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import initial_owner_route_image as image
from . import validate_live_communication_scoped_inputs as gate

ROOT=gate.ROOT
MODULE='scripts.experiments.g31_ics_circulation.run_live_communication_scoped_inputs_pure'
TEST=gate.TEST
LIMIT=120.


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    if args.worker:
        gate.require(sys.stdin.readline()==args.admission+'\n','focused_pure_owned_admission')
        import pytest
        result=pytest.main(['-q',TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        gate.no_execution_extensions();return result
    output.mkdir(parents=True,exist_ok=False)
    receipt={'status':'failed_or_unknown','native_calls':0,'model_calls':0,
        'actual_saved_raw_decodes':0,'performance_runs':0,'fixed_application_seconds':LIMIT}
    try:
        files=image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.')))
        before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        for name,data in files.items():
            path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        receipt['source_sha256']=before
        token=uuid.uuid4().hex
        command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--admission',token]
        remaining=LIMIT-(time.monotonic()-BOOT)-1.;gate.require(remaining>0,'pure_before_worker_budget')
        with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
            receipt['process']=bounded_windows_job.run(command,timeout=remaining,stdout=out,stderr=err,admission=token,cwd=ROOT)
        receipt['command']=command
        rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        receipt['tests']=len(rows);receipt['XML_sha256']=sha(output/'tests.xml')
        receipt['source_changed']=[name for name,digest in before.items() if sha(ROOT/name)!=digest]
        if (receipt['process']['status']=='exited' and receipt['process']['exitcode']==0
            and len(rows)==gate.PURE_COUNT and not receipt['source_changed']
            and not any(x.tag in ('failure','error','skipped') for row in rows for x in row)):
            receipt['status']='passed'
    except BaseException:receipt['error']=traceback.format_exc()
    receipt['post_interpreter_before_receipt_seconds']=time.monotonic()-BOOT
    gate.write(output/'receipt.json',receipt)
    print(json.dumps({key:value for key,value in receipt.items() if key!='source_sha256'}))
    return 0 if receipt['status']=='passed' and time.monotonic()-BOOT<=LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
