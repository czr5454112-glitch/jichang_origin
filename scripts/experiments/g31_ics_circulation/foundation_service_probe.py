"""Bounded saved-current-state ABBA comparison, not a live timing certificate."""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    expected_admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected_admission:
        raise SystemExit('service_probe:missing_parent_job_admission')

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import secrets
import statistics
import time
import traceback

from . import bounded_windows_job
from . import foundation_later_campaign as campaign

ROOT = campaign.ROOT
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_service_probe'
SCHEMA = 'g31.foundation.service_probe.v1'
HARD_SECONDS = 60
ORDER = ('legacy', 'request_shared', 'request_shared', 'legacy') * 2
PREFIX = ROOT / 'outputs/experiments/g31_ics_learning_next_20261017'
SOURCES = (
    ('default', PREFIX / 'later_episodes_001/guarded_default/episode/native', ('A', 'B')),
    ('delayed', PREFIX / 'later_repair_001/diagnostic_absolute_return/episode/native', ('B',)),
)


def require(condition, reason):
    if not condition:
        raise ValueError('service_probe:' + reason)


def encoding(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoding(value).encode()).hexdigest()


def check_plan(plan):
    require(plan['schema'] == SCHEMA and plan['hard_seconds'] == HARD_SECONDS
        and tuple(plan['order']) == ORDER and plan['automatic_retries'] == 0, 'fixed_protocol')
    require(campaign.source_pins() == plan['source_pins'], 'source_set_or_bytes_changed')
    for source in plan['inputs']:
        for name in ('raw', 'receipt'):
            item = source[name]
            require(campaign.sha(item['path']) == item['sha256'], 'saved_input_bytes_changed')


def inputs():
    result = []
    for name, directory, owners in SOURCES:
        receipt = campaign.read(directory / 'receipt.json')
        require(receipt['run_acceptance_status'] == 'closed_run_acceptance_passed'
            and receipt['status'] == 'assessed', 'closed_source_required')
        raw = campaign.reference(directory / 'raw.json.gz')
        require(receipt['raw_artifact']['sha256'] == raw['sha256'], 'raw_receipt_binding')
        result.append({'name': name, 'owners': list(owners), 'raw': raw,
                       'receipt': campaign.reference(directory / 'receipt.json')})
    return result


def legacy(model, evidence, actions):
    seed = model.build_seed(evidence)
    predictions = {action: model.predict(seed, action) for action in actions}
    return {'status': seed['status'], 'seed': seed, 'candidate_results': predictions}


def comparable(report):
    return {name: report[name] for name in ('status', 'seed', 'candidate_results')}


def known_report(report, actions):
    if type(report) is not dict or type(report.get('seed')) is not dict:
        return False
    predictions = report.get('candidate_results', {})
    return (report.get('status') == 'conditional_current_seed'
        and report.get('seed', {}).get('status') == 'conditional_current_seed'
        and type(predictions) is dict
        and set(predictions) == set(actions)
        and all(type(prediction) is dict and prediction.get('status') == 'conditional_prediction'
            and type(prediction.get('completion')) is dict
            and set(prediction['completion']) == {'loaded', 'receiver', 'reuse1', 'reuse2', 'blocker'}
            and all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                    for value in prediction['completion'].values())
            for prediction in predictions.values()))


def worker(output, plan_sha):
    from . import foundation_later_seed as model
    output = Path(output)
    plan = campaign.read(output / 'plan.json')
    result = {'schema': SCHEMA, 'status': 'unknown', 'rows': [], 'contexts': [],
        'native_executions': 0, 'complete_request_100ms_certified': False,
        'timing_scope': 'Saved evidence copy, source checks where implemented, all seed/prediction work and JSON detachment; excludes native collection, actor, submit, ACK, startup and report writes.',
        'independent_scene_count': 1, 'cross_event_prediction_cache': False}
    try:
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed')
        check_plan(plan)
        for source in plan['inputs']:
            raw = json.loads(gzip.decompress(Path(source['raw']['path']).read_bytes()))
            for owner in source['owners']:
                matches = [row for row in raw['later_transitions'] if row['owner'] == owner]
                require(len(matches) == 1, 'one_saved_current_context_per_owner')
                saved = matches[0]['model_report']
                evidence = saved['seed']['evidence']
                actions = model.ACTIONS[evidence['phase']]
                require(known_report(saved, actions), 'known_saved_reference_required')
                context = source['name'] + '_' + owner
                reference_sha = digest(comparable(saved))
                for index, method in enumerate(plan['order']):
                    started = time.perf_counter_ns()
                    supplied = json.loads(json.dumps(evidence, allow_nan=False))
                    report = (legacy(model, supplied, actions) if method == 'legacy'
                              else model.evaluate(supplied, actions))
                    report = json.loads(json.dumps(report, allow_nan=False))
                    elapsed = (time.perf_counter_ns() - started) / 1e6
                    current_known = known_report(report, actions)
                    comparable_result = comparable(report) if all(
                        name in report for name in ('status', 'seed', 'candidate_results')) else None
                    exact = current_known and encoding(comparable_result) == encoding(comparable(saved))
                    artifact = output / (context + '_' + str(index) + '.json.gz')
                    with artifact.open('xb') as stream:
                        stream.write(gzip.compress(encoding(report).encode(), mtime=0))
                    result['rows'].append({'context': context, 'owner': owner, 'at': evidence['at'],
                        'method': method, 'order_index': index, 'wall_ms': elapsed,
                        'current_predictions_known': current_known,
                        'saved_full_seed_and_predictions_exact': exact,
                        'result_sha256': digest(comparable_result) if comparable_result is not None else None,
                        'reference_sha256': reference_sha, 'artifact': campaign.reference(artifact),
                        'evaluation': report.get('evaluation')})
                    require(current_known, 'known_current_predictions_required')
                    require(exact, 'complete_saved_prediction_parity:' + context)
                context_rows = [row for row in result['rows'] if row['context'] == context]
                times = {method: [row['wall_ms'] for row in context_rows if row['method'] == method]
                         for method in ('legacy', 'request_shared')}
                summary = {method: {'min_ms': min(values), 'median_ms': statistics.median(values),
                    'max_ms': max(values), 'samples': len(values)} for method, values in times.items()}
                summary['median_ratio_legacy_over_shared'] = summary['legacy']['median_ms'] / summary['request_shared']['median_ms']
                result['contexts'].append({'context': context, 'timings': summary})
        check_plan(plan)
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed_at_exit')
        result.update(status='completed_exact_saved_comparison', source_exit_pins_passed=True)
    except Exception:
        result['exception'] = traceback.format_exc()
    campaign.write_new(output / 'report.json', result)
    return result


def launch(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and output != ROOT and not output.exists(), 'fresh_workspace_output')
    plan = {'schema': SCHEMA, 'hard_seconds': HARD_SECONDS, 'automatic_retries': 0,
        'order': list(ORDER), 'inputs': inputs(), 'source_pins': campaign.source_pins(),
        'native_executions': 0, 'python': campaign.reference(sys.executable)}
    output.mkdir(parents=True, exist_ok=False)
    campaign.write_new(output / 'plan.json', plan)
    plan_sha = campaign.sha(output / 'plan.json')
    admission = secrets.token_hex(24)
    with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, '-m', MODULE, '--worker', '--output', str(output),
            '--plan-sha256', plan_sha, '--admission', admission], timeout=HARD_SECONDS,
            stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    report_path = output / 'report.json'
    report = campaign.read(report_path) if report_path.exists() else {}
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and report.get('status') == 'completed_exact_saved_comparison'
    try:
        check_plan(plan)
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed_after_worker')
    except Exception:
        passed = False
    receipt = {'status': 'completed' if passed else 'unknown_failed', 'process': process,
        'report': campaign.reference(report_path) if report_path.exists() else None,
        'plan': campaign.reference(output / 'plan.json'), 'native_executions': 0}
    campaign.write_new(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    result = worker(args.output, args.plan_sha256) if args.worker else launch(args.output)
    print(json.dumps({'status': result['status']}))
    return 0 if result['status'] in ('completed', 'completed_exact_saved_comparison') else 1


if __name__ == '__main__':
    raise SystemExit(main())
