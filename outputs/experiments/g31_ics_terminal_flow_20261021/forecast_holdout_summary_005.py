"""Verify and pool four closed source005 C00 DEV holdouts; no prediction or fit.

Only small saved evaluation records and metadata are opened. Native observation,
ACK, decision and arrival tapes are not opened or rehashed. Re-scoring uses the
SHA-bound frozen005 scorer, and therefore is not an independent label audit.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'outputs/experiments/g31_ics_terminal_flow_20261021'
CYCLE = ROOT / 'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
SOURCE = CYCLE / 'sources/terminal_flow_runtime_005'
MANIFEST = SOURCE / 'source_manifest.json'
SOURCE_SHA = '22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef'
MODEL = DATA / 'forecast_full_train_001/model.json'
MODEL_SHA = 'c2d00b588272e0df52e672c607983df6b9b43ff7c761084eba4f044dc8f4834d'
FIT = CYCLE / 'terminal_flow/workflow_005/training_fit_receipt.json'
SCHEMA = 'g31.terminal_demand_four_parent_DEV_summary.v1'
EVAL_SCHEMA = 'g31.terminal_demand_saved_public_DEV_evaluation.v1'
PARENTS = (2201, 2202, 2203, 2204)
ORIGINS = tuple(range(7200, 57601, 1800))
METHODS = ('TF-B1-300', 'TF-predictor')
WINDOWS = ('300', '900', '1800')
PERIODS = ((7200, 18000), (18000, 36000), (36000, 59400))
TRAIN_IDS = [f'joint_reposition_group_plan_20261021:{seed}:r0' for seed in (2101, 2102)]
PRODUCERS = (
    'foundation_airport_terminal_forecast_holdout.py', 'foundation_airport_joint_calendar_prepared.py',
    'foundation_airport_terminal_forecast.py', 'foundation_airport_terminal_predictor.py',
    'foundation_airport_terminal_support_predictor.py', 'foundation_airport_joint_calendar.py',
    'foundation_airport_loader_mapping.py', 'foundation_flight_forecaster.py',
    'foundation_flight_forecaster_arrays.py', 'foundation_flight_context.py',
    'foundation_airport_feasible_domain.py', 'foundation_airport_flight.py',
    'foundation_airport_calendar_forecast.py', 'foundation_airport_learning_public.py',
    'foundation_airport_terminal_forecast_evaluation.py', 'foundation_airport_terminal_prediction_audit.py')
SCORE_FILES = ('foundation_airport_terminal_forecast.py', 'foundation_airport_terminal_predictor.py',
               'foundation_airport_terminal_support_predictor.py')
SUM_FIELDS = ('count', 'skipped_common_missing', 'absolute_error_sum', 'squared_error_sum',
              'signed_error_sum', 'actual_sum', 'predicted_sum')
SCRIPT_REL = Path('scripts/experiments/g31_ics_circulation')
SMALL_LIMIT = 2 * 1024**2
RECORD_COMPRESSED_LIMIT = 8 * 1024**2
RECORD_EXPANDED_LIMIT = 32 * 1024**2


def need(ok, reason):
    if not ok:
        raise ValueError('forecast_holdout_summary:' + reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def ref(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def same_ref(a, b):
    return (Path(a['path']).resolve() == Path(b['path']).resolve() and a['sha256'] == b['sha256'])


def parsed(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate_json_key:' + key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('forecast_holdout_summary:nonfinite_json:' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


class Inputs:
    """Finite, small-file entry/exit bindings; no implicit recursive references."""
    def __init__(self):
        self.bindings = {}

    def capture(self, path, *, expected=None, limit=SMALL_LIMIT):
        path = Path(path).resolve()
        need(path.is_file() and path.stat().st_size <= limit, 'small_input_required:' + str(path))
        actual = ref(path)
        if expected is not None:
            need(same_ref(actual, expected), 'input_binding_changed:' + str(path))
            if 'bytes' in expected:
                need(actual['bytes'] == expected['bytes'], 'input_size_changed:' + str(path))
        if str(path) in self.bindings:
            need(actual == self.bindings[str(path)], 'input_changed_during_read:' + str(path))
        self.bindings[str(path)] = actual
        return actual

    def read(self, path, *, expected=None, records=False):
        binding = self.capture(path, expected=expected,
                               limit=RECORD_COMPRESSED_LIMIT if records else SMALL_LIMIT)
        path = Path(binding['path'])
        if records:
            need(path.name == 'evaluation_records.json.gz', 'only_small_evaluation_records_gzip')
            with gzip.open(path, 'rb') as stream:
                raw = stream.read(RECORD_EXPANDED_LIMIT + 1)
            need(len(raw) <= RECORD_EXPANDED_LIMIT, 'expanded_records_limit')
        else:
            raw = path.read_bytes()
        return parsed(raw)

    def bound(self, binding, expected_path):
        need(Path(binding['path']).resolve() == Path(expected_path).resolve(), 'unexpected_bound_input_path')
        return self.read(expected_path, expected=binding)

    def verify_exit(self):
        for binding in self.bindings.values():
            path = Path(binding['path'])
            need(path.stat().st_size == binding['bytes'] and sha(path) == binding['sha256'],
                 'exit_binding_changed:' + str(path))


def load_scorers(inputs):
    manifest = inputs.read(MANIFEST, expected=dict(path=str(MANIFEST), sha256=SOURCE_SHA))
    need(Path(manifest['root']).resolve() == SOURCE.resolve(), 'source005_root')
    # Only these three stdlib-only modules execute in an isolated package.
    for name in SCORE_FILES:
        relative = (SCRIPT_REL / name).as_posix()
        inputs.capture(SOURCE / relative, expected=dict(path=str(SOURCE / relative), sha256=manifest['files'][relative]))
    package_name = '_terminal_holdout_summary_frozen005'
    for name in list(sys.modules):
        if name == package_name or name.startswith(package_name + '.'):
            del sys.modules[name]
    package = types.ModuleType(package_name)
    package.__path__ = [str(SOURCE / SCRIPT_REL)]
    sys.modules[package_name] = package
    modules = [importlib.import_module(package_name + '.' + name[:-3]) for name in SCORE_FILES]
    need(all(Path(module.__file__).resolve() == (SOURCE / SCRIPT_REL / name).resolve()
             for module, name in zip(modules, SCORE_FILES)), 'frozen_scorer_import_origin')
    return manifest, modules


def verify_producers(bindings, manifest, inputs, *, exact_names=None):
    if exact_names is not None:
        need(set(bindings) == set(exact_names), 'complete_prediction_producer_roster')
    for name, binding in bindings.items():
        relative = SCRIPT_REL / name
        need(Path(name).name == name and relative.as_posix() in manifest['files'], 'producer_in_manifest')
        need(Path(binding['path']).resolve() in ((ROOT / relative).resolve(), (SOURCE / relative).resolve()),
             'producer_source_path')
        need(binding['sha256'] == manifest['files'][relative.as_posix()], 'producer_source005_bytes')
        inputs.capture(binding['path'], expected=binding)


def model_contract(model, supported):
    supported.validate_model(model)
    base = model['base_calibration']
    need(base['training_row_count'] == 580 and base['train_parent_ids'] == TRAIN_IDS,
         'exact_580_TRAIN_2101_2102')
    need(len(base['parameters']) == 10 and all(p['windows'] == 58 for p in base['parameters'].values()),
         'ten_stations_58_mature_training_windows')
    need(base['bin_edges_seconds'] == [0., 300., 600., 900., 1200., 1500., 1800.], 'fixed_300_grid')
    need(all(intervals == [[7200., 59400.]] for intervals in model['support_by_station'].values()),
         'full_mature_TRAIN_support')
    return base


def verify_model(model_path, manifest, modules, inputs):
    need(Path(model_path).resolve() == MODEL.resolve(), 'registered_full_model_path')
    model = inputs.read(MODEL, expected=dict(path=str(MODEL), sha256=MODEL_SHA))
    base = model_contract(model, modules[2])
    fit = inputs.read(FIT)
    need(fit['schema'] == 'g31.terminal_demand_complete_TRAIN_fit.v1' and fit['row_count'] == 580
         and fit['native_starts'] == 0 and fit['model_sha256'] == model['sha256'], 'full_TRAIN_fit_receipt')
    need(same_ref(fit['model'], inputs.bindings[str(MODEL.resolve())]), 'fit_model_file_binding')
    provenance = inputs.bound(fit['provenance'], MODEL.parent / 'provenance.json')
    need(provenance['row_count'] == 580 and provenance['model_sha256'] == model['sha256']
         and provenance['training_labels_sha256'] == base['training_labels_sha256']
         and provenance['common_time_support'] == [7200., 59400.]
         and provenance['DEV_or_TEST_labels_read'] is False and provenance['native_starts'] == 0
         and provenance['producer_sources_unchanged'] is True, 'fit_provenance_contract')
    need(sorted(s['parent']['parent_seed'] for s in provenance['sources']) == [2101, 2102], 'fit_two_TRAIN_parents')
    for source in provenance['sources']:
        need(source['parent']['split'] == 'train' and source['end'] == 59400.
             and same_ref(source['source_bundle'], inputs.bindings[str(MANIFEST.resolve())]), 'fit_source005_full_TRAIN')
    verify_producers(provenance['source_files'], manifest, inputs)
    return model, base, provenance


def close_values(actual, expected, reason):
    if isinstance(expected, dict):
        need(isinstance(actual, dict) and set(actual) == set(expected), reason + ':keys')
        for key, value in expected.items():
            close_values(actual[key], value, reason + ':' + str(key))
    elif isinstance(expected, list):
        need(isinstance(actual, list) and len(actual) == len(expected), reason + ':list')
        for index, value in enumerate(expected):
            close_values(actual[index], value, reason + ':' + str(index))
    elif type(expected) is float:
        need(type(actual) in (int, float) and math.isfinite(actual)
             and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-8), reason + ':number')
    else:
        need(type(actual) == type(expected) and actual == expected, reason + ':value')


def record_contract(records, plan, provenance, model, base, demand):
    need(isinstance(records, list) and len(records) == 29, '29_origins_required')
    parent, stations = plan['parent'], set(base['parameters'])
    origins = []
    for record in records:
        need(record['split'] == 'dev' and record['parent_id'] == parent['parent_group'], 'record_DEV_parent')
        need(set(record['predictions']) == set(METHODS), 'two_fixed_prediction_methods')
        raw, predicted = (record['predictions'][method] for method in METHODS)
        origin = raw['forecast_origin']; origins.append(origin)
        for forecast in (raw, predicted):
            need(forecast['forecast_origin'] == origin and set(forecast['new_demand_mean_by_region']) == stations
                 and forecast['bin_edges_seconds'] == base['bin_edges_seconds'], 'same_fixed_grid_station_origin')
            calendar = forecast['calendar_provenance']
            need(calendar['calendar_start_epoch_seconds'] == parent['calendar_start_epoch_seconds']
                 and calendar['actual_callback_consumption'] is False
                 and calendar['forecast_provenance'] == 'offline_replay_saved_public_observation', 'offline_public_calendar')
            need(forecast['model_sha256'] == base['base_model_sha256']
                 and forecast['airport_mapping_sha256'] == base['mapping_sha256'], 'same_B1_mapping')
        calibration = predicted['predictor_calibration']
        need(calibration['model_sha256'] == model['sha256']
             and calibration['prior_forecast_sha256'] == demand.digest(raw)
             and calibration['native_execution_authority'] is False, 'record_frozen_predictor_binding')
        observed = parent['calendar_start_epoch_seconds'] + 59400.
        need(record['observed_through_epoch_seconds'] == observed, 'record_full_closed_window')
        for label in record['labels']:
            need(label['label_available_at_epoch_seconds'] == observed
                 and label['source_evidence_id'] == provenance['labels']['source_evidence_id'], 'label_source_and_maturity')
    need(origins == list(ORIGINS), 'fixed_29_unique_origins')
    predictions = [{key: value for key, value in record.items()
                    if key not in ('labels', 'observed_through_epoch_seconds')} for record in records]
    need(demand.digest(predictions) == provenance['predictions_frozen_before_label_tape_opened_sha256'],
         'record_predictions_frozen_digest')
    references = provenance['saved_references']
    need([row['physical_origin'] for row in references] == list(ORIGINS)
         and all(row['original_C00_consumed_forecast'] is False for row in references), 'saved_origin_references')


def score_report(directory, model, base, manifest, modules, inputs):
    directory = Path(directory).resolve()
    evaluation = inputs.read(directory / 'evaluation.json')
    provenance = inputs.read(directory / 'provenance.json')
    need(evaluation['schema'] == provenance['schema'] == EVAL_SCHEMA, 'frozen_holdout_schema')
    plan_path = Path(provenance['plan']['path']).resolve()
    need(plan_path.name == 'plan.json' and plan_path.parent.parent == (CYCLE / 'runs').resolve(), 'registered_run_plan_path')
    plan = inputs.bound(provenance['plan'], plan_path)
    parent = plan['parent']; seed = parent['parent_seed']
    need(type(seed) is int and seed in PARENTS and parent['split'] == 'dev' and plan['method'] == 'C00'
         and parent['parent_group'] == f'joint_reposition_group_plan_20261021:{seed}:r0'
         and plan['horizon'] == 59400., 'closed_C00_full_DEV_identity')
    run = CYCLE / f'runs/TF_bridge_all_005_C00_P{seed}'
    need(plan_path == (run / 'plan.json').resolve()
         and plan['task_id'] == run.name, 'registered_005_C00_task')
    need(same_ref(plan['source_bundle'], inputs.bindings[str(MANIFEST.resolve())])
         and same_ref(provenance['native_data_source_bundle'], plan['source_bundle']), 'native_source005')
    need(plan['worker_evidence_contract'] == 'deferred_complete_intermediate_results_and_transfer_ack_subset_v1',
         'source005_worker_contract')
    labels = provenance['labels']
    need(same_ref(labels['plan.json'], provenance['plan']) and labels['parent'] == parent
         and labels['physical_clock'] == 59400. and labels['future_jobs_used_as_arrival_labels'] is False,
         'same_closed_native_label_source')
    receipt = inputs.bound(provenance['receipt'], run / 'receipt.json')
    worker = inputs.bound(labels['worker_report.json'], run / 'worker_report.json')
    need(same_ref(labels['receipt.json'], provenance['receipt']) and receipt['worker'] == worker
         and receipt['task_id'] == worker['task_id'] == plan['task_id']
         and receipt['plan_sha256'] == provenance['plan']['sha256']
         and receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
         and worker['scientific_status'] == 'closed' and worker['process_status'] == 'completed'
         and worker['final_physical_time'] == 59400., 'actual_native_closed_receipts')
    model_ref = inputs.bindings[str(MODEL.resolve())]
    need(same_ref(evaluation['model_file'], model_ref) and same_ref(provenance['model'], model_ref)
         and evaluation['model_sha256'] == model['sha256'] and evaluation['model_training_row_count'] == 580,
         'same_full_frozen_model')
    need(provenance['model_unchanged_after_DEV'] is True and provenance['DEV_labels_used_for_fitting'] is False
         and provenance['TEST_opened'] is False and provenance['native_starts'] == 0
         and provenance['future_truth_read_by_prediction_builder'] is False
         and provenance['producer_sources_unchanged'] is True and provenance['owners_deduplicated_by_origin'] is True,
         'no_fit_TEST_native_or_truth_in_predictions')
    need(evaluation['native_data_method'] == 'C00' and evaluation['model_fitted_or_selected_by_this_report'] is False
         and evaluation['native_policy_pair_comparison'] is False
         and evaluation['evaluation_window_physical_seconds'] == [7200., 59400.]
         and evaluation['forecast_origins_stride_seconds'] == 1800., 'fixed_offline_evaluation_contract')
    verify_producers(provenance['prediction_producer_source_files'], manifest, inputs, exact_names=PRODUCERS)
    records = inputs.read(directory / 'evaluation_records.json.gz', records=True)
    demand, scorer, _supported = modules
    record_contract(records, plan, provenance, model, base, demand)
    recomputed = scorer.evaluate_common_windows(records, model=base)
    need(recomputed['label_count'] == 870 and recomputed['splits'] == ['dev'], '870_DEV_labels_per_parent')
    for method in METHODS:
        need(all(recomputed['methods'][method][window]['count'] == 290
                 and recomputed['methods'][method][window]['skipped_common_missing'] == 0 for window in WINDOWS),
             'complete_290_population_each_window')
    for key, value in recomputed.items():
        if key != 'schema':
            close_values(evaluation[key], value, 'recomputed_evaluation:' + key)
    for left, right in PERIODS:
        expected = scorer.evaluate_common_windows([row for row in records
            if left <= row['predictions']['TF-B1-300']['forecast_origin'] < right], model=base)
        close_values(evaluation['origin_periods'][f'{left}:{right}'], expected, 'origin_period_metrics')
    return dict(parent_seed=seed, parent=parent, run=str(run.resolve()), report=str(directory),
        model=model_ref, evaluation=inputs.bindings[str(directory / 'evaluation.json')],
        provenance=inputs.bindings[str(directory / 'provenance.json')],
        records=inputs.bindings[str(directory / 'evaluation_records.json.gz')],
        metrics=recomputed, origin_periods=evaluation['origin_periods'],
        role='previously_diagnosed_exploratory_DEV_reuse' if seed == 2201 else 'additional_fixed_DEV_parent',
        independent_real_airport_day=False)


def pool(rows):
    """Sum sufficient statistics, then derive metrics; never average parent RMSE."""
    methods = {}
    for method in METHODS:
        methods[method] = {}
        for window in WINDOWS:
            values = [row['metrics']['methods'][method][window] for row in rows]
            combined = {key: (sum(v[key] for v in values) if key in ('count', 'skipped_common_missing')
                              else math.fsum(v[key] for v in values)) for key in SUM_FIELDS}
            count = combined['count']
            combined.update(mae=combined['absolute_error_sum'] / count if count else None,
                rmse=math.sqrt(combined['squared_error_sum'] / count) if count else None,
                bias=combined['signed_error_sum'] / count if count else None)
            methods[method][window] = combined
    return dict(methods=methods, label_count=sum(row['metrics']['label_count'] for row in rows),
                aggregation='sum_parent_sufficient_statistics_then_derive_metrics', parent_mean_used=False)


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def run(model_path, reports, output):
    output = Path(output).resolve()
    need(output.is_relative_to(DATA.resolve()) and output != DATA.resolve() and not output.exists(), 'fresh_output_under_ROOTDATA')
    need(len(reports) == 4 and len({str(Path(p).resolve()) for p in reports}) == 4, 'four_distinct_reports_required')
    inputs = Inputs(); inputs.capture(__file__)
    manifest, modules = load_scorers(inputs)
    model, base, training = verify_model(model_path, manifest, modules, inputs)
    rows = [score_report(directory, model, base, manifest, modules, inputs) for directory in reports]
    rows.sort(key=lambda row: row['parent_seed'])
    need([row['parent_seed'] for row in rows] == list(PARENTS), 'exact_DEV_2201_2202_2203_2204')
    templates = {row['parent']['common_historical_template_sha256'] for row in rows}
    need(len(templates) == 1 and templates == {s['parent']['common_historical_template_sha256'] for s in training['sources']},
         'registered_shared_template_dependency')
    summary = dict(schema=SCHEMA, status='complete', source_bundle=inputs.bindings[str(MANIFEST.resolve())],
        model=inputs.bindings[str(MODEL.resolve())], training_fit=inputs.bindings[str(FIT.resolve())],
        model_identity=model['sha256'], training_row_count=580, train_parents=[2101, 2102],
        dev_parents=list(PARENTS), per_parent=rows, pooled=pool(rows),
        scope='recompute_frozen_metrics_from_saved_prediction_and_label_records_then_pool',
        prediction_generation_reexecuted=False, native_label_tape_independently_reaudited=False,
        prediction_provenance_claims_verified_by_bindings_not_reexecuted=True,
        observations_opened=False, ACK_opened=False, decisions_opened=False, native_arrival_tape_opened=False,
        native_starts=0, TEST_opened=False, parameters_fitted_or_selected=False,
        service_gain_or_RL_gain_claimed=False, source005_and_closed_native_receipts_verified=True,
        shared_historical_template_sha256=next(iter(templates)),
        dependency='synthetic parents share historical template; overlapping 5/15/30-minute labels are dependent',
        P2201_is_exploratory_reuse_not_independent_confirmation=True,
        predictive_interval_coverage='unavailable_no_joint_bin_and_projection_uncertainty',
        input_bindings=list(inputs.bindings.values()), producer=inputs.bindings[str(Path(__file__).resolve())],
        entry_exit_bindings_equal=True)
    inputs.verify_exit()
    output.mkdir(parents=True)
    write_new(output / 'forecast_holdout_summary.json', summary)
    # A mutation during writing leaves an explicit partial directory, no COMPLETE.
    inputs.verify_exit()
    write_new(output / 'COMPLETE.json', dict(schema=SCHEMA + '.completion', status='complete',
        summary=ref(output / 'forecast_holdout_summary.json'), producer=summary['producer'],
        source_bundle=summary['source_bundle'], model=summary['model'], dev_parents=list(PARENTS),
        full_DEV_labels=3480, entry_exit_bindings_equal=True, native_starts=0, TEST_opened=False,
        scientific_service_improvement_not_inferred=True))
    return dict(output=str(output), labels=3480, parents=list(PARENTS), native_starts=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--reports', nargs=4, type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.model, args.reports, args.output_dir), ensure_ascii=False))


if __name__ == '__main__':
    main()
