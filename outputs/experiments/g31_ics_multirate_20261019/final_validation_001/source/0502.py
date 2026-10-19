"""One owned120 synthetic functional gate; no raw replay or performance run."""
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
from . import initial_owner_route_image as image

ROOT=Path(__file__).resolve().parents[3]
TEST='tests/test_g31_circulation_bridge_replay_copy_scopes.py'
EXPECTED_TESTS=37


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    if args.worker:
        if sys.stdin.readline().strip()!=args.admission:raise ValueError('pure_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(output/'temp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    files=image.source_closure(ROOT,(__package__+'.run_bridge_replay_copy_scopes_pure',
        __package__+'.bridge_replay_copy_scopes','tests.test_g31_circulation_bridge_replay_copy_scopes'))
    files[TEST]=(ROOT/TEST).read_bytes()
    before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    admission=uuid.uuid4().hex
    command=[sys.executable,'-m',__package__+'.run_bridge_replay_copy_scopes_pure',
        '--output',str(output),'--worker','--admission',admission]
    with (output/'stdout.log').open('x',encoding='utf8') as stdout,(output/'stderr.log').open('x',encoding='utf8') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=admission,stdout=stdout,stderr=stderr,cwd=ROOT)
    changed=[name for name,sha in before.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha]
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    bad=any(c.tag in ('failure','error','skipped') for row in rows for c in row)
    report={'schema':'g31.bridge_replay_copy_scopes_pure.v1','process':process,'source_sha256':before,
        'source_changed':changed,'native_calls':0,'actual_raw_reads':0,'benchmark_executed':False,
        'test_fixture_scope':'Synthetic complete typed public records; no actual native delivery or history claim.',
        'tests':len(rows),'expected_tests':EXPECTED_TESTS,
        'XML_sha256':hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'post_interpreter_wall_seconds':time.perf_counter()-BOOT,
        'wall_scope':'From module BOOT through this sample; excludes interpreter startup and final receipt write. Child tree hard bound includes archive preparation.',
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed and len(rows)==EXPECTED_TESTS and not bad else 'failed_or_unknown'}
    (output/'receipt.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf8')
    print(json.dumps({k:report[k] for k in ('status','tests','expected_tests','XML_sha256','source_changed','post_interpreter_wall_seconds')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
