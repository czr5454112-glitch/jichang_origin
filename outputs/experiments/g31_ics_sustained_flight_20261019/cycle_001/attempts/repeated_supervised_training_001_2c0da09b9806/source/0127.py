"""Prepared fixed-six SAME-ACTION continuation test; execution is explicit.

Six initial engines, fourteen retained cuts and fourteen independent suffixes.
No actual endpoint is fed into a suffix, and no initial prefix is replayed.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET

from . import bounded_windows_job
from . import validate_live_phase_b_pause as passive

ROOT, OUT = passive.ROOT, passive.OUT
PRIOR = OUT / 'live_phase_b_pause_prepare_001'
PURE = OUT / 'conditional_continuation_driver_pure_001'
MODULE = 'scripts.experiments.g31_ics_circulation.validate_live_conditional_continuation'
SCHEMA = 'g31.live_obligation.same_action_six_continuation.v1'
ORDER = passive.ORDER
CUT_COUNTS = (2, 2, 2, 2, 2, 4)
LIMIT = 120.
PRIOR_PLAN = 'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb'
CORE_PURE_PLAN = '897293791205ba7587065b8dc831c0febac64c6ebc056caf1744bf238ae1144b'
sha, read, write, ref = passive.sha, passive.read, passive.write, passive.ref
bytes_of, graph_bytes = passive.bytes_of, passive.graph_bytes


def require(value, reason):
    if not value: raise ValueError('same_action_six:' + reason)


def remaining(elapsed):
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'elapsed')
    value = LIMIT - elapsed - 1.
    if value <= 0: raise TimeoutError('same_action_six:budget_before_worker')
    return value


def check_domain(rows):
    require(type(rows) is dict and tuple(rows) == ORDER and len(rows) == 6, 'six_ordered_rows')
    require(tuple(len(rows[k]['expected_collections']) for k in ORDER) == CUT_COUNTS, 'fixed_fourteen_cuts')
    require(sum(CUT_COUNTS) == 14 and sum(n*(n+1)//2 for n in CUT_COUNTS) == 25, 'fixed_resume_arithmetic')


def graph(state, model):
    return graph_bytes((state._engine, state._frames),
        (model.Projection, model.lazy.original.captures.CaptureWorld,
         model.lazy.original.policy.PhaseReplyBudget))


def point_description(state, model):
    model.validate(state, pc=model.PC)
    engine, frames = state._engine, state._frames
    decision = frames['decide']; pending = decision['p']; event = frames['run']['event']
    require(engine.world.e is engine and decision['s'] is engine.owner_state[decision['owner']] and
            pending is decision['s']['pending'], 'world_and_frame_alias')
    require(all(event is not item for item in engine.events), 'current_event_already_popped')
    require('_phase_b_recorder' not in vars(engine), 'no_external_recorder')
    encoded = graph(state, model)
    return {**state.description(), 'owner': decision['owner'], 'at': engine.time,
        'phase': pending['phase'], 'recollection_index': pending['recollection_index'],
        'information_status': decision['info'].get('status'), 'retry_status': decision['screen'].get('status'),
        'graph_sha256': hashlib.sha256(encoded).hexdigest(), 'graph_encoded_bytes': len(encoded),
        'heap_events': len(engine.events), 'event_sequence': engine.sequence,
        'current_event': {'at': event[0], 'priority': event[1], 'sequence': event[2], 'kind': event[3]},
        'current_event_already_popped': True, 'current_event_count_already_included': True,
        'before_event_already_called': True, 'after_event_not_yet_called': True,
        'tick_owner_order': list(frames['tick']['owners']), 'tick_owner_index': frames['tick']['index'],
        'owner_pending_alias': True, 'world_engine_alias': True, 'external_recorder_present': False,
        'native_authority': False, 'arbitrary_tamper_resistance_claimed': False}


def terminal_description(state, model):
    # The wrapper was consumed by _drive; the mutated graph is diagnostic only.
    require(state._consumed is True, 'terminal_consumed')
    value = graph(state, model)
    return {'graph_sha256': hashlib.sha256(value).hexdigest(), 'graph_encoded_bytes': len(value),
        'model_time': state._engine.time, 'event_count': state._frames['run']['count'],
        'handler_pc': state._frames['run']['handler_pc'], 'remaining_heap_events': len(state._engine.events),
        'event_sequence': state._engine.sequence, 'consumed': True}


def mutate_finished_copy(state):
    """Destructive probe only AFTER the independent suffix has terminated."""
    engine = state._engine
    engine.action['_finished_copy_isolation_probe'] = True
    engine.events.append(('finished_copy_isolation_probe',))
    if engine.client_rows: next(iter(engine.client_rows.values()))['_finished_copy_isolation_probe'] = True
    engine.world.entries['_finished_copy_isolation_probe'] = True
    state._frames['_finished_copy_isolation_probe'] = True


def run_case(context, action, maximum_cuts, model, save_prediction):
    """No comparison target, expected chronology or actual raw enters execution.

    `maximum_cuts` is a preregistered diagnostic work cap, never an action input.
    All reached outputs are saved by the callback before target reads/audits.
    """
    result = {'status': 'unknown_in_progress', 'main': {'status': 'unknown_unexecuted'},
        'suffixes': {f'cut_{i:02d}': {'status': 'unknown_unexecuted'} for i in range(maximum_cuts)},
        'points': [], 'counts': {'initial_engines': 0, 'initial_advances': 0, 'main_resumes': 0,
            'suffix_resumes': 0, 'retention_forks': 0, 'suffix_forks': 0}}
    counts = result['counts']; retained = []; main_terminal_graph = None
    try:
        counts['initial_engines'] += 1
        state = model.start_conditional(context, action)
        if type(state) is not model.Continuation:
            result['main'].update(status='unknown_initial_context', prediction=save_prediction('main', state))
        else:
            counts['initial_advances'] += 1; last = state
            value = model.advance_to_collection_or_terminal(state)
            while type(value) is model.Continuation:
                require(len(retained) < maximum_cuts, 'unexpected_extra_cut')
                description = point_description(value, model)
                before = graph(value, model)
                counts['retention_forks'] += 1; kept = model.fork_conditional(value)
                require(graph(kept, model) == before and graph(value, model) == before,
                        'retention_graph_alias_equal')
                retained.append((kept, before)); result['points'].append(description)
                counts['main_resumes'] += 1; last = value
                value = model.resume_same_action(value)
            result['main'].update(prediction=save_prediction('main', value), status='returned')
            main_terminal_graph = graph(last, model)
            result['main']['terminal_state'] = terminal_description(last, model)
    except Exception:
        result['main'].update(status='unknown_error', error=traceback.format_exc())
    # Each retained factory-made cut is forked independently. No start/init or
    # advance(next_event) call is permitted on these suffix paths.
    for index, (kept, before) in enumerate(retained):
        key = f'cut_{index:02d}'; row = result['suffixes'][key]
        try:
            require(graph(kept, model) == before, 'retained_unchanged_after_mainline')
            counts['suffix_forks'] += 1; state = model.fork_conditional(kept)
            require(graph(state, model) == before, 'suffix_start_graph_alias_equal')
            points = []; calls = 0
            while type(state) is model.Continuation:
                require(calls < maximum_cuts-index, 'unexpected_extra_suffix_cut')
                points.append(point_description(state, model))
                counts['suffix_resumes'] += 1; calls += 1; last = state
                state = model.resume_same_action(state)
            row.update(prediction=save_prediction(key, state), status='returned', resume_calls=calls,
                points=points, terminal_state=terminal_description(last, model))
            row['terminal_full_graph_equals_main'] = main_terminal_graph is not None and graph(last, model) == main_terminal_graph
            require(graph(kept, model) == before, 'retained_unchanged_after_suffix')
            mutate_finished_copy(last)
            require(graph(kept, model) == before, 'retained_unchanged_after_explicit_copy_mutation')
            row['retained_cut_isolated'] = True
        except Exception:
            row.update(status='unknown_error', error=traceback.format_exc())
    return result


def audit_case(result, expected, target):
    """Audit only; complete predictions have already been saved."""
    n = len(expected)
    require(tuple(result['suffixes']) == tuple(f'cut_{i:02d}' for i in range(n)), 'suffix_denominator')
    passive.check_points(result['points'], expected)
    require(result['counts'] == {'initial_engines': 1, 'initial_advances': 1, 'main_resumes': n,
        'suffix_resumes': n*(n+1)//2, 'retention_forks': n, 'suffix_forks': n}, 'complete_execution_counts')
    for label, row in [('main', result['main']), *result['suffixes'].items()]:
        require(row['status'] == 'returned', 'returned_every_path:' + label)
        artifact = row['prediction']; require(sha(artifact['path']) == artifact['sha256'], 'prediction_artifact')
        exact = gzip.decompress(Path(artifact['path']).read_bytes()) == target
        row['whole_prediction_bytes_exact'] = exact
        require(exact, 'whole_prediction_difference:' + label)
        if label != 'main':
            index = int(label[4:]); passive.check_points(row['points'], expected[index:])
            require(bytes_of(row['points']) == bytes_of(result['points'][index:]),
                    'every_reached_cut_full_model_graph:' + label)
            require(row['resume_calls'] == n-index and row['terminal_full_graph_equals_main'] is True and
                    row['retained_cut_isolated'] is True, 'complete_suffix_state:' + label)
    result['status'] = 'exact_main_and_all_same_action_suffixes'


def check_xml(path, count):
    suites = ET.parse(path).getroot().findall('testsuite')
    require(len(suites) == 1 and int(suites[0].get('tests')) == count and
        all(int(suites[0].get(k)) == 0 for k in ('failures', 'errors', 'skipped')), 'pure_gate')


def pure_gate():
    core = OUT/'conditional_continuation_pure_001'
    require(sha(core/'plan.json') == CORE_PURE_PLAN, 'core_pure_plan')
    paths = [(core/'tests.xml', 19), (PURE/'tests.xml', 16)]
    for path, count in paths: check_xml(path, count)
    for directory in (core, PURE):
        plan = read(directory/'plan.json'); receipt = read(directory/'receipt.json')
        require(receipt['status'] == 'passed_process' and receipt['source_changed'] == [] and
                receipt['plan_sha256'] == sha(directory/'plan.json'), 'pure_receipt')
        for path, digest in plan['source_sha256'].items():
            require(sha(path) == digest and sha(directory/'source'/Path(path).relative_to(ROOT)) == digest,
                    'pure_tested_source_identity')
    return [p for p, _ in paths] + [core/'plan.json', core/'receipt.json', PURE/'plan.json', PURE/'receipt.json']


def prepare(output):
    from . import live_obligation_conditional_continuation as model
    from . import validate_live_communication_projection as prior
    pure_paths = pure_gate()
    require(sha(PRIOR/'plan.json') == PRIOR_PLAN, 'passive_plan')
    pp = read(PRIOR/'plan.json'); receipt = read(PRIOR/'receipt.json')
    require(receipt['status'] == 'exact_six_passive_conformance' and receipt['exact_rows'] == 6 and
        receipt['hook_count'] == 14 and receipt['source_changed'] == [], 'closed_passive_six')
    require(sha(receipt['rows']['path']) == receipt['rows']['sha256'], 'closed_passive_rows')
    passive_rows = read(PRIOR/'rows.json'); output.mkdir(exist_ok=False)
    rows = {}
    for key in ORDER:
        require(passive_rows[key]['status'] == 'exact_passive_conformance', 'passive_row')
        source = pp['rows'][key]
        rows[key] = {'status': 'unknown_unexecuted', 'input': source['input'], 'action': source['action'],
            'comparison_only_saved_prediction': source['comparison_only_saved_prediction'],
            'expected_collections': source['expected_collections'],
            'main': {'status': 'unknown_unexecuted'},
            'suffixes': {f'cut_{i:02d}': {'status': 'unknown_unexecuted'} for i in range(len(source['expected_collections']))}}
    check_domain(rows)
    pins = dict(pp['source_sha256']); evidence = {}; archives = {}
    for p, digest in pins.items():
        require(sha(p) == digest and sha(PRIOR/pp['source_archive'][p]) == digest, 'prior105_unchanged')
        evidence[str(PRIOR/pp['source_archive'][p])] = digest
    paths = prior.source_paths()+[ROOT/'tests/test_g31_circulation_conditional_continuation.py',
        ROOT/'tests/test_g31_circulation_conditional_continuation_driver.py']
    for p in paths: pins[str(p)] = sha(p)
    for p, digest in pins.items():
        relative = Path('source')/Path(p).relative_to(ROOT)
        (output/relative).parent.mkdir(parents=True, exist_ok=True)
        (output/relative).write_bytes(Path(p).read_bytes()); archives[p] = str(relative)
    for path in [PRIOR/'plan.json', PRIOR/'receipt.json', PRIOR/'rows.json', PRIOR/'bounded_execution.json',
                 PRIOR/'external_application_wall.json', *pure_paths]: evidence[str(path)] = sha(path)
    for row in rows.values():
        for field in ('input', 'comparison_only_saved_prediction'):
            r = row[field]; require(sha(r['path']) == r['sha256'], 'selected_evidence'); evidence[r['path']] = r['sha256']
    plan = {'schema': SCHEMA, 'order': list(ORDER), 'rows': rows, 'source_sha256': pins,
        'source_archive': archives, 'evidence_sha256': evidence,
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'hard_application_seconds': LIMIT, 'maximum_initial_engines': 6, 'expected_cutpoints': 14,
        'expected_independent_suffixes': 14, 'expected_main_resumes': 14, 'expected_suffix_resumes': 25,
        'expected_total_resumes': 39, 'expected_whole_graph_forks': 28, 'source_proof': model.source_proof(),
        'budget_basis': {'prior_passive_whole_python_seconds': 12.4314135,
            'prior_passive_graph_copies': 42, 'current_graph_forks': 28,
            'current_initial_engines': 6, 'current_independent_suffix_paths': 14,
            'rationale': '120s includes parent imports/pins, six initial engines, fourteen suffixes,28 graph forks, full graph/alias/isolation and output comparisons,保存/exit pins. Prior passive12.43s is a cost reference, not a bound or latency promise. Timeout preserves all96-era evidence and new unknown paths.'},
        'boundaries': ['Only frozen initial owner data and fixed action enter start_conditional; target predictions and expected chronology are audit-only.',
            'Every suffix starts from one factory-produced four-frame cut and calls resume_same_action; no reinitialization/prefix replay.',
            'Full output bytes, every reached cut model alias graph, and complete terminal model alias graph are checked. This does not prove native hidden-state coverage.',
            'Private model objects are mutable; no arbitrary tamper resistance, native capability, actual opaque-ID mapping, belief coverage or online protection is claimed.',
            'Support inventories remain separate prior evidence; no actual context is stitched into a model snapshot.',
            'A main path plus every declared suffix must pass; missing, failed, over-budget and extra-point paths remain unknown.',
            'BOOT imports/setup subtract from120; owned JobObject bounds worker descendants, external whole Python wall remains required.']}
    write(output/'plan.json', plan); write(output/'rows.json', rows)
    write(output/'ready.json', {'status': 'prepared_unexecuted', 'plan': ref(output/'plan.json'),
        'source_count': len(pins), 'initial_engines_executed': 0, 'native_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
                            '--expected-plan', sha(output/'plan.json')]})


def worker(output, expected):
    from . import live_obligation_conditional_continuation as model
    from . import validate_live_communication_projection as prior
    started = time.perf_counter(); require(sha(output/'plan.json') == expected, 'plan_identity')
    plan = read(output/'plan.json'); check_domain(plan['rows'])
    require(plan['schema'] == SCHEMA and plan['order'] == list(ORDER) and plan['hard_application_seconds'] == LIMIT and
        [plan[k] for k in ('maximum_initial_engines', 'expected_cutpoints', 'expected_independent_suffixes',
        'expected_main_resumes', 'expected_suffix_resumes', 'expected_total_resumes', 'expected_whole_graph_forks')]
        == [6, 14, 14, 14, 25, 39, 28], 'closed_plan')
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'interpreter')
    pure_gate(); pins = {**plan['source_sha256'], **plan['evidence_sha256']}
    pins.update({str(output/plan['source_archive'][p]): d for p, d in plan['source_sha256'].items()})
    entry = {p: sha(p) for p in pins}; write(output/'entry_pins.json', entry); require(entry == pins, 'entry_pins')
    loaded = {str(p): sha(p) for p in prior.source_paths()}
    require(all(plan['source_sha256'].get(p) == d for p, d in loaded.items()), 'loaded_coverage')
    write(output/'loaded_sources.json', loaded); rows = copy.deepcopy(plan['rows'])
    for key in ORDER:
        row = rows[key]; row['status'] = 'unknown_in_progress'; write(output/'rows.json', rows)
        try:
            public = read(row['input']['path'])
            require(set(public) == {'initial_owners', 'action'} and set(public['initial_owners']) == {'A', 'B'} and
                bytes_of(public['action']) == bytes_of(row['action']), 'minimal_initial_input')
            contexts = {o: prior.context.initial_context(**public['initial_owners'][o]) for o in ('A', 'B')}
            require(all(type(c) is prior.context.SuppliedContext for c in contexts.values()), 'initial_guards')
            facts = {o: prior.context.initial_projection_bundle(c) for o, c in contexts.items()}
            require(all(prior.context.encoded({'v': facts['A'][f]}) == prior.context.encoded({'v': facts['B'][f]})
                        for f in ('jobs', 'trays', 'contract', 'now')), 'initial_independent_facts')
            def save_prediction(label, prediction):
                path = output/'predictions'/key/(label+'.json.gz'); path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(bytes_of(prediction), compresslevel=1, mtime=0))
                artifact = ref(path)
                # Expose every returned output immediately, even if target reads,
                # later state audits or later suffixes fail or hit the hard cap.
                destination = row['main'] if label == 'main' else row['suffixes'][label]
                destination.update(status='returned_audit_pending', prediction=artifact)
                write(output/'rows.json', rows)
                return artifact
            at = time.perf_counter()
            detail = run_case(contexts['A'], public['action'], len(row['expected_collections']), model, save_prediction)
            row['execution_and_snapshot_seconds'] = time.perf_counter()-at
            detail_path = output/'details'/key; detail_path.parent.mkdir(parents=True, exist_ok=True)
            detail_path = detail_path.with_suffix('.json'); write(detail_path, detail)
            row.update(main=detail['main'], suffixes=detail['suffixes'], detail=ref(detail_path), counts=detail['counts'])
            write(output/'rows.json', rows)
            target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())
            try: audit_case(detail, row['expected_collections'], target)
            finally: write(detail_path, detail); row['detail'] = ref(detail_path)
            row.update(status=detail['status'], main=detail['main'], suffixes=detail['suffixes'])
        except Exception:
            row.update(status='unknown_error', error=traceback.format_exc())
        write(output/'rows.json', rows)
    after = {p: sha(p) for p in pins}; write(output/'exit_pins.json', after); require(after == entry, 'exit_drift')
    loaded_after = {str(p): sha(p) for p in prior.source_paths()}
    require(all(plan['source_sha256'].get(p) == d for p, d in loaded_after.items()), 'exit_loaded_coverage')
    write(output/'exit_loaded_sources.json', loaded_after)
    exact = sum(r['status'] == 'exact_main_and_all_same_action_suffixes' for r in rows.values())
    totals = {k: sum(r.get('counts', {}).get(k, 0) for r in rows.values()) for k in
        ('initial_engines', 'initial_advances', 'main_resumes', 'suffix_resumes', 'retention_forks', 'suffix_forks')}
    expected_totals = dict(initial_engines=6, initial_advances=6, main_resumes=14, suffix_resumes=25,
        retention_forks=14, suffix_forks=14)
    write(output/'receipt.json', {'schema': SCHEMA,
        'status': 'exact_six_main_and_fourteen_same_action_suffixes' if exact == 6 and totals == expected_totals
            else 'completed_unknowns_preserved', 'exact_rows': exact, 'unknown_rows': 6-exact, 'counts': totals,
        'plan': ref(output/'plan.json'), 'rows': ref(output/'rows.json'),
        'entry_pins': ref(output/'entry_pins.json'), 'exit_pins': ref(output/'exit_pins.json'),
        'loaded_sources': ref(output/'loaded_sources.json'), 'exit_loaded_sources': ref(output/'exit_loaded_sources.json'),
        'source_changed': [], 'worker_seconds': time.perf_counter()-started, 'native_calls': 0,
        'same_action_conditional_model_only': True, 'actual_model_point_relation_established': False,
        'native_authority': False, 'hidden_state_coverage_certified': False})


def execute(output, expected):
    require(sha(output/'plan.json') == expected, 'launch_plan')
    require(read(output/'plan.json')['schema'] == SCHEMA, 'launch_schema')
    with (output/'execution_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'plan_sha256': expected, 'hard_application_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', expected]
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        elapsed = time.monotonic()-BOOT
        process = bounded_windows_job.run(command, timeout=remaining(elapsed), stdout=stdout, stderr=stderr,
            admission=expected, cwd=str(ROOT))
    end = time.monotonic()-BOOT
    bounded = process['status'] == 'exited' and process['exitcode'] == 0 and end <= LIMIT
    write(output/'bounded_execution.json', {'status': 'bounded_worker_completed' if bounded else 'unknown_failed_or_budget_exceeded',
        'process': process, 'command': command, 'plan_sha256': expected, 'fixed_application_seconds': LIMIT,
        'parent_before_worker_seconds': elapsed, 'application_seconds_before_final_receipt': end,
        'worker_receipt': ref(output/'receipt.json') if (output/'receipt.json').exists() else None,
        'external_python_launch_through_exit_required': True, 'native_calls': 0,
        'conformance_not_inferred_from_process_exit': True})
    return 0 if bounded and time.monotonic()-BOOT <= LIMIT else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--expected-plan')
    args = parser.parse_args(); output = args.output.resolve()
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline() == args.expected_plan+'\n', 'owned_job_admission')
        try: worker(output, args.expected_plan)
        except BaseException:
            write(output/'worker_failure.json', {'status': 'unknown_worker_failure', 'error': traceback.format_exc()}); raise
        return 0
    require(args.execute, 'explicit_action'); return execute(output, args.expected_plan)


if __name__ == '__main__': raise SystemExit(main())
