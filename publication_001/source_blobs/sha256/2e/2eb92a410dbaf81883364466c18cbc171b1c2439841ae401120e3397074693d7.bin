"""Uncached original-proof cost diagnosis kernel; no model or native calls.

This module is not an executable campaign. A separately reviewed owned120
driver must bind sources, the original callable, output paths and saved proof.
The wrapper times that callable without editing any of its globals/identity.
Nested attribution comes from cProfile; cumulative times must not be added.
"""
from __future__ import annotations

import cProfile
import gc
import hashlib
import json
from pathlib import Path
import pstats
import time
import traceback
from types import FunctionType

SCHEMA = 'g31.future_source_inventory.cost_kernel.v1'
CALLS = 65


def require(value, reason):
    if not value:
        raise ValueError('source_inventory_profile:' + reason)


def encoded(value):
    """Closed builtin JSON data; no custom serialization/capability traversal."""
    def validate(item):
        kind = type(item)
        if kind is dict:
            require(all(type(key) is str for key in item), 'JSON_keys')
            for child in item.values():
                validate(child)
        elif kind is list:
            for child in item:
                validate(child)
        else:
            require(kind in (str, int, float, bool, type(None)), 'JSON_type')
    validate(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
        separators=(',', ':')).encode('utf8')


def error_value(error):
    return {'type': type(error).__name__, 'message': str(error),
        'traceback': ''.join(traceback.format_exception(error))}


def clock_value(clock):
    value = clock()
    require(type(value) is int and value >= 0, 'clock_exact_nonnegative_int')
    return value


def one_original_call(original, profiler, clock):
    """Keep an original exception even if profiling/clock cleanup also fails.

    No monkeypatch, regenerated callable, private namespace or runtime identity
    substitution occurs here. Tests may inject tiny fake functions/timers.
    """
    result = None
    original_error = None
    monitor_errors = []
    start = end = None
    invoked = False
    try:
        start = clock_value(clock)
        profiler.enable()
        invoked = True
        try:
            result = original()
        except BaseException as error:
            original_error = error
    except BaseException as error:
        monitor_errors.append(error)
    finally:
        try:
            profiler.disable()
        except BaseException as error:
            monitor_errors.append(error)
        try:
            end = clock_value(clock)
            if start is not None:
                require(end >= start, 'clock_order')
        except BaseException as error:
            monitor_errors.append(error)
    timing = {'started_ns': start, 'finished_ns': end,
        'elapsed_ns': end-start if start is not None and end is not None and end >= start else None,
        'includes_profiler_enable_disable': True}
    return result, original_error, monitor_errors, timing, invoked


def statistic_rows(stats):
    return [{'file': filename, 'line': line, 'function': name,
        'primitive_calls': row[0], 'total_calls': row[1],
        'self_seconds': row[2], 'cumulative_seconds': row[3]}
        for (filename, line, name), row in sorted(stats.stats.items())]


def summarize_stats(stats):
    rows = statistic_rows(stats)
    identity = lambda row: (row['file'], row['line'], row['function'])
    watched = ('source_proof', '_source_inventory', 'build_parts', 'tree_of',
        '_tree', 'getsource', 'getsourcelines', 'parse', 'walk', 'compile',
        'deepcopy', 'read_bytes', 'sha256', 'action_uses')
    return {'function_count': len(rows), 'total_self_seconds': stats.total_tt,
        'total_calls': stats.total_calls, 'primitive_calls': stats.prim_calls,
        'top_cumulative': sorted(rows, key=lambda row: (-row['cumulative_seconds'], identity(row)))[:25],
        'top_self': sorted(rows, key=lambda row: (-row['self_seconds'], identity(row)))[:25],
        'top_calls': sorted(rows, key=lambda row: (-row['total_calls'], identity(row)))[:25],
        'watched': [row for row in rows if any(word in row['function'] for word in watched)],
        'cumulative_times_overlap_do_not_sum': True,
        'profiling_overhead_present': True, 'uninstrumented_latency_claim': False}


def profile_series(original, comparison_bytes, *, raw_profile_path,
                   save_proof, persist_rows, count=CALLS,
                   clock=time.perf_counter_ns, profiler_factory=cProfile.Profile):
    """Exactly65 scheduled calls, stopping after the first error/mismatch.

    Every remaining call retains an unknown_unexecuted row. Proofs are saved
    before comparison, and profiling data is exported on all ordinary failure
    paths. Results are observations only; this function never grants authority.
    Source binding, whole-process bound and entry/exit checks belong to driver.
    """
    require(type(original) is FunctionType, 'original_python_function')
    require(type(comparison_bytes) is bytes, 'comparison_bytes')
    require(type(count) is int and count == CALLS, 'fixed65_denominator')
    require(encoded(json.loads(comparison_bytes)) == comparison_bytes, 'canonical_comparison')
    require(gc.isenabled(), 'default_GC_required')
    profile_path = Path(raw_profile_path)
    require(not profile_path.exists(), 'profile_output_exists')
    rows = [{'ordinal': ordinal, 'status': 'unknown_unexecuted', 'invoked': False}
        for ordinal in range(CALLS)]
    report = {'schema': SCHEMA, 'status': 'unknown_incomplete', 'rows': rows,
        'planned_calls': CALLS, 'actual_calls': 0, 'exact_proofs': 0,
        'default_GC_changed': False, 'cache_used': False, 'runtime_globals_replaced': False,
        'model_predictions': 0, 'native_calls': 0, 'custom_data_C_loads': 0,
        'proof_target_is_comparison_only': True, 'failure': None}
    profiler = None
    try:
        profiler = profiler_factory()
        for ordinal in range(CALLS):
            row = rows[ordinal]
            value, original_error, monitor_errors, timing, invoked = one_original_call(original, profiler, clock)
            row.update(invoked=invoked, timing=timing)
            report['actual_calls'] += int(invoked)
            if original_error is not None:
                row['original_error'] = error_value(original_error)
            if monitor_errors:
                row['monitor_errors'] = [error_value(error) for error in monitor_errors]
            if original_error is not None or monitor_errors:
                row['status'] = 'unknown_original_or_monitor_failure'
                # A successful return can still be retained when timing failed.
                if original_error is None and invoked:
                    try:
                        raw = encoded(value)
                        row['saved_return'] = save_proof(ordinal, raw)
                    except BaseException as error:
                        row['return_export_error'] = error_value(error)
                persist_rows(rows)
                break
            raw = encoded(value)
            row['returned_bytes'] = len(raw)
            row['returned_sha256'] = hashlib.sha256(raw).hexdigest()
            row['saved_return'] = save_proof(ordinal, raw)
            row['full_bytes_exact'] = raw == comparison_bytes
            row['status'] = 'exact_proof' if row['full_bytes_exact'] else 'unknown_proof_mismatch'
            report['exact_proofs'] += int(row['full_bytes_exact'])
            persist_rows(rows)
            if not row['full_bytes_exact']:
                break
    except BaseException as error:
        report['failure'] = error_value(error)
        # The current row must not remain exact when its required export failed.
        if 'row' in locals() and row['status'] == 'exact_proof':
            report['exact_proofs'] -= 1
            row['status'] = 'unknown_required_export_failure'
        elif 'row' in locals() and row['status'] == 'unknown_unexecuted' and row['invoked']:
            row['status'] = 'unknown_return_encoding_or_export_failure'
    finally:
        try:
            require(profiler is not None, 'profile_not_initialized')
            profiler.disable()
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profiler.dump_stats(str(profile_path))
            stats = pstats.Stats(profiler)
            report['pstats'] = {'path': str(profile_path),
                'sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest()}
            report['statistics'] = summarize_stats(stats)
        except BaseException as error:
            report['profile_export_error'] = error_value(error)
    report['default_GC_changed'] = not gc.isenabled()
    report['unknown_rows'] = CALLS-report['exact_proofs']
    report['unexecuted_rows'] = sum(not row['invoked'] for row in rows)
    if report['exact_proofs'] == CALLS and report['actual_calls'] == CALLS and report['failure'] is None and 'profile_export_error' not in report and not report['default_GC_changed']:
        report['status'] = 'exact65_original_source_proofs_profiled'
    return report


def bind_original(future_module, expected_function):
    """Driver-facing exact target check, not a source validation substitute."""
    require(type(expected_function) is FunctionType and future_module.source_proof is expected_function,
        'original_target_identity')
    require(expected_function.__globals__ is vars(future_module), 'original_defining_globals')
    return expected_function
