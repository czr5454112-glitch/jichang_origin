"""Bounded offline B1 training/evaluation; runtime predictor never imports this.

The launcher must enforce the registered process timeout. A worker invocation
consumes its parent admission token on stdin before opening any dataset.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from scipy.stats import nbinom, poisson

from . import foundation_flight_data as data
from . import foundation_flight_forecaster as forecast

PLAN_SCHEMA = 'g31.foundation.flight_training_plan.v1'
ROOT = Path(__file__).resolve().parents[3]
DEFAULTS = {'train_cutoff': 43200., 'dev_cutoff': 57600., 'bin_seconds': 60,
    'horizon_seconds': 1800, 'evaluation_stride': 300, 'fit_wall_seconds': 120.,
    'task_wall_seconds': 600., 'bootstrap_seeds': [1701, 1702, 1703], 'bootstrap_replicates': 200,
    'lead_support_seconds': 86400, 'interval_level': .9, 'bootstrap_block_origins': 6}


def pins():
    files = [Path(__file__), Path(data.__file__), Path(forecast.__file__), Path(forecast.contexts.__file__)]
    return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def make_plan(source=None):
    source = ROOT / 'legacy/jichang_origin_readonly/inputdata.txt' if source is None else Path(source).resolve()
    return {'schema': PLAN_SCHEMA, 'source_path': str(source), 'source_sha256': data.SOURCE_SHA256,
        'source_sha256_pins': pins(), 'settings': copy.deepcopy(DEFAULTS), 'native_branches': 0,
        'training_kind': 'one_deterministic_closed_form_fit_three_bootstrap_seeds_not_three_neural_fits',
        'model_selection': 'fixed_first_gamma_poisson_no_test_selection_or_retraining',
        'runtime_count_contract': 'None_by_default_no_native_group_association',
        'lineage': 'one_legacy_simulated_source_day_original_1x_only'}


def check_plan(plan):
    data.require(plan['schema'] == PLAN_SCHEMA and plan['source_sha256'] == data.SOURCE_SHA256
        and plan['native_branches'] == 0 and plan['settings'] == DEFAULTS, 'frozen_B1_protocol')
    data.require(plan['source_sha256_pins'] == pins(), 'training_source_bytes_changed')


def fit(rows, context, split, *, wall_seconds=120.):
    """Train with closed train parents only, including group/region zero counts."""
    started = time.perf_counter()
    roster = [row for row in split['group_roster'] if row['split'] == 'train']
    refs = {row['parent_flight_ref'] for row in roster}
    cutoff = split['train_label_cutoff']
    data.require(refs and all(row['label_closes_at'] <= cutoff for row in roster), 'closed_training_parent_labels')
    selected = [row for row in rows if row['parent_flight_ref'] in refs]
    data.require(selected and all(row['arrived_at'] <= row['scheduled_std'] <= cutoff for row in selected),
        'full_CDF_and_count_labels_closed_before_freeze')
    grid = np.arange(-86400., 1., 60.)
    pooled = np.histogram([row['arrived_at'] - row['scheduled_std'] for row in selected], bins=grid)[0]
    data.require(pooled.sum() == len(selected), 'registered_lead_support_contains_training_labels')
    params, history, historical_rate = {}, [], {}
    for region in data.REGIONS:
        data.require(time.perf_counter() - started < wall_seconds, 'fit_wall_budget_exceeded')
        per_group = {ref: 0 for ref in refs}
        regional = [row for row in selected if row['region'] == region]
        for row in regional:
            per_group[row['parent_flight_ref']] += 1
        counts = np.asarray(list(per_group.values()), dtype=float)
        empirical_mean, empirical_variance = float(counts.mean()), float(counts.var())
        fallback = empirical_mean == 0.
        mean = empirical_mean if not fallback else len(selected) / len(refs) / len(data.REGIONS)
        # Poisson observation variance is removed before fitting Gamma variance.
        latent_variance = max(empirical_variance - empirical_mean, mean * .01, 1e-6)
        shape, rate = mean ** 2 / latent_variance, mean / latent_variance
        histogram = np.histogram([row['arrived_at'] - row['scheduled_std'] for row in regional], bins=grid)[0]
        histogram = pooled if not len(regional) else histogram
        cdf = np.concatenate([[0.], np.cumsum(histogram, dtype=float) / histogram.sum()])
        params[region] = {'shape': shape, 'rate': rate, 'rate_parameterization': True,
            'cdf_edges': grid.tolist(), 'cdf_values': cdf.tolist(), 'zero_count_groups_included': int((counts == 0).sum()),
            'training_parent_count': len(refs), 'training_region_bags': len(regional),
            'pooled_zero_region_fallback': fallback}
        loss = float(-nbinom.logpmf(counts, shape, rate / (rate + 1.)).mean())
        data.require(math.isfinite(loss), 'finite_closed_form_count_loss')
        history.append({'step': 1, 'method': 'closed_form_moments_and_empirical_CDF', 'region': region,
            'negative_log_likelihood_per_group': loss, 'empirical_count_mean': empirical_mean,
            'empirical_count_variance': empirical_variance, 'fitted_shape': shape, 'fitted_rate': rate})
        historical_rate[region] = len(regional) / cutoff
    checkpoint = {'schema': forecast.MODEL_SCHEMA, 'parameters': params, 'regions': data.REGIONS,
        'mapping_version': data.MAPPING_VERSION, 'time_basis': data.TIME_BASIS,
        'training_parent_refs': sorted(refs), 'training_parent_count': len(refs), 'training_bag_count': len(selected),
        'training_labels_closed_at': cutoff, 'frozen_at': cutoff, 'source_sha256': split['source_sha256'],
        'training_split_sha256': data.digest(split), 'static_plan_sha256': data.digest(context),
        'historical_arrival_rate_by_region': historical_rate, 'calibration_status': 'uncalibrated_model_interval_empirical_coverage_reported',
        'native_execution_authority': False, 'native_group_count_association_established': False,
        'fit_kind': 'deterministic_closed_form_gamma_poisson_with_train_only_empirical_CDF',
        'CDF_support_seconds_relative_STD': [-86400., 0.], 'region_share_already_in_count_prior': True}
    checkpoint['model_sha256'] = forecast.digest(checkpoint)
    forecast.validate_checkpoint(checkpoint)
    return checkpoint, {'schema': 'g31.foundation.flight_training_history.v1', 'fit_wall_seconds': time.perf_counter() - started,
        'steps': history, 'training_labels_used_after_freeze': False, 'training_parent_count': len(refs),
        'epoch_count': 1, 'stochastic_training_performed': False}


def public_observations(rows, context, *, now, owner):
    """Evaluator's explicit as-of feed; never called by runtime forecasting.

Group identity here is a declared synthetic arrival-message field, not an
established native field. Only arrived messages enter this public snapshot.
    """
    counts = {entry['flight_ref']: dict.fromkeys(data.REGIONS, 0) for entry in context['entries']}
    events = []
    for row in rows:
        if row['arrived_at'] > now:
            continue
        counts[row['flight_ref']][row['region']] += 1
        events.append({'schema': forecast.EVENT_SCHEMA, 'bag_id': row['bag_id'], 'region': row['region'],
            'arrived_at': row['arrived_at'], 'received_at': row['arrived_at'], 'owner_scope': owner})
    return {'schema': forecast.COUNTS_SCHEMA, 'owner_scope': owner, 'observed_at': now,
        'complete_history_from': 0., 'mapping_version': data.MAPPING_VERSION,
        'source_kind': 'explicit_synthetic_asof_arrival_feed', 'counts_by_flight': counts}, events


def _metrics(records):
    result = {}
    for split in ('development', 'test'):
        result[split] = {}
        for method in ('flight_prior_only', 'flight_synthetic_observed_counts', 'no_plan_recent_rate'):
            result[split][method] = {}
            for region in data.REGIONS:
                result[split][method][region] = {}
                for window in forecast.WINDOWS:
                    selected = [row for row in records if row['split'] == split and row['method'] == method
                        and row['region'] == region and row['window_seconds'] == window]
                    if not selected:
                        continue
                    truth, mean = np.asarray([row['actual'] for row in selected]), np.asarray([row['mean'] for row in selected])
                    low, high = np.asarray([row['lower'] for row in selected]), np.asarray([row['upper'] for row in selected])
                    safe = np.maximum(mean, 1e-12)
                    nll = safe - truth * np.log(safe) + np.asarray([math.lgamma(v + 1.) for v in truth])
                    latent = np.maximum(np.asarray([row['variance'] for row in selected]) - mean, 0.)
                    log_probability = poisson.logpmf(truth, mean)
                    mixed = (mean > 0) & (latent > 1e-12)
                    shape = mean[mixed] ** 2 / latent[mixed]
                    log_probability[mixed] = nbinom.logpmf(truth[mixed], shape, shape / (shape + mean[mixed]))
                    result[split][method][region][str(window)] = {'samples': len(selected),
                        'MAE': float(np.abs(mean - truth).mean()), 'bias_predicted_minus_actual': float((mean - truth).mean()),
                        'mean_underprediction': float(np.maximum(truth - mean, 0).mean()),
                        'poisson_count_negative_log_likelihood': float(nll.mean()),
                        'predictive_count_negative_log_likelihood': float(-np.maximum(log_probability, math.log(1e-12)).mean()),
                        'predictive_scoring_distribution': 'moment_matched_gamma_poisson_aggregate',
                        'predictive_scoring_probability_floor': 1e-12,
                        'interval_90_empirical_coverage': float(((low <= truth) & (truth <= high)).mean()),
                        'interval_mean_width': float((high - low).mean()), 'actual_total': int(truth.sum())}
    return result


def evaluate(rows, full_context, split, checkpoint, output, *, deadline):
    """Write causally frozen forecasts and separate private evaluator scores."""
    roster = {entry['parent_flight_ref']: entry['split'] for entry in split['group_roster']}
    scored, sample_counts = [], {}
    predictions = output / 'forecast_predictions.jsonl'
    with predictions.open('x', encoding='utf8') as stream:
        for split_name in ('development', 'test'):
            refs = {ref for ref, group_split in roster.items() if group_split == split_name}
            subrows = [row for row in rows if row['parent_flight_ref'] in refs]
            context = copy.deepcopy(full_context)
            context['source_id'] += ':' + split_name + '_statistical_subpopulation'
            context['entries'] = [entry for entry in context['entries'] if entry['flight_ref'] in refs]
            owner = context['owner_scope']
            actual_by_region = {region: sorted(row['arrived_at'] for row in subrows if row['region'] == region)
                for region in data.REGIONS}
            windows = [item for item in split['evaluation_windows'] if item['split'] == split_name]
            sample_counts[split_name] = {'parents': len(refs), 'bags_in_statistical_population': len(subrows),
                'forecast_origins': len(windows), 'public_count_feed': 'explicit_synthetic_experiment_not_native_integration'}
            for window in windows:
                data.require(time.perf_counter() < deadline, 'task_wall_budget_exceeded')
                now = window['forecast_origin']
                counts, events = public_observations(subrows, context, now=now, owner=owner)
                forecasts = {
                    'flight_prior_only': forecast.predict(context, checkpoint, now=now, owner=owner),
                    'flight_synthetic_observed_counts': forecast.predict(context, checkpoint, now=now, owner=owner, observed_counts=counts),
                    'no_plan_recent_rate': forecast.recent_rate_forecast(checkpoint, now=now, owner=owner, arrival_events=events)}
                for method, prediction in forecasts.items():
                    stream.write(json.dumps({'split': split_name, 'method': method,
                        'statistical_parent_scope': sorted(refs), 'forecast': prediction}, sort_keys=True, allow_nan=False) + '\n')
                    for region, summaries in prediction['window_summaries_by_region'].items():
                        arrivals = actual_by_region[region]
                        for horizon, summary in summaries.items():
                            horizon = int(horizon)
                            actual = bisect.bisect_right(arrivals, now + horizon) - bisect.bisect_right(arrivals, now)
                            scored.append({'split': split_name, 'method': method, 'region': region,
                                'forecast_origin': now, 'window_seconds': horizon, 'actual': actual, **summary})
    data.write_new(output / 'private/forecast_evaluation_labels.json', {'schema': 'g31.foundation.forecast_scoring.v1',
        'scope': 'private_evaluator_targets_not_predictor_input', 'rows': scored})
    metrics = _metrics(scored)
    # Moving blocks of six consecutive origins preserve overlap in the 1800s
    # target horizon. One source day cannot establish day-level generalization.
    # Three seeds measure only Monte Carlo variation, not model fitting variance.
    seed_reports = []
    test_origins = sorted({row['forecast_origin'] for row in scored if row['split'] == 'test'})
    for seed in DEFAULTS['bootstrap_seeds']:
        generator = np.random.default_rng(seed)
        per_origin = []
        for origin in test_origins:
            errors = {}
            for method in ('flight_prior_only', 'no_plan_recent_rate'):
                subset = [row for row in scored if row['split'] == 'test' and row['forecast_origin'] == origin
                    and row['method'] == method and row['window_seconds'] == 1800]
                errors[method] = np.mean([abs(row['mean'] - row['actual']) for row in subset])
            per_origin.append(errors['flight_prior_only'] - errors['no_plan_recent_rate'])
        block = DEFAULTS['bootstrap_block_origins']
        means = []
        for _ in range(DEFAULTS['bootstrap_replicates']):
            starts = generator.integers(0, len(per_origin), size=math.ceil(len(per_origin) / block))
            indices = [(int(start) + offset) % len(per_origin) for start in starts for offset in range(block)][:len(per_origin)]
            means.append(float(np.mean([per_origin[index] for index in indices])))
        seed_reports.append({'seed': seed, 'replicates': len(means),
            'resampling_unit': 'six_consecutive_forecast_origins_all_regions_circular_moving_block',
            'block_origin_count': block, 'block_span_seconds': block * DEFAULTS['evaluation_stride'],
            'MAE_difference_flight_minus_recent_1800s': float(np.mean(per_origin)),
            'bootstrap_90_interval': np.quantile(means, [.05, .95]).tolist(),
            'independent_generalization_claim': False})
    return {'schema': 'g31.foundation.flight_evaluation.v1', 'sample_support': sample_counts,
        'metrics': metrics, 'bootstrap': seed_reports, 'test_used_for_model_selection': False,
        'main_forecast_uses_native_group_counts': False, 'physical_tasks_removed': False,
        'calibration_status': checkpoint['calibration_status'], 'cross_day_generalization_supported': False,
        'main_result': 'flight_prior_only', 'auxiliary_result': 'flight_synthetic_observed_counts',
        'new_demand_not_current_inventory': True}


def run(plan, output):
    started = time.perf_counter()
    check_plan(plan)
    output = Path(output).resolve()
    data.require(output.is_relative_to(ROOT) and not output.exists(), 'fresh_workspace_training_output')
    output.mkdir(parents=True)
    receipt = {'schema': 'g31.foundation.flight_training_receipt.v1', 'status': 'running',
        'native_executed': False, 'plan_sha256': data.digest(plan), 'source_sha256_pins': plan['source_sha256_pins']}
    data.write_new(output / 'registered_plan.json', plan)
    try:
        settings = plan['settings']
        rows, context, split = data.export(plan['source_path'], output, **{key: settings[key] for key in (
            'train_cutoff', 'dev_cutoff', 'bin_seconds', 'horizon_seconds', 'evaluation_stride')})
        checkpoint, history = fit(rows, context, split, wall_seconds=settings['fit_wall_seconds'])
        data.write_new(output / 'flight_forecaster_checkpoint.json', checkpoint)
        data.write_new(output / 'training_history.json', history)
        assessment = evaluate(rows, context, split, checkpoint, output, deadline=started + settings['task_wall_seconds'])
        data.write_new(output / 'forecast_evaluation.json', assessment)
        check_plan(plan)
        data.require(time.perf_counter() - started < settings['task_wall_seconds'], 'task_wall_budget_exceeded')
        receipt.update(status='completed_forecaster_training_and_causal_evaluation', training_performed=True,
            model_sha256=checkpoint['model_sha256'], training_bags=checkpoint['training_bag_count'],
            training_parents=checkpoint['training_parent_count'], sample_support=assessment['sample_support'],
            source_exit_pins_passed=True, private_label_index_sha256=split['private_label_index_sha256'],
            scope='Static-plan single simulated source day; no actor/native/RL success claimed.')
    except Exception:
        receipt.update(status='failed', exception=traceback.format_exc())
    receipt['wall_seconds'] = time.perf_counter() - started
    receipt['artifacts'] = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob('*')) if path.is_file()}
    data.write_new(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--admission', required=True)
    args = parser.parse_args()
    data.require(sys.stdin.readline().strip() == args.admission, 'parent_process_admission_required')
    receipt = run(json.loads(args.plan.read_text(encoding='utf8')), args.output)
    print(json.dumps({'status': receipt['status'], 'wall_seconds': receipt['wall_seconds']}))
    return 0 if receipt['status'] == 'completed_forecaster_training_and_causal_evaluation' else 1


if __name__ == '__main__':
    raise SystemExit(main())
