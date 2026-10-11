"""Reconcile Round9 measured CPU without counting nested intervals twice.

Only this directory is written. Run --final only after root confirms all work
is complete; all six launched window result receipts are required then.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import argparse
import json
from pathlib import Path
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'pyproject.toml').exists())
EXPERIMENTS = HERE.parent
BASE_NAMES = (
    'phase4_round9_business_inputs_20261011',
    'phase4_round9_business_input_independent_audit_20261011',
    'phase4_round9_storage_routing_20261011',
    'phase4_round9_storage_lifecycle_20261011',
    'phase4_round9_storage_release_plateau_20261011',
    'phase4_round9_independent_review_20261011',
)
WINDOW_NAMES = ('business_window_h80_001', 'business_window_h21600_001',
                'business_window_h80_002', 'business_window_h21600_002',
                'business_window_h80_003', 'business_window_h21600_003')


def rel(path):
    return path.relative_to(ROOT).as_posix()


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError('invalid nonnegative resource value: ' + label)
    return value


def status(data):
    if 'status' in data:
        return data['status']
    for key in ('pytest_exit', 'pytest_exit_code', 'exit_code'):
        if key in data:
            return 'passed' if data[key] == 0 else 'failed'
    if 'success' in data:
        return 'passed' if data['success'] else 'failed'
    return 'receipt_without_explicit_status'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-name', required=True)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    if '/' in args.run_name or '\\' in args.run_name or args.run_name in ('', '.', '..'):
        raise ValueError('run-name must be one directory component')
    out = HERE / args.run_name
    out.mkdir()  # Never overwrite an earlier ledger invocation.
    started_cpu, started_wall = process_time(), perf_counter()
    bindings, rows, excluded, unknown, pending = {}, [], [], [], []
    docs, raw_data = {}, {}
    changed = []

    def read(path):
        data = path.read_bytes()
        bindings[rel(path)] = sha256(data).hexdigest()
        return data

    def add(path, field, value, data, *, group=None, physics=None, detail=''):
        rows.append(dict(receipt=rel(path), field=field, cpu_seconds=number(value, rel(path)+'#'+field),
            status=status(data), group=group or path.parts[path.parts.index('ics_circulation_v3')+1],
            wall_seconds=data.get('parent_wall_seconds', data.get('wall_seconds', data.get('wall_s'))),
            physical_runs=physics, detail=detail,
            source_changed=data.get('source_changed'),
            scope=data.get('scope', data.get('resource_scope', data.get('cpu_scope', 'receipt explicit interval')))))

    for base_name in BASE_NAMES:
        base = EXPERIMENTS / base_name
        if not base.is_dir():
            pending.append({'kind': 'missing_base', 'path': rel(base)})
            continue
        for path in sorted(base.rglob('*.json')):
            components = path.relative_to(base).parts
            if any(x in ('pytest_tmp', 'fixture', 'fixtures', '__pycache__') or x.startswith('test_')
                   for x in components[:-1]):
                continue
            try:
                data = json.loads(path.read_bytes())
            except (ValueError, OSError) as error:
                pending.append({'kind': 'unreadable_json', 'path': rel(path), 'error': str(error)})
                continue
            if not isinstance(data, dict):
                continue
            raw_data[rel(path)] = data
            if path.name == 'resource_summary.json' and base_name == BASE_NAMES[0]:
                docs[rel(path)] = json.loads(read(path))
                for key in ('prior_bookkeeping_cpu_seconds', 'bookkeeping_cpu_before_write'):
                    if key in data:
                        add(path, key, data[key], data, physics=0,
                            detail='bookkeeping only; invocation total below is not counted again')
                excluded.append(dict(receipt=rel(path), field='known_invocation_cpu_seconds',
                    value=data.get('known_invocation_cpu_seconds'), reason='duplicate aggregate of separately included raw invocation receipts'))
                continue
            field = next((k for k in ('parent_cpu_seconds', 'cpu_seconds', 'cpu_s') if k in data), None)
            if field is None:
                continue  # CPU caps, status counts, bindings and setup manifests are not consumption.
            read(path)
            docs[rel(path)] = data
            physics = None
            detail = ''
            if path.name.startswith('bridge_round'):
                physics = data.get('physical_runs')
                detail = 'standalone bridge child process; counted separately from parent'
            elif 'mechanisms_' in str(path):
                physics = data.get('physical_runs_started')
                detail = 'complete mechanism denominator including replay continuations'
            elif path.name == 'results.json' and any(n.startswith('business_window_') for n in components):
                physics = int(data['physics_started']) if isinstance(data.get('physics_started'), bool) else None
                detail = 'one deployed fixed-window engine; total process CPU includes nested physics CPU'
            elif base_name in BASE_NAMES[:2]:
                # These standalone tests/audits construct data only, as verified in their sources.
                physics = data.get('physical_calls', data.get('physics_calls'))
            elif data.get('physical_simulations') == 0:
                physics = 0
            elif 'physical_continuations' in data:
                physics = data['physical_continuations']
                detail = 'plateau receipt: real checkpoint continuations counted; standalone routing queries are not physics'
            elif 'physical_replays' in data:
                physics = data['physical_replays']
                detail = 'independent physical continuation replays, included in this process CPU interval'
            elif 'physical_runs' in data:
                physics = data['physical_runs']
            elif 'physics_calls' in data:
                physics = data['physics_calls']
            elif 'physical_calls' in data:
                physics = data['physical_calls']
            if physics is None:
                unknown.append(dict(kind='uninstrumented_test_physical_run_count', receipt=rel(path),
                    explanation='Tests may construct/step/replay simulations; no exact counter. Never treat a business-batch count of zero as zero test physics.'))
            add(path, field, data[field], data, physics=physics, detail=detail)
            for nested in ('pytest_cpu_seconds', 'physics_cpu_seconds', 'continuation_cpu_seconds', 'query_cpu_seconds'):
                if nested in data and data[nested] > data[field] + 1e-9:
                    raise AssertionError('claimed nested CPU exceeds parent interval: ' + rel(path) + '#' + nested)
            for nested in ('pytest_cpu_seconds', 'physics_cpu_seconds', 'bridge_child_cpu_seconds',
                           'continuation_cpu_seconds', 'query_cpu_seconds'):
                if nested in data:
                    excluded.append(dict(receipt=rel(path), field=nested, value=data[nested], reason=
                        'child bridge raw receipts are separately counted; this aggregate is not additional' if nested == 'bridge_child_cpu_seconds'
                        else 'nested in the selected parent/process CPU interval'))
            if isinstance(data.get('scales'), list):
                scale_cpu = sum(child.get('cpu_seconds', 0) for child in data['scales'])
                if scale_cpu > data[field] + 1e-9:
                    raise AssertionError('same-process scale intervals exceed invocation total: ' + rel(path))
                for index, child in enumerate(data['scales']):
                    if 'cpu_seconds' in child:
                        excluded.append(dict(receipt=rel(path), field=f'scales[{index}].cpu_seconds',
                            value=child['cpu_seconds'], reason='nested in this same invocation total'))
            if isinstance(data.get('chunk_bridges'), list):
                nested_cpu = sum(child.get('cpu_seconds_nested', 0) for child in data['chunk_bridges'])
                if nested_cpu > data[field] + 1e-9:
                    raise AssertionError('continuation replay nested intervals exceed parent: ' + rel(path))
                for index, child in enumerate(data['chunk_bridges']):
                    if 'cpu_seconds_nested' in child:
                        excluded.append(dict(receipt=rel(path), field=f'chunk_bridges[{index}].cpu_seconds_nested',
                            value=child['cpu_seconds_nested'], reason='physical replay CPU already included in same process'))
            for key in ('unmetered_auxiliary', 'unknown_auxiliary'):
                if key in data:
                    unknown.append(dict(kind='receipt_declared_auxiliary', receipt=rel(path), details=data[key]))

    # Failed launch before the runner's try/finally had no CPU receipt.
    failure = EXPERIMENTS / BASE_NAMES[-1] / 'attempt_001/FAILURE.md'
    if failure.exists():
        read(failure)
        unknown.append(dict(kind='failed_launch_cpu_unknown', receipt=rel(failure), cpu_seconds=None,
            known_shell_wall_seconds=0.6914782, physical_runs=0,
            explanation='Missing test filename aborted binding capture before pytest or bridges. CPU was not recorded.'))
    else:
        pending.append(dict(kind='missing_failure_record', path=rel(failure)))

    # This directory also holds explicitly requested read-only domain work and
    # previous ledger builds. Their CPU is distinct from upstream invocations.
    for path in sorted(HERE.glob('*/resource.json')):
        data = json.loads(read(path))
        if 'cpu_seconds' in data:
            docs[rel(path)] = data
            add(path, 'cpu_seconds', data['cpu_seconds'], data,
                group='round9_resource_ledger_auxiliary', physics=data.get('physical_calls'),
                detail='independent static analysis in ledger-owned outputs; no simulation')
    for path in sorted(HERE.glob('*/ledger.json')):
        data = json.loads(read(path))
        add(path, 'ledger_build_cpu_seconds', data['ledger_build_cpu_seconds'], data,
            group='round9_resource_ledger_prior_builds', physics=0,
            detail='prior ledger construction interval only; its already-counted upstream CPU sum is excluded')
        excluded.append(dict(receipt=rel(path), field='known_invocation_cpu_seconds',
            value=data['known_invocation_cpu_seconds'], reason='prior duplicate ledger total; only that build CPU is additional'))

    # Audit bridge overlapping intervals against the raw child records.
    for path_key, data in docs.items():
        if 'bridge_child_cpu_seconds' not in data:
            continue
        parent = ROOT / path_key
        children = [parent.parent / name for name in ('bridge_round8_frozen.json', 'bridge_round9_current.json')]
        if any(rel(p) not in docs for p in children):
            pending.append(dict(kind='missing_bridge_child_receipt', parent=path_key))
            continue
        child_cpu = sum(docs[rel(p)]['cpu_seconds'] for p in children)
        child_physics = sum(docs[rel(p)]['physical_runs'] for p in children)
        if abs(child_cpu - data['bridge_child_cpu_seconds']) > 1e-9 or child_physics != data['bridge_physical_runs']:
            raise AssertionError('bridge parent/child discrepancy: ' + path_key)

    mechanisms = []
    first_expected = {'mechanisms_001': 60, 'mechanisms_002': 60, 'mechanisms_003': 6}
    mechanism_names = sorted(set(first_expected) | {p.name for p in (EXPERIMENTS / BASE_NAMES[3]).glob('mechanisms_*') if p.is_dir()})
    for name in mechanism_names:
        path = EXPERIMENTS / BASE_NAMES[3] / name / 'results.json'
        if rel(path) not in docs:
            pending.append(dict(kind='missing_mechanism_receipt', path=rel(path)))
            continue
        data = docs[rel(path)]
        protocol_path = path.parent / 'protocol.json'
        protocol = json.loads(read(protocol_path))
        expected = len(protocol['cases']) * len(protocol['modes']) * (1 + len(protocol['pause_ticks']))
        if name in first_expected and expected != first_expected[name]:
            raise AssertionError('original mechanism protocol denominator changed: ' + name)
        if data['physical_runs_started'] != expected or data['physical_runs_completed'] != expected:
            raise AssertionError('mechanism physical denominator mismatch: ' + name)
        mechanisms.append(dict(name=name, started=expected, completed=expected, status=status(data)))

    windows = []
    window_names = sorted(set(WINDOW_NAMES) | {p.name for p in (EXPERIMENTS / BASE_NAMES[3]).glob('business_window_*') if p.is_dir()})
    for name in window_names:
        base = EXPERIMENTS / BASE_NAMES[3] / name
        result, protocol_path = base / 'results.json', base / 'protocol.json'
        protocol = json.loads(read(protocol_path)) if protocol_path.exists() else None
        if rel(result) not in docs:
            pending.append(dict(kind='window_still_pending', path=rel(result),
                planned_cpu_cap=None if protocol is None else protocol['cpu_cap_seconds'],
                cap_is_not_measured_consumption=True))
            windows.append(dict(name=name, status='pending', measured_cpu_seconds=None))
        else:
            data = docs[rel(result)]
            scope_path = base / 'scope.json'
            scope = json.loads(read(scope_path)) if scope_path.exists() else {}
            windows.append(dict(name=name, status=status(data), physics_started=data.get('physics_started'),
                measured_cpu_seconds=data['cpu_seconds'], nested_physics_cpu_seconds=data.get('physics_cpu_seconds'),
                included_count=scope.get('included_count'), source_changed=data.get('source_changed'),
                outer_advance_chunk_ticks=1 if protocol is None else protocol.get('outer_advance_chunk_ticks', 1)))
    expected_test = EXPERIMENTS / BASE_NAMES[3] / 'test_001.json'
    if rel(expected_test) not in docs:
        pending.append(dict(kind='missing_root_initial_failed_test_receipt', path=rel(expected_test)))
    elif docs[rel(expected_test)].get('cpu_s') != 1.203125:
        raise AssertionError('root initial failed test CPU does not match original receipt')

    # Catch new attempts/full checks without resource receipts, rather than silently omitting them.
    review = EXPERIMENTS / BASE_NAMES[-1]
    for directory in sorted(review.iterdir()):
        if directory.is_dir() and (directory.name.startswith('attempt_') or 'fullcheck' in directory.name):
            if directory.name == 'attempt_001':
                continue
            candidates = list(directory.glob('*resource*.json')) + list(directory.glob('result.json'))
            if not candidates:
                pending.append(dict(kind='attempt_resource_pending', path=rel(directory)))

    ids = [(r['receipt'], r['field']) for r in rows]
    if len(ids) != len(set(ids)):
        raise AssertionError('duplicate resource row')
    subtotals = defaultdict(float)
    for row in rows:
        subtotals[row['group']] += row['cpu_seconds']
    known_physics = sum(r['physical_runs'] for r in rows if r['physical_runs'] is not None)
    unknown.extend([
        dict(kind='general_auxiliary_cpu_unknown', explanation='Reading, editing, messaging, py_compile, early file discovery/failed shell syntax and final writes were not fully metered.'),
        dict(kind='closure_auxiliary_cpu_unknown', receipt=rel(EXPERIMENTS / BASE_NAMES[-1] / 'closure.json'),
             explanation='Final source closure process CPU excludes child git CPU and final hash-seal writes, which were not separately metered.'),
        dict(kind='lifecycle_test_physics_unknown', receipt=rel(EXPERIMENTS / BASE_NAMES[3] / 'TEST_FAILURES.md'),
             explanation='test_001 had seven setup failures with zero new lifecycle physics, but its 48 passing independent tests did run uncounted physics.'),
        dict(kind='no_global_wall_sum', explanation='Processes overlap. Report each wall interval only; summing walls is not elapsed time or CPU.'),
    ])
    for path_key, before_hash in bindings.items():
        if sha256((ROOT / path_key).read_bytes()).hexdigest() != before_hash:
            changed.append(path_key)
    if changed:
        pending.append(dict(kind='receipt_changed_during_ledger_read', paths=changed))
    known_cpu = sum(r['cpu_seconds'] for r in rows)
    ledger_cpu, ledger_wall = process_time() - started_cpu, perf_counter() - started_wall
    record = dict(schema='ics_round9_resource_ledger_v1', status='final' if args.final and not pending else 'provisional',
        final_requested=args.final, known_invocation_cpu_seconds=known_cpu, group_subtotals=dict(subtotals),
        resource_rows=rows, nested_or_duplicate_values_not_added=excluded,
        mechanism_physical_runs=sum(x['started'] for x in mechanisms), mechanisms=mechanisms,
        bridge_physical_runs=sum(r['physical_runs'] or 0 for r in rows if 'bridge_round' in r['receipt']),
        plateau_standalone_queries=sum(d.get('standalone_queries', 0) for path, d in docs.items()
                                      if 'plateau' in path),
        plateau_physical_continuations=sum(d.get('physical_continuations', 0) for path, d in docs.items()
                                           if 'plateau' in path),
        full_regression_receipts=[dict(receipt=path, outcomes=data['test_outcomes'],
            source_changed=data.get('source_changed'), parent_cpu_seconds=data.get('parent_cpu_seconds'),
            bridge_child_cpu_seconds=data.get('bridge_child_cpu_seconds'))
            for path, data in docs.items() if data.get('test_outcomes', {}).get('passed', 0) >= 1000],
        known_explicit_physical_runs=known_physics, exact_total_physical_runs=None,
        exact_total_cpu_seconds=None, windows=windows,
        unknown_entries=unknown, pending_entries=pending, pending_count=len(pending),
        ledger_build_cpu_seconds=ledger_cpu, ledger_build_wall_seconds=ledger_wall,
        ledger_scope='current process after imports; ledger CPU separate from upstream measured sum; final write excluded',
        input_sha256=bindings, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'ledger.json').write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = [f'# Round9 resource ledger — {record["status"]}', '',
        f'已记录、不重复计入的上游 CPU：**{known_cpu:.6f} 秒**；这是已知区间之和，不是含全部辅助工作的精确总量。',
        f'本次账本自身 CPU：{ledger_cpu:.6f} 秒，另列。待完成记录：{len(pending)} 项。', '',
        '| 工作目录 | 已知 CPU 秒 |', '|---|---:|']
    lines += [f'| {k} | {v:.6f} |' for k, v in sorted(subtotals.items())]
    lines += ['', f'明确计数的机制试验 {record["mechanism_physical_runs"]} 次，直接桥接 {record["bridge_physical_runs"]} 次。',
        f'全部明确计数的 physical runs 当前为 {known_physics}；测试内部物理运行次数未知，不能把它当作精确总分母。', '',
        'parent CPU 已包含同进程 pytest；physics/scales 子区间和汇总字段均不重复相加。bridge child 单独计入。',
        '窗口 001 的每 tick result 采集、002 的 chunk60 采集及003修复后部署均保留；chunk60仍逐 tick 物理推进。CPU cap 不是实际已用 CPU；预算删失不是物理不可行。', '',
        '| 窗口部署 | 状态 | 已知总 CPU 秒 |', '|---|---|---:|']
    lines += [f'| {w["name"]} | {w["status"]} | {w["measured_cpu_seconds"]} |' for w in windows]
    lines += ['', '| 全回归原件 | 通过 | 失败/错误/跳过 | parent CPU 秒 |', '|---|---:|---|---:|']
    lines += [f'| {r["receipt"]} | {r["outcomes"]["passed"]} | '
              f'{r["outcomes"].get("failed")}/{r["outcomes"].get("errors")}/{r["outcomes"].get("skipped")} | '
              f'{r["parent_cpu_seconds"]} |' for r in record['full_regression_receipts']]
    lines += ['', '未知辅助、失败、每项输入 SHA、重复排除依据和未完成列表均在 ledger.json；未计量不填 0。',
        '没有把并发 wall 相加成总历时，没有把同源重试或增密当作独立运行日。']
    (out / 'LEDGER.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps({'outputs': {p.name: sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir() if p.name != 'manifest.json'}, 'ledger_script_sha256': record['source_sha256']}, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('status', 'known_invocation_cpu_seconds', 'known_explicit_physical_runs',
        'pending_count', 'ledger_build_cpu_seconds')}, indent=2))
    if args.final and pending:
        raise SystemExit('Final closure rejected: required receipts remain pending; provisional evidence retained.')


if __name__ == '__main__':
    main()
