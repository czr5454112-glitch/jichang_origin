"""Owned120 functional gate. No native, predictor, saved raw scan or benchmark."""
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
TEST = 'tests/test_g31_circulation_complete_root_evidence_codec.py'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission + '\n':
            raise ValueError('codec_pure_admission')
        import pytest
        return pytest.main(['-q', TEST, '--basetemp=' + str(output/'tmp'),
                            '--junitxml=' + str(output/'tests.xml')])
    output.mkdir(parents=True, exist_ok=False)
    files = image.source_closure(ROOT, (__package__ + '.run_complete_root_evidence_codec_pure',
        __package__ + '.complete_root_evidence_candidate', TEST[:-3].replace('/', '.')))
    before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        target = output/'source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', __package__ + '.run_complete_root_evidence_codec_pure',
               '--output', str(output), '--worker', '--admission', token]
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        process = bounded_windows_job.run(command, timeout=max(.001, 120-(time.monotonic()-BOOT)),
            stdout=out, stderr=err, admission=token, cwd=ROOT)
    rows = ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    changed = [name for name, digest in before.items()
               if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
    bad = any(child.tag in ('failure', 'error', 'skipped') for row in rows for child in row)
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and rows and not bad and not changed
    report = {'status': 'passed' if passed else 'failed_or_unknown', 'process': process,
        'source_sha256': before, 'source_changed': changed, 'tests': len(rows),
        'XML_sha256': hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'native_calls': 0, 'predictor_calls': 0, 'saved_raw_scans': 0, 'performance_runs': 0,
        'scope': 'Synthetic builtin, error and full-root source/representation differential gate only.',
        'post_interpreter_before_receipt_seconds': time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({key: value for key, value in report.items() if key != 'source_sha256'}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
