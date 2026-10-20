"""Owned120 synthetic harness tests; no original digest or real fixture reads."""
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
from . import measure_planning_v2_digest as m

ROOT=m.ROOT
EXPECTED_TESTS=56


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',action='store_true');p.add_argument('--admission')
    a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline().strip()!=a.admission:raise ValueError('pure_admission')
        import pytest
        return pytest.main(['-q',m.TEST,'--basetemp='+str(output/'temp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    files=m.source_files();before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',m.PURE,'--output',str(output),'--worker','--admission',token]
    with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=token,stdout=stdout,stderr=stderr,cwd=ROOT)
    changed=[name for name,digest in before.items() if m.sha(ROOT/name)!=digest]
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    bad=any(c.tag in ('failure','error','skipped') for row in rows for c in row)
    result={'schema':'g31.planning_v2_digest.focused_pure.v1','process':process,
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed
            and len(rows)==EXPECTED_TESTS and not bad else 'failed_or_unknown',
        'source_sha256':before,'source_changed':changed,'tests':len(rows),'expected_tests':EXPECTED_TESTS,
        'XML_sha256':m.sha(output/'tests.xml') if rows else None,
        'digest_calls':0,'native_calls':0,'actual_raw_reads':0,'predictions':0,'benchmark_runs':0,
        'fixture_scope':'Tiny fabricated envelope/header only; original digest replaced by explicit spies in call-path tests.',
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,
        'wall_scope':'Owned120 includes source preparation and test child. External launch-to-exit additionally includes Python startup and final receipt write.'}
    m.write(output/'receipt.json',result)
    print(json.dumps({k:result[k] for k in ('status','tests','expected_tests','XML_sha256','source_changed','post_BOOT_before_receipt_seconds')}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
