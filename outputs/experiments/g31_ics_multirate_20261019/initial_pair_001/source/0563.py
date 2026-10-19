"""Owned120 synthetic harness gate plus unchanged75 candidate functional cases."""
from __future__ import annotations
import time
BOOT=time.perf_counter()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import measure_planning_v2_batched_digest_cost as m


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission')
    a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline().strip()!=a.admission:raise ValueError('pure_admission')
        import pytest
        return pytest.main(['-q',m.SOURCE_TEST,m.TEST,'--basetemp='+str(output/'temp'),
            '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False);files=m.source_files()
    before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',m.PURE,'--output',str(output),'--worker','--admission',token]
    with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=token,stdout=stdout,stderr=stderr,cwd=m.ROOT)
    changed=[name for name,digest in before.items() if m.sha(m.ROOT/name)!=digest]
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    bad=any(c.tag in ('failure','error','skipped') for row in rows for c in row)
    result={'schema':'g31.planning_v2_batched_digest.cost_pure.v1','process':process,
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed
            and len(rows)==m.PURE_TESTS and not bad else 'failed_or_unknown',
        'source_sha256':before,'source_changed':changed,'tests':len(rows),'expected_tests':m.PURE_TESTS,
        'XML_sha256':m.sha(output/'tests.xml') if rows else None,
        'native_calls':0,'real_raw_reads':0,'model_calls':0,'benchmark_runs':0,
        'scope':'Fabricated tiny complete bodies only; includes unchanged75 candidate tests and cost-harness guards. No historical fixed-input decode or performance experiment.',
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT}
    m.write(output/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','tests','expected_tests','XML_sha256','source_changed','post_BOOT_before_receipt_seconds')}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
