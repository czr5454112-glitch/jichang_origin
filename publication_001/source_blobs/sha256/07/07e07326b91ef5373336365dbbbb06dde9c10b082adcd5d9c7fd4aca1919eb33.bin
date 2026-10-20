"""Read-only pure instrumentation of the unchanged event loop, not a fork API.

All original candidates execute independently. Tracing captures exact states
before an action-dependent event is popped and measures whole-graph copying.
No shared-prefix execution, tick deletion, native session or runtime edit.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import pickle
import statistics
import sys
import time

from . import public_native_preference_projection as model
from .validate_public_native_preference_projection import imported_source_pins, sha


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest_state(state, ignored):
    state = copy.deepcopy(state)
    for key in ignored: state['action'].pop(key)
    return hashlib.sha256(pickle.dumps(state, protocol=5)).hexdigest()


def quiet_ticks(state):
    if not state.events or any(row[3] != 'tick' for row in state.events): return False
    if any(not request['terminal'] for request in state.requests): return False
    request = state.last_supply; tray = state.trays['E']
    # Future ticks can start cooldown recovery even when every existing
    # request is terminal. Only the lifetime-independent part of that guard
    # is checked here, not the current time comparison.
    recovery_possible = (request and request['ack'] == 'rejected'
        and len([r for r in state.requests if r['tray'] == 'E']) < 16
        and tray['mode'] == 'empty' and tray['node'] == 5)
    return not recovery_possible


def trace_one(projection):
    code = model.Projection.run.__code__
    source, start = inspect.getsourcelines(model.Projection.run)
    pop_line = start + next(i for i, line in enumerate(source) if 'heapq.heappop(self.events)' in line)
    cuts = {}; kinds = Counter(); quiet = None
    def trace(frame, event, arg):
        nonlocal quiet
        if frame.f_code is not code: return None
        if event == 'line' and frame.f_lineno == pop_line and projection.events:
            item = projection.events[0]; kind = item[3]
            if kind in ('return_decision', 'later_decision') and kind not in cuts:
                before = time.perf_counter_ns(); snapshot = copy.deepcopy(projection.__dict__)
                elapsed = time.perf_counter_ns() - before
                ignored = ('return_delay', 'later_action') if kind == 'return_decision' else ('later_action',)
                cuts[kind] = {'next_event': list(item[:4]), 'processed_count': frame.f_locals['count'],
                    'kind_counts': dict(kinds), 'copied_state_fields': sorted(snapshot),
                    'whole_graph_copy_ns': elapsed,
                    'normalized_state_sha256': digest_state(snapshot, ignored),
                    'ignored_only_unread_action_fields': list(ignored),
                    'serialized_state_bytes': len(pickle.dumps(snapshot, protocol=5)),
                    'heap_items': len(snapshot['events']), 'request_objects': len(snapshot['requests']),
                    'request_aliases_preserved': all(
                        any(r is args[0] for r in snapshot['requests'])
                        for _, _, _, k, args in snapshot['events'] if k in ('ack', 'grant', 'request_delivery')),
                    'last_supply_alias_preserved': snapshot['last_supply'] is None or any(
                        r is snapshot['last_supply'] for r in snapshot['requests']),
                    'tray_request_aliases_preserved': all(
                        any(r is tray['request'] for r in snapshot['requests'])
                        for tray in snapshot['trays'].values() if 'request' in tray)}
            if quiet is None and quiet_ticks(projection):
                quiet = {'before_event': list(item[:4]), 'processed_count': frame.f_locals['count'],
                         'remaining_ticks': len(projection.events), 'last_existing_tick': max(e[0] for e in projection.events),
                         'all_jobs_completed': set(projection.completed) == model.contract.JOBS,
                         'all_requests_terminal': True}
            kinds[kind] += 1
        return trace
    if sys.gettrace() is not None: raise ValueError('preexisting_trace_hook')
    sys.settrace(trace)
    try: result = projection.run()
    finally: sys.settrace(None)
    return result, {'cuts': cuts, 'event_kinds': dict(kinds), 'quiet_tick_tail': quiet}


def analyze(audit_path, output):
    started = time.perf_counter(); audit = json.loads(audit_path.read_text())
    if audit['status'] != 'saved192_revalidated_no_new_native' or len(audit['rows']) != 192:
        raise ValueError('unexpected_corpus')
    pins = {str(audit_path.resolve()): sha(audit_path), **imported_source_pins()}
    rows = {}; groups = {}
    for name, saved in audit['rows'].items():
        path = Path(saved['raw_artifact'])
        if sha(path) != saved['raw_sha256']: raise ValueError('changed_saved_raw')
        pins[str(path)] = saved['raw_sha256']
        raw = json.loads(gzip.decompress(path.read_bytes()))
        bundle = raw['initial_owners']['A']['information']['bundle']; action = saved['vector']
        # Complete original guard and independent run provide the comparator.
        # No saved native output enters either model execution.
        before = time.perf_counter_ns(); reference = model.predict(bundle, action)
        independent_ns = time.perf_counter_ns() - before
        before = time.perf_counter_ns(); projection = model.Projection(bundle, action)
        constructor_ns = time.perf_counter_ns() - before
        result, detail = trace_one(projection)
        if canonical(result) != canonical(reference): raise ValueError('instrumentation_changed_output')
        detail.update(action=action, independent_full_prediction_ns=independent_ns,
                      original_constructor_ns=constructor_ns, complete_output_exact=True,
                      event_count=result.get('event_count'), native_status_retained=saved['status_retained'])
        rows[name] = detail
        group = (name.split('/')[0], action['initial_action'], action['empty_departure'])
        groups.setdefault(group, []).append(detail)
    comparisons = []
    saved_events = total_events = total_quiet = copies_ns = 0
    for group, values in groups.items():
        if len(values) != 4: raise ValueError('incomplete_four_group')
        first = [v['cuts'].get('return_decision') for v in values]
        first_equal = all(first) and len({v['normalized_state_sha256'] for v in first}) == 1
        second = []
        for delay in (0., .5):
            pair = [v for v in values if v['action']['return_delay'] == delay]
            cuts = [v['cuts'].get('later_decision') for v in pair]
            equal = len(pair) == 2 and all(cuts) and len({v['normalized_state_sha256'] for v in cuts}) == 1
            second.append({'return_delay': delay, 'same_state': equal,
                           'counts': [c['processed_count'] if c else None for c in cuts]})
        estimate = None
        if first_equal and all(v['same_state'] for v in second):
            n0 = first[0]['processed_count']
            # Eight roots per32: share fourfold prefix, then each twofold
            # return branch through its first later-route decision.
            estimate = 3 * n0 + sum(v['counts'][0] - n0 for v in second)
            saved_events += estimate
            # One graph copy at first split, one at each later split if one
            # branch safely reuses its parent after its sibling is copied.
            copies_ns += first[0]['whole_graph_copy_ns'] + sum(
                next(v for v in values if v['action']['return_delay'] == delay)['cuts']['later_decision']['whole_graph_copy_ns']
                for delay in (0., .5))
        total_events += sum(v['event_count'] for v in values)
        total_quiet += sum((v['quiet_tick_tail'] or {}).get('remaining_ticks', 0) for v in values)
        comparisons.append({'case': group[0], 'initial_action': group[1], 'Ewindow': group[2],
                            'first_return_prefix_exact_after_masking_unread_choices': first_equal,
                            'later_prefix_pairs': second, 'potential_saved_event_handlers': estimate})
    if any(sha(name) != digest for name, digest in pins.items()): raise ValueError('source_or_input_drift')
    report = {'schema': 'g31.public_projection_prefix_feasibility.v1', 'status': 'pure_independent_runs_instrumented',
        'pins': pins, 'native_calls': 0, 'shared_prefix_executions': 0, 'independent_runs': 384,
        'all_192_complete_outputs_exact': True, 'rows': rows, 'groups': comparisons,
        'totals': {'events': total_events, 'potential_saved_prefix_handlers': saved_events,
            'quiet_tail_tick_handlers': total_quiet,
            'naive_three_copies_per_four_group_observed_ns': copies_ns},
        'cost_limits': 'Instrumented timings contain tracing and snapshot overhead. Prefix event counts are not equal CPU weights. Copy samples and original full prediction times are diagnostic under concurrent host work, not an optimized benchmark or complete-request timing.',
        'wall_seconds': time.perf_counter() - started,
        'proposal': {'pause': 'Before heap pop at return_decision, then before later_decision. Preserve pending tuple and same-timestamp ordering.',
            'clone': 'One deepcopy of entire dynamic object graph, preserving request aliases; carry cumulative run count separately. No fieldwise copies or native forks.',
            'static': 'Only independently proven read-only static data may be memo-shared, including frozen context potential; no mutable messages or calendars.',
            'quiet_tail': 'Only when all remaining heap items are tick, every request terminal and future E recovery impossible; preserve exact existing tick count, last clock, horizon and event-budget behavior.',
            'test_gate': 'All32/4 full result bytes against independent original runs; count constructor, snapshot, clone, output-copy and all preparation costs. Preserve18 historical unknowns.'}}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(); p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    analyze(a.audit, a.output)


if __name__ == '__main__': main()
