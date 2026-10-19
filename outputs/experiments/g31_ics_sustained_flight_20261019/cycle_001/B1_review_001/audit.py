"""Independent stdlib audit: never import the training/runtime/native modules."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
OUTPUT = Path(__file__).resolve().parent
RUN = OUTPUT.parent / 'B1_training_001'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(name):
    return json.loads((RUN / name).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


checks = 0


def check(condition, reason):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(reason)


receipt, plan, split, model = (read(name) for name in ('receipt.json', 'registered_plan.json',
    'flight_split_manifest.json', 'flight_forecaster_checkpoint.json'))
check(receipt['status'] == 'completed_forecaster_training_and_causal_evaluation', 'receipt completed')
check(receipt['native_executed'] is False and plan['native_branches'] == 0, 'no native authority claimed')
check(receipt['plan_sha256'] == digest(plan), 'registered plan binding')
check(0 < receipt['wall_seconds'] < plan['settings']['task_wall_seconds'] == 600., 'total time budget')
for file, expected in receipt['artifacts'].items():
    check(sha(RUN / file) == expected, 'artifact binding ' + file)
for file, expected in receipt['source_sha256_pins'].items():
    check(sha(Path(file)) == expected, 'source exit pin ' + file)
raw = Path(plan['source_path'])
check(sha(raw) == plan['source_sha256'] == split['source_sha256'] == model['source_sha256'], 'raw bytes binding')
check(sha(RUN / 'private/flight_label_index.jsonl') == split['private_label_index_sha256'], 'private label binding')
check(sha(RUN / 'public/static_flight_plan.json') == split['static_plan_sha256'], 'static plan binding')

private = [json.loads(line) for line in (RUN / 'private/flight_label_index.jsonl').read_text().splitlines()]
labels = {row['bag_id']: row for row in private}
check(len(private) == len(labels) == split['raw_bag_count'] == 28506, 'all physical identities retained')
raw_lines = raw.read_text(encoding='utf8').splitlines()[1:]
for line in raw_lines:
    if not line.strip():
        continue
    ident, entry, std, start, end, unloader, loader = line.split()
    label = labels['legacy_' + ident]
    ref = 'hg_' + digest([float(std), int(end), unloader])[:24]
    check(label['flight_ref'] == label['parent_flight_ref'] == ref, 'stable original parent identity')
    check(label['arrived_at'] == float(entry) <= float(std) == label['scheduled_std'], 'original label and STD closure')
    check(label['region'] == 'legacy_start_' + start and label['loader'] == loader
        and label['original_start'] == int(start) and label['copy_lineage'] == 'original_1x', 'unmodified private original metadata')

public = read('public/static_flight_plan.json')
check(public['published_at'] is None and public['received_at'] == 0.
    and public['availability_basis'] == 'static_predeclared' and public['static_assumption'], 'honest static availability')
roster = {row['parent_flight_ref']: row for row in split['group_roster']}
public_entries = {row['flight_ref']: row for row in public['entries']}
check(len(roster) == len(public_entries) == len(public['entries']) == 360, 'complete retrospective source group roster')
check(set(roster) == set(public_entries) == {row['parent_flight_ref'] for row in private}, 'parent partition complete')
train_refs = {ref for ref, row in roster.items() if row['split'] == 'train'}
check(set(model['training_parent_refs']) == train_refs and len(train_refs) == 153, 'training only closed train parents')
for ref, row in roster.items():
    expected_split = 'train' if row['scheduled_std'] <= 43200 else 'development' if row['scheduled_std'] <= 57600 else 'test'
    check(row['split'] == expected_split and row['label_closes_at'] == row['scheduled_std'], 'STD-defined parent split and closure')
    entry = public_entries[ref]
    check(set(entry) == {'flight_ref', 'identity_kind', 'scheduled_event_type', 'scheduled_event_at',
        'planned_injection_region', 'mapping_version'} and entry['planned_injection_region'] is None
        and entry['mapping_version'] is None and entry['identity_kind'] == 'historical_group'
        and entry['scheduled_event_type'] == 'STD' and entry['scheduled_event_at'] == row['scheduled_std'], 'no private truth in plan entry')
for window in split['evaluation_windows']:
    check(window['forecast_origin'] >= (43200 if window['split'] == 'development' else 57600)
        and window['label_window_end'] == window['forecast_origin'] + 1800
        and window['label_window_end'] <= (57600 if window['split'] == 'development' else 86400), 'no cross-split future target')
check(split['all_physical_source_rows_retained'] and not split['physical_task_deletion_performed'], 'statistical purge only')

train_rows = [row for row in private if row['parent_flight_ref'] in train_refs]
check(len(train_rows) == model['training_bag_count'] == 12549, 'closed train bag count')
check(model['training_labels_closed_at'] == model['frozen_at'] == 43200, 'training freeze cutoff')
check(model['model_sha256'] == digest({key: value for key, value in model.items() if key != 'model_sha256'}), 'model content binding')
for region, params in model['parameters'].items():
    selected = [row for row in train_rows if row['region'] == region]
    counts = Counter(row['parent_flight_ref'] for row in selected)
    values = [counts[ref] for ref in train_refs]
    check(params['training_parent_count'] == len(values) and params['zero_count_groups_included'] == values.count(0), 'zero count groups included')
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    fitted_mean = mean if mean else len(train_rows) / len(train_refs) / len(model['regions'])
    latent_variance = max(variance - mean, fitted_mean * .01, 1e-6)
    check(math.isclose(params['shape'], fitted_mean ** 2 / latent_variance, rel_tol=1e-9)
        and math.isclose(params['rate'], fitted_mean / latent_variance, rel_tol=1e-9), 'independent train-only moments')
    bins = [0] * 1440
    for row in selected or train_rows:
        lead = row['arrived_at'] - row['scheduled_std']
        check(-86400 <= lead <= 0 and row['scheduled_std'] <= 43200, 'closed relative training arrival')
        bins[min(1439, int((lead + 86400) // 60))] += 1
    total, cumulative = sum(bins), 0
    expected = [0.]
    for count in bins:
        cumulative += count
        expected.append(cumulative / total)
    check(params['cdf_edges'] == list(range(-86400, 1, 60))
        and all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(params['cdf_values'], expected, strict=True)), 'independent train-only CDF')

forecast_counts = Counter()
for line in (RUN / 'forecast_predictions.jsonl').read_text().splitlines():
    record = json.loads(line)
    prediction = record['forecast']
    forecast_counts[(record['split'], record['method'])] += 1
    check(set(record['statistical_parent_scope']) == {ref for ref, row in roster.items() if row['split'] == record['split']}, 'population never mixes parent splits')
    check(prediction['model_sha256'] == model['model_sha256'] and prediction['forecast_origin'] >= model['frozen_at'], 'forecast frozen model binding')
    check(prediction['native_execution_authority'] is False and prediction['predicted_inventory_is_actual'] is False, 'prediction has no physical authority')
    check(prediction['bin_edges_seconds'] == list(range(0, 1801, 60)) and prediction['absolute_bin_edges'] ==
        [prediction['forecast_origin'] + offset for offset in range(0, 1801, 60)], 'future absolute bin projection')
    cutoffs = prediction['information_cutoffs']
    check(all(value is None or value <= prediction['forecast_origin'] for value in cutoffs.values()), 'no future forecast information')
    if record['method'] == 'flight_prior_only':
        check(not prediction['observed_count_update'] and cutoffs['observed_arrivals_through'] is None, 'main uses unknown counts not observed zero')
    elif record['method'] == 'flight_synthetic_observed_counts':
        check(prediction['count_source_kind'] == 'explicit_synthetic_asof_arrival_feed', 'auxiliary synthetic identity disclosed')
    else:
        check(prediction['context_sha256'] is None and prediction['method'] == 'no_plan_recent_arrival_rate', 'baseline has no plan')
    check(not {'actual', 'arrived_at', 'bag_id', 'loader', 'parent_flight_ref', 'scheduled_std'} & set(prediction), 'no private target fields in forecast')
    for values in prediction['new_demand_mean_by_region'].values():
        check(len(values) == 30 and all(math.isfinite(value) and value >= 0 for value in values), 'finite future count means')

evaluation = read('forecast_evaluation.json')
development_summary = {}
for method, regions in evaluation['metrics']['development'].items():
    development_summary[method] = {horizon: {metric: sum(region[horizon][metric] for region in regions.values()) / len(regions)
        for metric in ('MAE', 'bias_predicted_minus_actual', 'interval_90_empirical_coverage', 'interval_mean_width')}
        for horizon in ('60', '300', '900', '1800')}
report = {'status': 'passed', 'checks': checks, 'auditor_imports': 'Python standard library only',
    'run': str(RUN), 'receipt_sha256': sha(RUN / 'receipt.json'), 'training_wall_seconds': receipt['wall_seconds'],
    'split_parent_counts': dict(Counter(row['split'] for row in roster.values())),
    'forecast_record_counts': {split_name + ':' + method: count for (split_name, method), count in forecast_counts.items()},
    'formal_test_performance_not_extracted_by_this_audit': True, 'development_macro_region_summary': development_summary,
    'limits': ['single simulated source day', 'static retrospective group roster may omit zero-bag flights',
        'legacy source regions are not yet airport owners', 'main counts unavailable; synthetic observed-count variant auxiliary only',
        'intervals uncalibrated', 'no actor/native/RL success inferred from forecast fit']}
with (OUTPUT / 'audit_report.json').open('x', encoding='utf8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
print(json.dumps({'status': report['status'], 'checks': checks, 'report': str(OUTPUT / 'audit_report.json')}))
