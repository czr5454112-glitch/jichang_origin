"""Offline time-scale evidence for exactly two closed full TRAIN005 runs.

Default: bind inputs and check closure metadata only. --execute streams saved
evidence, never starts native, never reads owner ACK histories, and never writes
the experiment ledger. Actual BAG_ARRIVAL receipts, not planned jobs, are labels.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import sys

SOURCE_SHA = '22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef'
WORKFLOW_SHA = '1509684b0eaa8433795343d508142654f90927ef70553783c272f343205aa30d'
PLAN_SHAS = {2101: '0ad42c8c5b96e48b4801e649209d463da4ddbecd799e0a54c86200a18b77238c',
             2102: '91f41e380b08ce02e4ba49ee58a8af8879c5de2d7a451683ad989b286bb02c09'}
PARENTS = (2101, 2102)
START, END, PERIOD = 7200., 59400., 60.
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
SUGGESTED_HARD_SECONDS = 1200
RUN_FILES = ('plan.json', 'worker_report.json', 'receipt.json', 'trajectory.json.gz',
             'terminal_evidence.json.gz', 'observations.json.gz', 'decisions.json.gz', 'calls.json.gz')
FAILED = {'failed', 'rejected', 'expired', 'cancelled'}
# Frozen foundation_airport_batch_patch.ACTIVE, with explicit submission reply
# aliases retained. Native starts with undelivered before command delivery.
ACTIVE = {'pending', 'submitted', 'accepted', 'granted', 'requested', 'delivered',
          'undelivered', 'dispatching', 'departed', 'in_transit'}


def need(ok, why):
    if not ok:
        raise ValueError('full_train_time_scale:' + why)


def number(value):
    need(type(value) in (int, float) and math.isfinite(value), 'finite_number')
    return float(value)


def nonnegative(value):
    value = number(value)
    need(value >= 0, 'nonnegative_duration')
    return value


def strict_pairs(items):
    value = {}
    for key, item in items:
        need(key not in value, 'duplicate_json_key:' + key)
        value[key] = item
    return value


DECODER = json.JSONDecoder(object_pairs_hook=strict_pairs,
    parse_float=lambda text: number(float(text)),
    parse_constant=lambda text: need(False, 'nonfinite_json:' + text))


def read(path):
    with Path(path).open(encoding='utf8') as stream:
        return DECODER.decode(stream.read())


def bind(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), sha256=digest)


def verify(refs):
    for ref in refs:
        need(bind(ref['path']) == ref, 'changed_bound_bytes:' + ref['path'])


def fresh(path, value):
    path = Path(path)
    if path.suffix == '.gz':
        with path.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as z:
            with io.TextIOWrapper(z, encoding='utf8', newline='\n') as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                stream.write('\n')
    else:
        with path.open('x', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write('\n')
    need(path.stat().st_size < MAX_OUTPUT_BYTES, 'output_size_limit')
    return bind(path)


def stream_object(path, handlers, *, chunk_chars=1024*1024, max_item_chars=64*1024*1024):
    """Stream every top-level array, retaining only scalar/object metadata.

    Fully consumes gzip/JSON tail. A handler receives one array item at a time;
    unrequested arrays are parsed and discarded. No giant terminal object or
    trajectory is loaded. Limits are decoded characters per individual item.
    """
    need(type(chunk_chars) is int and chunk_chars > 0 and max_item_chars > 0, 'stream_limits')
    metadata, seen = {}, set()
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        buffer, eof = '', False
        def fill():
            nonlocal buffer, eof
            text = stream.read(min(chunk_chars, max_item_chars+1))
            buffer += text
            eof = not text
        def ws():
            nonlocal buffer
            while True:
                buffer = buffer.lstrip(' \t\r\n')
                if buffer or eof:
                    return
                fill()
        def char(expected):
            nonlocal buffer
            ws()
            need(buffer.startswith(expected), 'expected_delimiter:' + expected)
            buffer = buffer[1:]
        def value(delimiters):
            nonlocal buffer
            ws()
            while True:
                try:
                    result, end = DECODER.raw_decode(buffer)
                except json.JSONDecodeError:
                    need(len(buffer) <= max_item_chars and not eof, 'truncated_or_oversized_item')
                    fill()
                    continue
                need(end <= max_item_chars, 'oversized_item')
                rest = buffer[end:].lstrip(' \t\r\n')
                if rest and rest[0] in delimiters:
                    buffer = rest
                    return result
                need(len(buffer) <= max_item_chars and not eof, 'missing_item_delimiter')
                fill()
        char('{')
        ws()
        if not buffer.startswith('}'):
            while True:
                key = value(':')
                need(isinstance(key, str) and key not in seen, 'unique_top_level_key')
                seen.add(key)
                char(':')
                ws()
                if buffer.startswith('['):
                    char('[')
                    ws()
                    count = 0
                    if not buffer.startswith(']'):
                        while True:
                            item = value(',]')
                            if key in handlers:
                                handlers[key](item)
                            count += 1
                            del item
                            ws()
                            if buffer.startswith(']'):
                                break
                            char(',')
                    char(']')
                    metadata[key] = dict(streamed_items=count)
                else:
                    metadata[key] = value(',}')
                ws()
                if buffer.startswith('}'):
                    break
                char(',')
        char('}')
        ws()
        need(not buffer and eof, 'trailing_object_data')
    return metadata


def source_check(ref):
    need(ref['sha256'] == SOURCE_SHA, 'source005_required')
    root = Path(ref['path']).parent
    manifest = read(ref['path'])
    need(root.name == 'terminal_flow_runtime_005' and Path(manifest['root']).resolve() == root, 'source_root')
    need(bool(manifest['files']), 'nonempty_source_manifest')
    refs = []
    for relative, sha in manifest['files'].items():
        path = (root/relative).resolve()
        need(path.is_relative_to(root), 'source_escape')
        refs.append(dict(path=str(path), sha256=sha))
    verify([ref] + refs)
    return root


def load_helpers(root):
    need(not any(k == 'scripts' or k.startswith('scripts.') for k in sys.modules), 'fresh_python_required')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    package = 'scripts.experiments.g31_ics_circulation.'
    helpers = {key: importlib.import_module(package+name) for key, name in dict(
        transport='foundation_airport_transport_evidence', stream='foundation_airport_json_stream',
        projection='foundation_airport_inventory_projection', digest='foundation_airport_batch_patch',
        campaign='foundation_airport_transport_campaign').items()}
    refs = []
    for name, module in list(sys.modules.items()):
        if (name == 'scripts' or name.startswith('scripts.')) and getattr(module, '__file__', None):
            path = Path(module.__file__).resolve()
            need(path.is_relative_to(root), 'nonfrozen_import:' + name)
            refs.append(bind(path))
    return helpers, refs


def collect(source_ref, workflow_ref, h):
    need(workflow_ref['sha256'] == WORKFLOW_SHA, 'workflow005_required')
    workflow = read(workflow_ref['path'])
    need(workflow['source_bundle'] == source_ref and workflow['TEST_unlocked'] is False
         and workflow['R1_enabled'] is False, 'workflow_source_or_lock')
    stages = [s for s in workflow['stages'] if s['phase'] == 'train_demand']
    need(len(stages) == 1 and stages[0]['name'] == 'full_train_005'
         and stages[0]['parents'] == list(PARENTS), 'full_train_stage')
    block_path = Path(workflow_ref['path']).parent.parent/'full_train_005/block.json'
    inputs = {ref['path']: ref for ref in (source_ref, workflow_ref, bind(block_path))}
    def add(path, expected=None):
        ref = bind(path)
        need(expected is None or ref['sha256'] == expected, 'registered_input_changed')
        need(ref['path'] not in inputs or inputs[ref['path']] == ref, 'input_changed_during_binding')
        inputs[ref['path']] = ref
        return ref
    block = read(block_path)
    need(block['source_bundle'] == source_ref and block['parents'] == list(PARENTS)
         and block['methods'] == ['TF-B1-300'] and block['phase'] == 'train_demand', 'full_train_block')
    h['campaign']._validate_block_manifest(block)
    rows = {}
    for registered in block['task_plans']:
        ref = add(registered['path'], registered['sha256'])
        plan = read(ref['path'])
        parent = plan['parent']['parent_seed']
        need(parent in PARENTS and parent not in rows and ref['sha256'] == PLAN_SHAS[parent], 'exact_train_plan_roster')
        need(plan['parent']['split'] == 'train' and plan['parent']['synthetic'] is True
             and plan['activation'] == START and plan['horizon'] == END
             and plan['source_bundle'] == source_ref and plan['method'] == 'TF-B1-300', 'full_train_identity')
        need(not h['campaign'].method_contract_errors(plan), 'method_contract')
        directory = Path(ref['path']).parent
        need(Path(plan['output']).resolve() == directory, 'plan_output')
        for name in RUN_FILES:
            add(directory/name)
        for dependency in plan.values():
            if isinstance(dependency, dict) and {'path', 'sha256'} <= dependency.keys():
                add(dependency['path'], dependency['sha256'])
        receipt, worker = read(directory/'receipt.json'), read(directory/'worker_report.json')
        need(receipt['plan_sha256'] == ref['sha256'] and receipt['worker'] == worker, 'receipt_worker_plan_binding')
        need(receipt['process'].get('exitcode') == 0 and worker['process_status'] == 'completed'
             and worker['scientific_status'] == 'closed' and worker['final_physical_time'] == END, 'closed_full_train_required')
        rows[parent] = dict(plan=plan, worker=worker, directory=directory)
    need(set(rows) == set(PARENTS), 'two_closed_train_parents')
    need(len({r['plan']['parent']['common_historical_template_sha256'] for r in rows.values()}) == 1, 'same_template')
    return rows, list(inputs.values())


def actual_arrival(event, jobs, seen, arrivals, end):
    if event.get('event') != 'BAG_ARRIVAL':
        return
    identity = event['business_bag_id']
    need(identity in jobs and identity not in seen, 'unique_known_actual_arrival')
    job = jobs[identity]
    at = number(event['time'])
    need(0 <= at <= end and at == job['arrival'] and event['node'] == job['origin'], 'actual_arrival_identity_time_node')
    seen.add(identity)
    arrivals.append(dict(business_bag_id=identity, origin=event['node'], arrival=at))


def validate_actual_arrivals(jobs, seen, end):
    need(seen == {identity for identity, job in jobs.items() if job['arrival'] <= end}, 'complete_actual_arrival_receipts')


def time_or_none(value):
    if value is None:
        return None
    value = number(value)
    return value if value >= 0 else None


def lifecycle(call, native, edge, *, cutoff):
    request = call['request']
    submitted = number(request['issued_at'])
    need(submitted == call['at'] and submitted <= cutoff, 'call_submission_clock')
    if native is not None:
        need(native['request_id'] == request['request_id'], 'native_request_identity')
        for key in ('owner_id', 'tray_id', 'source', 'destination'):
            if key in native:
                need(native[key] == request[key], 'native_payload_identity:' + key)
    received = time_or_none((native or {}).get('received_at'))
    departed = time_or_none((native or {}).get('departed_at'))
    if edge is not None:
        edge = number(edge)
        need(submitted <= edge <= cutoff, 'first_edge_clock')
    if departed is not None:
        need(submitted <= departed <= cutoff, 'departure_clock')
    if received is not None:
        need(submitted <= received <= cutoff and (departed is None or departed <= received)
             and (edge is None or edge <= received), 'receipt_clock')
    status = (native or {}).get('status')
    if native is not None:
        need((status == 'received') == (received is not None), 'received_status_time_consistency')
    reply_status = (call.get('reply') or {}).get('status')
    failed = status in FAILED or (received is None and reply_status in FAILED)
    need(not (received is not None and failed), 'received_failure_conflict')
    outcome = ('received' if received is not None else 'failed' if failed else
               'right_censored' if native is not None and status in ACTIVE else 'unknown_native_outcome')
    return dict(request_id=request['request_id'], owner_id=request['owner_id'],
        physical_tray_id=request['tray_id'], source=request['source'], destination=request['destination'],
        submitted_at=submitted, departed_at=departed, first_edge_at=edge, received_at=received,
        native_status=status, reply_status=reply_status, outcome=outcome,
        submission_to_departure_seconds=None if departed is None else departed-submitted,
        submission_to_first_edge_seconds=None if edge is None else edge-submitted,
        submission_to_received_seconds=None if received is None else received-submitted,
        first_edge_to_received_seconds=None if received is None or edge is None else received-edge,
        unreceived_elapsed_lower_bound_seconds=cutoff-submitted if outcome == 'right_censored' else None)


def sample_bounds(samples, start=START, end=END, period=PERIOD):
    """Sampling bounds only: no interpolation across missing or unknown samples."""
    samples = sorted(samples, key=lambda x: x['at'])
    need(len({r['at'] for r in samples}) == len(samples), 'duplicate_station_sample_time')
    expected = {start+i*period for i in range(int((end-start)/period)+1)}
    actual = {r['at'] for r in samples}
    need(actual <= expected, 'station_sample_outside_registered_ticks')
    rows = {r['at']: r for r in samples}
    known = {t for t, r in rows.items() if r['stock'] is not None and r['waiting'] is not None}
    shortage = lambda r: r['stock'] == 0 and r['waiting'] is not None and r['waiting'] > 0
    episodes, depleted = [], []
    active, stock_start, prev = None, None, None
    for at in sorted(expected):
        row = rows.get(at)
        ok = at in known
        if not ok:
            if active is not None:
                active.update(last_shortage_sample_at=prev['at'], cessation_upper_bound=None, right_censored=True)
                episodes.append(active)
                active = None
            stock_start = None
            prev = None
            continue
        if row['stock'] > 0 and stock_start is None:
            stock_start = at
        if row['stock'] == 0 and stock_start is not None:
            depleted.append(dict(first_positive_sample_at=stock_start, last_positive_sample_at=prev['at'],
                first_zero_sample_at=at, elapsed_from_first_positive_lower_bound=prev['at']-stock_start,
                elapsed_from_first_positive_upper_bound=at-stock_start,
                continuous_stock_between_samples_not_observed=True))
            stock_start = None
        if shortage(row) and active is None:
            active = dict(first_shortage_sample_at=at, onset_lower_bound=prev['at'] if prev else None,
                onset_upper_bound=at, left_censored=prev is None)
        if not shortage(row) and active is not None:
            active.update(last_shortage_sample_at=prev['at'], cessation_upper_bound=at, right_censored=False)
            episodes.append(active)
            active = None
        prev = row
    if active is not None:
        active.update(last_shortage_sample_at=prev['at'], cessation_upper_bound=None, right_censored=True)
        episodes.append(active)
    for row in episodes:
        row['sample_span_lower_bound_seconds'] = row['last_shortage_sample_at']-row['first_shortage_sample_at']
        row['duration_upper_bound_seconds'] = (row['cessation_upper_bound']-row['onset_lower_bound']
            if row['cessation_upper_bound'] is not None and row['onset_lower_bound'] is not None else None)
        row['bounds_assume_no_unobserved_state_reversal_between_adjacent_samples'] = True
    first = episodes[0]['first_shortage_sample_at'] if episodes else None
    return dict(expected_tick_count=len(expected), observed_tick_count=len(actual), known_tick_count=len(known),
        absent_tick_count=len(expected-actual), unknown_sample_count=len(actual-known),
        first_sampled_shortage_at=first,
        first_sampled_shortage_offset_from_activation=None if first is None else first-start,
        earlier_shortage_unobserved_possible=bool((expected-known) & {t for t in expected if first is None or t < first}),
        shortage_episodes=episodes, sampled_stock_depletion_intervals=depleted,
        exact_continuous_shortage_duration_known=False, exact_continuous_depletion_duration_known=False)


def metrics(rows, keys, distribution):
    return {key: dict(distribution([r[key] for r in rows if r.get(key) is not None]),
                      denominator=len(rows), missing=sum(r.get(key) is None for r in rows)) for key in keys}


TRANSFER_KEYS = ('submission_to_departure_seconds', 'submission_to_first_edge_seconds',
    'submission_to_received_seconds', 'first_edge_to_received_seconds', 'unreceived_elapsed_lower_bound_seconds')
SELECTED_KEYS = ('estimated_static_travel_seconds', 'estimated_decision_to_arrival_seconds',
    'decision_to_submission_seconds', 'order_proposed_to_submission_seconds',
    'plan_creation_to_submission_seconds', 'submission_minus_planned_slot_seconds',
    'actual_decision_to_received_seconds', 'submission_to_received_seconds', 'arrival_minus_selected_eta_seconds',
    'forecast_first_shortage_lead_seconds', 'unreceived_eta_lateness_lower_bound_seconds')


def summarize_transfers(all_requests, selected, distribution):
    matched = [r for r in selected if r['outcome'] == 'received'
               and r.get('estimated_decision_to_arrival_seconds') is not None]
    return dict(all_actual_requests=dict(denominator=len(all_requests),
        population='unique recorded nonretry transfer calls issued in the registered window; native records without calls counted separately',
        outcomes=dict(Counter(r['outcome'] for r in all_requests)),
        timing_seconds=metrics(all_requests, TRANSFER_KEYS, distribution)),
        selected_proposals=dict(denominator=len(selected), outcomes=dict(Counter(r['outcome'] for r in selected)),
            timing_seconds=metrics(selected, SELECTED_KEYS, distribution)),
        matched_received_selected_proposals=dict(denominator=len(matched),
            timing_seconds=metrics(matched, SELECTED_KEYS, distribution),
            selection_bias='conditional on selected, submitted, observed received and known ETA; failures and censoring excluded explicitly'),
        distributions_descriptive_only=True, failures_not_censored=True, unknown_native_outcomes_not_censored=True)


def pooled_timing(timings):
    def merge(rows):
        return dict(count=sum(r['count'] for r in rows), total_seconds=math.fsum(r['total_seconds'] for r in rows),
            p50_seconds=None, p90_seconds=None, p95_seconds=None,
            quantiles_unknown_reason='raw callback durations not retained; parent quantiles are not averaged')
    result = merge(timings)
    stages = set.intersection(*(set(t['stages']) for t in timings))
    need(all(set(t['stages']) == stages for t in timings), 'same_callback_stage_names')
    result['stages'] = {name: merge([t['stages'][name] for t in timings]) for name in sorted(stages)}
    result['submission_wall_seconds'] = None
    result['excludes'] = ['catalogue', 'submission', 'native advance', 'final export']
    result['complete_request_100ms_certified'] = False
    return result


def analyze(row, h):
    directory, plan = row['directory'], row['plan']
    distribution = h['transport'].distribution
    population = read(plan['input']['path'])
    jobs = {r['business_bag_id']: r for r in population['jobs']}
    need(len(jobs) == len(population['jobs']) == plan['parent']['offered_count'], 'unique_complete_input_identity_population')
    del population
    arrivals, seen_arrivals, native, edges = [], set(), {}, {}
    def receipt(event):
        actual_arrival(event, jobs, seen_arrivals, arrivals, END)
        leg = event.get('transport_leg_id') or ''
        if event.get('event') == 'EDGE_ENTER' and ':empty_return:' in leg:
            rid = leg.rsplit(':empty_return:', 1)[0]
            at = number(event['time'])
            edges[rid] = min(edges.get(rid, at), at)
    def transfer(item):
        identity = item['request_id']
        need(identity not in native, 'duplicate_native_request')
        native[identity] = item
    terminal_meta = stream_object(directory/'terminal_evidence.json.gz', dict(receipts=receipt, transfers=transfer))
    need(terminal_meta['physical_clock'] == END and terminal_meta['advance']['horizon_complete'] is True
         and terminal_meta['advance']['status'] == 'reached', 'terminal_closed_horizon')
    validate_actual_arrivals(jobs, seen_arrivals, END)
    del jobs
    trajectory, calendar = {}, set()
    def trajectory_row(item):
        identity, key = item['decision_id'], (item['owner_id'], item['decision_time'])
        need(identity not in trajectory and key not in calendar and START <= key[1] < END, 'unique_trajectory_identity_window')
        calendar.add(key)
        keep = ('decision_id', 'decision_time', 'owner_id', 'public_observation_ref', 'legal_catalog_ref',
            'requested_action', 'actual_submission', 'request_id', 'first_edge_event', 'received_event')
        trajectory[identity] = {k: item.get(k) for k in keep}
    trajectory_meta = stream_object(directory/'trajectory.json.gz', dict(rows=trajectory_row))
    manifest = trajectory_meta['manifest']
    need(trajectory_meta['scientific_status'] == 'closed_finite_horizon' and trajectory_meta['physical_clock'] == END
         and trajectory_meta['process_status'] == 'completed' and trajectory_meta['logs_complete'] is True, 'closed_trajectory')
    need(manifest['trajectory_id'] == plan['task_id'] and manifest['split'] == 'train'
         and manifest['environment_seed'] == plan['parent']['parent_seed'] and manifest['physical_start'] == START
         and manifest['physical_end'] == END and manifest['execution_source_id'] == SOURCE_SHA
         and manifest['native_domain_id'] == plan['binary']['sha256']
         and manifest['episode_parent_group'] == plan['parent']['parent_group'], 'trajectory_manifest_identity')
    calls, request_rows, all_call_count = {}, {}, 0
    for call in h['stream'].iter_json_array_gz(directory/'calls.json.gz'):
        if call.get('kind') != 'transfer' or call.get('retry'):
            continue
        rid = call['request']['request_id']
        need(rid not in calls, 'duplicate_nonretry_request')
        calls[rid] = call
        all_call_count += 1
        if START <= call['at'] < END:
            request_rows[rid] = lifecycle(call, native.get(rid), edges.get(rid), cutoff=END)
    observations, samples, loaders, local_nodes, obs_count = {}, defaultdict(list), set(), set(), 0
    observation_calendar, last_observation_time = set(), -1.
    for record in h['stream'].iter_json_array_gz(directory/'observations.json.gz'):
        obs, digest = record['observation'], record['digest']
        need(h['digest'].digest(obs) == digest and digest not in observations, 'unique_valid_observation_digest')
        at, owner = number(obs['now']), obs['owner_id']
        need(START <= at <= END and at >= last_observation_time, 'observation_window_or_order')
        need((owner, at) not in observation_calendar, 'unique_observation_owner_time')
        observation_calendar.add((owner, at))
        last_observation_time = at
        observations[digest] = (owner, at)
        obs_count += 1
        current = h['projection'].prepare_inventory_projection(obs)
        loaders.update(obs['static_role_contract']['loader_nodes'])
        for node, state in current.nodes.items():
            if state['local']:
                local_nodes.add(node)
                samples[node].append(dict(at=at, owner_id=owner,
                    stock=state['stock'] if state['inventory_known'] else None,
                    waiting=state['waiting'] if state['waiting_known'] else None))
    sources, plans, selected, used_requests, decisions_seen = set(), {}, [], set(), set()
    decision_count, endpoint_count = 0, 0
    for decision in h['stream'].iter_json_array_gz(directory/'decisions.json.gz'):
        identity, at = decision['decision_id'], decision['decision_time']
        need(identity not in decisions_seen, 'unique_decision_identity')
        decisions_seen.add(identity)
        need(observations.get(decision['public_observation_ref']) == (decision['owner_id'], at), 'decision_observation_join')
        decision_count += 1
        if identity not in trajectory:
            need(at == END, 'decision_missing_from_trajectory')
            endpoint_count += 1
            continue
        tr = trajectory[identity]
        for key in ('owner_id', 'decision_time', 'public_observation_ref', 'legal_catalog_ref', 'requested_action'):
            need(tr[key] == decision[key], 'decision_trajectory_join:' + key)
        sources.update(a['source'] for a in decision['catalog']['candidates'] if a.get('kind', a.get('action_type')) == 'transfer')
        selection = decision['selection']
        flow = selection.get('flow_plan')
        if flow is not None:
            compact = dict(plan_id=flow['plan_id'], information_asof=flow['information_asof'],
                owner_scope=flow['owner_scope'], dispatch_profile=flow['dispatch_profile'],
                solve_seconds=nonnegative(flow['solve_seconds']))
            pid = compact['plan_id']
            need(pid not in plans or plans[pid] == compact, 'same_plan_identity_changed')
            plans[pid] = compact
        action = tr['requested_action']
        if action['kind'] != 'transfer':
            continue
        request = tr['actual_submission']
        rid = tr['request_id'] or (request or {}).get('request_id')
        need(rid is None or rid not in used_requests, 'selected_request_credited_twice')
        if rid is not None:
            used_requests.add(rid)
            need(rid in request_rows and calls[rid]['request'] == request, 'selected_actual_call_join')
            for key in ('source', 'destination', 'tray_id'):
                need(request[key] == action[key], 'selected_payload_identity:' + key)
            need(request['owner_id'] == tr['owner_id'], 'selected_owner_identity')
        item = dict(request_rows[rid]) if rid is not None else dict(outcome='not_submitted', request_id=None)
        eta = action.get('nominal_arrival_time', action.get('static_arrival_estimate'))
        eta = None if eta is None else number(eta)
        received = item.get('received_at')
        for event_key, physical_time in (('first_edge_event', item.get('first_edge_at')), ('received_event', received)):
            event = tr.get(event_key)
            need((None if event is None else event['time']) == physical_time, 'selected_physical_event_join:' + event_key)
        profile = None if flow is None else next((r for r in flow['dispatch_profile']
            if all(r[k] == action[k] for k in ('tray_id', 'source', 'destination'))), None)
        submitted = item.get('submitted_at')
        verification = decision.get('flow_verification', selection.get('flow_verification')) or {}
        before = (verification.get('exact_projection') or {}).get('destination_without_move') or {}
        shortage = before.get('first_shortage_offset')
        metadata = selection.get('empty_transport_order')
        if metadata is not None:
            need(metadata['plan_id'] == flow['plan_id'] and metadata['owner_scope'] == tr['owner_id'], 'order_plan_owner')
            for field, key in (('physical_tray_id', 'tray_id'), ('source_terminal', 'source'), ('destination_terminal', 'destination')):
                need(metadata[field] == action[key], 'order_action_identity')
        linked_plan_item = metadata is not None and profile is not None
        proposed_at = None if metadata is None else metadata.get('proposed_at')
        item.update(decision_id=identity, owner_id=tr['owner_id'], source=action['source'], destination=action['destination'],
            physical_tray_id=action['tray_id'], decision_time=at,
            order_id=None if metadata is None else metadata['order_id'], plan_id=None if flow is None else flow['plan_id'],
            original_plan_item_queue_identity_confirmed=linked_plan_item,
            classification='ordinary_return' if action.get('source_category') == 'ordinary_return' else 'extra_reposition',
            estimated_static_travel_seconds=None if action.get('static_travel_time') is None else nonnegative(action['static_travel_time']),
            estimated_decision_to_arrival_seconds=None if eta is None else nonnegative(eta-at),
            decision_to_submission_seconds=None if submitted is None else nonnegative(submitted-at),
            order_proposed_to_submission_seconds=None if submitted is None or proposed_at is None else nonnegative(submitted-number(proposed_at)),
            plan_creation_to_submission_seconds=None if submitted is None or not linked_plan_item else nonnegative(submitted-flow['information_asof']),
            submission_minus_planned_slot_seconds=None if submitted is None or not linked_plan_item else submitted-profile['submit_at'],
            actual_decision_to_received_seconds=None if received is None else nonnegative(received-at),
            arrival_minus_selected_eta_seconds=None if received is None or eta is None else received-eta,
            forecast_first_shortage_lead_seconds=None if shortage is None else nonnegative(shortage),
            forecast_first_shortage_population='selected destination exact-projection only; not all stations or observed actual onset',
            unreceived_eta_lateness_lower_bound_seconds=max(0., END-eta) if item['outcome'] == 'right_censored' and eta is not None else None)
        selected.append(item)
    need(set(trajectory) <= decisions_seen and decision_count == row['worker']['policy_timing']['count'], 'complete_decision_denominator')
    need(len({r['order_id'] for r in selected if r['order_id'] is not None}) == sum(r['order_id'] is not None for r in selected), 'unique_selected_order')
    station_rows = {}
    for node in sorted(loaders | sources):
        values = samples.get(node, [])
        need(len({r['owner_id'] for r in values}) <= 1, 'station_own_sensor_unique_owner')
        station_rows[str(node)] = dict(is_loader=node in loaders, is_legal_source=node in sources,
            frozen_sample_episode_summary=h['transport'].observation_episodes(values),
            sampling_bounds=sample_bounds(values), sample_rows=values)
    arrival_bins = actual_bins(arrivals, sorted(loaders), START, END)
    timing = row['worker']['policy_timing']
    need(timing['complete_request_100ms_certified'] is False and 'excluded' in timing['stage_scope'], 'callback_scope')
    report = dict(parent=plan['parent'], task_id=plan['task_id'], method=plan['method'], physical_window=[START, END],
        denominators=dict(native_arrival_labels=len(arrivals), in_window_native_arrivals=sum(START <= a['arrival'] < END for a in arrivals),
            all_nonretry_transfer_calls=all_call_count, in_window_actual_transfer_requests=len(request_rows),
            native_transfers_without_any_recorded_call=len(set(native)-set(calls)), observations=obs_count,
            decisions=decision_count, trajectory_decisions=len(trajectory), final_endpoint_decisions_excluded=endpoint_count,
            unique_plans=len(plans), legal_source_nodes=len(sources), loader_nodes=len(loaders)),
        transfers=summarize_transfers(list(request_rows.values()), selected, distribution),
        actual_request_rows=list(request_rows.values()), selected_transfer_rows=selected,
        station_observations=station_rows, arrival_counts=describe_bins(arrival_bins, distribution),
        unique_plan_solve_seconds=distribution([p['solve_seconds'] for p in plans.values()]),
        existing_policy_timing=timing, submission_wall_seconds=None,
        submission_wall_seconds_unknown_reason='not separately instrumented; callback excludes submission/native/export',
        future_jobs_used_as_arrival_labels=False, actual_arrival_labels_source='native BAG_ARRIVAL receipts',
        arrival_count_interval='[activation, horizon); actual horizon arrivals counted in closure but excluded from bins',
        first_shortage_lead_scope='selected exact forecast destination offsets plus sampled onset bounds; global all-station forecast lead unknown',
        multi_tick_queue_scope='same plan_id information_asof to real submit; no old-plan credit for later replan',
        limitations=['post-priority own-sensor samples do not observe continuous station state',
            'unknown waiting or stock stays unknown; missing ticks never become zero',
            'sampled shortage duration bounds assume no unobserved reversals between adjacent samples',
            'forecast first-shortage offsets are recorded selected-action projections, not actual outcomes',
            'predicted timing is unavailable for priority transfers without a selected action ETA',
            'failed and unknown requests are separate from live right-censoring',
            'callback stage totals exclude catalogue, submission, native advance and final export'])
    return report, arrival_bins


def actual_bins(arrivals, nodes, start, end):
    bins = {}
    for width in (60, 300, 600):
        n = math.ceil((end-start)/width)
        values = {str(node): [0]*n for node in nodes}
        for event in arrivals:
            key, at = str(event['origin']), event['arrival']
            if key in values and start <= at < end:
                values[key][int((at-start)//width)] += 1
        bins[str(width)] = values
    return bins


def describe_bins(bins, distribution):
    return {width: {node: dict(distribution(values), zero_count=values.count(0),
        zero_fraction=values.count(0)/len(values), total_arrivals=sum(values),
        population='parent-station time bins; all zero bins retained') for node, values in stations.items()}
        for width, stations in bins.items()}


def pooled_reports(reports, bins, distribution):
    combined = {width: {node: [count for parent in bins for count in parent[width][node]]
        for node in bins[0][width]} for width in bins[0]}
    need(all({w: set(b[w]) for w in b} == {w: set(bins[0][w]) for w in bins[0]} for b in bins), 'same_loader_bin_roster')
    station = {}
    for node in sorted(set().union(*(r['station_observations'] for r in reports))):
        rows = [r['station_observations'][node] for r in reports if node in r['station_observations']]
        episodes = [e for r in rows for e in r['sampling_bounds']['shortage_episodes']]
        depletions = [e for r in rows for e in r['sampling_bounds']['sampled_stock_depletion_intervals']]
        station[node] = dict(parent_station_cases=len(rows),
            expected_ticks=sum(r['sampling_bounds']['expected_tick_count'] for r in rows),
            known_ticks=sum(r['sampling_bounds']['known_tick_count'] for r in rows),
            absent_ticks=sum(r['sampling_bounds']['absent_tick_count'] for r in rows),
            unknown_samples=sum(r['sampling_bounds']['unknown_sample_count'] for r in rows),
            sampled_shortage_episodes=len(episodes), left_censored=sum(e['left_censored'] for e in episodes),
            right_censored=sum(e['right_censored'] for e in episodes),
            sampled_shortage_span_seconds=distribution([e['sample_span_lower_bound_seconds'] for e in episodes]),
            first_sampled_shortage_offset=distribution([r['sampling_bounds']['first_sampled_shortage_offset_from_activation']
                for r in rows if r['sampling_bounds']['first_sampled_shortage_offset_from_activation'] is not None]),
            sampled_stock_to_zero_upper_seconds=distribution([e['elapsed_from_first_positive_upper_bound'] for e in depletions]))
    return dict(transfers=summarize_transfers([v for r in reports for v in r['actual_request_rows']],
            [v for r in reports for v in r['selected_transfer_rows']], distribution),
        arrival_counts=describe_bins(combined, distribution), station_observations=station,
        existing_policy_timing=pooled_timing([r['existing_policy_timing'] for r in reports]),
        sampling_scope='two synthetic TRAIN parents derived from one historical template; pooled descriptive parent-event cases',
        independent_airport_days=False, independence_or_significance_claim=False,
        arrival_labels_not_duplicated_across_methods=True, parent_station_series_never_concatenated_in_time=True)


def execute(rows, inputs, producers, source_ref, workflow_ref, h, output):
    need(not output.exists(), 'fresh_output_directory_required')
    verify(inputs+producers)
    output.mkdir(parents=True)
    fresh(output/'pending.json', dict(status='in_progress', native_starts=0, not_a_completed_report=True))
    reports, bins, refs = [], [], []
    for parent in PARENTS:
        print(json.dumps(dict(stage='full_train_time_scale', parent=parent)), flush=True)
        report, counts = analyze(rows[parent], h)
        report.update(input_evidence=inputs, analysis_producers=producers)
        refs.append(fresh(output/f'P{parent}_full_train_time_scale.json.gz', report))
        reports.append(report)
        bins.append(counts)
        need(sum(p.stat().st_size for p in output.iterdir() if p.is_file()) < MAX_OUTPUT_BYTES, 'aggregate_output_limit')
    pooled = pooled_reports(reports, bins, h['transport'].distribution)
    verify(inputs+producers+refs)
    source_check(source_ref)
    result = dict(schema='g31.terminal_flow.full_train_time_scale.v1', status='complete',
        parents=list(PARENTS), methods=['TF-B1-300'], closed_full_train_runs=2, physical_window=[START, END],
        source_bundle=source_ref, workflow=workflow_ref, input_evidence=inputs, analysis_producers=producers,
        per_parent_reports=refs, pooled=pooled, native_starts=0, full_owner_ACK_opened=False,
        ledger_modified=False, future_jobs_used_as_arrival_labels=False,
        all_source_input_producer_bytes_bound_at_entry_and_exit=True,
        independent_airport_days=False, test_unlocked=False, R1_enabled=False, promotion_approved=False)
    ref = fresh(output/'full_train_time_scale_report.json', result)
    need(sum(p.stat().st_size for p in output.iterdir() if p.is_file()) < MAX_OUTPUT_BYTES, 'aggregate_output_limit')
    verify(inputs+producers+refs+[ref])
    fresh(output/'COMPLETE.json', dict(schema='g31.terminal_flow.full_train_time_scale.complete.v1',
        status='complete', final_report=ref, parents=list(PARENTS), closed_full_train_runs=2,
        native_starts=0, all_source_input_producer_bytes_bound_at_entry_and_exit=True))
    print(json.dumps(dict(final_report=ref, native_starts=0)), flush=True)


def main():
    entry = bind(__file__)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest', required=True, type=Path)
    parser.add_argument('--workflow', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    source_ref, workflow_ref = bind(args.source_manifest), bind(args.workflow)
    root = source_check(source_ref)
    h, helper_refs = load_helpers(root)
    producers = [entry]+helper_refs
    verify(producers)
    rows, inputs = collect(source_ref, workflow_ref, h)
    if not args.execute:
        verify(inputs+producers)
        print(json.dumps(dict(status='ready', parents=list(PARENTS), closed_full_train_runs=2,
            science_executed=False, native_starts=0, source_bundle=source_ref, workflow=workflow_ref,
            input_evidence=inputs, analysis_producers=producers), ensure_ascii=False, indent=2))
        return
    need(args.output_dir is not None, 'execute_requires_output_directory')
    execute(rows, inputs, producers, source_ref, workflow_ref, h, args.output_dir.resolve())


if __name__ == '__main__':
    main()
