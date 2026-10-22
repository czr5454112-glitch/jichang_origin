"""Export every selected transfer from completed bound DEV reports, without replay.

This is a descriptive evidence index, not a policy evaluation or causal test.
It reads decisions, not full observations, and never constructs a native session.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

def need(ok, reason):
    if not ok: raise ValueError('selected_order_cases:' + reason)

def bind(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        return dict(path=str(path), sha256=hashlib.file_digest(stream, 'sha256').hexdigest())

def checked(ref):
    need(bind(ref['path'])['sha256'] == ref['sha256'], 'changed_bound_bytes')
    return Path(ref['path'])

def read(ref):
    path = checked(ref)
    with (gzip.open(path, 'rt', encoding='utf8') if path.suffix == '.gz' else path.open(encoding='utf8')) as stream:
        return json.load(stream)

def extract(decision, lifecycle):
    action = decision['requested_action']
    need(action['action_type'] == 'transfer', 'transfer_only')
    need(decision['decision_id'] == lifecycle['decision_id'], 'decision_identity')
    need(all(action[k] == lifecycle[k] for k in ('source', 'destination', 'tray_id')), 'action_identity')
    selection = decision.get('selection', {})
    plan = selection.get('flow_plan', {})
    source, destination = action['source'], action['destination']
    stations = [r for r in plan.get('station_table', []) if r['node'] in (source, destination)]
    return dict(decision_id=decision['decision_id'], owner=decision['owner_id'],
        selected_at=decision['decision_time'], action=action,
        actual_submission=lifecycle.get('actual_submission'),
        decision_record_submission=decision.get('actual_submission'),
        actual_submission_source='Completed audit lifecycle joined to trajectory/native evidence; decision may precede submission.',
        current_features=decision.get('features_current'),
        forecast_features=decision.get('features_forecast'),
        plan_id=decision.get('flow_plan_id'), planned_quantity=decision.get('planned_quantity'),
        source_offers=plan.get('source_offers'), source_and_destination_stations=stations,
        flows=plan.get('flows'), original_dispatch_profile=plan.get('dispatch_profile'),
        execution_dispatch_profile=selection.get('execution_dispatch_profile'),
        exact_verification=decision.get('flow_verification'),
        planned_order=decision.get('empty_transport_order'), lifecycle=lifecycle,
        forecast_binding=decision.get('forecast_binding'),
        statement='Planned slots and soft target times are not native departure or arrival guarantees.')

def execute(complete, output):
    output = Path(output)
    need(not output.exists(), 'fresh_output_required')
    producer = bind(__file__)
    marker_ref = bind(complete)
    marker = read(marker_ref)
    need(marker['status'] == 'complete', 'completed_science_required')
    final_ref = marker['final_report']; final = read(final_ref)
    need(final['status'] == 'complete' and final['registered_runs'] == 28, 'full_matrix_required')
    source_ref = final['source_bundle']; source = read(source_ref)
    source_root = Path(source_ref['path']).parent
    relative = 'scripts/experiments/g31_ics_circulation/foundation_airport_json_stream.py'
    stream_path = source_root / relative
    need(bind(stream_path)['sha256'] == source['files'][relative], 'frozen_stream_producer')
    spec = importlib.util.spec_from_file_location('selected_cases_frozen_stream', stream_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    refs = [producer, marker_ref, final_ref, source_ref, bind(stream_path)]
    runs = []; seen_runs = set()
    for entry in final['runs']:
        identity = entry['parent'], entry['method']
        need(identity not in seen_runs, 'duplicate_run'); seen_runs.add(identity)
        report = read(entry['evidence']); refs.append(entry['evidence'])
        need((report['parent'], report['method']) == identity, 'run_identity')
        lives = {}
        for row in report['selected_transfer_lifecycle']:
            key = row['decision_id']; need(key not in lives, 'duplicate_lifecycle'); lives[key] = row
        decisions_ref = report['evidence']['decisions.json.gz']; refs.append(decisions_ref)
        decisions_path = checked(decisions_ref)
        valid = {(r['owner_id'], r['at']) for r in report['decision_choices']}
        need(len(valid) == len(report['decision_choices']), 'duplicate_valid_owner_time')
        cases = []; decision_count = 0; excluded = 0; seen_decisions = set()
        for decision in module.iter_json_array_gz(decisions_path):
            decision_count += 1
            key = decision['owner_id'], decision['decision_time']
            if key not in valid:
                excluded += 1; continue
            need(key not in seen_decisions, 'duplicate_decision_owner_time'); seen_decisions.add(key)
            if decision['requested_action']['action_type'] != 'transfer': continue
            key = decision['decision_id']; need(key in lives, 'unmatched_transfer')
            cases.append(extract(decision, lives.pop(key)))
        need(not lives, 'unmatched_lifecycle')
        need(seen_decisions == valid, 'incomplete_valid_decisions')
        runs.append(dict(parent=identity[0], method=identity[1], evidence=entry['evidence'],
            decisions=decisions_ref, all_decisions_read=decision_count, outside_evaluation_window=excluded,
            valid_decisions=len(valid), selected_transfers=len(cases), cases=cases))
    need(len(seen_runs) == 28, 'exact_run_count')
    for ref in refs: checked(ref)
    result = dict(schema='g31.terminal_flow.selected_order_cases.v1', source_bundle=source_ref,
        completed_science=marker_ref, producer=producer, runs=runs,
        selected_transfers=sum(r['selected_transfers'] for r in runs),
        selection_scope='All transfer selections in all 28 completed DEV runs, including failures and censoring.',
        independent_airport_days=False, native_starts=0, causal_conclusion=False,
        promotion_approved=False, evidence_rechecked_at_end=True)
    with output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2); stream.write('\n')
    print(json.dumps(bind(output)), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--complete', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); execute(args.complete, args.output)
