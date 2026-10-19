"""One-shot pinned regression runner with a parent-owned Windows Job."""
import sys

if '--worker' in sys.argv:
    admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != admission:
        raise SystemExit('missing_parent_job_admission')

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import xml.etree.ElementTree as etree

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_later_campaign as campaign
from scripts.experiments.g31_ics_circulation import bounded_windows_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        plan = campaign.read(output / 'plan.json')
        if not all(campaign.sha(path) == expected for path, expected in plan['source_pins'].items()):
            raise SystemExit('source_changed_before_tests')
        import pytest
        return pytest.main(plan['tests'] + ['-q', '--junitxml=' + str(output / 'tests.xml'),
                                           '--basetemp=' + plan['basetemp']])
    if output.exists() or not output.is_relative_to(ROOT):
        raise SystemExit('fresh_workspace_output_required')
    added = ['tests/test_g31_foundation_request_context.py', 'tests/test_g31_foundation_service_refresh.py',
             'tests/test_g31_foundation_service_probe.py']
    tests = (campaign.read(ROOT / 'outputs/experiments/g31_ics_learning_next_20261017/final_validation_003/plan.json')['tests']
             if args.full else ['tests/test_g31_foundation_later_control.py']) + added
    timeout = 180 if args.full else 60
    basetemp = ROOT / 'tmp' / ('su_' + output.name)
    if basetemp.exists():
        raise SystemExit('fresh_pytest_basetemp_required')
    pins = campaign.source_pins()
    pins.update({str((ROOT / path).resolve()): campaign.sha(ROOT / path) for path in tests})
    pins[str(Path(__file__).resolve())] = campaign.sha(__file__)
    protected = Path('C:/PROGRAMING/czr005/cpp/ics_core/runtime/bounded_local_pibt.hpp')
    pins[str(protected)] = campaign.sha(protected)
    plan = {'tests': tests, 'source_pins': pins, 'hard_seconds': timeout,
            'basetemp': str(basetemp), 'automatic_retries': 0}
    output.mkdir(parents=True)
    campaign.write_new(output / 'plan.json', plan)
    admission = secrets.token_hex(24)
    with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, str(Path(__file__).resolve()), '--worker',
            '--output', str(output), '--admission', admission], timeout=timeout,
            stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    changed = [path for path, expected in pins.items() if campaign.sha(path) != expected]
    xml = output / 'tests.xml'
    suites = list(etree.parse(xml).getroot().iter('testsuite')) if xml.exists() else []
    counts = {name: sum(int(suite.get(name, '0')) for suite in suites)
              for name in ('tests', 'failures', 'errors', 'skipped')}
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and not changed and bool(suites)
    receipt = {'status': 'passed' if passed else 'unknown_or_failed', 'process': process,
        'source_changed': changed, 'source_pin_count': len(pins), 'counts': counts,
        'pytest_seconds': sum(float(suite.get('time', '0')) for suite in suites),
        'plan': campaign.reference(output / 'plan.json'),
        'xml': campaign.reference(xml) if xml.exists() else None}
    campaign.write_new(output / 'receipt.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
