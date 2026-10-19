"""Bounded public feature replay. No fitting, native loading, or outcome labels."""
from __future__ import annotations

import sys
TOKEN = 'g31_airport_public_feature_audit_v1'
if __name__ == '__main__' and '--run' in sys.argv:
    if sys.stdin.readline().strip() != TOKEN:
        raise SystemExit('airport_learning_audit:bounded_parent_admission_required')

import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
SCHEMA = 'g31.foundation.airport_public_feature_audit.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_learning_audit'


def require(value, reason):
    if not value:
        raise ValueError('airport_learning_audit:' + reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def prepare(output):
    """Metadata and SHA inventory only; do not replay rows during preparation."""
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and not output.exists(), 'fresh_workspace_output')
    collection = BASE / 'C00_cyclic_od_001'; obs = collection / 'C00/policy_observation_receipt.json'
    receipt = read(collection / 'receipt.json'); recorded = read(obs); collection_plan = read(collection / 'plan.json')
    require(receipt['status'] == 'requested_calibration_end_reached'
        and receipt['worker_report']['acceptance_status'] == 'closed_run_acceptance_passed'
        and receipt['plan_sha256_at_launch'] == sha(collection / 'plan.json'), 'closed_historical_collection')
    require(recorded['record_count'] == 946 and recorded['first_at'] == 43200. and recorded['last_at'] == 59400.
        and recorded['contains_true_conditional_outcome_labels'] is False
        and ref(recorded['artifact']['path']) == recorded['artifact'], 'frozen_actual_public_trace')
    inputs = {'trace': recorded['artifact'], 'observation_receipt': ref(obs), 'collection_receipt': ref(collection / 'receipt.json'),
        'collection_plan': ref(collection / 'plan.json'), 'acceptance': receipt['worker_report']['acceptance'],
        'mapping': ref(collection / 'airport_mapping.json'),
        'checkpoint': ref(BASE / 'B1_training_001/flight_forecaster_checkpoint.json'),
        'public_plan': ref(BASE / 'B1_training_001/public/static_flight_plan.json'),
        'B1_receipt': ref(BASE / 'B1_training_001/receipt.json')}
    historical_sources = {}
    for source, relative in collection_plan['source_archive'].items():
        path = collection / relative
        require(sha(path) == collection_plan['source_sha256'][source], 'historical_source_archive')
        historical_sources[str(path.resolve())] = sha(path)
    names = ['foundation_airport_learning_audit.py', 'foundation_airport_learning_public.py',
        'foundation_action_value.py', 'foundation_flight_forecaster.py', 'foundation_flight_context.py', 'analytic_control.py', '__init__.py']
    sources = {str(Path(__file__).with_name(name).resolve()): sha(Path(__file__).with_name(name)) for name in names}
    plan = {'schema': SCHEMA, 'status': 'prepared_not_executed', 'output': str(output), 'inputs': inputs,
        'source_sha256': sources, 'historical_collection_sources': historical_sources,
        'expected_record_count': 946, 'first_at': 43200., 'last_at': 59400., 'episode_end': 59400.,
        'soft_wall_seconds': 240, 'native_branches': 0, 'fit_calls': 0, 'outcome_labels_created': 0,
        'observed_counts': None, 'forecast_mode': 'frozen_B1_prior_only_static_plan',
        'future_global_result_read': False, 'training_or_test_selection': False,
        'scope': 'Historical native027 cyclic C00 public callback compatibility, not native028 benefit or training data readiness.'}
    output.mkdir(parents=True); write(output / 'plan.json', plan)
    spec = {'task_id': output.name, 'module': MODULE, 'args': ['--run', '--output', str(output)],
        'native_branches': 0, 'hard_seconds': 270, 'inner_admission': TOKEN,
        'sources': [*sources, *historical_sources, *(item['path'] for item in inputs.values()), str(output / 'plan.json')],
        'requires': [], 'assessment': {'path': str(output / 'receipt.json'), 'allowed_statuses': ['completed_public_feature_audit']},
        'next_action': 'Review actual public feature compatibility and unknown coverage; no labels, training or native consumption are implied.'}
    write(output.parent / (output.name + '_task.json'), spec)
    return plan


def validate_plan(plan):
    require(plan['schema'] == SCHEMA and plan['native_branches'] == plan['fit_calls'] == plan['outcome_labels_created'] == 0
        and plan['expected_record_count'] == 946 and plan['soft_wall_seconds'] == 240
        and plan['observed_counts'] is None and plan['episode_end'] == 59400., 'fixed_public_only_audit')
    for path, expected in {**plan['source_sha256'], **plan['historical_collection_sources']}.items():
        require(sha(path) == expected, 'source_bytes')
    for item in plan['inputs'].values():
        require(ref(item['path']) == item, 'input_bytes')


def project(forecast, mapping):
    """Independent push-forward of the frozen public role weights only."""
    require(mapping['schema'] == 'g31.foundation.airport_role_mapping.v2'
        and mapping['version'] == 'airport151_std8_pushforward92to95_gtc3_v2'
        and mapping['sha256'] == digest({key: value for key, value in mapping.items() if key != 'sha256'}), 'mapping_identity')
    regions = tuple('legacy_start_' + str(i) for i in (0,1,2,3,4,5,53))
    require(set(mapping['regions']) == set(forecast['new_demand_mean_by_region']) == set(regions), 'mapping_source_domain')
    count = len(forecast['bin_edges_seconds']) - 1
    nodes = sorted({node for row in mapping['regions'].values() for node in row['nodes']})
    values = {'airport_node_' + str(node): [0.]*count for node in nodes}; missing = dict.fromkeys(values, False)
    original = [0.]*count
    for region in regions:
        row = mapping['regions'][region]
        expected_nodes = [134,136,138] if region == 'legacy_start_53' else [0,24,26,49,57,95,149]
        expected_weights = [1/3]*3 if region == 'legacy_start_53' else [1/8,1/8,1/8,1/8,1/8,2/8,1/8]
        require(row['nodes'] == expected_nodes and row['weights'] == expected_weights, 'predeclared_role_prior')
        absent = forecast['missing_mask_by_region'][region]
        require(type(absent) is bool, 'missing_boolean')
        for node in row['nodes']:
            missing['airport_node_' + str(node)] |= absent
        if absent:
            continue
        for index, mass in enumerate(forecast['new_demand_mean_by_region'][region]):
            require(type(mass) in (int,float) and math.isfinite(mass) and mass >= 0, 'finite_expected_mass')
            original[index] += mass
            for node, weight in zip(row['nodes'], row['weights'], strict=True):
                values['airport_node_' + str(node)][index] += mass*weight
    require(all(abs(math.fsum(row[i] for row in values.values())-total) <= 1e-12*max(1.,total)
        for i,total in enumerate(original)), 'known_mass_conservation')
    for key in values:
        if missing[key]:
            values[key] = [None]*count
    result = copy.deepcopy(forecast)
    result.update(new_demand_mean_by_region=values, missing_mask_by_region=missing,
        mapping_version=mapping['version'], source_regional_forecast_sha256=digest(forecast),
        airport_mapping_sha256=mapping['sha256'], uncertainty_by_region={key:None for key in values},
        window_summaries_by_region={}, node_uncertainty_status='unknown_dependent_projection')
    return result


def run(output):
    output = Path(output); plan = read(output / 'plan.json'); validate_plan(plan)
    started = time.monotonic(); deadline = started + plan['soft_wall_seconds']; counts = Counter(); failures = []; samples = []
    report = {'schema': SCHEMA, 'status': 'failed_public_feature_audit', 'plan': ref(output / 'plan.json'),
        'native_branches': 0, 'fit_calls': 0, 'outcome_labels_created': 0}
    try:
        from . import foundation_airport_learning_public as public
        from . import foundation_action_value as value
        from . import foundation_flight_forecaster as forecaster
        model = forecaster.validate_checkpoint(read(plan['inputs']['checkpoint']['path']))
        static_plan = read(plan['inputs']['public_plan']['path']); mapping = read(plan['inputs']['mapping']['path'])
        require(static_plan['availability_basis'] == 'static_predeclared' and static_plan['received_at'] == 0., 'explicit_plan_availability_assumption')
        stream_path = output / 'public_feature_rows.jsonl.gz'
        with gzip.open(plan['inputs']['trace']['path'], 'rt', encoding='utf8') as source, gzip.open(stream_path, 'xt', encoding='utf8') as target:
            for line in source:
                require(time.monotonic() < deadline, 'audit_wall_budget')
                row = json.loads(line); counts['records'] += 1
                require(row['sequence'] == counts['records']-1 and plan['first_at'] <= row['now'] <= plan['last_at'], 'actual_sequence_time')
                result = {'sequence':row['sequence'], 'now':row['now'], 'owner':row['owner_id'], 'observation_sha256':digest(row['observation']),
                          'target_value':None, 'label_status':'no_actual_candidate_outcome_label', 'status':'rejected_public_feature_input'}
                counts['recorded_proposals'] += len(row['decision']['intents'])
                try:
                    context = copy.deepcopy(static_plan); context['owner_scope'] = row['owner_id']
                    counts['B1_forward_attempts'] += 1
                    regional = forecaster.predict(context, model, now=row['now'], owner=row['owner_id'], observed_counts=None)
                    counts['B1_forward_calls'] += 1
                    projected = project(regional, mapping)
                    wrapped, audit = public.wrap_record(row, projected, episode_id='C00_cyclic_od_001', episode_end=plan['episode_end'])
                    candidates = public.proposal_actions(row)
                    vectors = [{'action':candidate, 'features':value.features(wrapped, candidate['semantic'])} for candidate in candidates]
                    counts['valid_records'] += 1; counts['feature_vectors'] += len(vectors)
                    counts['records_with_current_free'] += bool(wrapped['circulation_accounts']['current_free_trays'])
                    result.update(status='public_features_verified_no_labels', forecast_sha256=digest(projected),
                        forecast_information_cutoffs=projected['information_cutoffs'], wrapped_observation_sha256=digest(wrapped),
                        accounts_audit=audit, candidates=vectors)
                    if vectors and len(samples) < 3:
                        samples.append({'sequence':row['sequence'],'wrapped_observation':wrapped,'candidate':candidates[0]})
                except (KeyError, ValueError, TypeError, OverflowError) as error:
                    counts['rejected_records'] += 1; failures.append({'sequence':row['sequence'],'reason':str(error)})
                    result['reason'] = str(error)
                target.write(json.dumps(result, separators=(',', ':'), allow_nan=False)+'\n')
        require(counts['records'] == plan['expected_record_count'], 'complete_registered_trace')
        validate_plan(plan)
        write(output / 'samples.json', samples)
        report.update(status='completed_public_feature_audit', counts=dict(counts), failures=failures,
            feature_rows=ref(stream_path), samples=ref(output / 'samples.json'), source_exit_pins_passed=True,
            unknown_inbound_or_outbound_not_imputed=True, prediction_is_not_outcome_label=True,
            actual_training_ready=False, native_action_consumption_tested=False,
            claim='Frozen B1 forwards and legal public action features only; proposed actions still need actual selection/guard/ACK/effect/reward binding.')
    except Exception:
        report.update(exception=traceback.format_exc(), counts=dict(counts), failures=failures)
    report['wall_seconds'] = time.monotonic()-started
    write(output / 'receipt.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__); group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true'); group.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path, required=True); args=parser.parse_args()
    result = prepare(args.output) if args.prepare else run(args.output)
    print(json.dumps({'status':result['status'], 'native_branches':0, 'fit_calls':0}))
    return 0 if result['status'] in ('prepared_not_executed','completed_public_feature_audit') else 1


if __name__ == '__main__':
    raise SystemExit(main())
