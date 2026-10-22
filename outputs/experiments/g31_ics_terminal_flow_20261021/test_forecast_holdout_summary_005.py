"""Pure synthetic records/metadata; no native or real DEV report is evaluated."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import pytest

PATH = Path(__file__).with_name('forecast_holdout_summary_005.py')
spec = importlib.util.spec_from_file_location('holdout_summary_tested', PATH)
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
    return w.ref(path)


@pytest.fixture(scope='module')
def frozen():
    inputs = w.Inputs()
    manifest, modules = w.load_scorers(inputs)
    model = inputs.read(w.MODEL)
    base = w.model_contract(model, modules[2])
    return manifest, modules, model, base


@pytest.fixture
def case(tmp_path, monkeypatch, frozen):
    manifest, modules, model, base = frozen
    monkeypatch.setattr(w, 'CYCLE', tmp_path / 'cycle')
    monkeypatch.setattr(w, 'DATA', tmp_path / 'data')
    seed = 2201
    parent = dict(parent_seed=seed, split='dev', parent_group=f'joint_reposition_group_plan_20261021:{seed}:r0',
                  calendar_start_epoch_seconds=1796918400., common_historical_template_sha256='a' * 64)
    run = w.CYCLE / f'runs/TF_bridge_all_005_C00_P{seed}'
    plan = dict(parent=parent, method='C00', horizon=59400., task_id=run.name,
                source_bundle=w.ref(w.MANIFEST),
                worker_evidence_contract='deferred_complete_intermediate_results_and_transfer_ack_subset_v1')
    plan_ref = save(run / 'plan.json', plan)
    worker = dict(task_id=run.name, scientific_status='closed', process_status='completed', final_physical_time=59400.)
    worker_ref = save(run / 'worker_report.json', worker)
    receipt = dict(task_id=run.name, worker=worker, plan_sha256=plan_ref['sha256'], process=dict(status='exited', exitcode=0))
    receipt_ref = save(run / 'receipt.json', receipt)
    records = []
    for origin in w.ORIGINS:
        raw = dict(forecast_origin=origin, owner_scope='owner:synthetic',
            model_sha256=base['base_model_sha256'], airport_mapping_sha256=base['mapping_sha256'],
            native_execution_authority=False, bin_edges_seconds=base['bin_edges_seconds'],
            new_demand_mean_by_region={station: [1., 2., 3., 4., 5., 6.] for station in base['parameters']},
            missing_mask_by_region={station: [False] * 6 for station in base['parameters']},
            calendar_provenance=dict(calendar_start_epoch_seconds=parent['calendar_start_epoch_seconds'],
                actual_callback_consumption=False, forecast_provenance='offline_replay_saved_public_observation'))
        predicted = modules[2].transform(model, raw, now=origin, parent_id=parent['parent_group'])
        mature = parent['calendar_start_epoch_seconds'] + 59400.
        records.append(dict(parent_id=parent['parent_group'], split='dev',
            predictions={'TF-B1-300': raw, 'TF-predictor': predicted}, observed_through_epoch_seconds=mature,
            labels=[dict(station=station, window_seconds=window, actual_arrivals=window // 300,
                         label_available_at_epoch_seconds=mature, source_evidence_id='synthetic-label-tape')
                    for station in sorted(base['parameters']) for window in (300, 900, 1800)]))
    predictions = [{k: v for k, v in row.items() if k not in ('labels', 'observed_through_epoch_seconds')} for row in records]
    evaluation = modules[1].evaluate_common_windows(records, model=base)
    evaluation.update(schema=w.EVAL_SCHEMA, model_file=w.ref(w.MODEL), model_sha256=model['sha256'],
        model_training_row_count=580, native_data_method='C00', model_fitted_or_selected_by_this_report=False,
        native_policy_pair_comparison=False, evaluation_window_physical_seconds=[7200., 59400.],
        forecast_origins_stride_seconds=1800.,
        origin_periods={f'{a}:{b}': modules[1].evaluate_common_windows(
            [r for r in records if a <= r['predictions']['TF-B1-300']['forecast_origin'] < b], model=base)
                        for a, b in w.PERIODS})
    provenance = dict(schema=w.EVAL_SCHEMA, plan=plan_ref, receipt=receipt_ref, model=w.ref(w.MODEL),
        native_data_source_bundle=plan['source_bundle'], model_unchanged_after_DEV=True,
        DEV_labels_used_for_fitting=False, TEST_opened=False, native_starts=0,
        future_truth_read_by_prediction_builder=False, producer_sources_unchanged=True,
        owners_deduplicated_by_origin=True,
        labels={'plan.json': plan_ref, 'receipt.json': receipt_ref, 'worker_report.json': worker_ref,
                'parent': parent, 'physical_clock': 59400., 'future_jobs_used_as_arrival_labels': False,
                'source_evidence_id': 'synthetic-label-tape'},
        prediction_producer_source_files={name: w.ref(w.SOURCE / w.SCRIPT_REL / name) for name in w.PRODUCERS},
        predictions_frozen_before_label_tape_opened_sha256=modules[0].digest(predictions),
        saved_references=[dict(physical_origin=origin, original_C00_consumed_forecast=False) for origin in w.ORIGINS])
    directory = w.DATA / 'synthetic_report'
    def rewrite():
        save(directory / 'evaluation.json', evaluation)
        save(directory / 'provenance.json', provenance)
        with gzip.open(directory / 'evaluation_records.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(records, stream)
    rewrite()
    def score():
        inputs = w.Inputs(); inputs.capture(w.MANIFEST); inputs.capture(w.MODEL)
        return w.score_report(directory, model, base, manifest, modules, inputs)
    return dict(score=score, rewrite=rewrite, evaluation=evaluation, provenance=provenance,
                records=records, directory=directory, plan=plan, worker=worker, receipt=receipt)


def test_valid_small_records_recompute_all_three_windows(case):
    row = case['score']()
    assert row['metrics']['label_count'] == 870
    assert all(row['metrics']['methods'][m][v]['count'] == 290 for m in w.METHODS for v in w.WINDOWS)
    assert row['role'] == 'previously_diagnosed_exploratory_DEV_reuse'


@pytest.mark.parametrize('mutation,reason', [
    (lambda c: c['evaluation']['methods']['TF-B1-300']['300'].update(absolute_error_sum=999999), 'recomputed_evaluation'),
    (lambda c: c['evaluation']['origin_periods']['7200:18000']['methods']['TF-predictor']['300'].update(rmse=100), 'origin_period_metrics'),
    (lambda c: c['evaluation'].update(model_training_row_count=120), 'same_full_frozen_model'),
    (lambda c: c['provenance'].update(TEST_opened=True), 'no_fit_TEST'),
    (lambda c: c['provenance'].update(DEV_labels_used_for_fitting=True), 'no_fit_TEST'),
    (lambda c: c['provenance']['prediction_producer_source_files'].pop('foundation_airport_terminal_predictor.py'), 'complete_prediction_producer'),
    (lambda c: c['provenance']['native_data_source_bundle'].update(sha256='0' * 64), 'native_source005'),
    (lambda c: c['records'].pop(), '29_origins'),
    (lambda c: c['records'][0].update(split='test'), 'record_DEV_parent'),
    (lambda c: c['records'][0]['labels'][0].update(source_evidence_id='other'), 'label_source'),
    (lambda c: c['records'][0]['predictions']['TF-predictor']['predictor_calibration'].update(model_sha256='0'*64), 'record_frozen_predictor'),
    (lambda c: c['provenance']['saved_references'][0].update(original_C00_consumed_forecast=True), 'saved_origin_references'),
    (lambda c: c['records'][0]['labels'].pop(), 'complete_same_station_same_windows'),
])
def test_invalid_or_partial_reports_fail_closed(case, mutation, reason):
    mutation(case); case['rewrite']()
    with pytest.raises(ValueError, match=reason): case['score']()


def test_absent_and_duplicate_window_label_never_change_population_silently(case):
    case['records'][0]['labels'][1] = copy.deepcopy(case['records'][0]['labels'][0])
    case['rewrite']()
    with pytest.raises(ValueError, match='complete_same_station_same_windows'): case['score']()


def test_raw_prediction_changed_after_frozen_digest_is_rejected(case):
    case['records'][0]['predictions']['TF-B1-300']['new_demand_mean_by_region']['airport_node_0'][0] = 88.
    case['rewrite']()
    with pytest.raises(ValueError, match='record_frozen_predictor_binding'): case['score']()


def test_same_binding_accepts_extra_bytes_field(tmp_path):
    path = tmp_path / 'a'; path.write_text('x')
    bound = w.ref(path)
    assert w.same_ref(bound, {k: bound[k] for k in ('path', 'sha256')})


def test_pool_uses_sufficient_statistics_not_parent_rmse_mean():
    rows = []
    for n, error in ((1, 0.), (3, 4.)):
        metrics = dict(label_count=3*n, methods={method: {window: dict(count=n, skipped_common_missing=0,
            absolute_error_sum=n*error, squared_error_sum=n*error**2, signed_error_sum=n*error,
            actual_sum=0., predicted_sum=n*error) for window in w.WINDOWS} for method in w.METHODS})
        rows.append(dict(metrics=metrics))
    result = w.pool(rows)['methods']['TF-B1-300']['300']
    assert result['count'] == 4 and result['mae'] == 3 and result['rmse'] == pytest.approx(12**.5)
    assert result['rmse'] != 2  # Mean of the two parent RMSE values.


@pytest.mark.parametrize('raw', ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}'])
def test_duplicate_keys_and_nonfinite_json_rejected(raw):
    with pytest.raises(ValueError): w.parsed(raw)


def test_entry_exit_mutation_is_detected(tmp_path):
    path = tmp_path / 'evidence.json'; path.write_text('{}')
    inputs = w.Inputs(); inputs.read(path)
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='exit_binding_changed'): inputs.verify_exit()


def test_small_input_and_gzip_expansion_limits(tmp_path, monkeypatch):
    path = tmp_path / 'evaluation_records.json.gz'
    with gzip.open(path, 'wb') as stream: stream.write(b' ' * 200)
    monkeypatch.setattr(w, 'RECORD_EXPANDED_LIMIT', 100)
    with pytest.raises(ValueError, match='expanded_records_limit'): w.Inputs().read(path, records=True)
    with pytest.raises(ValueError, match='small_input_required'): w.Inputs().capture(path, limit=1)


def test_existing_output_and_duplicate_report_roster_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'DATA', tmp_path)
    existing = tmp_path / 'existing'; existing.mkdir()
    with pytest.raises(ValueError, match='fresh_output'): w.run(w.MODEL, ['x']*4, existing)
    with pytest.raises(ValueError, match='four_distinct'): w.run(w.MODEL, ['x']*4, tmp_path/'fresh')


def test_no_large_native_tape_read_is_required(case, monkeypatch):
    original = w.Inputs.capture
    paths = []
    def guarded(self, path, **kwargs):
        paths.append(Path(path).name)
        assert Path(path).name not in ('observations.json.gz', 'decisions.json.gz',
            'delivered_ack_evidence.json.gz', 'terminal_evidence.json.gz')
        return original(self, path, **kwargs)
    monkeypatch.setattr(w.Inputs, 'capture', guarded)
    assert case['score']()['metrics']['label_count'] == 870
    assert 'evaluation_records.json.gz' in paths


def test_wrong_producer_bytes_are_not_excused_by_filename(case):
    case['provenance']['prediction_producer_source_files']['foundation_airport_terminal_predictor.py']['sha256'] = '0'*64
    case['rewrite']()
    with pytest.raises(ValueError, match='producer_source005_bytes'): case['score']()


def test_mutated_small_plan_is_rejected_by_provenance(case):
    path = Path(case['provenance']['plan']['path'])
    plan = dict(case['plan'], method='TF-B1-60'); save(path, plan)
    with pytest.raises(ValueError, match='input_binding_changed'): case['score']()


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Mock only scientific loading here to isolate publication lifecycle checks."""
    monkeypatch.setattr(w, 'DATA', tmp_path / 'data')
    for name in ('MANIFEST', 'MODEL', 'FIT'):
        path = tmp_path / (name + '.json'); save(path, {})
        monkeypatch.setattr(w, name, path)
    def load(inputs):
        inputs.capture(w.MANIFEST)
        return {}, None
    def model(*args):
        inputs = args[-1]; inputs.capture(w.MODEL); inputs.capture(w.FIT)
        return {'sha256': 'model_identity'}, {}, {'sources': [
            {'parent': {'common_historical_template_sha256': 'shared'}}]}
    monkeypatch.setattr(w, 'load_scorers', load)
    monkeypatch.setattr(w, 'verify_model', model)
    reports = []
    for seed in w.PARENTS:
        directory = tmp_path / str(seed); save(directory / 'evaluation.json', {'seed': seed}); reports.append(directory)
    def score(directory, _model, _base, _manifest, _modules, inputs):
        seed = inputs.read(Path(directory) / 'evaluation.json')['seed']
        return dict(parent_seed=seed, parent={'common_historical_template_sha256': 'shared'},
            metrics=dict(label_count=870, methods={method: {window: dict(count=290,
                skipped_common_missing=0, absolute_error_sum=290., squared_error_sum=290.,
                signed_error_sum=290., actual_sum=290., predicted_sum=580.) for window in w.WINDOWS}
                for method in w.METHODS}))
    monkeypatch.setattr(w, 'score_report', score)
    return reports, w.DATA / 'summary'


def test_four_parent_pipeline_writes_bound_completion_after_summary(pipeline):
    reports, output = pipeline
    result = w.run(w.MODEL, reports, output)
    complete = w.parsed((output / 'COMPLETE.json').read_bytes())
    summary = w.parsed((output / 'forecast_holdout_summary.json').read_bytes())
    assert result['labels'] == 3480 and result['parents'] == list(w.PARENTS)
    assert complete['summary'] == w.ref(output / 'forecast_holdout_summary.json')
    assert summary['pooled']['methods']['TF-B1-300']['300']['count'] == 1160
    assert summary['entry_exit_bindings_equal'] and summary['TEST_opened'] is False


def test_four_distinct_directories_cannot_hide_duplicate_parent(pipeline):
    reports, output = pipeline
    save(reports[-1] / 'evaluation.json', {'seed': 2201})
    with pytest.raises(ValueError, match='exact_DEV_2201'): w.run(w.MODEL, reports, output)
    assert not output.exists()


def test_input_change_during_output_write_leaves_no_complete_marker(pipeline, monkeypatch):
    reports, output = pipeline
    original = w.write_new
    def mutate(path, value):
        original(path, value)
        if Path(path).name == 'forecast_holdout_summary.json':
            save(reports[0] / 'evaluation.json', {'changed': True})
    monkeypatch.setattr(w, 'write_new', mutate)
    with pytest.raises(ValueError, match='exit_binding_changed'): w.run(w.MODEL, reports, output)
    assert (output / 'forecast_holdout_summary.json').exists()
    assert not (output / 'COMPLETE.json').exists()
