"""One owned120 synthetic functional gate; no historical fixture/performance run."""
from __future__ import annotations
import time
BOOT = time.perf_counter()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.run_planning_v2_batched_digest_pure'
TEST = 'tests/test_g31_circulation_planning_v2_batched_digest.py'
EXPECTED = 75
FILES = [
    TEST, 'scripts/experiments/g31_ics_circulation/planning_capture_v2_batched_digest.py',
    'scripts/experiments/g31_ics_circulation/planning_capture_v2_digest.py',
    'scripts/experiments/g31_ics_circulation/run_planning_v2_batched_digest_pure.py',
    'scripts/experiments/g31_ics_circulation/bounded_windows_job.py']


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    if args.worker:
        if sys.stdin.readline().strip()!=args.admission:raise ValueError('pure_admission')
        import pytest
        return pytest.main(['-q',TEST,'--basetemp='+str(output/'temp'),'--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True,exist_ok=False)
    paths=FILES+[name for name in ('scripts/__init__.py','scripts/experiments/__init__.py',
        'scripts/experiments/g31_ics_circulation/__init__.py') if (ROOT/name).exists()]
    before={name:sha(ROOT/name) for name in paths}
    for name in paths:
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
        if sha(target)!=before[name]:raise ValueError('archive_changed')
    token=uuid.uuid4().hex
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--admission',token]
    with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
        process=bounded_windows_job.run(command,timeout=max(.001,120.-(time.perf_counter()-BOOT)),
            admission=token,stdout=stdout,stderr=stderr,cwd=ROOT)
    changed=[name for name,digest in before.items() if sha(ROOT/name)!=digest]
    cases=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    bad=sum(any(item.tag in ('failure','error','skipped') for item in case) for case in cases)
    result={'schema':'g31.planning_v2_batched_digest.focused_pure.v1',
        'status':'passed' if process['status']=='exited' and process['exitcode']==0 and not changed
            and len(cases)==EXPECTED and not bad else 'failed_or_unknown',
        'process':process,'source_sha256':before,'source_changed':changed,
        'tests':len(cases),'expected_tests':EXPECTED,'failed_error_or_skipped':bad,
        'XML_sha256':sha(output/'tests.xml') if cases else None,
        'scope':'Tiny fabricated complete typed captures and explicit hook/failure fixtures; byte equality and original SHA checks. No historical data, timings comparison, native or model execution.',
        'real_raw_reads':0,'native_calls':0,'model_calls':0,'benchmark_runs':0,
        'post_BOOT_before_receipt_seconds':time.perf_counter()-BOOT,
        'wall_scope':'Owned120 includes source archive and tests; interpreter startup/final receipt write require an external launch-to-exit clock.'}
    with (output/'receipt.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ('status','tests','expected_tests','failed_error_or_skipped','source_changed','post_BOOT_before_receipt_seconds')}))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
