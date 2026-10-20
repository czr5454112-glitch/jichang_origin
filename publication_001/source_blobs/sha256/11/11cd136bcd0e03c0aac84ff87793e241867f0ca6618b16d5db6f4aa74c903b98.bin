"""All192 offline validation; outcome data never enters the projection API."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

from . import public_native_preference_projection as model


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def imported_source_pins():
    root = Path(__file__).resolve().parents[3]
    paths = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and path.is_relative_to(root): paths.add(path)
    return {str(path): sha(path) for path in sorted(paths)}


def validate(audit_path):
    audit_path = Path(audit_path).resolve()
    audit = json.loads(audit_path.read_bytes())
    assert audit['status'] == 'saved192_revalidated_no_new_native' and len(audit['rows']) == 192
    source_pins = imported_source_pins()
    pins = {str(audit_path): sha(audit_path), **source_pins}
    rows, counts = {}, Counter()
    for key, saved in audit['rows'].items():
        path = Path(saved['raw_artifact']); assert sha(path) == saved['raw_sha256']; pins[str(path)] = saved['raw_sha256']
        raw = json.loads(gzip.decompress(path.read_bytes()))
        bundle = raw['initial_owners']['A']['information']['bundle']
        assert raw['initial_owners']['A']['information']['native_delivery_verified'] is True
        # The pure API receives only the declared action and initial public
        # bundle. Native outcomes and later raw observations are compared only
        # after that API returns, never fed back into its event projection.
        start = time.perf_counter()
        prediction = model.predict(bundle, saved['vector'])
        elapsed = time.perf_counter() - start
        completion = prediction.get('completion', {})
        all_jobs = prediction['status'] == 'conditional_prediction' and set(completion) == model.contract.JOBS
        delta = {job: completion[job] - saved['completion'][job] for job in completion} if all_jobs else None
        projections = prediction.get('physical_projection', [])
        def first(job, source):
            edges = [r['target'] for r in projections if r['event'] == 'EDGE_ENTER' and r.get('job') == job and r['source'] == source]
            return edges[0] if len(edges) == 1 else None
        edges = {'initial': first('loaded', 0), 'first_reuse': first('reuse1', 7)}
        actual_edges = {'initial': saved['initial_actual_next'], 'first_reuse': saved['first_reuse_actual_next']}
        projected_edge_sequence = [(r['tray'], r.get('job') or '', r['source'], r['target'], r['at'])
                                   for r in projections if r['event'] == 'EDGE_ENTER']
        actual_edge_sequence = [(r['tray_id'], r['business_bag_id'], r['from'], r['to'], r['time'])
                                for r in raw['result']['receipts'] if r['event'] == 'EDGE_ENTER']
        actual_commands = {r['request']['business_bag_id']: r['ack']['status'] for r in saved['route_operations']}
        projected_commands = {r['job']: r['status'] for r in prediction.get('projected_commands', [])}
        admitted = saved['status_retained'] == 'assessed'
        row = {'actual_status_retained': saved['status_retained'], 'action': saved['vector'],
               'prediction': prediction, 'model_call_wall_seconds': elapsed,
               'actual_completion': saved['completion'], 'prediction_minus_native_per_job': delta,
               'max_abs_error_seconds': max(map(abs, delta.values())) if delta else None,
               'projected_edges': edges, 'actual_edges': actual_edges,
               'edge_identity_match': edges == actual_edges,
               'all_ordered_edge_entries_and_times_match': projected_edge_sequence == actual_edge_sequence,
               'projected_edge_sequence': projected_edge_sequence, 'actual_edge_sequence': actual_edge_sequence,
               'all_five_completion_doubles_exactly_match': all_jobs and all(value == 0 for value in delta.values()),
               'projected_command_statuses': projected_commands, 'actual_command_statuses': actual_commands,
               'command_set_and_status_match': projected_commands == actual_commands,
               'authority_valid_counterfactual_comparison': admitted,
               'unknown_promoted': False, 'model_protection_certified': False}
        rows[key] = row
        counts[('native_status', saved['status_retained'])] += 1
        counts[('projection_status', prediction['status'])] += 1
        if admitted:
            counts[('assessed_edges_match', str(row['edge_identity_match']))] += 1
            counts[('assessed_command_status_match', str(row['command_set_and_status_match']))] += 1
            counts[('assessed_all_ordered_edges_and_times_match', str(row['all_ordered_edge_entries_and_times_match']))] += 1
            counts[('assessed_all_five_completion_doubles_exact', str(row['all_five_completion_doubles_exactly_match']))] += 1
        else:
            counts[('unknown_native_comparison_not_admitted', 'retained')] += 1
    assert all(sha(path) == value for path, value in pins.items())
    assert imported_source_pins() == source_pins
    return {'schema': 'g31.public_native_preference_projection.validation.v1',
            'status': 'offline_all192_prediction_validation_no_new_native', 'pins': pins,
            'loaded_project_source_pins_before_and_after': source_pins,
            'counts': [{'category': category, 'value': value, 'count': count} for (category, value), count in counts.items()],
            'rows': rows, 'native_executions': 0, 'projection_evaluations': len(rows),
            'online_method_execution': False, 'native_protection_certified': False,
            'unknown_reference_families_promoted': False,
            'used_for_source_semantic_debugging': True, 'statistically_held_out_validation': False,
            'limits': ['These192 traces are retrospective conformance/regression comparands used for semantic debugging, not unseen or statistically held-out validation.',
                       'Saved outcomes are not supplied as prediction API inputs; this is distinct from statistical holdout.',
                       'Point estimate agreement does not establish bounded model error or strict native protection.',
                       'All18 originally unknown action/input rows remain unknown even if a conditional projection completes.',
                       'No later-state replanning implementation or new native campaign is certified by this report.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); assert not args.output.exists()
    value = validate(args.audit)
    args.output.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(value['counts'], indent=2))


if __name__ == '__main__': main()
