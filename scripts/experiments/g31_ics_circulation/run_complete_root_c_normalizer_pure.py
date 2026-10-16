"""Owned120 synthetic harness checks; no C load, fixture or performance run."""
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job as bounded
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.run_complete_root_c_normalizer_pure'
TEST = 'tests/test_g31_circulation_complete_root_c_normalizer_campaign.py'


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args(); output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission+'\n': raise ValueError('C_mock_pure_admission')
        import pytest
        code = pytest.main(['-q', TEST, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
        if any('_g31_complete_tree_normalizer' in n or 'czr005_circulation' in n for n in sys.modules):
            raise ValueError('C_mock_pure_extension_loaded')
        return code
    output.mkdir(parents=True, exist_ok=False)
    files = image.source_closure(ROOT, (MODULE, 'scripts.experiments.g31_ics_circulation.measure_complete_root_c_normalizer',
        TEST[:-3].replace('/', '.')))
    before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--admission', token]
    with (output/'stdout.log').open('x', encoding='utf8') as stdout, (output/'stderr.log').open('x', encoding='utf8') as stderr:
        process = bounded.run(command, timeout=120-(time.monotonic()-BOOT)-1, admission=token,
            stdout=stdout, stderr=stderr, cwd=ROOT)
    xml = output/'tests.xml'
    cases = ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
    changed = [name for name, digest in before.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
    passed = (process['status'] == 'exited' and process['exitcode'] == 0 and cases and not changed and
        not any(child.tag in ('failure', 'error', 'skipped') for row in cases for child in row))
    receipt = {'status': 'passed' if passed else 'failed_or_unknown', 'process': process,
        'source_sha256': before, 'source_changed': changed, 'tests': len(cases),
        'XML_sha256': hashlib.sha256(xml.read_bytes()).hexdigest() if xml.is_file() else None,
        'native_calls': 0, 'predictor_calls': 0, 'performance_runs': 0, 'C_extension_loads': 0,
        'actual_saved_fixture_reads': 0, 'post_interpreter_before_receipt_seconds': time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'source_sha256'}))
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
