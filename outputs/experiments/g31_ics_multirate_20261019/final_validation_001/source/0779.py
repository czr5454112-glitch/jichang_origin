"""Pinned continuation of the prior 844-test suite plus this stage's tests."""
import sys
if '--worker' in sys.argv:
    token = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != token:
        raise SystemExit('missing_parent_job_admission')

import argparse
import json
from pathlib import Path
import secrets
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_later_campaign as campaign
from scripts.experiments.g31_ics_circulation import bounded_windows_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        plan = campaign.read(output / 'plan.json')
        if any(campaign.sha(path) != expected for path, expected in plan['source_pins'].items()):
            raise SystemExit('changed_sources')
        import pytest
        return pytest.main(plan['tests'] + ['-q', '--junitxml=' + str(output / 'tests.xml'),
            '--basetemp=' + str(output / 'pytest_tmp')])
    if output.exists() or not output.is_relative_to(ROOT):
        raise SystemExit('fresh_workspace_output_required')
    tests = campaign.read(ROOT / 'outputs/experiments/g31_ics_refresh_next_20261017/final_validation_001/plan.json')['tests']
    additions = sorted(str(path.relative_to(ROOT)).replace('\\', '/') for path in (ROOT / 'tests').glob('test_g31_foundation*.py'))
    tests = list(dict.fromkeys(tests + additions))
    pins = campaign.source_pins()
    for path in [*(ROOT / test for test in tests), Path(__file__),
                 ROOT / 'outputs/experiments/g31_ics_refresh_next_20261017/build_review_bundle.py',
                 ROOT / 'outputs/experiments/g31_ics_refresh_next_20261017/verify_review_bundle.py',
                 Path('C:/PROGRAMING/czr005/cpp/ics_core/runtime/bounded_local_pibt.hpp')]:
        pins[str(path.resolve())] = campaign.sha(path)
    output.mkdir(parents=True)
    archives = {}
    for index, source in enumerate(pins):
        target = output / 'source' / f'{index:04d}.py'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(source).read_bytes())
        archives[source] = str(target)
    plan = {'tests': tests, 'source_pins': pins, 'source_archive': archives,
        'hard_seconds': 180, 'automatic_retries': 0, 'scope': 'prior stage regression plus new stage tests'}
    campaign.write_new(output / 'plan.json', plan)
    token = secrets.token_hex(24)
    with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, str(Path(__file__).resolve()), '--worker',
            '--output', str(output), '--admission', token], timeout=180,
            stdout=stdout, stderr=stderr, admission=token, cwd=ROOT)
    changed = [path for path, expected in pins.items() if campaign.sha(path) != expected]
    xml = output / 'tests.xml'
    suites = list(ET.parse(xml).getroot().iter('testsuite')) if xml.exists() else []
    counts = {key: sum(int(suite.get(key, '0')) for suite in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    passed = (process['status'] == 'exited' and process['exitcode'] == 0 and not changed and bool(suites)
        and counts['failures'] == counts['errors'] == counts['skipped'] == 0)
    receipt = {'status': 'passed' if passed else 'unknown_or_failed', 'process': process,
        'source_changed': changed, 'source_pin_count': len(pins), 'counts': counts,
        'pytest_seconds': sum(float(s.get('time', '0')) for s in suites),
        'plan': campaign.reference(output / 'plan.json'), 'xml': campaign.reference(xml) if xml.exists() else None}
    campaign.write_new(output / 'receipt.json', receipt)
    print(json.dumps(receipt))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
