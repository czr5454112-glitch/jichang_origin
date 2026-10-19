"""Same bounded public replay with the independently verified array predictor.

The frozen B1 and original audit modules remain unchanged. No native, fitting,
outcome labels, cross-call prediction cache, or private index reads occur here.
"""
from __future__ import annotations

import sys
TOKEN = 'g31_airport_public_feature_audit_arrays_v1'
if __name__ == '__main__' and '--run' in sys.argv:
    if sys.stdin.readline().strip() != TOKEN:
        raise SystemExit('airport_learning_audit_arrays:bounded_parent_admission_required')

import argparse
from collections import Counter
import copy
import gzip
import json
from pathlib import Path
import time
import traceback

from . import foundation_airport_learning_audit as original
from . import foundation_flight_forecaster as frozen_forecaster
from . import foundation_flight_forecaster_arrays as arrays

ROOT, BASE = original.ROOT, original.BASE
SCHEMA = 'g31.foundation.airport_public_feature_audit_arrays.v1'
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_learning_audit_arrays'
require, sha, read, ref = original.require, original.sha, original.read, original.ref
digest, write, project = original.digest, original.write, original.project
PARITY_STATUS = 'completed_exact_saved_forecast_and_B2_parity'
METHOD_COUNTS = {'flight_prior_only':134, 'flight_synthetic_observed_counts':134, 'no_plan_recent_rate':134}


def validate_parity(receipt, validation, inputs):
    """Completed full-output evidence, bound to this exact runtime and inputs."""
    require(receipt['status'] == PARITY_STATUS and receipt['completed_saved_forecasts'] == 402
        and receipt['saved_parity_by_method'] == METHOD_COUNTS
        and receipt['AST_exact_except_array_materialization'] is True
        and receipt['source_exit_pins_passed'] is True
        and receipt['native_branches'] == receipt['fit_calls'] == receipt['new_training_labels'] == 0
        and receipt['no_training_or_test_selection'] is True and receipt['cross_call_cache'] is False
        and receipt['native_execution_authority'] is False, 'completed_exact_array_validation')
    rows = receipt['B2_rows']
    require([r['sequence'] for r in rows] == [0,473,945]
        and all(r['exact_forecast_and_features_bytes'] is True for r in rows), 'three_actual_B2_full_byte_checks')
    require(validation['schema'] == 'g31.flight_arrays_exact_saved_parity.v1'
        and validation['expected_saved_forecasts'] == 402 and validation['B2_sequences'] == [0,473,945]
        and validation['native_branches'] == validation['fit_calls'] == 0
        and validation['cross_call_cache'] is False, 'exact_validation_scope')
    require(receipt['plan'] == inputs['array_validation_plan'], 'completed_validation_plan_binding')
    for key in ('checkpoint', 'public_plan', 'trace', 'mapping'):
        require(validation['inputs'][key] == inputs[key], 'validation_same_' + key)
    for module in (arrays, frozen_forecaster, original):
        path = str(Path(module.__file__).resolve())
        require(validation['sources'].get(path) == sha(path), 'validated_runtime_source_bytes')


def prepare(output, *, parity_receipt=None):
    """Pin closed validation first, then retain the original 946-row budget."""
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and not output.exists(), 'fresh_workspace_output')
    parity_receipt = Path(parity_receipt or BASE/'B2_arrays_validation_001/receipt.json').resolve()
    receipt = read(parity_receipt)
    validation_ref = receipt['plan']; require(ref(validation_ref['path']) == validation_ref, 'closed_validation_plan_bytes')
    validation = read(validation_ref['path'])
    previous_path = BASE/'B2_public_feature_audit_002/plan.json'
    previous = read(previous_path); original.validate_plan(previous)
    plan = copy.deepcopy(previous)
    plan['inputs'].update(array_validation_receipt=ref(parity_receipt), array_validation_plan=validation_ref,
        original_audit_plan=ref(previous_path))
    validate_parity(receipt, validation, plan['inputs'])
    require(all(sha(path) == expected for path, expected in validation['sources'].items()), 'closed_validation_source_bytes')
    sources = {**previous['source_sha256'], **validation['sources'], str(Path(__file__).resolve()):sha(__file__)}
    plan.update(schema=SCHEMA, status='prepared_not_executed', output=str(output), source_sha256=sources,
        predictor_implementation=arrays.VERSION, same_original_replay_rules=True,
        scope='Historical native027 cyclic C00 public compatibility using exact-equivalent per-call arrays; no native028 benefit or training readiness claim.')
    validate_plan(plan)
    output.mkdir(parents=True); write(output/'plan.json', plan)
    task = {'task_id':output.name, 'module':MODULE, 'args':['--run','--output',str(output)],
        'native_branches':0, 'hard_seconds':270, 'inner_admission':TOKEN,
        'sources':[*sources,*plan['historical_collection_sources'],*(item['path'] for item in plan['inputs'].values()),str(output/'plan.json')],
        'requires':[], 'assessment':{'path':str(output/'receipt.json'),'allowed_statuses':['completed_public_feature_audit']},
        'next_action':'Review complete public compatibility and unknown coverage; no labels, fitting or native consumption are implied.'}
    write(output.parent/(output.name+'_task.json'), task)
    return plan


def validate_plan(plan):
    require(plan['schema'] == SCHEMA and plan['predictor_implementation'] == arrays.VERSION
        and plan['same_original_replay_rules'] is True, 'fixed_array_replay_implementation')
    original.validate_plan({**plan, 'schema':original.SCHEMA})
    validate_parity(read(plan['inputs']['array_validation_receipt']['path']),
        read(plan['inputs']['array_validation_plan']['path']), plan['inputs'])


def run(output):
    output = Path(output); plan = read(output / 'plan.json'); validate_plan(plan)
    started = time.monotonic(); deadline = started + plan['soft_wall_seconds']; counts = Counter(); failures = []; samples = []
    report = {'schema': SCHEMA, 'status': 'failed_public_feature_audit', 'plan': ref(output / 'plan.json'),
        'native_branches': 0, 'fit_calls': 0, 'outcome_labels_created': 0}
    try:
        from . import foundation_airport_learning_public as public
        from . import foundation_action_value as value
        from . import foundation_flight_forecaster_arrays as forecaster
        model = frozen_forecaster.validate_checkpoint(read(plan['inputs']['checkpoint']['path']))
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
    parser = argparse.ArgumentParser(description=__doc__); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true'); group.add_argument('--run',action='store_true')
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--parity-receipt',type=Path)
    args = parser.parse_args()
    result = prepare(args.output,parity_receipt=args.parity_receipt) if args.prepare else run(args.output)
    print(json.dumps({'status':result['status'],'native_branches':0,'fit_calls':0}))
    return 0 if result['status'] in ('prepared_not_executed','completed_public_feature_audit') else 1


if __name__ == '__main__': raise SystemExit(main())
