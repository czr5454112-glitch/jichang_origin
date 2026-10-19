"""Owned120 fixed functional gate; does not call the synthetic cost worker."""
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
from . import measure_bridge_copy_scopes as m


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true');p.add_argument('--admission')
    a=p.parse_args();output=a.output.resolve()
    if a.worker:
        if sys.stdin.readline().strip()!=a.admission:raise ValueError('pure_owned_admission')
        import pytest
        return pytest.main(['-q','tests/test_g31_circulation_bridge_replay_copy_scopes.py',m.TEST,
            '--basetemp='+str(output/'temp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False);files=m.source_files();before={name:m.digest(data) for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    admission=uuid.uuid4().hex
    command=[sys.executable,'-m',m.PURE_MODULE,'--output',str(output),'--worker','--admission',admission]
    with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=admission,stdout=stdout,stderr=stderr,cwd=m.ROOT)
    changed=[name for name,digest in before.items() if m.sha(m.ROOT/name)!=digest]
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    bad=any(c.tag in ('failure','error','skipped') for row in rows for c in row)
    report={'schema':'g31.bridge.copy_scopes.synthetic_pure.v1','process':process,'source_sha256':before,
        'source_changed':changed,'tests':len(rows),'expected_tests':m.PURE_TESTS,
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed and len(rows)==m.PURE_TESTS and not bad else 'failed_or_unknown',
        'XML_sha256':m.sha(output/'tests.xml') if rows else None,'native_calls':0,'actual_raw_reads':0,
        'benchmark_executed':False,'scope':'Functional synthetic invocations and fake-clock256-record guards, not the cost ABBA worker.',
        'post_interpreter_before_receipt_seconds':time.perf_counter()-BOOT}
    m.write(output/'receipt.json',report)
    print(json.dumps({k:report[k] for k in ('status','tests','expected_tests','XML_sha256','source_changed','post_interpreter_before_receipt_seconds')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
