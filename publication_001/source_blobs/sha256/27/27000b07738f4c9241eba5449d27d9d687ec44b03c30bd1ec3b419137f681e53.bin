"""Owned120 synthetic audit tests only; no saved prediction decode/model."""
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
from . import review_scoped_public_inputs_saved as audit

ROOT=audit.ROOT
MODULE='scripts.experiments.g31_ics_circulation.run_scoped_inputs_saved_pure'
TEST='tests/test_g31_circulation_scoped_inputs_saved.py'
TEST_COUNT=49


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission');a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline()!=a.admission+'\n':raise ValueError('scoped_saved_pure_admission')
        import pytest
        result=pytest.main(['-q',TEST,'--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')])
        audit.no_execution_modules();return result
    output.mkdir(parents=True,exist_ok=False)
    receipt={'status':'failed_or_unknown','native_calls':0,'model_calls':0,'actual_saved_raw_reads':0,'performance_runs':0}
    try:
        files=image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.')))
        before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        for name,data in files.items():
            path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        receipt['source_sha256']=before
        token=uuid.uuid4().hex
        command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--admission',token]
        with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
            receipt['process']=bounded_windows_job.run(command,timeout=audit.remaining(time.monotonic()-BOOT),
                stdout=out,stderr=err,admission=token,cwd=ROOT)
        rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        receipt['tests']=len(rows);receipt['XML_sha256']=sha(output/'tests.xml')
        receipt['source_changed']=[n for n,d in before.items() if sha(ROOT/n)!=d]
        if (receipt['process']['status']=='exited' and receipt['process']['exitcode']==0 and len(rows)==TEST_COUNT
            and not receipt['source_changed'] and not any(x.tag in ('failure','error','skipped') for row in rows for x in row)):
            receipt['status']='passed'
    except BaseException:receipt['error']=traceback.format_exc()
    receipt['post_interpreter_before_receipt_seconds']=time.monotonic()-BOOT
    audit.write(output/'receipt.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}))
    return 0 if receipt['status']=='passed' and time.monotonic()-BOOT<=120 else 1


if __name__=='__main__':raise SystemExit(main())
