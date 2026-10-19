"""Owned120 synthetic harness checks; no real model/input decode/native."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job, initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.run_scoped_public_inputs_v2_cost_pure'
TEST = 'tests/test_g31_circulation_scoped_public_inputs_v2_cost.py'
COUNT = 32
LIMIT = 120.


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream: stream.write(json.dumps(value, indent=2, allow_nan=False)+'\n')


def require(value, why):
    if not value: raise ValueError('scoped_v2_cost_pure:'+why)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker:
        require(sys.stdin.readline() == args.admission+'\n', 'owned_admission')
        import pytest
        result = pytest.main(['-q', TEST, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
        require(not any('czr005_circulation' in name or '_g31_complete_tree_normalizer' in name for name in sys.modules), 'forbidden_extension')
        return result
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'failed_or_unknown', 'native_calls': 0, 'model_engine_runs': 0,
        'performance_runs': 0, 'real_saved_input_decodes': 0, 'fixed_application_seconds': LIMIT}
    try:
        files = image.source_closure(ROOT, (MODULE, TEST[:-3].replace('/', '.')))
        before = {p: hashlib.sha256(data).hexdigest() for p,data in files.items()}
        for name,data in files.items():
            path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        receipt['source_sha256'] = before
        token = uuid.uuid4().hex
        command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--admission', token]
        remaining = LIMIT-(time.monotonic()-BOOT)-1.; require(remaining > 0, 'before_worker_budget')
        with (output/'stdout.log').open('x') as out, (output/'stderr.log').open('x') as err:
            receipt['process'] = bounded_windows_job.run(command, timeout=remaining, stdout=out, stderr=err, admission=token, cwd=ROOT)
        receipt['command'] = command
        cases = ET.parse(output/'tests.xml').getroot().findall('.//testcase')
        receipt['tests'] = len(cases); receipt['XML_sha256'] = sha(output/'tests.xml')
        receipt['source_changed'] = [p for p,d in before.items() if sha(ROOT/p) != d]
        if (receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
            and len(cases) == COUNT and not receipt['source_changed']
            and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c)):
            receipt['status'] = 'passed'
    except BaseException: receipt['error'] = traceback.format_exc()
    receipt['post_interpreter_before_receipt_seconds'] = time.monotonic()-BOOT
    write(output/'receipt.json', receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k != 'source_sha256'}))
    return 0 if receipt['status'] == 'passed' and time.monotonic()-BOOT <= LIMIT else 1


if __name__ == '__main__': raise SystemExit(main())
