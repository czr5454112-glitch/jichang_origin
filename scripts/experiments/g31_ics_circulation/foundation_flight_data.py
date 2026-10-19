"""Offline exporter of a declared static plan and separate private arrival labels.

This module is training/evaluator-only. Runtime forecasting imports neither it
nor the original task parser. Source grouping is retrospective and may omit
zero-bag flights; it is not a real complete airport timetable.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = '0f39d359b47a3f243ab077e4a294cbab56ec306a0f89bcc0ccc1d946caceef87'
REGIONS = ['legacy_start_' + str(node) for node in (0, 1, 2, 3, 4, 5, 53)]
MAPPING_VERSION = 'g31.legacy_source_start_identity.v1'
TIME_BASIS = {'unit': 'seconds', 'origin': 'legacy_simulated_source_day_start',
    'timezone': 'Asia/Shanghai', 'conversion_version': 'legacy_seconds_identity_experiment_v1'}


def require(ok, reason):
    if not ok:
        raise ValueError('flight_data:' + reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def load_source(path, *, expected_sha256=SOURCE_SHA256):
    payload = Path(path).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == expected_sha256, 'frozen_raw_source_identity')
    lines = payload.decode('utf8').splitlines()
    require(lines[0].split() == ['ID', 'EntryTime(s)', 'STD(s)', 'star', 'end', 'Unloader', 'Loader'], 'source_header')
    rows, ids = [], set()
    for line in lines[1:]:
        if not line.strip():
            continue
        item = line.split()
        require(len(item) == 7, 'seven_source_fields')
        bag_id, entry, std, start, end, unloader, loader = item
        require(bag_id not in ids, 'unique_source_bag')
        ids.add(bag_id)
        entry, std = float(entry), float(std)
        require(0 <= entry <= std <= 86400., 'STD_group_closure_contract')
        region = 'legacy_start_' + start
        require(region in REGIONS, 'registered_source_region')
        group = 'hg_' + digest([std, int(end), unloader])[:24]
        rows.append({'bag_id': 'legacy_' + bag_id, 'parent_flight_ref': group, 'flight_ref': group,
            'copy_lineage': 'original_1x', 'arrived_at': entry, 'scheduled_std': std,
            'region': region, 'loader': loader, 'original_start': int(start)})
    return rows


def split_of(std, train_cutoff=43200., dev_cutoff=57600.):
    return 'train' if std <= train_cutoff else 'development' if std <= dev_cutoff else 'test'


def build_artifacts(rows, *, train_cutoff=43200., dev_cutoff=57600.,
                    bin_seconds=60, horizon_seconds=1800, evaluation_stride=300):
    require(0 < train_cutoff < dev_cutoff < 86400., 'chronological_cutoffs')
    groups = {}
    for row in rows:
        require(row['parent_flight_ref'] == row['flight_ref'] and row['copy_lineage'] == 'original_1x',
            'no_unregistered_duplicate_lineage')
        require(0 <= row['arrived_at'] <= row['scheduled_std'] <= 86400., 'STD_group_closure_contract')
        previous = groups.setdefault(row['flight_ref'], row['scheduled_std'])
        require(previous == row['scheduled_std'], 'stable_parent_STD')
    require(groups, 'nonempty_group_roster')
    entries = [{'flight_ref': ref, 'identity_kind': 'historical_group', 'scheduled_event_type': 'STD',
        'scheduled_event_at': std, 'planned_injection_region': None, 'mapping_version': None}
        for ref, std in sorted(groups.items(), key=lambda item: (item[1], item[0]))]
    context = {'schema_version': 'g31.foundation.flight_context.v1', 'source_id': 'legacy_static_declared_plan_v1',
        'version': 1, 'published_at': None, 'received_at': 0., 'owner_scope': 'flight_forecast_evaluator',
        'time_basis': TIME_BASIS, 'validity_policy': {'mode': 'until_superseded', 'valid_until': None},
        'availability_basis': 'static_predeclared',
        'static_assumption': 'Retrospectively identified historical groups and STD are pre-supplied at experiment time 0; '
            'receipt time is experimental, publication remains missing; zero-bag flights may be absent.',
        'entries': entries}
    roster = [{'parent_flight_ref': ref, 'split': split_of(std, train_cutoff, dev_cutoff),
        'scheduled_std': std, 'label_closes_at': std, 'closure_rule': 'declared_all_group_arrivals_no_later_than_STD',
        'copy_lineage': ['original_1x']} for ref, std in sorted(groups.items(), key=lambda item: (item[1], item[0]))]
    windows, purged = [], []
    for name, start, end in [('development', train_cutoff, dev_cutoff), ('test', dev_cutoff, 86400.)]:
        for origin in range(int(start), int(end), evaluation_stride):
            item = {'split': name, 'forecast_origin': float(origin), 'label_window_end': float(origin + horizon_seconds)}
            if origin + horizon_seconds <= end:
                windows.append(item)
            else:
                purged.append({**item, 'reason': 'forecast_label_window_crosses_split_close'})
    manifest = {'schema': 'g31.foundation.flight_split_manifest.v1', 'source_sha256': SOURCE_SHA256,
        'source_scope': 'legacy_simulated_one_day_stream_not_independent_airport_days',
        'region_mapping_version': MAPPING_VERSION, 'regions': REGIONS, 'time_basis': TIME_BASIS,
        'train_label_cutoff': train_cutoff, 'development_label_cutoff': dev_cutoff,
        'test_model_selection_frozen_at': dev_cutoff, 'observed_source_day_end': 86400.,
        'group_closure_rule': 'all arrivals by declared STD; all rows checked, last_entry_time is not a live closure signal',
        'group_roster': roster, 'evaluation_windows': windows, 'purged_statistical_windows': purged,
        'bin_seconds': bin_seconds, 'horizon_seconds': horizon_seconds, 'evaluation_stride_seconds': evaluation_stride,
        'main_count_update': 'None_no_native_public_group_association_established',
        'auxiliary_count_update': 'explicit_synthetic_asof_arrival_feed_only',
        'statistical_population': 'Each split evaluates only its parent groups; development excludes test parents even if they arrive early.',
        'all_physical_source_rows_retained': True, 'physical_task_deletion_performed': False,
        'balanced_airport_projection_used_as_prior': False, 'cross_day_generalization_supported': False}
    return context, manifest


def export(source, output, **settings):
    rows = load_source(source)
    context, manifest = build_artifacts(rows, **settings)
    output = Path(output)
    write_new(output / 'public/static_flight_plan.json', context)
    private = output / 'private/flight_label_index.jsonl'
    private.parent.mkdir(parents=True, exist_ok=True)
    with private.open('x', encoding='utf8') as stream:
        for row in rows:
            stream.write(json.dumps({'schema': 'g31.foundation.private_flight_label.v1',
                'scope': 'training_evaluator_only_never_runtime_predictor', **row}, sort_keys=True) + '\n')
    manifest.update(private_label_index_sha256=hashlib.sha256(private.read_bytes()).hexdigest(),
        static_plan_sha256=hashlib.sha256((output / 'public/static_flight_plan.json').read_bytes()).hexdigest(),
        raw_bag_count=len(rows), historical_group_count=len(context['entries']))
    write_new(output / 'flight_split_manifest.json', manifest)
    return rows, context, manifest
