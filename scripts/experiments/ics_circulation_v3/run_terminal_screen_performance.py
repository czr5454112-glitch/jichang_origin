"""Round8 fixed paired fresh-process terminal-screen performance experiment."""
from time import process_time_ns, perf_counter_ns
MODULE_ENTRY_CPU_NS, MODULE_ENTRY_WALL_NS = process_time_ns(), perf_counter_ns()

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from .run_terminal_capacity_screen import compare_physical
from .run_same_zone_query_coverage import (ROOT, SOURCE, BASE, OLD, read, write,
    manifest, verify_manifest, exact_json_value, write_gzip)
from .phase4_network_workloads import file_sha
from .run_same_zone_supply import exact_original_scene
from .same_zone_experiment import CASE_BUDGET, TAIL_CAP, install_supply_policy
from .same_zone_labels import run_cycle
from .phase4_control import build_engine
from .network_role_labels import SPEC, bind_accounting
from .model import Bag
from .physical_observation import InstantPhysicalCursorSimulation
from .routing_cache_contract import enable_replay_cache, routing_cache_state
from .experiment_resources import memory_snapshot
from .terminal_screen_performance import install_performance_probe

IMPORT_END_CPU_NS, IMPORT_END_WALL_NS = process_time_ns(), perf_counter_ns()
SCREEN = BASE / 'phase4_w3_terminal_capacity_screen_20261010'
ROUND7_VALIDATION = BASE / 'phase4_w3_round7_independent_review_20261010/full_validation_terminal/result.json'
DEFAULT = BASE / 'phase4_w3_terminal_screen_performance_20261010'
NEW_SOURCES = ('terminal_screen_performance.py', 'run_terminal_screen_performance.py')
NEW_TESTS = ('test_ics_circulation_v3_terminal_screen_performance.py',
             'test_ics_circulation_v3_terminal_screen_performance_audit.py')
QUERY_IDENTITY = ('time', 'version', 'bag_id', 'tray_id', 'destination',
                  'requested_k', 'public_snapshot_sha256', 'options')


def fixed_pairs(requests):
    """No outcome input: every business case repeated twice, reversed arm order."""
    ordered = sorted(requests, key=lambda r: r['case_id'])
    return [{'block': block, 'case': request,
             'arms': ['off', 'on'] if (i + block) % 2 == 0 else ['on', 'off']}
            for block in (0, 1) for i, request in enumerate(ordered)]


def verify(output):
    output = Path(output)
    verify_manifest(output / 'preparation_manifest.json')
    p = read(output / 'protocol.json')
    for kind, root in (('source', SOURCE), ('test', ROOT / 'tests')):
        for name, expected in p[kind + '_sha256'].items():
            if file_sha(root / name) != expected:
                raise ValueError('frozen ' + kind + ' drift: ' + name)
    for name, expected in p['input_sha256'].items():
        if file_sha(name) != expected:
            raise ValueError('frozen input drift: ' + name)
    return p


def prepare(output):
    cpu, wall = process_time_ns(), perf_counter_ns()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    old = read(SCREEN / 'protocol.json')
    # Bind the old closure, not unrelated concurrently developing Round8 files.
    for name, h in old['source_sha256'].items():
        if file_sha(SOURCE / name) != h:
            raise ValueError('Round7 source drift: ' + name)
    for name, h in old['test_sha256'].items():
        if file_sha(ROOT / 'tests' / name) != h:
            raise ValueError('Round7 test drift: ' + name)
    verify_manifest(SCREEN / 'preparation_manifest.json')
    verify_manifest(SCREEN / 'formal_manifest.json')
    sources = dict(old['source_sha256'])
    previous = read(ROUND7_VALIDATION)
    if previous['exit_code'] != 0 or not previous['source_and_test_and_cpp_unchanged']:
        raise ValueError('Round7 final source freeze is not validated')
    for path, expected in previous['before'].items():
        if file_sha(ROOT / path) != expected:
            raise ValueError('Round7 complete freeze drift: ' + path)
        if path.startswith('scripts/experiments/ics_circulation_v3/'):
            sources[Path(path).name] = expected
    sources.update({name: file_sha(SOURCE / name) for name in NEW_SOURCES})
    tests = dict(old['test_sha256'])
    tests.update({name: file_sha(ROOT / 'tests' / name) for name in NEW_TESTS})
    inputs = dict(old['input_sha256'])
    inputs[str(ROUND7_VALIDATION.resolve())] = file_sha(ROUND7_VALIDATION)
    references = {r['case_id']: r for r in read(SCREEN / 'formal/summary.json')['rows']}
    for name in ('protocol.json', 'preparation_manifest.json', 'formal_manifest.json', 'formal/summary.json'):
        inputs[str((SCREEN / name).resolve())] = file_sha(SCREEN / name)
    for row in references.values():
        path = SCREEN / row['file']
        if file_sha(path) != row['sha256']:
            raise ValueError('old screen deployment artifact drift')
        inputs[str(path.resolve())] = row['sha256']
    for name, h in inputs.items():
        if file_sha(name) != h:
            raise ValueError('ancestral input drift: ' + name)
    for kind, values, root in (('source', sources, SOURCE), ('test', tests, ROOT / 'tests')):
        folder = output / (kind + '_snapshot')
        folder.mkdir()
        for name in values:
            (folder / name).write_bytes((root / name).read_bytes())
    requests = sorted(old['requests'], key=lambda r: r['case_id'])
    p = {'schema': 'ics_round8_screen_performance_v1', 'source_sha256': sources,
        'test_sha256': tests, 'input_sha256': inputs, 'screen_references': references,
        'requests': requests, 'formal_pairs': fixed_pairs(requests),
        'pilot_pairs': fixed_pairs([r for r in requests if r['tape_id'] == 'nominal']),
        'max_concurrent_children': 3, 'blocks': 2, 'block_barrier': True,
        'fresh_process_per_arm': True, 'formal_reuses_pilot': False, 'warmup_calls': 0,
        'screen_max_records': 200000, 'case_budget': asdict(CASE_BUDGET), 'tail_cap': TAIL_CAP,
        'observer': 'Both arms hash the same complete pre-query Snapshot/cache, copy ordered raw pools, use frozen InstantPhysicalCursorSimulation for detached actual per-tick observations, also retain legacy compatibility trace, and use the same fixed-field schema and gzip persistence. Observer excluded from algorithm timer.',
        'algorithm_scope': 'Request destination lookup, validity checks, dispatch, optional certificate and delegate; diagnostic deepcopy, state hash and row copy excluded. Nested screen/search intervals do not add to algorithm interval.',
        'clock_scope': 'Fresh child process CPU from OS after exit when supported; earliest module cumulative CPU exposes pre-entry CPU; import interval measured. Parent launch-to-exit elapsed includes startup/teardown under <=3 worker contention. Not production latency or a hard realtime claim.',
        'comparison': 'Every pair checks complete pre-query Snapshot hash, query identity/K, ordered pool, task ledger, actual action and per-tick physical/event trajectories through full drain. Every arm also compares frozen Round7 screen artifacts; cache/search-status differences are separate.',
        'statistics': '27 business cases, 2 repeated timing blocks, not 54 independent business samples. Report all paired CPU/wall differences including regressions and zeros; no sample deletion or budget tuning.',
        'prepare_cpu_seconds': (process_time_ns() - cpu) / 1e9,
        'prepare_wall_seconds': (perf_counter_ns() - wall) / 1e9}
    write(output / 'protocol.json', p)
    manifest(output, 'preparation_manifest.json', [f for f in output.rglob('*') if f.is_file()])


def query_comparison(left, right):
    def normalized(value):
        # Accept both live dataclass candidates and their persisted JSON form.
        return json.loads(json.dumps(value, default=asdict, allow_nan=False))
    mismatches = []
    for i, (a, b) in enumerate(zip(left, right)):
        fields = [field for field in QUERY_IDENTITY if normalized(a[field]) != normalized(b[field])]
        if fields:
            mismatches.append({'ordinal': i, 'fields': fields})
    return {'same_count': len(left) == len(right), 'left_count': len(left),
            'right_count': len(right), 'mismatches': mismatches,
            'all_exact': len(left) == len(right) and not mismatches}


def child(output, stage, block, case_id, arm):
    cpu, wall = process_time_ns(), perf_counter_ns()
    output = Path(output)
    stem = f'b{block}__{case_id}__{arm}'
    folder = output / stage
    target = folder / (stem + '.json.gz')
    receipt = folder / (stem + '.receipt.json')
    outcome = accounting = engine = None
    physical = False
    simulation_cpu = simulation_wall = None
    cache_before = None
    failure = None
    recovery = None
    complete = False
    try:
        p = verify(output)
        request = next(r for r in p['requests'] if r['case_id'] == case_id)
        scene = exact_original_scene(request['scene'])
        saved = read(OLD / 'saved_tapes.json')[request['scene']][request['tape_id']]
        future = tuple(Bag(**b) for b in saved['future_engine_only'])
        base = build_engine(scene.initial, scene.forecasts, future, SPEC)
        enable_replay_cache(base)
        engine = InstantPhysicalCursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
        install_supply_policy(engine, 'same_zone32plus32')
        cache_before = routing_cache_state(engine)
        if cache_before['fast_cache']['entries_lru_oldest_first']:
            raise ValueError('fresh-process initial replay cache is unexpectedly warm')
        accounting = install_performance_probe(engine, enabled=arm == 'on', max_records=p['screen_max_records'])
        owner = bind_accounting(engine, CASE_BUDGET)
        sc, sw = process_time_ns(), perf_counter_ns()
        physical = True
        try:
            outcome = run_cycle(engine, {**engine.state.bags, **{b.bag_id: b for b in future}},
                minimum_observation_at=scene.horizon, budget=CASE_BUDGET,
                tail_cap=TAIL_CAP, owner=owner, retain_physical_ticks=True)
        finally:
            simulation_cpu, simulation_wall = (process_time_ns() - sc) / 1e9, (perf_counter_ns() - sw) / 1e9
        payload = {'case': request, 'block': block, 'arm': arm, 'outcome': outcome,
                   'cache_before': cache_before, 'measurement': asdict(accounting),
                   'instant_physical_ticks': engine.instant_physical_ticks}
        write_gzip(target, payload)
        complete = True
        verify(output)
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        recovery = folder / (stem + '.recovery.json')
        try:
            write(recovery, {'case_id': case_id, 'arm': arm, 'block': block, 'outcome': outcome,
                'measurement': None if accounting is None else asdict(accounting),
                'cache_before': cache_before, 'failure': failure,
                'instant_physical_ticks': None if engine is None else engine.instant_physical_ticks})
        except BaseException as second:
            failure['recovery_error'] = {'type': type(second).__name__, 'message': str(second)}
    rows = [] if accounting is None else accounting.rows
    status = 'invocation_failure' if failure else outcome['status']
    result = {'case_id': case_id, 'arm': arm, 'block': block, 'status': status, 'failure': failure,
        'physical_call_entered': physical, 'raw_complete': complete,
        'file': str(target.relative_to(output)) if target.exists() else None,
        'sha256': file_sha(target) if target.exists() else None,
        'recovery_file': str(recovery.relative_to(output)) if recovery and recovery.exists() else None,
        'recovery_sha256': file_sha(recovery) if recovery and recovery.exists() else None,
        'search_calls': len(rows), 'search_work': sum(r['search_work'] for r in rows),
        'screen_work': sum(r['screen_work'] for r in rows),
        'certified_queries': sum(r['certified'] for r in rows),
        'timings': {key[:-3] + '_seconds': sum(r[key] for r in rows) / 1e9
            for key in ('algorithm_cpu_ns', 'algorithm_wall_ns', 'search_cpu_ns', 'search_wall_ns',
                        'screen_cpu_ns', 'screen_wall_ns', 'observer_cpu_ns', 'observer_wall_ns')},
        'whole_simulation_cpu_seconds': simulation_cpu, 'whole_simulation_wall_seconds': simulation_wall,
        'module_entry_cumulative_cpu_seconds': MODULE_ENTRY_CPU_NS / 1e9,
        'module_entry_monotonic_ns': MODULE_ENTRY_WALL_NS,
        'imports_cpu_seconds': (IMPORT_END_CPU_NS - MODULE_ENTRY_CPU_NS) / 1e9,
        'imports_wall_seconds': (IMPORT_END_WALL_NS - MODULE_ENTRY_WALL_NS) / 1e9,
        'child_invocation_cpu_seconds': (process_time_ns() - cpu) / 1e9,
        'child_invocation_wall_seconds': (perf_counter_ns() - wall) / 1e9,
        'child_cumulative_cpu_at_receipt_seconds': process_time_ns() / 1e9,
        'memory': memory_snapshot(),
        'receipt_scope': 'Child invocation begins after imports; includes setup, symmetric observation, full simulation, raw serialization and after-binding verification. Excludes this final receipt serialization and teardown; parent captures final OS process CPU independently.'}
    write(receipt, result)
    return 0 if failure is None and status == 'controller_quiescent' else 1


def final_process_cpu(proc):
    """Windows process handle remains valid after wait until Popen is closed."""
    if os.name != 'nt':
        return None, 'final OS child CPU unavailable on this platform'
    from ctypes import wintypes
    class FILETIME(ctypes.Structure):
        _fields_ = [('low', wintypes.DWORD), ('high', wintypes.DWORD)]
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetProcessTimes
    api.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FILETIME)] * 4
    api.restype = wintypes.BOOL
    values = [FILETIME() for _ in range(4)]
    if not api(int(proc._handle), *(ctypes.byref(v) for v in values)):
        return None, 'GetProcessTimes error ' + str(ctypes.get_last_error())
    cpu = sum((v.high << 32) + v.low for v in values[2:]) / 1e7
    return cpu, None


def persist_record(path, value):
    """Never discard a completed arm's resource evidence on JSON helper failure."""
    try:
        write(path, value)
        return None
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc)}
        fallback = Path(str(path) + '.plain_recovery.json')
        try:
            with fallback.open('x', encoding='utf8') as stream:
                json.dump({'payload': value, 'persistence_failure': failure}, stream,
                          ensure_ascii=False, indent=2, allow_nan=False)
            failure['recovery_file'] = str(fallback)
            failure['recovery_sha256'] = file_sha(fallback)
        except BaseException as second:
            failure['recovery_error'] = {'type': type(second).__name__, 'message': str(second)}
        return failure


def launch_arm(output, stage, pair, arm):
    output = Path(output)
    name = f"b{pair['block']}__{pair['case']['case_id']}__{arm}"
    started = perf_counter_ns()
    row = {'arm': arm, 'case_id': pair['case']['case_id'], 'block': pair['block'],
           'process_cpu_seconds': None, 'process_cpu_unavailable_reason': None,
           'launch_failure': None, 'exit_code': None, 'receipt': None}
    command = [sys.executable, '-m', 'scripts.experiments.ics_circulation_v3.run_terminal_screen_performance',
        '--stage', 'child', '--output', str(output), '--run-stage', stage,
        '--block', str(pair['block']), '--case', pair['case']['case_id'], '--arm', arm]
    try:
        with (output / stage / (name + '.log')).open('x', encoding='utf8') as log:
            with subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT) as proc:
                row['pid'] = proc.pid
                row['exit_code'] = proc.wait()
                row['process_cpu_seconds'], row['process_cpu_unavailable_reason'] = final_process_cpu(proc)
    except BaseException as exc:
        row['launch_failure'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    row['launch_to_exit_wall_seconds'] = (perf_counter_ns() - started) / 1e9
    path = output / stage / (name + '.receipt.json')
    try:
        if path.exists():
            row['receipt'] = read(path)
            row['receipt_file'], row['receipt_sha256'] = str(path.relative_to(output)), file_sha(path)
            row['launch_to_module_entry_wall_seconds'] = (row['receipt']['module_entry_monotonic_ns'] - started) / 1e9
    except BaseException as exc:
        row['receipt_error'] = {'type': type(exc).__name__, 'message': str(exc)}
    row['persistence_failure'] = persist_record(output / stage / (name + '.launch.json'), row)
    return row


def pair_job(output, stage, pair):
    output = Path(output)
    arms = {}
    # Finish and preserve both arms even when the first arm fails.
    for arm in pair['arms']:
        try:
            arms[arm] = launch_arm(output, stage, pair, arm)
        except BaseException as exc:
            arms[arm] = {'arm': arm, 'exit_code': None, 'receipt': None,
                'process_cpu_seconds': None, 'unexpected_launcher_failure': traceback.format_exc()}
    result = {'block': pair['block'], 'case_id': pair['case']['case_id'],
        'arm_order': pair['arms'], 'arms': arms, 'all_exact': False, 'comparison_failure': None}
    try:
        if any(v['exit_code'] != 0 or v['receipt'] is None or not v['receipt']['raw_complete']
               or v.get('persistence_failure') for v in arms.values()):
            raise ValueError('one or both arms incomplete; keep all physical and resource evidence')
        raw = {}
        for arm, row in arms.items():
            receipt = row['receipt']
            if file_sha(output / receipt['file']) != receipt['sha256']:
                raise ValueError('arm output SHA mismatch')
            raw[arm] = read(output / receipt['file'])
        result['physical_comparison'] = compare_physical(raw['off']['outcome'], raw['on']['outcome'])
        result['physical_comparison']['instant_detached_ticks'] = exact_json_value(
            raw['off']['instant_physical_ticks'], raw['on']['instant_physical_ticks'])
        result['query_comparison'] = query_comparison(raw['off']['measurement']['rows'], raw['on']['measurement']['rows'])
        result['cache_before_equal'] = exact_json_value(raw['off']['cache_before'], raw['on']['cache_before'])
        result['both_initial_caches_cold'] = all(not r['cache_before']['fast_cache']['entries_lru_oldest_first'] for r in raw.values())
        result['cache_after_equal'] = exact_json_value(raw['off']['outcome']['cache_after'], raw['on']['outcome']['cache_after'])
        reference = read(output / 'protocol.json')['screen_references'][pair['case']['case_id']]
        if file_sha(SCREEN / reference['file']) != reference['sha256']:
            raise ValueError('old wrapper reference changed')
        old = read(SCREEN / reference['file'])
        result['old_wrapper_comparison'] = {arm: {
            'physical': compare_physical(old['outcome'], current['outcome']),
            'queries': query_comparison(old['screen_accounting']['rows'], current['measurement']['rows'])}
            for arm, current in raw.items()}
        result['all_exact'] = (all(result['physical_comparison'].values())
            and result['query_comparison']['all_exact'] and result['cache_before_equal'] and result['both_initial_caches_cold']
            and all(all(v['physical'].values()) and v['queries']['all_exact']
                    for v in result['old_wrapper_comparison'].values()))
    except BaseException as exc:
        result['comparison_failure'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    result['persistence_failure'] = persist_record(output / stage / f"b{pair['block']}__{pair['case']['case_id']}.pair.json", result)
    if result['persistence_failure']:
        result['all_exact'] = False
    return result


def run(output, stage):
    cpu, wall = process_time_ns(), perf_counter_ns()
    output = Path(output)
    p = verify(output)
    if stage == 'formal':
        verify_manifest(output / 'pilot_manifest.json')
        pilot = read(output / 'pilot/summary.json')
        if not pilot['all_exact'] or not pilot['source_inputs_tests_unchanged']:
            raise ValueError('all fixed pilot checks must pass before formal')
    (output / stage).mkdir(exist_ok=False)
    pairs = p[stage + '_pairs']
    results, blocks = [], []
    for block in (0, 1):
        block_started = perf_counter_ns()
        selected = [pair for pair in pairs if pair['block'] == block]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(pair_job, str(output), stage, pair): pair for pair in selected}
            for future in as_completed(futures):
                pair = futures[future]
                try:
                    row = future.result()
                except BaseException as exc:
                    row = {'case_id': pair['case']['case_id'], 'block': block,
                           'all_exact': False, 'arms': {}, 'parent_pair_failure': traceback.format_exc()}
                results.append(row)
                print(json.dumps({'completed_pairs': len(results), 'block': block,
                    'case_id': row['case_id'], 'all_exact': row['all_exact']}), flush=True)
        blocks.append({'block': block, 'wall_makespan_seconds': (perf_counter_ns() - block_started) / 1e9})
    stable = True
    drift = None
    try:
        verify(output)
    except BaseException as exc:
        stable, drift = False, str(exc)
    arms = [v for r in results for v in r['arms'].values()]
    summary = {'stage': stage, 'pairs': sorted(results, key=lambda r: (r['block'], r['case_id'])),
        'planned_pairs': len(pairs), 'planned_physical_calls': len(pairs) * 2,
        'recorded_arm_launches': len(arms), 'physical_calls_recorded': sum(
            bool(v['receipt'] and v['receipt']['physical_call_entered']) for v in arms),
        'worker_final_process_cpu_seconds_sum': sum(v['process_cpu_seconds'] or 0 for v in arms),
        'unknown_final_process_cpu_arms': sum(v['process_cpu_seconds'] is None for v in arms),
        'parent_cpu_seconds': (process_time_ns() - cpu) / 1e9,
        'wall_makespan_seconds': (perf_counter_ns() - wall) / 1e9, 'blocks': blocks,
        'all_exact': len(results) == len(pairs) and all(r['all_exact'] for r in results),
        'source_inputs_tests_unchanged': stable, 'drift': drift,
        'resource_scope': 'Worker final OS CPU is complete process lifetime (imports/exit included). Parent interval includes launch, comparison, reference reads and receipt/hash work through summary construction; final summary/manifest serialization excluded. Nested query/simulation/child-invocation costs are not added again.'}
    write(output / stage / 'summary.json', summary)
    manifest(output, stage + '_manifest.json', [f for f in (output / stage).rglob('*') if f.is_file()])
    if not summary['all_exact'] or not stable:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--stage', choices=('prepare', 'pilot', 'formal', 'child'), required=True)
    parser.add_argument('--run-stage', choices=('pilot', 'formal'))
    parser.add_argument('--block', type=int)
    parser.add_argument('--case')
    parser.add_argument('--arm', choices=('on', 'off'))
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare(args.output)
    elif args.stage == 'child':
        raise SystemExit(child(args.output, args.run_stage, args.block, args.case, args.arm))
    else:
        run(args.output, args.stage)
