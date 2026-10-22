"""Bounded offline coverage of closed terminal-flow and baseline behavior.

Observations/decisions/calls are read one array record at a time. The full owner
ACK export is never opened: selected-action ACKs come from the joined trajectory.
Source depletion is a sampled temporal association, not an intervention effect.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from .foundation_airport_terminal_flow_audit import ACCEPTED, closed_run
from .foundation_airport_terminal_service_audit import require
from .foundation_airport_transport_evidence import binding, distribution, read
from .foundation_airport_json_stream import iter_json_array_gz
from .foundation_airport_inventory_projection import prepare_inventory_projection


def decision_coverage(decisions, trajectory_rows):
    valid = {row['decision_id']: row for row in trajectory_rows}
    counts, reasons, plans = Counter(), Counter(), {}
    cache_ages, forecast_ages = [], []
    selected_by_category = defaultdict(Counter)
    for decision in decisions:
        identity = decision['decision_id']
        if identity not in valid:
            counts['endpoint_or_nontrajectory_records_excluded'] += 1
            continue
        row = valid[identity]
        counts['valid_decisions'] += 1
        catalog = decision['catalog']['candidates']
        moves = [a for a in catalog if a.get('kind') == 'transfer']
        counts['legal_transfer_opportunities'] += bool(moves)
        counts['ordinary_return_menu_opportunities'] += any(a.get('source_category') == 'ordinary_return' for a in moves)
        counts['multiple_legal_trays'] += len({a['tray_id'] for a in moves}) > 1
        choice = decision.get('selection', {})
        cache = row.get('flow_cache') or choice.get('cache') or {}
        if cache:
            counts['cache_observed_decisions'] += 1
            counts['cache_hits'] += bool(cache.get('hit'))
            reasons[str(cache.get('invalidation_reason'))] += 1
            if cache.get('plan_age_seconds') is not None:
                cache_ages.append(cache['plan_age_seconds'])
            if cache.get('forecast_age_seconds') is not None:
                forecast_ages.append(cache['forecast_age_seconds'])
        plan = choice.get('flow_plan')
        if plan is not None:
            pid = plan['plan_id']
            keys = {(a['tray_id'], a['source'], a['destination']) for a in plan.get('chosen', [])}
            require(len(keys) == len(plan.get('chosen', [])), 'unique_behavior_plan_items')
            if pid not in plans:
                plans[pid] = dict(plan_id=pid, keys=keys, occurrences=0, issued=set(), received=set(),
                    source_count=len({a[1] for a in keys}), destination_count=len({a[2] for a in keys}),
                    dispatch_slots=[p['dispatch_slot'] for p in plan.get('dispatch_profile', [])],
                    shared_witness_edges=len(plan.get('shared_witness_edges', [])))
            require(plans[pid]['keys'] == keys, 'stable_behavior_plan_identity')
            plans[pid]['occurrences'] += 1
            if row.get('request_id'):
                plans[pid]['issued'].add(row['request_id'])
                if row.get('received_event') is not None:
                    plans[pid]['received'].add(row['request_id'])
        action = row['requested_action']
        if action['kind'] == 'transfer':
            category = action.get('source_category', 'unknown')
            selected_by_category[category]['selected'] += 1
            selected_by_category[category]['submitted'] += row.get('actual_submission') is not None
            selected_by_category[category]['accepted'] += any(a.get('status') in ACCEPTED for a in row.get('ack') or [])
            selected_by_category[category]['received'] += row.get('received_event') is not None
            selected_by_category[category]['failed'] += bool(row.get('physical_failure'))
    plan_rows = [dict(plan_id=p['plan_id'], unique_items=len(p['keys']), source_count=p['source_count'],
        destination_count=p['destination_count'], occurrences=p['occurrences'], issued_requests=len(p['issued']),
        received_requests=len(p['received']), dispatch_slots=p['dispatch_slots'], shared_witness_edges=p['shared_witness_edges'])
        for p in plans.values()]
    return dict(decision_counts=dict(counts), selected_by_source_category={k: dict(v) for k,v in selected_by_category.items()},
        cache=dict(denominator='valid decisions with serialized flow_cache', invalidation_reasons=dict(reasons),
            plan_age_seconds=distribution(cache_ages), forecast_age_seconds=distribution(forecast_ages)),
        plan_counts=dict(unique_plan_ids=len(plans), empty_plans=sum(not p['keys'] for p in plans.values()),
            multi_item_plans=sum(len(p['keys']) > 1 for p in plans.values()),
            multi_source_plans=sum(p['source_count'] > 1 for p in plans.values()),
            multi_destination_plans=sum(p['destination_count'] > 1 for p in plans.values()),
            multi_item_plans_with_actual_request=sum(len(p['keys']) > 1 and bool(p['issued']) for p in plans.values()),
            multi_item_plans_with_two_actual_requests=sum(len(p['keys']) > 1 and len(p['issued']) > 1 for p in plans.values()),
            later_dispatch_slot_suggestions=sum(slot > 0 for p in plans.values() for slot in p['dispatch_slots']),
            shared_witness_plans=sum(p['shared_witness_edges'] > 0 for p in plans.values()),
            cached_repeats_not_additional_plans=True), plans=plan_rows)


def reverse_requests(calls, terminal, *, selected_request_ids=()):
    """Same tray returning to its last received source; loading remains explicit."""
    first = [row for row in calls if row.get('kind') == 'transfer' and not row.get('retry')]
    require(len({row['request']['request_id'] for row in first}) == len(first), 'unique_reverse_first_submissions')
    native = {row['request_id']: row for row in terminal['transfers']}
    by_tray, loads, reverses = defaultdict(list), defaultdict(list), []
    selected = set(selected_request_ids)
    for event in terminal['receipts']:
        if event['event'] == 'LOAD_START':
            loads[event['tray_id']].append(event['time'])
    for row in first:
        by_tray[row['request']['tray_id']].append(row)
    for tray, history in by_tray.items():
        history.sort(key=lambda r: (r['at'], r['request']['request_id']))
        for index, current in enumerate(history):
            previous = next((old for old in reversed(history[:index])
                if 0 <= native.get(old['request']['request_id'], {}).get('received_at', -1) <= current['at']), None)
            if previous is None:
                continue
            a,b = previous['request'], current['request']
            if (a['source'],a['destination']) != (b['destination'],b['source']):
                continue
            received_at = native[a['request_id']]['received_at']
            loaded = [t for t in loads[tray] if received_at <= t <= current['at']]
            reverses.append(dict(tray_id=tray, previous_request=a['request_id'], reverse_request=b['request_id'],
                previous_source=a['source'], previous_destination=a['destination'], previous_received_at=received_at,
                reverse_submitted_at=current['at'], seconds_after_receive=current['at']-received_at,
                intervening_load_start_count=len(loaded), intervening_load_start_times=loaded,
                previous_is_selected_optional=a['request_id'] in selected, reverse_is_selected_optional=b['request_id'] in selected,
                reverse_native_status=native.get(b['request_id'], {}).get('status'),
                reverse_departed_at=native.get(b['request_id'], {}).get('departed_at', -1),
                reverse_received_at=native.get(b['request_id'], {}).get('received_at', -1), unnecessary_move_proven=False))
    return dict(unique_nonretry_requests=len(first), same_tray_reverse_requests=len(reverses),
        reverse_actually_departed=sum(r['reverse_departed_at'] >= 0 for r in reverses),
        reverse_actually_received=sum(r['reverse_received_at'] >= 0 for r in reverses),
        reverse_without_intervening_load=sum(not r['intervening_load_start_count'] for r in reverses),
        optional_involved_reverse_without_intervening_load=sum(not r['intervening_load_start_count'] and
            (r['previous_is_selected_optional'] or r['reverse_is_selected_optional']) for r in reverses), rows=reverses,
        definition='reverse of latest previously received request for same tray; rejected retries do not become new physical trips',
        future_load_after_cutoff_unknown=True, unnecessary_or_harmful_moves_inferred=False)


def source_windows(selected_rows, samples, *, cutoff, window_seconds=600.):
    results = []
    for row in selected_rows:
        source, start = row['requested_action']['source'], row['decision_time']
        end = min(cutoff, start+window_seconds)
        local = [r for r in samples.get(source, []) if start < r['at'] <= end]
        known = [r for r in local if r['stock'] is not None and r['waiting'] is not None]
        zero = next((r for r in known if r['stock'] == 0), None)
        shortage = next((r for r in known if r['stock'] == 0 and r['waiting'] > 0), None)
        times = [start, *[r['at'] for r in known]]
        largest_gap = max([b-a for a,b in zip(times,times[1:])] + [end-times[-1]])
        results.append(dict(request_id=row.get('request_id'), source=source, selected_at=start, window_end=end,
            registered_window_seconds=window_seconds, source_empty_before=row['requested_action'].get('source_actual_unpledged'),
            local_samples=len(local), known_samples=len(known), maximum_sample_gap_seconds=largest_gap,
            right_censored=cutoff < start+window_seconds, complete_60s_sample_coverage=bool(known) and largest_gap<=60.000001,
            first_observed_zero_stock=zero, first_observed_zero_stock_with_waiting=shortage,
            stock_after_move_not_directly_measured=True, causal_depletion_or_service_harm_proven=False))
    return dict(selected_moves=len(results), with_any_known_followup=sum(r['known_samples']>0 for r in results),
        complete_60s_sample_windows=sum(r['complete_60s_sample_coverage'] and not r['right_censored'] for r in results),
        followed_by_observed_zero_stock=sum(r['first_observed_zero_stock'] is not None for r in results),
        followed_by_observed_waiting_and_zero_stock=sum(r['first_observed_zero_stock_with_waiting'] is not None for r in results),
        rows=results, observation_scope='local-owner post-priority samples; overlapping move windows are not independent effects')


def summarize(directory):
    directory=Path(directory)
    plan,receipt,trajectory=closed_run(directory)
    require(plan['parent']['split']!='test', 'behavior_test_locked')
    selected=[r for r in trajectory['rows'] if r['requested_action']['kind']=='transfer']
    coverage=decision_coverage(iter_json_array_gz(directory/'decisions.json.gz'), trajectory['rows'])
    terminal=read(directory/'terminal_evidence.json.gz')
    reverse=reverse_requests(iter_json_array_gz(directory/'calls.json.gz'), terminal,
        selected_request_ids=[r['request_id'] for r in selected if r.get('request_id')])
    sources={r['requested_action']['source'] for r in selected}
    samples=defaultdict(list)
    # Keep only source scalars within a registered post-move window. Never retain
    # past observations, planning captures or command histories in this scan.
    windows=defaultdict(list)
    for row in selected:
        windows[row['requested_action']['source']].append((row['decision_time'], min(plan['horizon'],row['decision_time']+600.)))
    last_needed_at=max((end for intervals in windows.values() for _,end in intervals), default=None)
    observations_read=0
    if sources:
        for record in iter_json_array_gz(directory/'observations.json.gz'):
            obs=record['observation']; now=obs['now']
            observations_read+=1
            # Producer observations are chronological. All requested 600-second
            # followups are over; remaining history cannot supply a needed sample.
            if now > last_needed_at:
                break
            needed={node for node in sources if any(a < now <= b for a,b in windows[node])}
            if not needed:
                continue
            current=prepare_inventory_projection(obs)
            for node in needed:
                state=current.nodes[node]
                if state['local']:
                    samples[node].append(dict(at=now,
                        stock=state['stock'] if state['inventory_known'] else None,
                        waiting=state['waiting'] if state['waiting_known'] else None))
    return dict(schema='g31.terminal_flow.closed_behavior_coverage.v1',task_id=plan['task_id'],method=plan['method'],
        horizon=plan['horizon'], native_starts=0, test_data_read=False, **coverage,
        source_followup=source_windows(selected,samples,cutoff=plan['horizon']),reverse_moves=reverse,
        all_native_status_counts=dict(Counter(r['status'] for r in terminal['transfers'])),
        full_owner_ack_export_opened=False, selected_ack_evidence_source='trajectory joined actual request history',
        source_observation_scan=dict(records_read=observations_read,needed_through=last_needed_at,
            chronological_producer_prefix_only=True,whole_file_sha256_bound=True,unread_tail_json_reparsed=False),
        ordinary_target_redirection_counterfactual_not_established=True,
        evidence={name:binding(directory/name) for name in ('plan.json','receipt.json','trajectory.json.gz',
            'terminal_evidence.json.gz','decisions.json.gz','calls.json.gz','observations.json.gz')})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists(),'fresh_output_required')
    result=summarize(args.directory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8') as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(task_id=result['task_id'], output=str(args.output.resolve()),
        selected=result['source_followup']['selected_moves'], native_starts=0)))


if __name__=='__main__':
    main()
