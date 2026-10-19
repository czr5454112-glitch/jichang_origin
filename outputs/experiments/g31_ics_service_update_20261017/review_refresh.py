"""Saved evidence pairing audit; repeated data is not a fresh observation."""
import sys

if '--worker' in sys.argv:
    if sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission') + 1]:
        raise SystemExit('missing_parent_job_admission')

import copy
import gzip
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import bounded_windows_job
from scripts.experiments.g31_ics_circulation import foundation_later_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_service_refresh as refresh

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / 'refresh_audit_001'
CURRENT = BASE / 'native_002/guarded_default/episode/native/raw.json.gz'
PREVIOUS = ROOT / 'outputs/experiments/g31_ics_learning_next_20261017/later_episodes_001/guarded_default/episode/native/raw.json.gz'


def records(path):
    raw = json.loads(gzip.decompress(path.read_bytes()))
    return {row['owner']: refresh.make_record(row['model_report']['seed']['evidence'],
        episode_id=campaign.sha(path), original_reference_sha256=row['initial_reference_sha256'])
        for row in raw['later_transitions']}


def worker():
    plan = campaign.read(OUTPUT / 'plan.json')
    assert all(campaign.sha(path) == expected for path, expected in plan['pins'].items())
    current, previous = records(CURRENT), records(PREVIOUS)
    cases = [
        ('duplicate_A', current['A'], current['A'], None, 'unchanged_revalidated'),
        ('duplicate_B', current['B'], current['B'], None, 'unchanged_revalidated'),
        ('old_snapshot_with_later_clock', current['B'], current['B'], current['B']['evidence']['at'] + .1, 'unknown'),
        ('separate_actual_episodes', previous['B'], current['B'], None, 'unknown'),
        ('separate_owners_same_episode', current['A'], current['B'], None, 'unknown'),
    ]
    rows = []
    for name, before, after, epoch, expected in cases:
        result = refresh.refresh_audit(before, after, audit_at=epoch)
        rows.append({'case': name, 'expected_status': expected, 'result': result,
            'passed': result['status'] == expected and not result['cache_execution_authorized']
                      and not result['native_computation_reduced'] and result['prediction_calls'] == 0})
    unchanged = all(campaign.sha(path) == expected for path, expected in plan['pins'].items())
    report = {'status': 'passed_saved_refresh_invalidation_checks' if unchanged and all(row['passed'] for row in rows) else 'unknown_failed',
        'rows': rows, 'source_exit_pins_passed': unchanged, 'native_executions': 0,
        'actual_same_owner_two_fresh_later_contexts_available': False,
        'cross_event_saved_calls_avoided': 0, 'local_suffix_repair_verified': False,
        'scope': 'Two duplicate supplied contexts and three explicit refusal cases; not fresh live monitoring or cache savings.'}
    campaign.write_new(OUTPUT / 'report.json', report)
    return 0 if report['status'] == 'passed_saved_refresh_invalidation_checks' else 1


def launch():
    OUTPUT.mkdir(exist_ok=False)
    pins = campaign.source_pins()
    for path in (CURRENT, PREVIOUS, Path(__file__).resolve()):
        pins[str(path)] = campaign.sha(path)
    campaign.write_new(OUTPUT / 'plan.json', {'pins': pins, 'hard_seconds': 60, 'automatic_retries': 0})
    admission = secrets.token_hex(24)
    with (OUTPUT / 'stdout.log').open('x') as stdout, (OUTPUT / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, str(Path(__file__).resolve()), '--worker',
            '--admission', admission], timeout=60, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    report_path = OUTPUT / 'report.json'
    report = campaign.read(report_path) if report_path.exists() else {}
    campaign.write_new(OUTPUT / 'receipt.json', {'process': process, 'status': report.get('status', 'unknown'),
        'report': campaign.reference(report_path) if report_path.exists() else None})
    print(json.dumps({'process': process, 'status': report.get('status')}))
    return 0 if process['exitcode'] == 0 and report.get('status') == 'passed_saved_refresh_invalidation_checks' else 1


if __name__ == '__main__':
    raise SystemExit(worker() if '--worker' in sys.argv else launch())
