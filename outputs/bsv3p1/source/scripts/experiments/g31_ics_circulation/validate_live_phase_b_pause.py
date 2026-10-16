"""Fixed six-input passive-hook regression, prepared separately from execution."""
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

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
PRIOR = OUT / 'live_communication_lazy_prepare_001'
MODULE = 'scripts.experiments.g31_ics_circulation.validate_live_phase_b_pause'
SCHEMA = 'g31.live_obligation.passive_six_conformance.v1'
LIMIT = 120.
ORDER = ('mechanism/vector_00', 'mechanism/vector_25', 'no_overlap/vector_00',
         'no_overlap/vector_25', 'insufficient_advance/vector_00', 'insufficient_advance/vector_17')
PRIOR_FINAL = '07b26e476cd5ab328498e919a88503aa2ee64ef73ed21d6c02eb9af0f01c36b0'
PRIOR_ROWS = '7753bc2c9731ded83300435814f5b9c033197237cbaaa0c33721fe09c1a74a3e'


def require(value, reason):
    if not value: raise ValueError('passive_six:' + reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')
def ref(path): return {'path': str(Path(path).resolve()), 'sha256': sha(path)}
def bytes_of(value): return json.dumps(value, allow_nan=False).encode()


def remaining(elapsed):
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'elapsed')
    value = LIMIT - elapsed - 1.
    if value <= 0: raise TimeoutError('passive_six:budget_before_worker')
    return value


def check_order(rows):
    require(type(rows) is dict and tuple(rows) == ORDER and len(rows) == 6, 'six_ordered_rows')


def graph_bytes(value, allowed_objects=()):
    """Diagnostic alias graph, not a deserializer or authority representation.

    Float hex and dictionary order are retained. Set iteration is canonicalized
    only for immutable scalar/tuple elements; no arbitrary user hooks execute.
    """
    memo, nodes = {}, []
    def atom(item):
        if item is None: return ['none']
        if type(item) is bool: return ['bool', item]
        if type(item) is int: return ['int', str(item)]
        if type(item) is float: return ['float', item.hex()]
        if type(item) is str: return ['str', item]
        return None
    def set_key(item):
        scalar = atom(item)
        if scalar is not None: return scalar
        require(type(item) is tuple, 'unsupported_set_element')
        return ['tuple', [set_key(v) for v in item]]
    def visit(item):
        scalar = atom(item)
        if scalar is not None: return scalar
        require(type(item) in (dict, list, tuple, set, frozenset) or type(item) in allowed_objects,
                'unsupported_graph_object')
        if id(item) in memo: return ['ref', memo[id(item)]]
        index = len(nodes); memo[id(item)] = index; nodes.append(None)
        if type(item) is dict: node = ['dict', [[visit(k), visit(v)] for k, v in item.items()]]
        elif type(item) in (list, tuple): node = [type(item).__name__, [visit(v) for v in item]]
        elif type(item) in (set, frozenset):
            ordered = sorted(item, key=lambda v: json.dumps(set_key(v), separators=(',', ':')))
            node = [type(item).__name__, [visit(v) for v in ordered]]
        else: node = ['object', type(item).__module__+'.'+type(item).__qualname__, visit(vars(item))]
        nodes[index] = node
        return ['ref', index]
    root = visit(value)
    return bytes_of({'root': root, 'nodes': nodes})


def inspect_point(point, model):
    allowed = (model.Projection, model.lazy.original.captures.CaptureWorld,
               model.lazy.original.policy.PhaseReplyBudget)
    before = graph_bytes(point._state, allowed)
    copied = point.copied_state()
    require(graph_bytes(copied, allowed) == before, 'complete_graph_and_alias_copy')
    engine, pending, info, screen, view = copied
    require(engine.world.e is engine and pending is engine.owner_state[point.owner]['pending'],
            'world_and_pending_alias')
    require(engine._phase_b_recorder is None, 'external_recorder_detached')
    require(point.resumable is False and point.native_authority is False, 'no_resume_or_authority')
    description = point.description()
    description.update(graph_sha256=hashlib.sha256(before).hexdigest(), graph_encoded_bytes=len(before),
        heap_events=len(engine.events), event_sequence=engine.sequence, client_row_count=len(engine.client_rows),
        pending_is_owner_pending=True, world_engine_backref=True, recorder_detached=True,
        complete_graph_copy_equal=True, python_stack_and_run_local_counter_saved=False)
    # Mutation is exclusively on a returned clone after the prediction ended.
    # No cloned engine is advanced and no future action is selected here.
    engine.action['_passive_isolation_probe'] = True
    pending['_passive_isolation_probe'] = True
    engine.events.append(('isolation_probe',))
    if engine.client_rows: next(iter(engine.client_rows.values()))['_passive_isolation_probe'] = True
    engine.world.entries['_passive_isolation_probe'] = True
    require(graph_bytes(point._state, allowed) == before, 'retained_point_unchanged_after_clone_mutation')
    require(graph_bytes(point.copied_state(), allowed) == before, 'next_copy_unchanged')
    description['clone_mutation_isolated'] = True
    return description


def check_points(descriptions, expected):
    require(len(descriptions) == len(expected), 'complete_hook_count')
    for a, b in zip(descriptions, expected, strict=True):
        for key in ('owner', 'at', 'phase', 'recollection_index'):
            require(bytes_of(a[key]) == bytes_of(b[key]), 'point_chronology:' + key)
        require(a['information_status'] == b['information_status'] and
                a['retry_status'] == b['retry_admission']['status'], 'point_collected_result')


def pure_gate():
    paths = ((OUT/'live_phase_b_pause_pure_001/tests.xml', 16),
             (OUT/'live_phase_b_pause_driver_pure_001/tests.xml', 10))
    for path, count in paths:
        suites = ET.parse(path).getroot().findall('testsuite')
        require(len(suites) == 1 and int(suites[0].get('tests')) == count and
                all(int(suites[0].get(k)) == 0 for k in ('failures', 'errors', 'skipped')), 'pure_gate')
    return [path for path, _ in paths]


def prepare(output):
    from . import validate_live_communication_projection as prior
    from . import public_live_obligation_phase_b_pause as model
    from . import live_obligation_phase_b_support as support
    pure_paths = pure_gate()
    require(sha(PRIOR/'final_receipt.json') == PRIOR_FINAL and sha(PRIOR/'rows.json') == PRIOR_ROWS,
            'closed_lazy96')
    final = read(PRIOR/'final_receipt.json'); old = read(PRIOR/'rows.json'); prior_plan = read(PRIOR/'plan.json')
    require(final['status'] == 'exact_all96_and_saved73', 'prior_success_scope')
    output.mkdir(exist_ok=False)
    rows, evidence = {}, {}
    for key in ORDER:
        row = old[key]; require(row['status'] == 'exact_conformance', 'saved_comparand_status')
        for name in ('actual_raw', 'prediction'):
            require(sha(row[name]['path']) == row[name]['sha256'], 'selected_saved_sha')
            evidence[row[name]['path']] = row[name]['sha256']
        raw = json.loads(gzip.decompress(Path(row['actual_raw']['path']).read_bytes()))
        prediction = json.loads(gzip.decompress(Path(row['prediction']['path']).read_bytes()))
        public = {'initial_owners': {o: prior.public_initial(raw, o) for o in ('A', 'B')},
                  'action': copy.deepcopy(row['action'])}
        path = output/'inputs'/key; path.parent.mkdir(parents=True, exist_ok=True); path = path.with_suffix('.json')
        write(path, public)
        rows[key] = {'status': 'unknown_unexecuted', 'input': ref(path), 'action': public['action'],
            'comparison_only_saved_prediction': row['prediction'], 'comparison_only_actual_raw': row['actual_raw'],
            'expected_collections': prediction['projected_collections'],
            'prior_lazy_model_seconds': row['model_wall_seconds']}
    check_order(rows)
    require(sum(len(r['expected_collections']) for r in rows.values()) == 14, 'fourteen_points')
    # Bind every original dependency and archive, plus all newly loaded modules.
    pins = dict(prior_plan['source_sha256']); archives = {}
    for path, digest in pins.items():
        require(sha(path) == digest and sha(PRIOR/prior_plan['source_archive'][path]) == digest,
                'prior100_sources_unchanged')
        evidence[str(PRIOR/prior_plan['source_archive'][path])] = digest
    loaded = prior.source_paths()
    loaded += [ROOT/'tests/test_g31_circulation_live_phase_b_pause.py',
               ROOT/'tests/test_g31_circulation_live_phase_b_pause_driver.py']
    for path in loaded: pins[str(path)] = sha(path)
    for path, digest in pins.items():
        rel = Path('source')/Path(path).relative_to(ROOT)
        (output/rel).parent.mkdir(parents=True, exist_ok=True); (output/rel).write_bytes(Path(path).read_bytes())
        archives[path] = str(rel)
    for path in [PRIOR/'plan.json', PRIOR/'final_receipt.json', PRIOR/'rows.json',
                 PRIOR/'bounded_execution.json', PRIOR/'external_application_wall.json', *pure_paths,
                 OUT/'live_phase_b_pause_source_prepare_001/receipt.json']:
        evidence[str(path)] = sha(path)
    for row in rows.values(): evidence[row['input']['path']] = row['input']['sha256']
    plan = {'schema': SCHEMA, 'order': list(ORDER), 'rows': rows, 'maximum_model_calls': 6,
        'expected_hook_points': 14, 'source_sha256': pins, 'source_archive': archives,
        'evidence_sha256': evidence, 'environment': {'python': sys.executable, 'sha256': sha(sys.executable)},
        'hard_application_seconds': LIMIT, 'source_proof': model.source_proof(),
        'budget_basis': {'saved_six_model_seconds': sum(r['prior_lazy_model_seconds'] for r in rows.values()),
            'maximum_saved_single_model_seconds': max(r['prior_lazy_model_seconds'] for r in rows.values()),
            'graph_copies_per_point': 3, 'total_expected_graph_copies': 42,
            'rationale': 'Finite120s includes all setup/pins, six model calls,42 whole-state copies, graph audits,14 actual context guards, outputs and exit pins. Copy cost is unmeasured; timeout remains unknown. This is not a latency benchmark.'},
        'boundaries': ['Initial endpoint/publication facts only enter prediction; future actual data and prior prediction are comparison targets only.',
            'Actual support inventory is independent supplied-data evidence labelled by owner/phase/time; no relation or opaque-ID mapping to a model point is established.',
            'No filtering, resumed execution, native authority, belief coverage, online policy or protection is certified.',
            'No saved native fork, new native call, candidate search, omitted action or timing approximation.',
            'Parent BOOT elapsed subtracted from120; owned JobObject kills worker descendants; whole Python wall must also be recorded externally.']}
    write(output/'plan.json', plan); write(output/'rows.json', rows)
    write(output/'ready.json', {'status': 'prepared_unexecuted', 'plan': ref(output/'plan.json'),
        'source_count': len(pins), 'model_calls': 0, 'native_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output),
                            '--expected-plan', sha(output/'plan.json')]})


def worker(output, expected):
    from . import validate_live_communication_projection as prior
    from . import public_live_obligation_phase_b_pause as model
    from . import live_obligation_phase_b_support as support
    started = time.perf_counter()
    require(sha(output/'plan.json') == expected, 'plan_identity'); plan = read(output/'plan.json')
    require(plan['schema'] == SCHEMA and plan['hard_application_seconds'] == LIMIT and
            plan['maximum_model_calls'] == 6 and plan['expected_hook_points'] == 14, 'closed_plan')
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'interpreter')
    check_order(plan['rows']); require(plan['order'] == list(ORDER), 'fixed_order'); pure_gate()
    pins = {**plan['source_sha256'], **plan['evidence_sha256']}
    pins.update({str(output/plan['source_archive'][p]): d for p, d in plan['source_sha256'].items()})
    entry = {p: sha(p) for p in pins}; write(output/'entry_pins.json', entry); require(entry == pins, 'entry_pins')
    loaded = {str(p): sha(p) for p in prior.source_paths()}
    require(all(plan['source_sha256'].get(p) == d for p, d in loaded.items()), 'loaded_source_coverage')
    write(output/'loaded_sources.json', loaded)
    rows = copy.deepcopy(plan['rows']); calls = 0
    for key in ORDER:
        row = rows[key]; row['status'] = 'unknown_in_progress'; write(output/'rows.json', rows)
        try:
            public = read(row['input']['path'])
            require(set(public) == {'initial_owners', 'action'} and set(public['initial_owners']) == {'A', 'B'} and
                    public['action'] == row['action'], 'minimal_input_shape')
            contexts = {o: prior.context.initial_context(**public['initial_owners'][o]) for o in ('A', 'B')}
            require(all(type(c) is prior.context.SuppliedContext for c in contexts.values()), 'initial_guards')
            facts = {o: prior.context.initial_projection_bundle(c) for o, c in contexts.items()}
            require(all(prior.context.encoded({'value': facts['A'][f]}) == prior.context.encoded({'value': facts['B'][f]})
                        for f in ('jobs', 'trays', 'contract', 'now')), 'initial_independent_facts')
            calls += 1; require(calls <= 6, 'model_budget')
            at = time.perf_counter(); prediction, points = model.predict_with_points(contexts['A'], public['action'])
            elapsed = time.perf_counter()-at
            # All future comparands are read only after this prediction returned.
            target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())
            encoded = bytes_of(prediction); exact = encoded == target
            path = output/'predictions'/key; path.parent.mkdir(parents=True, exist_ok=True); path = path.with_suffix('.json.gz')
            path.write_bytes(gzip.compress(encoded, compresslevel=1, mtime=0))
            row.update(prediction=ref(path), model_and_capture_seconds=elapsed,
                       whole_prediction_bytes_exact=exact, returned_hook_count=len(points))
            write(output/'rows.json', rows)
            descriptions = [inspect_point(point, model) for point in points]
            check_points(descriptions, row['expected_collections'])
            raw = json.loads(gzip.decompress(Path(row['comparison_only_actual_raw']['path']).read_bytes()))
            inventories = []
            for owner in ('A', 'B'):
                for attempt in raw['collection_attempts'][owner]:
                    supplied = prior.future_context(raw, owner, attempt)
                    inventory = support.inspect_supplied_context(supplied)
                    inventories.append({'owner': owner, 'phase': attempt['phase'], 'at': attempt['at'],
                        'recollection_index': attempt['collection']['recollection_index'],
                        'source': 'saved_actual_owner_endpoints_only', 'model_point_relation_established': False,
                        'actual_delivery_capability_minted': False, 'inventory': inventory})
            detail = output/'points'/key; detail.parent.mkdir(parents=True, exist_ok=True); detail = detail.with_suffix('.json')
            write(detail, {'points': descriptions, 'independent_actual_support_inventories': inventories,
                'model_point_relation_established': False, 'resumable': False, 'native_authority': False})
            row.update(status='exact_passive_conformance' if exact else 'unknown_prediction_difference',
                prediction=ref(path), point_audit=ref(detail), model_and_capture_seconds=elapsed,
                whole_prediction_bytes_exact=exact, hook_count=len(points))
        except Exception:
            row.update(status='unknown_error', error=traceback.format_exc())
        write(output/'rows.json', rows)
    after = {p: sha(p) for p in pins}; write(output/'exit_pins.json', after); require(after == entry, 'exit_drift')
    after_loaded = {str(p): sha(p) for p in prior.source_paths()}
    require(all(plan['source_sha256'].get(p) == d for p, d in after_loaded.items()), 'exit_loaded_coverage')
    write(output/'exit_loaded_sources.json', after_loaded)
    count = sum(r['status'] == 'exact_passive_conformance' for r in rows.values())
    hooks = sum(r.get('hook_count', 0) for r in rows.values())
    receipt = {'schema': SCHEMA, 'status': 'exact_six_passive_conformance' if count == 6 and hooks == 14 and calls == 6
        else 'completed_unknowns_preserved', 'exact_rows': count, 'unknown_rows': 6-count, 'hook_count': hooks,
        'model_calls': calls, 'native_calls': 0, 'plan': ref(output/'plan.json'), 'rows': ref(output/'rows.json'),
        'entry_pins': ref(output/'entry_pins.json'), 'exit_pins': ref(output/'exit_pins.json'),
        'loaded_sources': ref(output/'loaded_sources.json'), 'exit_loaded_sources': ref(output/'exit_loaded_sources.json'),
        'source_changed': [], 'worker_seconds': time.perf_counter()-started,
        'resumable': False, 'model_point_relation_established': False, 'native_authority': False}
    write(output/'receipt.json', receipt)


def execute(output, expected):
    require(sha(output/'plan.json') == expected, 'launch_plan')
    plan = read(output/'plan.json'); require(plan['schema'] == SCHEMA, 'launch_schema')
    with (output/'execution_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'plan_sha256': expected, 'hard_application_seconds': LIMIT}, stream)
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', expected]
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        elapsed = time.monotonic()-BOOT
        process = bounded_windows_job.run(command, timeout=remaining(elapsed), stdout=stdout, stderr=stderr,
            admission=expected, cwd=str(ROOT))
    end = time.monotonic()-BOOT
    passed = process['status'] == 'exited' and process['exitcode'] == 0 and end <= LIMIT
    write(output/'bounded_execution.json', {'status': 'bounded_worker_completed' if passed else 'unknown_failed_or_budget_exceeded',
        'process': process, 'command': command, 'plan_sha256': expected, 'fixed_application_seconds': LIMIT,
        'parent_before_worker_seconds': elapsed, 'application_seconds_before_final_receipt': end,
        'worker_receipt': ref(output/'receipt.json') if (output/'receipt.json').exists() else None,
        'external_python_launch_through_exit_required': True, 'native_calls': 0})
    return 0 if passed and time.monotonic()-BOOT <= LIMIT else 1


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
