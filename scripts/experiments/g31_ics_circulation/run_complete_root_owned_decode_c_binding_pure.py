"""Combined owned120 synthetic gate; no C load, saved18 read or performance."""
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

from . import bounded_windows_job
from . import initial_owner_route_image as image

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.run_complete_root_owned_decode_c_binding_pure'
CANDIDATE = 'scripts.experiments.g31_ics_circulation.complete_root_evidence_owned_decode_c_binding'
TESTS = ('tests/test_g31_circulation_complete_root_owned_decode_v2.py',
         'tests/test_g31_circulation_complete_root_owned_decode_c_binding.py')
EXPECTED_TESTS = 105


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission + '\n':
            raise ValueError('owned_C_binding_pure_admission')
        import pytest
        return pytest.main(['-q', *TESTS, '--basetemp=' + str(output/'tmp'),
                            '--junitxml=' + str(output/'tests.xml')])
    output.mkdir(parents=True, exist_ok=False)
    files = image.source_closure(ROOT, (MODULE, CANDIDATE, *(x[:-3].replace('/', '.') for x in TESTS)))
    before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        target = output/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--output', str(output), '--worker', '--admission', token]
    remaining = 120 - (time.monotonic() - BOOT) - 1
    if remaining <= 0:
        process = {'status': 'budget_exhausted_before_worker', 'exitcode': None}
    else:
        with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
            process = bounded_windows_job.run(command, timeout=remaining, stdout=out, stderr=err,
                                              admission=token, cwd=ROOT)
    xml = output/'tests.xml'
    rows = ET.parse(xml).getroot().findall('.//testcase') if xml.is_file() else []
    changed = [name for name, digest in before.items()
               if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest or
               hashlib.sha256((output/'source'/name).read_bytes()).hexdigest() != digest]
    bad = any(child.tag in ('failure', 'error', 'skipped') for row in rows for child in row)
    elapsed = time.monotonic() - BOOT
    passed = (process['status'] == 'exited' and process['exitcode'] == 0
              and len(rows) == EXPECTED_TESTS and not bad and not changed and elapsed < 120)
    report = {'status': 'passed' if passed else 'failed_or_unknown', 'process': process,
        'source_sha256': before, 'source_changed': changed, 'tests': len(rows),
        'expected_tests': EXPECTED_TESTS, 'command': command,
        'XML_sha256': hashlib.sha256(xml.read_bytes()).hexdigest() if xml.is_file() else None,
        'native_calls': 0, 'predictor_calls': 0, 'C_extension_loads': 0,
        'saved_raw_scans': 0, 'performance_runs': 0,
        'scope': 'Synthetic full-publisher and fair-C-wiring gate only; no extension loaded.',
        'post_interpreter_before_receipt_seconds': elapsed,
        'external_launcher_required_for_full_startup_to_exit_wall': True}
    (output/'receipt.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('source_sha256', 'command')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
