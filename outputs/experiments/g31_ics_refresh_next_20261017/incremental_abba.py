"""Archived request-shared versus catalog-copy ABBA, no native execution."""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    expected_admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected_admission:
        raise SystemExit('incremental_abba:missing_parent_job_admission')

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
from types import FunctionType, ModuleType

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import bounded_windows_job
from scripts.experiments.g31_ics_circulation import foundation_later_campaign as campaign

SCHEMA = 'g31.refresh_next.incremental_abba.v1'
PACKAGE = 'scripts.experiments.g31_ics_circulation'
HARD_SECONDS = 60
ORDER = ('request_shared_previous', 'catalog_copy_current', 'catalog_copy_current', 'request_shared_previous') * 2
BASE = ROOT / 'outputs/experiments/g31_ics_refresh_next_20261017'
ARCHIVE = BASE / 'preoptimization_source_001'
SOURCES = (
    ('default', ROOT / 'outputs/experiments/g31_ics_service_update_20261017/native_002/guarded_default/episode/native', ('A', 'B')),
    ('delayed', ROOT / 'outputs/experiments/g31_ics_learning_next_20261017/later_repair_001/diagnostic_absolute_return/episode/native', ('B',)),
)


def require(condition, reason):
    if not condition:
        raise ValueError('incremental_abba:' + reason)


def encoding(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoding(value).encode()).hexdigest()


def comparable(report):
    return {name: report[name] for name in ('status', 'seed', 'candidate_results')}


def known_report(report, actions):
    predictions = report.get('candidate_results', {})
    return (report.get('status') == 'conditional_current_seed'
        and report.get('seed', {}).get('status') == 'conditional_current_seed'
        and type(predictions) is dict and set(predictions) == set(actions)
        and all(type(prediction) is dict and prediction.get('status') == 'conditional_prediction'
            and type(prediction.get('completion')) is dict
            and set(prediction['completion']) == {'loaded', 'receiver', 'reuse1', 'reuse2', 'blocker'}
            and all(type(value) in (int, float) and math.isfinite(value) and value >= 0
                for value in prediction['completion'].values()) for prediction in predictions.values()))


def archived_evaluate(plan):
    modules = {}
    before = dict(sys.modules)
    for stem in ('foundation_request_context', 'foundation_later_seed'):
        reference = plan['baseline_archive']['modules'][stem]
        path = Path(reference['path'])
        require(campaign.sha(path) == reference['sha256'], 'archived_module_bytes_changed')
        module = ModuleType(PACKAGE + '.incremental_previous_' + stem)
        module.__dict__.update(__file__=str(path), __package__=PACKAGE)
        exec(compile(path.read_bytes(), str(path), 'exec'), vars(module))
        modules[stem] = module
    original = modules['foundation_later_seed'].evaluate
    namespace = dict(original.__globals__)
    namespace['request_context'] = modules['foundation_request_context']
    evaluate = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    require(all(sys.modules[name] is value for name, value in before.items()), 'existing_module_binding_mutated')
    require(all(module not in sys.modules.values() for module in modules.values()), 'private_module_registered')
    return evaluate


def check_plan(plan):
    require(plan['schema'] == SCHEMA and plan['hard_seconds'] == HARD_SECONDS
        and tuple(plan['order']) == ORDER and plan['automatic_retries'] == 0, 'fixed_protocol')
    require(all(campaign.sha(path) == expected for path, expected in plan['source_pins'].items()), 'source_bytes_changed')
    require(set(campaign.source_pins()) == set(plan['campaign_source_paths']), 'campaign_source_set_changed')
    for source in plan['inputs']:
        for name in ('raw', 'receipt'):
            require(campaign.sha(source[name]['path']) == source[name]['sha256'], 'saved_input_bytes_changed')
    baseline = plan['baseline_archive']
    require(campaign.sha(baseline['manifest']['path']) == baseline['manifest']['sha256'], 'archive_manifest_changed')
    for reference in baseline['modules'].values():
        require(campaign.sha(reference['path']) == reference['sha256'], 'archived_module_bytes_changed')


def prepare_inputs():
    result = []
    for name, directory, owners in SOURCES:
        receipt = campaign.read(directory / 'receipt.json')
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
            'closed_saved_native_input')
        raw = campaign.reference(directory / 'raw.json.gz')
        require(raw['sha256'] == receipt['raw_artifact']['sha256'], 'raw_receipt_binding')
        result.append({'name': name, 'owners': list(owners), 'raw': raw,
            'receipt': campaign.reference(directory / 'receipt.json')})
    return result


def worker(output, plan_sha):
    from scripts.experiments.g31_ics_circulation import foundation_later_seed as current_model
    output = Path(output)
    plan = campaign.read(output / 'plan.json')
    result = {'schema': SCHEMA, 'status': 'unknown', 'rows': [], 'contexts': [],
        'native_executions': 0, 'legacy_build_plus_predict_baseline_used': False,
        'complete_request_100ms_certified': False, 'independent_scene_count': 1,
        'cross_event_prediction_cache': False,
        'timing_scope': 'Saved evidence JSON detachment, evaluate including source checks, and complete output JSON detachment; excludes native collection, actor, submission, ACK, imports and report writes.',
        'baseline_source_scope': 'Both preoptimization modules restored privately from pinned archive bytes; __file__ and factory code filename identify archive files in evaluation metadata, not current production files.'}
    try:
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed')
        check_plan(plan)
        previous_evaluate = archived_evaluate(plan)
        for source in plan['inputs']:
            raw = json.loads(gzip.decompress(Path(source['raw']['path']).read_bytes()))
            for owner in source['owners']:
                matches = [row for row in raw['later_transitions'] if row['owner'] == owner]
                require(len(matches) == 1, 'one_saved_context_per_owner')
                saved = matches[0]['model_report']
                evidence = saved['seed']['evidence']
                actions = list(current_model.ACTIONS[evidence['phase']])
                require(known_report(saved, actions), 'known_saved_reference_required')
                context = source['name'] + '_' + owner
                reference_sha = digest(comparable(saved))
                for index, method in enumerate(plan['order']):
                    started = time.perf_counter_ns()
                    supplied = json.loads(json.dumps(evidence, allow_nan=False))
                    report = (previous_evaluate(supplied, actions) if method == 'request_shared_previous'
                        else current_model.evaluate(supplied, actions))
                    report = json.loads(json.dumps(report, allow_nan=False))
                    elapsed = (time.perf_counter_ns() - started) / 1e6
                    known = known_report(report, actions)
                    compared = comparable(report)
                    exact = known and encoding(compared) == encoding(comparable(saved))
                    artifact = output / (context + '_' + str(index) + '.json.gz')
                    with artifact.open('xb') as stream:
                        stream.write(gzip.compress(encoding(report).encode(), mtime=0))
                    evaluation = report.get('evaluation', {})
                    baseline_pins = evaluation.get('source_sha256', {})
                    archive_binding = method != 'request_shared_previous' or all(
                        baseline_pins.get(item['path']) == item['sha256']
                        for item in plan['baseline_archive']['modules'].values())
                    result['rows'].append({'context': context, 'owner': owner, 'at': evidence['at'],
                        'action_ids': actions, 'method': method, 'order_index': index, 'wall_ms': elapsed,
                        'current_predictions_known': known, 'saved_full_seed_and_predictions_exact': exact,
                        'result_sha256': digest(compared), 'reference_sha256': reference_sha,
                        'artifact': campaign.reference(artifact), 'evaluation': evaluation,
                        'previous_archive_file_pins_exact': archive_binding})
                    require(known and exact, 'complete_seed_and_predictions_parity:' + context)
                    require(archive_binding, 'previous_archive_filename_binding')
                    require(evaluation.get('source_exit_pins_passed') is True, 'request_source_exit_binding')
                rows = [row for row in result['rows'] if row['context'] == context]
                timings = {}
                for method in ('request_shared_previous', 'catalog_copy_current'):
                    times = [row['wall_ms'] for row in rows if row['method'] == method]
                    timings[method] = {'min_ms': min(times), 'median_ms': statistics.median(times),
                        'max_ms': max(times), 'samples': len(times)}
                result['contexts'].append({'context': context, 'timings': timings,
                    'median_ratio_previous_over_current': timings['request_shared_previous']['median_ms']
                        / timings['catalog_copy_current']['median_ms']})
        check_plan(plan)
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed_at_exit')
        result.update(status='completed_exact_incremental_comparison', source_exit_pins_passed=True)
    except Exception:
        result['exception'] = traceback.format_exc()
    campaign.write_new(output / 'report.json', result)
    return result


def launch(output):
    from scripts.experiments.g31_ics_circulation import foundation_later_seed
    output = Path(output).resolve()
    require(output.is_relative_to(BASE) and not output.exists(), 'fresh_refresh_next_output')
    manifest_path = ARCHIVE / 'manifest.json'
    manifest = campaign.read(manifest_path)
    for row in manifest['files']:
        require(campaign.sha(ARCHIVE / row['archive']) == row['sha256'], 'preoptimization_archive_changed')
    modules = {stem: campaign.reference(ARCHIVE / (stem + '.py'))
        for stem in ('foundation_request_context', 'foundation_later_seed')}
    source_pins = campaign.source_pins()
    campaign_paths = sorted(source_pins)
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT):
                source_pins[str(path)] = campaign.sha(path)
    source_pins[str(Path(__file__).resolve())] = campaign.sha(__file__)
    plan = {'schema': SCHEMA, 'hard_seconds': HARD_SECONDS, 'automatic_retries': 0, 'order': list(ORDER),
        'inputs': prepare_inputs(), 'source_pins': source_pins, 'campaign_source_paths': campaign_paths,
        'baseline_archive': {'manifest': campaign.reference(manifest_path), 'modules': modules},
        'native_executions': 0, 'python': campaign.reference(sys.executable)}
    output.mkdir(parents=True)
    campaign.write_new(output / 'plan.json', plan)
    plan_sha = campaign.sha(output / 'plan.json')
    admission = secrets.token_hex(24)
    with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
        process = bounded_windows_job.run([sys.executable, str(Path(__file__).resolve()), '--worker',
            '--output', str(output), '--plan-sha256', plan_sha, '--admission', admission],
            timeout=HARD_SECONDS, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    report_path = output / 'report.json'
    report = campaign.read(report_path) if report_path.exists() else {}
    passed = process['status'] == 'exited' and process['exitcode'] == 0
    passed = passed and report.get('status') == 'completed_exact_incremental_comparison'
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
    return 0 if result['status'] in ('completed', 'completed_exact_incremental_comparison') else 1


if __name__ == '__main__':
    raise SystemExit(main())
