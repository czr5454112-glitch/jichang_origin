"""Owned120 focused new campaign/source gate; no native, predictor or timing."""
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
from . import run_initial_owner_route_entry_pure as entry_pure
from . import run_initial_entry_codec_integration_pure as integration_pure

ROOT = entry_pure.old.ROOT
TESTS = ('tests/test_g31_circulation_initial_owner_route_entry_codec_integration.py',
    'tests/test_g31_circulation_initial_owner_route_entry_verifier_v2.py',
    'tests/test_g31_circulation_initial_owner_route_entry_codec_campaign.py')


def modules():
    return entry_pure.modules()+tuple(__package__+'.'+name for name in (
        'run_complete_root_evidence_codec_campaign_pure', 'measure_complete_root_evidence_codec',
        'run_initial_entry_codec_integration_pure', 'initial_owner_route_entry_codec_integration',
        'run_initial_entry_codec_campaign_pure', 'initial_owner_route_entry_codec_campaign',
        'verify_initial_owner_route_entry_codec_campaign', 'launch_initial_owner_route_entry_codec_campaign',
        'prepare_initial_owner_route_entry_codec_campaign'))+(
        'tests.test_g31_circulation_complete_root_evidence_codec_campaign',
        *tuple(path[:-3].replace('/', '.') for path in TESTS))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True, type=Path)
    p.add_argument('--worker', action='store_true'); p.add_argument('--admission')
    args = p.parse_args(); output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission+'\n': raise ValueError('entry_codec_campaign_pure_admission')
        import pytest
        return pytest.main(['-q', *TESTS, '--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')])
    output.mkdir(parents=True, exist_ok=False)
    old_before = integration_pure.frozen()
    files = image.source_closure(ROOT, modules())
    before = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', __package__+'.run_initial_entry_codec_campaign_pure',
               '--output', str(output), '--worker', '--admission', token]
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        remaining = 120-(time.monotonic()-BOOT)
        if remaining <= 0: raise TimeoutError('entry_codec_pure_budget_before_assignment')
        process = bounded_windows_job.run(command, timeout=remaining, admission=token, stdout=out, stderr=err, cwd=ROOT)
    rows = ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    changed = [name for name, digest in before.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
    unchanged = integration_pure.frozen() == old_before
    bad = any(node.tag in ('failure', 'error', 'skipped') for row in rows for node in row)
    report = {'status': 'passed' if process['status'] == 'exited' and process['exitcode'] == 0 and
        len(rows) >= 40 and not bad and not changed and unchanged else 'failed_or_unknown',
        'process': process, 'source_sha256': before, 'source_changed': changed, 'tests': len(rows),
        'original151_and_codec135_current_and_archive_unchanged': unchanged,
        'XML_sha256': hashlib.sha256((output/'tests.xml').read_bytes()).hexdigest() if rows else None,
        'native_calls': 0, 'predictor_evaluations': 0, 'performance_runs': 0, 'saved_raw_reads': 0,
        'post_interpreter_before_receipt_seconds': time.monotonic()-BOOT}
    (output/'receipt.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({key: value for key, value in report.items() if key != 'source_sha256'}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
