"""Fixed-six cProfile diagnosis of the frozen lazy communication projection.

No new policy, native call, data-C extension, performance comparison or speed
claim. Preparation is separate; the parent owns one shared120s worker tree.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import copy
import cProfile
import gc
import gzip
import hashlib
import json
import math
from pathlib import Path
import pstats
import sys
import traceback
import xml.etree.ElementTree as ET

from . import bounded_windows_job
from . import validate_live_phase_b_pause as passive

ROOT, OUT, ORDER = passive.ROOT, passive.OUT, passive.ORDER
SOURCE = OUT/'live_phase_b_pause_prepare_001'
CONTINUATION = OUT/'conditional_continuation_six_prepare_001'
PURE = OUT/'live_lazy_six_profile_pure_001'
MODULE = 'scripts.experiments.g31_ics_circulation.profile_live_lazy_six'
TEST = 'tests/test_g31_circulation_live_lazy_six_profile.py'
SCHEMA = 'g31.live_lazy_six.cProfile.v1'
LIMIT = 120.
SOURCE_PLAN = 'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb'
CONTINUATION_RECEIPT = '30ab6972140d8411d8c9d301c6d1690906112a18e350c7dccb2811b31e8705db'
HISTORY = ('public_projection_008_profile_001/report.json', 'preference_prefix_profile_001/report.json',
           'preference_quiet_profile_001/report.json', 'live_communication_partial_review_001/report.json')
sha, read, write, ref, bytes_of = passive.sha, passive.read, passive.write, passive.ref, passive.bytes_of


def require(value, reason):
    if not value: raise ValueError('lazy_six_profile:'+reason)


def no_execution_extensions():
    require('_g31_complete_tree_normalizer' not in sys.modules and
        not any('czr005_circulation' in name for name in sys.modules), 'forbidden_extension_loaded')


def remaining(elapsed):
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, 'elapsed')
    seconds = LIMIT-elapsed-1.
    if seconds <= 0: raise TimeoutError('lazy_six_profile:budget_before_worker')
    return seconds


def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict: return list(a) == list(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list: return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b, strict=True))
    if type(a) is float: return a.hex() == b.hex()
    require(type(a) in (str, int, bool, type(None)), 'non_JSON_semantics')
    return a == b


def compare_full(prediction_bytes, target_bytes):
    semantic = exact(json.loads(prediction_bytes), json.loads(target_bytes))
    return {'full_bytes_exact': prediction_bytes == target_bytes, 'full_ordered_types_and_float_semantics_exact': semantic}


def check_rows(rows):
    require(type(rows) is dict and tuple(rows) == ORDER and len(rows) == 6, 'six_fixed_rows')


def function_rows(stats):
    return [{'file': f, 'line': line, 'function': name, 'primitive_calls': value[0], 'total_calls': value[1],
        'self_seconds': value[2], 'cumulative_seconds': value[3]}
        for (f, line, name), value in sorted(stats.stats.items())]


def compact_stats(rows, total_tt, total_calls, primitive_calls):
    # Rankings only. In particular, cumulative times of callers and their
    # callees overlap, so no summed cumulative "share" is produced.
    key = lambda r: (r['file'], r['line'], r['function'])
    needles = ('deepcopy', 'digest', 'normalize', 'revalidate', 'collect', 'activate', 'view', 'tray',
               'run', '__init__', 'heappush', 'heappop', 'capture')
    return {'function_count': len(rows), 'total_self_seconds': total_tt,
        'total_calls': total_calls, 'primitive_calls': primitive_calls,
        'top_cumulative': sorted(rows, key=lambda r: (-r['cumulative_seconds'], key(r)))[:25],
        'top_self': sorted(rows, key=lambda r: (-r['self_seconds'], key(r)))[:25],
        'top_total_calls': sorted(rows, key=lambda r: (-r['total_calls'], key(r)))[:25],
        'watched_functions': [r for r in rows if any(x in r['function'].lower() for x in needles)],
        'cumulative_times_overlap_do_not_sum': True, 'profile_overhead_included': True,
        'uninstrumented_performance_claim': False}


def profiled_call(path, callback):
    """Exactly one callback; even its exception exports a completed profile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile(); started = time.perf_counter(); value = None; error = None
    try:
        profiler.enable(); value = callback()
    except Exception: error = traceback.format_exc()
    finally: profiler.disable()
    ended = time.perf_counter(); export_started = time.perf_counter()
    profiler.dump_stats(str(path)); stats = pstats.Stats(profiler)
    rows = function_rows(stats); full = path.with_suffix('.functions.json'); write(full, rows)
    summary = compact_stats(rows, stats.total_tt, stats.total_calls, stats.prim_calls)
    detail = {'status': 'returned' if error is None else 'unknown_callback_error',
        'callback_count': 1, 'wall_with_profiler_seconds': ended-started,
        'pstats': ref(path), 'full_function_rows': ref(full), 'statistics': summary,
        'profile_export_seconds': time.perf_counter()-export_started}
    if error is not None: detail['error'] = error
    return value, detail


def build_initial(public, prior):
    require(set(public) == {'initial_owners', 'action'} and set(public['initial_owners']) == {'A', 'B'}, 'minimal_initial_input')
    contexts = {owner: prior.context.initial_context(**public['initial_owners'][owner]) for owner in ('A', 'B')}
    require(all(type(value) is prior.context.SuppliedContext for value in contexts.values()), 'initial_context_guards')
    facts = {o: prior.context.initial_projection_bundle(c) for o, c in contexts.items()}
    require(all(prior.context.encoded({'v': facts['A'][f]}) == prior.context.encoded({'v': facts['B'][f]})
        for f in ('jobs', 'trays', 'contract', 'now')), 'independent_owner_facts')
    return contexts['A']


def source_files(prior):
    base = read(SOURCE/'plan.json'); files = {}
    for path, digest in base['source_sha256'].items():
        require(sha(path) == digest == sha(SOURCE/base['source_archive'][path]), 'frozen105_source')
        files[path] = Path(path).read_bytes()
    for path in prior.source_paths()+[ROOT/TEST]: files[str(path)] = Path(path).read_bytes()
    return files


def pure_gate():
    receipt, plan = read(PURE/'receipt.json'), read(PURE/'plan.json')
    require(receipt['status'] == 'passed_process' and receipt['source_changed'] == [] and
        receipt['native_calls'] == receipt['model_predictions'] == 0 and receipt['plan_sha256'] == sha(PURE/'plan.json'), 'pure_receipt')
    cases = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 12 and not any(c.tag in ('failure', 'error', 'skipped') for case in cases for c in case), 'pure12')
    for path, digest in plan['source_sha256'].items():
        require(sha(path) == digest == sha(PURE/'source'/Path(path).relative_to(ROOT)), 'pure_source')
    return [PURE/name for name in ('plan.json', 'receipt.json', 'tests.xml')]


def prepare(output):
    from . import public_live_obligation_lazy_communication_projection as lazy
    from . import validate_live_communication_projection as prior
    no_execution_extensions(); pure_paths = pure_gate()
    require(sha(SOURCE/'plan.json') == SOURCE_PLAN and sha(CONTINUATION/'receipt.json') == CONTINUATION_RECEIPT, 'previous_six_identity')
    original = read(SOURCE/'plan.json'); receipt = read(SOURCE/'receipt.json'); continued = read(CONTINUATION/'receipt.json')
    require(receipt['status'] == 'exact_six_passive_conformance' and receipt['source_changed'] == [] and
        continued['status'] == 'exact_six_main_and_fourteen_same_action_suffixes' and continued['source_changed'] == [], 'previous_six_passed')
    output.mkdir(exist_ok=False); rows = {}
    for key in ORDER:
        old = original['rows'][key]
        rows[key] = {'status': 'unknown_unexecuted', 'input': old['input'], 'action': old['action'],
            'comparison_only_saved_prediction': old['comparison_only_saved_prediction'],
            'expected_collections': old['expected_collections'], 'initial_context_calls': 0, 'model_calls': 0}
    check_rows(rows); files = source_files(prior); pins = {}; archives = {}
    for path, data in files.items():
        relative = Path('source')/Path(path).relative_to(ROOT); destination = output/relative
        destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(data)
        pins[path] = hashlib.sha256(data).hexdigest(); archives[path] = str(relative)
    evidence = {}
    for row in rows.values():
        for field in ('input', 'comparison_only_saved_prediction'):
            r = row[field]; require(sha(r['path']) == r['sha256'], 'fixed_input_or_comparand'); evidence[r['path']] = r['sha256']
    for directory in (SOURCE, CONTINUATION):
        for name in ('plan.json', 'rows.json', 'receipt.json', 'bounded_execution.json', 'external_application_wall.json'):
            path = directory/name; evidence[str(path)] = sha(path)
    for path in [*(OUT/name for name in HISTORY), *pure_paths]: evidence[str(path)] = sha(path)
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'order': list(ORDER), 'rows': rows,
        'source_sha256': pins, 'source_archive': archives, 'evidence_sha256': evidence,
        'environment': {'python': sys.executable, 'sha256': sha(sys.executable)}, 'hard_application_seconds': LIMIT,
        'maximum_model_calls': 6, 'maximum_initial_context_profiles': 6, 'maximum_model_profiles': 6,
        'default_GC_required': True, 'model_source': ref(lazy.__file__),
        'history': {'references': [ref(OUT/name) for name in HISTORY],
            'finding': 'Existing008/prefix/quiet profiles use earlier physical or request-context projections; prefix copies and quiet scans were negative optimizations. They do not profile the current lazy communication model. Old eager communication180s ended73exact/23unknown; lazy96 subsequently passed, still far above100ms/32.'},
        'phase_boundaries': {'initial_context_profile': 'Both lawful initial contexts, existing guards and independent-fact equality. Exactly once per selected input.',
            'model_profile': 'Unchanged lazy.predict(Acontext, fixed action), including its own validation, Projection construction, full run/communication/guards and finish. Exactly once; no candidate search, suffix continuation or warmup.',
            'exports': 'Profile dump/function summary and full prediction gzip/hash after respective callback; outside cProfile but inside120.',
            'audit': 'Only after prediction saved: full byte/ordered-type/float comparison against frozen lazy result and complete collection chronology. No actual future endpoints enter prediction.',
            'whole': 'Parent imports, all source/input hashes, context/model profiles, exports, comparison and exit pins share120; external complete Python wall also required.'},
        'budget_basis': {'prior_passive_six_whole_seconds': 12.4314135, 'prior_continuation_six_whole_seconds': 18.6451326,
            'rationale': 'Six single-path calls, no14forks; cProfile overhead and exports unknown.120 is a bounded diagnostic allowance, not a runtime guarantee.'},
        'failure': 'All six remain in ledger; returned predictions/profiles saved before comparison. Exceptions/timeout/drift/different bytes remain unknown, no retry or tuning.',
        'cumulative_times_overlap_do_not_sum': True, 'performance_or_speedup_claim': False,
        'complete_request_100ms_certified': False, 'native_calls': 0, 'data_C_extension_loads': 0,
        'preparation_model_calls': 0}
    write(output/'plan.json', plan); write(output/'rows.json', rows)
    write(output/'preparation.json', {'status': 'prepared_source_review_pending', 'plan': ref(output/'plan.json'),
        'source_count': len(pins), 'pure_tests': 12, 'actual_model_calls': 0, 'native_calls': 0,
        'execute_command': [sys.executable, '-m', MODULE, '--execute', '--output', str(output), '--expected-plan', sha(output/'plan.json')]})


def pins_now(output, plan):
    result = {}
    for path, digest in plan['source_sha256'].items():
        for p in (Path(path), output/plan['source_archive'][path]): result[str(p)] = sha(p); require(result[str(p)] == digest, 'source_drift')
    for path, digest in plan['evidence_sha256'].items(): result[path] = sha(path); require(result[path] == digest, 'evidence_drift')
    require(plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'interpreter')
    return result


def loaded_sources(plan, prior):
    no_execution_extensions(); result = {str(path): sha(path) for path in prior.source_paths()}
    require(all(plan['source_sha256'].get(p) == d for p, d in result.items()), 'loaded_source_coverage')
    return result


def worker(output, expected):
    from . import public_live_obligation_lazy_communication_projection as lazy
    from . import validate_live_communication_projection as prior
    started = time.perf_counter(); require(sha(output/'plan.json') == expected, 'plan_identity')
    plan = read(output/'plan.json'); check_rows(plan['rows'])
    require(plan['schema'] == SCHEMA and plan['order'] == list(ORDER) and plan['hard_application_seconds'] == LIMIT and
        plan['maximum_model_calls'] == plan['maximum_initial_context_profiles'] == plan['maximum_model_profiles'] == 6 and
        plan['default_GC_required'] is True and gc.isenabled(), 'fixed_scope_and_GC')
    entry = pins_now(output, plan); write(output/'entry_pins.json', entry)
    loaded_entry = loaded_sources(plan, prior); write(output/'loaded_sources_entry.json', loaded_entry)
    rows = copy.deepcopy(plan['rows']); profiles = []; total_model_calls = 0
    for key in ORDER:
        row = rows[key]; row['status'] = 'unknown_in_progress'; write(output/'rows.json', rows)
        case_started = time.perf_counter()
        try:
            require(gc.isenabled(), 'GC_disabled'); at = time.perf_counter()
            try:
                public = read(row['input']['path'])
                require(bytes_of(public['action']) == bytes_of(row['action']), 'fixed_action')
            finally: row['input_decode_seconds'] = time.perf_counter()-at
            row['initial_context_calls'] += 1
            context, initial_profile = profiled_call(output/'profiles'/key/'initial_context.pstats', lambda: build_initial(public, prior))
            row['initial_context_profile'] = initial_profile; profiles.append({'case': key, 'phase': 'initial_context', **initial_profile})
            write(output/'rows.json', rows); require(initial_profile['status'] == 'returned', 'initial_context_error')
            total_model_calls += 1; row['model_calls'] += 1; require(total_model_calls <= 6, 'model_budget')
            prediction, model_profile = profiled_call(output/'profiles'/key/'model.pstats', lambda: lazy.predict(context, public['action']))
            row['model_profile'] = model_profile; profiles.append({'case': key, 'phase': 'model', **model_profile})
            write(output/'rows.json', rows); require(model_profile['status'] == 'returned', 'model_error')
            export_started = time.perf_counter()
            try:
                encoded = bytes_of(prediction)
                path = output/'predictions'/key; path.parent.mkdir(parents=True, exist_ok=True); path = path.with_suffix('.json.gz')
                path.write_bytes(gzip.compress(encoded, compresslevel=1, mtime=0))
                row.update(prediction=ref(path), status='returned_audit_pending')
            finally: row['prediction_export_seconds'] = time.perf_counter()-export_started
            write(output/'rows.json', rows)
            audit_started = time.perf_counter()
            try:
                target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())
                checks = compare_full(encoded, target); row['comparison'] = checks
                require(all(checks.values()), 'full_prediction_changed')
                require(bytes_of(prediction['projected_collections']) == bytes_of(row['expected_collections']), 'complete_chronology')
            finally: row['audit_seconds'] = time.perf_counter()-audit_started
            require(gc.isenabled(), 'GC_changed')
            row.update(status='exact_profiled_single_path', default_GC_retained=True)
        except Exception: row.update(status='unknown_error', error=traceback.format_exc())
        row['case_wall_including_exports_and_audit_seconds'] = time.perf_counter()-case_started
        write(output/'rows.json', rows)
    exit_pins = pins_now(output, plan); write(output/'exit_pins.json', exit_pins); require(exit_pins == entry, 'exit_pins')
    loaded_exit = loaded_sources(plan, prior); write(output/'loaded_sources_exit.json', loaded_exit)
    require(all(loaded_exit.get(p) == d for p, d in loaded_entry.items()) and gc.isenabled(), 'loaded_or_GC_changed')
    exact_rows = sum(r['status'] == 'exact_profiled_single_path' for r in rows.values())
    write(output/'report.json', {'schema': SCHEMA, 'status': 'exact_six_profiled_diagnostic' if exact_rows == 6 and total_model_calls == 6
        else 'completed_unknowns_preserved', 'exact_rows': exact_rows, 'unknown_rows': 6-exact_rows,
        'model_calls': total_model_calls, 'profiles': profiles, 'rows': ref(output/'rows.json'),
        'source_changed': [], 'default_GC_retained': True, 'worker_seconds': time.perf_counter()-started,
        'profile_overhead_included': True, 'cumulative_times_overlap_do_not_sum': True,
        'native_calls': 0, 'data_C_extension_loads': 0, 'performance_or_speedup_claim': False,
        'complete_request_100ms_certified': False})
    write(output/'receipt.json', {'status': 'diagnostic_completed_with_full_denominator', 'plan': ref(output/'plan.json'),
        'report': ref(output/'report.json'), 'rows': ref(output/'rows.json'), 'entry_pins': ref(output/'entry_pins.json'),
        'exit_pins': ref(output/'exit_pins.json'), 'loaded_entry': ref(output/'loaded_sources_entry.json'),
        'loaded_exit': ref(output/'loaded_sources_exit.json'), 'exact_rows': exact_rows, 'unknown_rows': 6-exact_rows,
        'model_calls': total_model_calls, 'source_changed': [], 'native_calls': 0, 'data_C_extension_loads': 0})


def execute(output, expected):
    require(sha(output/'plan.json') == expected, 'launch_plan')
    with (output/'execution_claim').open('x'): pass
    command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output), '--expected-plan', expected]
    with (output/'stdout.log').open('x') as stdout, (output/'stderr.log').open('x') as stderr:
        elapsed = time.monotonic()-BOOT
        process = bounded_windows_job.run(command, timeout=remaining(elapsed), stdout=stdout, stderr=stderr,
            admission=expected, cwd=str(ROOT))
    wall = time.monotonic()-BOOT; passed = process['status'] == 'exited' and process['exitcode'] == 0 and wall <= LIMIT
    write(output/'bounded_execution.json', {'status': 'bounded_worker_completed' if passed else 'unknown_failed_or_timeout',
        'process': process, 'command': command, 'hard_application_seconds': LIMIT, 'parent_before_worker_seconds': elapsed,
        'whole_python_before_final_receipt_seconds': wall, 'external_launch_to_exit_required': True,
        'receipt': ref(output/'receipt.json') if (output/'receipt.json').exists() else None,
        'prediction_conformance_not_inferred_from_exit_code': True})
    return 0 if passed and time.monotonic()-BOOT <= LIMIT else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--expected-plan')
    args = parser.parse_args(); output = args.output.resolve(); no_execution_extensions()
    if args.prepare: prepare(output); return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline() == args.expected_plan+'\n', 'owned_admission')
        try: worker(output, args.expected_plan)
        except BaseException:
            write(output/'failure.json', {'status': 'unknown_profile_failure', 'error': traceback.format_exc(),
                'native_calls': 0, 'data_C_extension_loads': 0}); raise
        return 0
    require(args.execute, 'explicit_execute'); return execute(output, args.expected_plan)


if __name__ == '__main__': raise SystemExit(main())
