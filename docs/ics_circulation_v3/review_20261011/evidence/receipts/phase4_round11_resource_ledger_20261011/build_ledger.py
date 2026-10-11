"""Reconcile Round11 metered intervals; retain unknowns and pending windows."""
from collections import defaultdict
from hashlib import sha256
import argparse
import json
import math
from pathlib import Path
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'pyproject.toml').exists())
BASES = tuple(HERE.parent / ('phase4_round11_' + name + '_20261011') for name in
              ('headway_design', 'independent_review', 'projection_runtime', 'projection_query_diagnosis',
               'storage_terminal_screen', 'validation'))
SKIP = {'source_snapshot', 'test_snapshot', 'round9_frozen', 'round10_frozen', 'pytest_tmp', 'fixtures', '__pycache__'}
EXPECTED_WINDOWS = ('original_h80_001', 'original_h21600_001', 'projected_h80_001', 'projected_h21600_001')
OLD_DIAGNOSIS_COPY = 'outputs/experiments/ics_circulation_v3/phase4_round11_storage_terminal_screen_20261011/comparison_001/old_result.json'
OLD_DIAGNOSIS_ORIGINAL = 'outputs/experiments/ics_circulation_v3/phase4_round11_projection_query_diagnosis_20261011/diagnosis_002/result.json'
COPY_BINDING_RECEIPT = 'outputs/experiments/ics_circulation_v3/phase4_round11_storage_terminal_screen_20261011/comparison_001/result.json'
SUPERSEDED_BUILDS = {'final_001': 'Scanner counted explicitly copied diagnosis_002 old_result.json a second time; CPU overcount 1.265625 and query-entry overcount 4. Its own measured build CPU remains counted.'}


def relative(path):
    return path.relative_to(ROOT).as_posix()


def status(data):
    if 'status' in data:
        return data['status']
    for key in ('pytest_exit', 'exit_code', 'pytest_exit_code'):
        if key in data:
            return 'passed' if data[key] == 0 else 'failed'
    return 'receipt_without_explicit_status'


def numeric(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid nonnegative resource: ' + label)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-name', required=True)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    if args.run_name in ('', '.', '..') or '/' in args.run_name or '\\' in args.run_name:
        raise ValueError('one new run-name component required')
    out = HERE / args.run_name
    out.mkdir()
    cpu, wall = process_time(), perf_counter()
    bindings, docs, rows, excluded, unknown, pending = {}, {}, [], [], [], []
    def read(path):
        raw = path.read_bytes()
        bindings[relative(path)] = sha256(raw).hexdigest()
        return raw
    for base in BASES:
        if not base.exists():
            pending.append(dict(kind='missing_base', path=relative(base)))
            continue
        for path in sorted(base.rglob('*.json')):
            if any(part in SKIP or part.startswith('test_') for part in path.relative_to(base).parts[:-1]):
                continue
            try:
                data = json.loads(path.read_bytes())
            except (ValueError, OSError) as error:
                pending.append(dict(kind='unreadable_json', path=relative(path), error=str(error)))
                continue
            if not isinstance(data, dict):
                continue
            field = next((key for key in ('parent_cpu_seconds', 'cpu_seconds', 'cpu_s') if key in data), None)
            if field is None:
                continue  # Planned CPU/wall caps and source hashes are not consumption.
            read(path)
            docs[relative(path)] = (path, data, field, base)

    for key, (path, data, field, base) in docs.items():
        if key == OLD_DIAGNOSIS_COPY:
            # Only this explicitly documented cross-directory copy is an
            # alias. Equal hashes alone do NOT identify independent invocations.
            original = docs.get(OLD_DIAGNOSIS_ORIGINAL)
            comparator = docs.get(COPY_BINDING_RECEIPT)
            if original is None or comparator is None or data != original[1]:
                raise AssertionError('unproven explicit diagnosis receipt copy')
            digest = bindings[key]
            if digest != bindings[OLD_DIAGNOSIS_ORIGINAL] or digest != comparator[1].get('baseline_result_sha256'):
                raise AssertionError('diagnosis copy lacks original bytes and comparison binding')
            for copied_field in (field, 'standalone_routing_queries', 'physical_runs'):
                excluded.append(dict(receipt=key, field=copied_field, value=data[copied_field],
                    reason='Explicit copy of original diagnosis_002 receipt, proven by byte SHA and comparison baseline_result_sha256; not another invocation.',
                    original_receipt=OLD_DIAGNOSIS_ORIGINAL, binding_receipt=COPY_BINDING_RECEIPT,
                    exact_copy_sha256=digest))
            continue
        if path.name == 'query.json':
            # Baseline query records duplicate intervals already inside baseline/result.json.
            parent = path.parent.parent / 'result.json'
            parent_row = docs.get(relative(parent))
            matches = [] if parent_row is None else [r for r in parent_row[1].get('queries', []) if r.get('name') == path.parent.name]
            if len(matches) != 1 or matches[0] != data:
                pending.append(dict(kind='unproven_query_interval_parent', path=key, expected_parent=relative(parent)))
            excluded.append(dict(receipt=key, field=field, value=data[field],
                reason='raw duplicate of baseline queries[] interval, already inside baseline process CPU'))
            continue
        physics = None
        for counter in ('physical_runs_started', 'physical_runs', 'physics_calls', 'physical_calls',
                        'physical_continuations', 'physical_replays'):
            if counter in data:
                physics = data[counter]
                break
        if physics is None and 'physics_started' in data:
            physics = int(data['physics_started']) if isinstance(data['physics_started'], bool) else None
        if physics is not None:
            numeric(physics, key + '#physical counter')
            if type(physics) is not int:
                raise ValueError('physical counter must be an integer')
        if physics is None:
            unknown.append(dict(kind='physical_run_count_unknown', receipt=key,
                explanation='No complete physical counter. Zero business batches is not zero test physics.'))
        if 'pytest_exit' in data and data.get('physical_calls') != 0 and data.get('exact_total_test_physical_runs') is None:
            unknown.append(dict(kind='additional_test_physics_unknown', receipt=key,
                explanation=data.get('physical_count_scope', 'Only explicit instrumented calls may be counted; other test-internal physics are not established.')))
        change = data.get('source_changed')
        if change is None and 'source_sha256_before' in data and 'source_sha256_after' in data:
            before, after = data['source_sha256_before'], data['source_sha256_after']
            change = [name for name in set(before) | set(after) if before.get(name) != after.get(name)]
        if data[field] is None:
            unknown.append(dict(kind='receipt_cpu_unknown', receipt=key,
                explanation='Failed or unmetered invocation explicitly reports null CPU; retained without replacing it with zero.'))
        rows.append(dict(receipt=key, field=field, cpu_seconds=None if data[field] is None else numeric(data[field], key),
            wall_seconds=data.get('parent_wall_seconds', data.get('wall_seconds', data.get('wall_s'))),
            group=base.name, status=status(data), physical_runs=physics,
            source_changed=change, standalone_queries=data.get('standalone_queries', data.get('standalone_routing_queries')),
            standalone_query_scope=data.get('query_count_scope', data.get('scope')),
            prototype_checks=data.get('checks') if base.name.startswith('phase4_round11_headway_design') else None,
            prototype_oracle_cases=data.get('oracle_cases') if base.name.startswith('phase4_round11_headway_design') else None,
            scope=data.get('scope', data.get('resource_scope', data.get('cpu_scope', 'explicit receipt interval')))))
        for name in ('pytest_cpu_seconds', 'physics_cpu_seconds', 'continuation_cpu_seconds', 'query_cpu_seconds'):
            if name in data:
                if data[field] is None or numeric(data[name], key+'#'+name) > data[field] + 1e-9:
                    raise AssertionError('same-process interval exceeds parent: ' + key + '#' + name)
                excluded.append(dict(receipt=key, field=name, value=data[name], reason='included in same process parent CPU'))
        for name in ('bridge_child_cpu_seconds', 'main_receipt_cpu_seconds', 'known_previous_audit_cpu_seconds',
                     'known_previous_cpu_seconds', 'run_parent_cpu_seconds_reference', 'run_physics_cpu_seconds_reference'):
            if name in data:
                excluded.append(dict(receipt=key, field=name, value=data[name],
                    reason='upstream aggregate/reference already covered by selected process receipts, not additional CPU'))
        for collection, names in (('queries', ('cpu_seconds',)), ('rows', ('query_cpu_seconds',)),
                                  ('scales', ('cpu_seconds_nested', 'cpu_seconds'))):
            child_sum = 0
            for i, child in enumerate(data.get(collection, [])):
                for name in names:
                    if name in child:
                        child_sum += numeric(child[name], key+'#'+name)
                        excluded.append(dict(receipt=key, field=f'{collection}[{i}].{name}', value=child[name],
                            reason='nested interval already included in this process CPU'))
            if child_sum and (data[field] is None or child_sum > data[field] + 1e-9):
                raise AssertionError('same-process child sum exceeds parent: ' + key + '#' + collection)
        for i, child in enumerate(data.get('rows', [])):
            for sub, name in (('terminal_certificate_shadow', 'screen_cpu_seconds'),
                              ('instrumented_replay', 'query_cpu_seconds')):
                if name in child.get(sub, {}):
                    value = numeric(child[sub][name], key + '#' + sub)
                    if data[field] is None or value > data[field] + 1e-9:
                        raise AssertionError('nested shadow interval exceeds parent: ' + key)
                    excluded.append(dict(receipt=key, field=f'rows[{i}].{sub}.{name}', value=value,
                        reason='shadow query/screen interval is already included in same process parent CPU'))
        # Screen/observer accounting can occur both as an aggregate and inside
        # raw per-query rows. Neither copy is additional to process CPU.
        seen_excluded = {r['field'] for r in excluded if r['receipt'] == key}
        def screen_intervals(node, prefix=''):
            if isinstance(node, dict):
                for name, value in node.items():
                    label = prefix + '.' + name if prefix else name
                    if name in ('screen_cpu_seconds', 'observation_cpu_seconds',
                                'screen_cpu_seconds_nested', 'observation_cpu_seconds_nested'):
                        numeric(value, key + '#' + label)
                        if label not in seen_excluded:
                            excluded.append(dict(receipt=key, field=label, value=value,
                                reason='screen/observer aggregate or raw nested interval already inside process CPU; no extra addition'))
                    else:
                        screen_intervals(value, label)
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    screen_intervals(value, f'{prefix}[{i}]')
        screen_intervals(data)
        receipt_collection = data.get('receipts', [])
        receipt_items = receipt_collection.items() if isinstance(receipt_collection, dict) else enumerate(receipt_collection)
        for i, child in receipt_items:
            if 'cpu_seconds' in child:
                excluded.append(dict(receipt=key, field=f'receipts[{i}].cpu_seconds', value=child['cpu_seconds'],
                    reason='copied upstream receipt, not work performed by the binding audit'))
        for name in ('unmetered_auxiliary', 'unknown_auxiliary'):
            if name in data:
                unknown.append(dict(kind='receipt_declared_auxiliary', receipt=key, details=data[name]))

    # Child Python bridge CPU is not part of process_time() in the pytest parent.
    for key, (path, data, field, base) in docs.items():
        if 'bridge_child_cpu_seconds' not in data:
            continue
        children = [item[1] for item in docs.values() if item[0].parent == path.parent and item[0].name.startswith('bridge_round')]
        if not children:
            pending.append(dict(kind='bridge_children_pending', receipt=key))
            continue
        if sum(c['cpu_seconds'] for c in children) != data['bridge_child_cpu_seconds'] or sum(c['physical_runs'] for c in children) != data['bridge_physical_runs']:
            raise AssertionError('bridge parent/child counter mismatch: ' + key)

    mechanisms = []
    for base in BASES:
        for directory in sorted(base.glob('mechanisms_*')):
            if not directory.is_dir():
                continue
            protocol = json.loads(read(directory / 'protocol.json'))
            expected = len(protocol['cases']) * len(protocol['modes']) * (1 + len(protocol['pause_ticks']))
            item = docs.get(relative(directory / 'results.json'))
            if item is None:
                pending.append(dict(kind='mechanisms_pending', path=relative(directory)))
            elif item[1]['physical_runs_started'] != expected or item[1]['physical_runs_completed'] != expected:
                raise AssertionError('complete mechanism denominator mismatch: ' + relative(directory))
            else:
                mechanisms.append(dict(path=relative(directory), physical_runs=expected))

    windows = []
    validation = BASES[-1]
    names = set(EXPECTED_WINDOWS)
    for directory in validation.iterdir():
        protocol_path = directory / 'protocol.json'
        if directory.is_dir() and protocol_path.is_file():
            candidate_protocol = json.loads(read(protocol_path))
            if any(key in candidate_protocol for key in ('cpu_cap_seconds', 'additional_cpu_cap_seconds')):
                names.add(directory.name)
    names = sorted(names)
    for name in names:
        directory = validation / name
        protocol_path = directory / 'protocol.json'
        protocol = json.loads(read(protocol_path)) if protocol_path.exists() else None
        item = docs.get(relative(directory / 'results.json'))
        continuation = protocol is not None and 'original_run' in protocol
        budget = None if protocol is None else protocol.get('cpu_cap_seconds', protocol.get('additional_cpu_cap_seconds'))
        context = dict(kind='checkpoint_continuation_additional_budget' if continuation else 'original_fixed_budget_deployment',
            original_run=None if not continuation else protocol['original_run'],
            original_stop=None if not continuation else protocol.get('original_stop'),
            checkpoint_tick=None if not continuation else protocol.get('checkpoint_tick'),
            declared_cpu_cap=budget, cap_is_not_consumption=True,
            input_variant=None if protocol is None else protocol.get('only_variant'),
            screen_enabled=None if protocol is None else protocol.get('screen_enabled', False),
            screen_budget_contract=None if protocol is None else protocol.get('screen_budget_contract'))
        if item is None:
            pending.append(dict(kind='window_pending', path=relative(directory / 'results.json')))
            windows.append(dict(name=name, status='pending', measured_cpu_seconds=None, **context))
        else:
            data = item[1]
            scope_path = directory / 'scope.json'
            scope = json.loads(read(scope_path)) if scope_path.exists() else {}
            windows.append(dict(name=name, status=status(data), measured_cpu_seconds=data['cpu_seconds'],
                nested_physics_cpu_seconds=data.get('physics_cpu_seconds'), source_changed=data.get('source_changed'),
                nested_screen_accounting=data.get('screen_accounting'),
                complete_window_business_count=scope.get('included_count'), physics_started=data.get('physics_started'), **context))

    prefixes = ('attempt_', 'authoring_', 'comparison_', 'baseline_', 'full_audit_', 'author_tests_',
                'cache_bridge_', 'projection_independent_', 'source_closeout_', 'mechanism_review_',
                'projection_boundary_', 'window_review_', 'window_audit_', 'window_diagnosis_', 'tail_review_',
                'full_adapter_', 'prototype_', 'headway_review_', 'closure_', 'source_closure_', 'projection_review_',
                'clock_probe_', 'source_capture_', 'diagnosis_', 'shadow_', 'run_', 'backlog_analysis_',
                'screen_window_review_', 'certificate_review_')
    for base in BASES:
        for directory in base.iterdir():
            if directory.is_dir() and directory.name.startswith(prefixes):
                if not any(item[0].parent == directory for item in docs.values()):
                    pending.append(dict(kind='attempt_receipt_pending', path=relative(directory)))
    for path in sorted(HERE.glob('*/ledger.json')):
        data = json.loads(read(path))
        rows.append(dict(receipt=relative(path), field='ledger_build_cpu_seconds',
            cpu_seconds=data['ledger_build_cpu_seconds'], wall_seconds=data['ledger_build_wall_seconds'],
            group='prior_round11_ledger_builds', status='superseded_duplicate_reference_failure' if path.parent.name in SUPERSEDED_BUILDS else data['status'], physical_runs=0, source_changed=None,
            standalone_queries=0, scope='Prior ledger construction interval only; its upstream sum is excluded.'))
        excluded.append(dict(receipt=relative(path), field='known_invocation_cpu_seconds',
            value=data['known_invocation_cpu_seconds'], reason='duplicate prior ledger total'))
    ids = [(r['receipt'], r['field']) for r in rows]
    if len(ids) != len(set(ids)):
        raise AssertionError('duplicate selected interval')
    subtotals = defaultdict(float)
    for row in rows:
        if row['cpu_seconds'] is not None:
            subtotals[row['group']] += row['cpu_seconds']
    changed = [name for name, digest in bindings.items() if sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    if changed:
        pending.append(dict(kind='receipt_changed_while_read', paths=changed))
    unknown.append(dict(kind='general_auxiliary_cpu_unknown',
        explanation='Reading, editing, communication, discovery failures, py_compile/imports, final documentation/Git/SHA inspection and final writes were not fully metered. Do not fill missing CPU with zero.'))
    unknown.append(dict(kind='concurrent_wall_not_summed', explanation='Wall intervals overlap and are not an additive total.'))
    record = dict(schema='ics_round11_resource_ledger_v1', status='final' if args.final and not pending else 'provisional',
        known_invocation_cpu_seconds=sum(r['cpu_seconds'] for r in rows if r['cpu_seconds'] is not None), group_subtotals=dict(subtotals),
        known_explicit_physical_runs=sum(r['physical_runs'] for r in rows if r['physical_runs'] is not None),
        exact_total_cpu_seconds=None, exact_total_physical_runs=None,
        known_standalone_queries=sum(r['standalone_queries'] for r in rows if r['standalone_queries'] is not None),
        standalone_query_qualification='Reported standalone query entry calls/attempts only; authoring instrumentation can include intentionally invalid calls. Nested delegate entries are not additional queries. See each receipt scope; this is not a count of successful routes.',
        bridge_physical_runs=sum(r['physical_runs'] or 0 for r in rows if Path(r['receipt']).name.startswith('bridge_round')),
        mechanism_physical_runs=sum(m['physical_runs'] for m in mechanisms), mechanisms=mechanisms,
        headway_prototypes=[dict(receipt=r['receipt'], checks=r['prototype_checks'], oracle_cases=r['prototype_oracle_cases'],
            physical_runs=r['physical_runs'], qualification='Ledger prototype/oracle checks only; not an integrated business-physics deployment.')
            for r in rows if r.get('prototype_checks') is not None],
        resource_rows=rows, nested_or_duplicate_values_not_added=excluded,
        superseded_ledger_builds=SUPERSEDED_BUILDS,
        windows=windows, pending_entries=pending, pending_count=len(pending), unknown_entries=unknown,
        full_regressions=[dict(receipt=key, outcomes=data['test_outcomes'], source_changed=data.get('source_changed'),
            cpu_seconds=data[field], bridge_child_cpu_seconds=data.get('bridge_child_cpu_seconds'))
            for key, (path, data, field, base) in docs.items() if data.get('test_outcomes', {}).get('passed', 0) >= 1000],
        ledger_build_cpu_seconds=process_time()-cpu, ledger_build_wall_seconds=perf_counter()-wall,
        ledger_scope='Current process after imports; final output writes excluded; separate from upstream sum.',
        input_sha256=bindings, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'ledger.json').write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    (out / 'build_ledger.py').write_bytes(Path(__file__).read_bytes())
    lines = [f'# Round11 resource ledger — {record["status"]}', '',
        f'已知、去重后的上游 CPU **{record["known_invocation_cpu_seconds"]:.6f} 秒**；本次账本构建 CPU {record["ledger_build_cpu_seconds"]:.6f} 秒另列。',
        f'待封存项：{len(pending)}。全部工作的精确 CPU 与精确物理运行总数均未知。', '',
        '| 目录 | 已知 CPU 秒 |', '|---|---:|']
    lines += [f'| {name} | {value:.6f} |' for name, value in sorted(subtotals.items())]
    lines += ['', f'明确计数的物理运行 {record["known_explicit_physical_runs"]} 次，包含机制 {record["mechanism_physical_runs"]}、独立桥 {record["bridge_physical_runs"]}。测试内未仪表化物理次数继续未知。',
        f'显式报告的独立 query 入口调用/attempt {record["known_standalone_queries"]} 次；作者测试可包含故意非法调用，按各行 scope 解读，不是成功路线数，不等同物理运行。', '',
        '| 窗口 | 状态 | 实测 CPU 秒 |', '|---|---|---:|']
    lines += [f'| {w["name"]} | {w["status"]} | {w["measured_cpu_seconds"]} |' for w in windows]
    lines += ['', '父进程CPU包括同进程pytest/physics/query/scale；这些区间不重复加入。单独bridge child按原始receipt另计。CPU cap不是消耗；预算删失不是物理不可行。',
        'final_001 因重复收录 comparison_001/old_result.json 复本作废并保留；仅以原 diagnosis 路径、字节 SHA 和 comparison 的 baseline_result_sha256 共同证明该别名。不是按相同 SHA 泛化去重；final_001 自身构建 CPU 仍计入。',
        '头距 ledger 原型和枚举 oracle 的检查数单列，不是完整业务物理运行，也没有接入本轮四格窗口。显式 null CPU 的启动失败保留为未知。',
        '若有tail续跑，其额外预算、原停止点和checkpoint单列；不能把新增预算当成原固定预算的算法比较，也不能把重复前缀合并成新的独立数据。',
        '失败尝试、逐项SHA、重复排除依据、未知辅助和待封存项见ledger.json。不能将并发wall相加。']
    (out / 'LEDGER.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps({p.name:sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir() if p.name != 'manifest.json'}, indent=2), encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('status','known_invocation_cpu_seconds','known_explicit_physical_runs',
        'pending_count','ledger_build_cpu_seconds')}, indent=2))
    if args.final and pending:
        raise SystemExit('Final closure rejected; provisional evidence retained.')


if __name__ == '__main__':
    main()
