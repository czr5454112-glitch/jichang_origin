"""Read only round-six resources. No simulator imports or physical replays.

Final output must be fresh. Use --require-file for final audit/analysis/plot
artifacts confirmed by their owners. Numeric CPU is always a measured interval,
therefore a lower bound for entire process/round CPU, never a complete total.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'outputs/experiments/ics_circulation_v3'
HERE = Path(__file__).resolve().parent
INITIAL = BASE / 'phase4_w3_same_zone_supply_20261010'
REPAIRED = BASE / 'phase4_w3_same_zone_supply_repaired_20261010'
REVIEW = BASE / 'phase4_w3_round6_independent_review_20261010'
MECHANISMS = BASE / 'phase4_w3_same_zone_supply_mechanisms_20261010'


def collect(output, required):
    cpu0, wall0 = process_time(), perf_counter()
    if output.exists():
        raise FileExistsError(output)
    for name in required:
        if not (BASE / name).is_file():
            raise FileNotFoundError('Required final artifact: ' + name)
    rows, checks, bound = [], [], {}

    def read(path):
        data = path.read_bytes()
        key = str(path.relative_to(ROOT))
        digest = sha256(data).hexdigest()
        if key in bound and bound[key] != digest:
            raise ValueError('Changed during read: ' + key)
        bound[key] = digest
        return json.loads(data.decode('utf-8-sig'))

    def component(scope, cpu, field, note=''):
        return {'scope': scope, 'cpu_seconds': cpu,
                'quality': 'measured_interval_lower_bound' if cpu is not None else 'unknown',
                'source_field': field, 'note': note}

    def add(identity, path, components, *, wall=None, status='complete', counts=None, notes=()):
        if any(r['id'] == identity for r in rows):
            raise ValueError('Duplicate invocation identity: ' + identity)
        row = {'id': identity, 'source': str(path.relative_to(ROOT)) if path else None,
               'status': status, 'cpu_components': components,
               'wall_seconds_individual_scope': wall, 'counts': counts or {}, 'notes': list(notes)}
        rows.append(row)
        return row

    for label, directory in [('initial', INITIAL), ('repaired', REPAIRED)]:
        p = directory / 'protocol.json'
        s = read(p)
        add('prepare_' + label, p,
            [component('prepare function', s['preparation_cpu_seconds'], 'preparation_cpu_seconds',
                       'Includes binding, snapshots and workload construction inside the clock; interpreter bootstrap/final serialization excluded.')],
            wall=s['preparation_wall_seconds'], counts={'new_preparation_invocations': 1},
            notes=['Two preparations actually executed; copied source snapshots are artifacts, not extra simulation runs.'])

    stages = [('initial_mechanism6', INITIAL, 'mechanism', 6),
              ('repaired_mechanism6', REPAIRED, 'mechanism', 6),
              ('nominal_pilot9', REPAIRED, 'nominal_pilot', 9),
              ('formal81', REPAIRED, 'full', 81)]
    for identity, directory, stage, count in stages:
        p = directory / stage / 'summary.json'
        if not p.exists():
            add(identity, p, [component('worker and parent', None, 'not completed')],
                status='pending', counts={'planned_cases': count})
            continue
        s = read(p)
        invocations = s['case_invocation_cpu_seconds_recorded']
        checks.append({'kind': 'worker_cpu_sum', 'id': identity,
                       'okay': abs(invocations-sum(r.get('invocation_cpu_seconds') or 0 for r in s['rows'])) < 1e-8})
        checks.append({'kind': 'complete_case_denominator', 'id': identity,
                       'okay': len(s['rows']) == s['planned_cases'] == count})
        counts = {k: s[k] for k in ('planned_cases', 'status_counts', 'actual_physical_calls_recorded',
                  'unknown_physical_call_statuses', 'unknown_resource_cases', 'complete_resource_accounting')}
        counts.update(search_calls=sum(r.get('search_calls', 0) for r in s['rows']),
                      search_work=sum(r.get('search_work', 0) for r in s['rows']))
        r = add(identity, p,
                [component('worker invocation intervals', invocations, 'case_invocation_cpu_seconds_recorded',
                           'Setup, cycle, trace and raw serialization included; cycle CPU is nested and excluded from addition.'),
                 component('coordinator interval', s['parent_cpu_seconds'], 'parent_cpu_seconds')],
                wall=s['wall_makespan_seconds'], counts=counts,
                notes=['All stages are separately executed. Formal nominal identities rerun pilot cases; no reuse discount.',
                       'complete_resource_accounting describes recorded invocation intervals, not process bootstrap or all development CPU.'])
        r['nested_cycle_cpu_seconds_not_added'] = sum(x.get('cycle_cpu_seconds_nested', 0) for x in s['rows'])
        r['worker_lifetime_peak_memory_not_additive'] = {
            key: max((x.get('memory', {}).get(key, 0) or 0 for x in s['rows']), default=0)
            for key in ('peak_working_set_bytes', 'peak_commit_bytes')}
        if identity == 'initial_mechanism6':
            r['notes'].append('Two old32 replication flags failed only because Python cache tuple vs persisted JSON list; raw physical results retained and all six rerun after comparator-only repair.')

    # Explicit author validation/freeze invocations; snapshot copies are not runs.
    author = BASE / 'phase4_w3_round6_same_zone_authoring_20261010'
    for name in ('authoring_initial.json', 'authoring_path_repaired.json', 'freeze.json'):
        p = author / name; s = read(p)
        add('author_' + name, p, [component('author host interval', s['cpu_seconds'], 'cpu_seconds',
            s.get('resource_scope', s.get('scope', 'Measured interval, output serialization excluded.')))],
            wall=s['wall_seconds'], status='failed_test_collection' if s.get('exit_code', 0) else 'complete',
            counts={k: s[k] for k in ('exit_code', 'author_tests_passed') if k in s},
            notes=['Initial import-path collection failure and repaired 23-test invocation are distinct.',
                   'Zero process_time increment means timer resolution, not a proof of no work.'])

    p = REVIEW / 'guard_initial_validation.json'; s = read(p)
    add('review_initial9', p,
        [component('parent', s['parent_cpu_seconds'], 'parent_cpu_seconds'),
         component('pytest child', s['child_cpu_seconds'], 'child_cpu_seconds')],
        wall=s['wall_seconds'], counts={'passed': 9})
    for name in ('controller_initial_validation.json', 'independent_focused_validation.json',
                 'independent_focused_repaired_validation.json', 'full_validation/result.json'):
        p = REVIEW / name; s = read(p)
        r = add('review_tests_' + name, p, [component('pytest host interval', s['cpu_seconds'], 'cpu_seconds',
            s.get('resource_scope', 'Measured host interval; process bootstrap and output not asserted complete.'))],
            wall=s['wall_seconds'], status='failed_test_fixture' if s.get('exit_code') else 'complete',
            counts={k: s[k] for k in ('exit_code', 'tests', 'failures', 'counts') if k in s})
        if 'test_cpu_seconds' in s:
            r['nested_test_cpu_seconds_not_added'] = s['test_cpu_seconds']
            r['notes'].append('777-test suite predates comparator repair. Later 11 affected tests are separate; this is not a 779-test full-suite claim.')

    p = BASE / 'phase4_w3_same_zone_supply_repair_validation_20261010/validation.json'; s = read(p)
    for i, attempt in enumerate(s['attempts']):
        add('repair_test_attempt_' + str(i+1), p,
            [component('pytest child', attempt['child_cpu_seconds'], f'attempts[{i}].child_cpu_seconds')],
            wall=attempt['tool_wall_seconds'], status='failed_test_fixture' if attempt['exit_code'] else 'complete',
            counts={k: attempt[k] for k in ('passed', 'setup_errors', 'exit_code')},
            notes=[attempt.get('cause', 'Workspace basetemp repair; all 11 affected tests pass.'),
                   'Wall is tool wall only. CPU remains unknown; not inferred from duration.'])
    p = HERE / 'auxiliary_invocations.json'; s = read(p)
    for i, invocation in enumerate(s['runner_helper_tests']):
        add('early_helper6_' + str(i+1), p, [component('pytest child', None, f'runner_helper_tests[{i}].cpu_seconds')],
            wall=invocation['tool_wall_seconds'], counts={'passed': invocation['tests_passed']},
            notes=['Author disclosure; no saved process CPU, tool wall only.'])
    add('unmetered_auxiliary', p, [component('development, inspection, docs and subprocess/bootstrap gaps', None, 'unmetered_auxiliary')],
        notes=s['unmetered_auxiliary'])
    p = REVIEW / 'final_comparison_wait_failure.json'
    if p.exists():
        s = read(p)
        add('review_final_comparison_premature', p,
            [component('failed pure-file comparison child', None, 'cpu_seconds=null')],
            wall=s['tool_wall_seconds'], status='failed_analysis_missing_file',
            counts={'new_physical_simulations': s['new_physical_simulations']},
            notes=[s['cause'], 'Tool wall only; no child CPU measurement. Later comparison is a separate invocation.'])

    # Restrict discovery to this round. In particular the round5 same_zone_supply_analysis
    # design diagnostic is deliberately excluded even though its name sounds relevant.
    analyses = set()
    for directory in BASE.glob('phase4_w3_round6_*_20261010'):
        if directory in (HERE, REVIEW, author):
            continue
        # An analysis and its manifest are one invocation; prefer its primary
        # result. Plot-only folders instead expose their direct clock in manifest.
        primary = directory / 'analysis.json'
        fallback = directory / 'manifest.json'
        if primary.is_file():
            analyses.add(primary)
        elif fallback.is_file():
            analyses.add(fallback)
        if 'visual' in directory.name or 'plot' in directory.name:
            analyses.update(directory.glob('*/manifest.json'))
            if (directory / 'metadata.json').is_file():
                analyses.add(directory / 'metadata.json')
    analyses.update(REVIEW.glob('*audit*.json'))
    analyses.update(REVIEW.glob('*comparison*.json'))
    analyses.update(REVIEW.glob('*overlap*.json'))
    analyses.update(MECHANISMS.glob('*/analysis.json'))
    for name in ('initial_repaired_consistency.json', 'chain_evidence.json', 'formal_chain_evidence.json', 'formal_tradeoffs.json', 'service_regressions.json'):
        if (MECHANISMS / name).exists():
            analyses.add(MECHANISMS / name)
    analyses.add(BASE / 'phase4_w3_same_zone_supply_repair_diagnostic_20261010/diagnosis.json')
    for name in required:
        path = BASE / name
        if not any(r['source'] == str(path.relative_to(ROOT)) for r in rows):
            analyses.add(path)
    for p in sorted(analyses):
        s = read(p)
        ck = next((k for k in ('analysis_cpu_seconds', 'cpu_seconds', 'process_cpu_seconds', 'cpu_seconds_measured_after_plot_imports')
                   if isinstance(s.get(k), (int, float))), None)
        if ck is None:
            # Binding-only files do not automatically denote another invocation.
            continue
        wk = next((k for k in ('analysis_wall_seconds', 'wall_seconds', 'wall_seconds_measured_after_plot_imports') if isinstance(s.get(k), (int, float))), None)
        add('analysis:' + str(p.relative_to(BASE)), p,
            [component('pure-file analysis/audit/plot interval', s[ck], ck,
                       s.get('resource_scope', s.get('scope', 'Clock covers reported analysis interval; final serialization/host bootstrap excluded.')))],
            wall=s[wk] if wk else None,
            counts={k: s[k] for k in ('checks', 'failed_checks', 'errors', 'new_physical_simulations')
                    if k in s and not isinstance(s[k], list)},
            notes=['Embedded experiment metrics are metadata and are not added to this direct CPU. Each saved invocation counts exactly once.'])

    # Work detail comes from the already-metered pure-file mechanism analyzer.
    # Re-reading its summaries is this ledger's work; original physical work remains nested.
    budget_rows = []
    for stage in ('repaired_mechanism', 'nominal_pilot', 'full'):
        p = MECHANISMS / stage / 'analysis.json'
        if not p.exists():
            continue
        s = read(p)
        for c in s['cases']:
            if 'metrics' not in c:
                continue
            m = c['metrics']
            budget_rows.append({'stage': stage, 'case': c['case'],
                'search_queries': m['search_calls'], 'search_work': m['search_work'],
                'guard_work': c['guard_work'],
                'guard_max_single_call': c.get('max_guard_work_single_slow_call'),
                'case_budget_stop': c.get('case_budget_stop', 'not extracted in earlier analysis'),
                'search_status_counts': c.get('search_status_counts'),
                'slow_bounded_stop_counts': c.get('slow_bounded_stop_counts'),
                'candidate_budget_omissions': c.get('candidate_budget_omissions'),
                'guard_work_limit_reached_calls': c.get('guard_work_limit_reached_calls'),
                'invocation_cpu_seconds': c.get('invocation_cpu_seconds'),
                'cycle_cpu_seconds_nested': m.get('cycle_cpu_seconds_nested')})
    changed = [p for p, h in bound.items() if sha256((ROOT/p).read_bytes()).hexdigest() != h]
    checks.append({'kind': 'evidence_immutable', 'okay': not changed})
    cpu = sum(c['cpu_seconds'] for r in rows for c in r['cpu_components'] if c['cpu_seconds'] is not None)
    payload = {'schema': 'ics_round6_resource_ledger_v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'new_physical_simulations': 0, 'rows': rows, 'checks': checks,
        'failed_checks': sum(not c['okay'] for c in checks), 'bound_evidence_sha256': bound,
        'changed_evidence': changed, 'required_final_files': required,
        'pending': [r['id'] for r in rows if r['status'] == 'pending'],
        'totals': {'known_nonoverlapping_cpu_seconds_lower_bound': cpu,
            'unknown_cpu_components': sum(c['cpu_seconds'] is None for r in rows for c in r['cpu_components']),
            'whole_round_cpu_completely_measured': False, 'global_wall_makespan_seconds': None,
            'reason': 'Disjoint measured intervals can add; bootstrap, child CPU and auxiliary intervals remain unknown. Concurrent walls cannot be added.'},
        'nonadditive_budget_detail': budget_rows,
        'budget_interpretation': 'old64 and new32+32 share a candidate query-count ceiling only. New temporal reachability/matching guard work is additional and is outside CASE_BUDGET.search_work. Report queries, logical search work, guard work and CPU separately; caps are not observed work.',
        'source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'ledger_cpu_seconds': process_time()-cpu0, 'ledger_wall_seconds': perf_counter()-wall0,
        'ledger_scope': 'Read/hash/aggregation through final evidence verification; final JSON/Markdown serialization and bootstrap excluded. Not added to totals above.'}
    output.mkdir(parents=True)
    (output/'ledger.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 第六轮资源与失败账', '',
        '各数只代表明确计量区间；已知 CPU 合计是整个第六轮的下界。未知值不填零，预算上限不当耗时，并发 wall 不相加。', '',
        '| 独立调用 | 状态 | 已记录 CPU(s) | 未知分量 | 本调用 wall(s) |',
        '|---|---|---:|---:|---:|']
    for r in rows:
        vals = [c['cpu_seconds'] for c in r['cpu_components'] if c['cpu_seconds'] is not None]
        value = f'{sum(vals):.6f}' if vals else 'unknown'
        wall = f"{r['wall_seconds_individual_scope']:.6f}" if r['wall_seconds_individual_scope'] is not None else 'unknown'
        lines.append(f"| {r['id']} | {r['status']} | {value} | {sum(c['cpu_seconds'] is None for c in r['cpu_components'])} | {wall} |")
    lines += ['', f'互不重叠的已知 CPU 区间合计 **{cpu:.6f} 秒**；这是下界，不能称完整总 CPU。汇总器自身另计 {payload["ledger_cpu_seconds"]:.6f} 秒，未加入上述合计。', '',
        '初始 6 格、修复后 6 格、9 pilot 与正式 81 均实际独立运行；即使身份重复也没有跨批复用。case invocation 包含 cycle，777 总时钟包含 test 子区间，均只加最外层已记区间。初始旧策略两格的 cache tuple/list 误报与修复、两次测试 fixture 问题、各次独立审计均保留。', '',
        'old64 与 new32+32 只有候选查询数上限相同。新方法额外 guard 工作不在 CASE_BUDGET.search_work 内；逐例 queries、search_work、guard_work、CPU 与触顶信息另列于 JSON 的 nonadditive_budget_detail。', '',
        '777 全套在比较器修复前完成；后来 11 项为独立受影响回归，不能写成 779 全套。早期 9 项 guard 测试只记父 CPU，pytest 子 CPU 未测；tool wall 不代替 CPU。', '',
        f'绑定 {len(bound)} 份证据，变化 {len(changed)}，检查失败 {payload["failed_checks"]}。待完成批次：{payload["pending"] or "无"}。', '',
        '第五轮 same_zone_supply_analysis 设计诊断已经入第五轮账，未重复加入。所有字段、范围、来源 SHA 与额外未计量工作见 ledger.json。']
    (output/'RESOURCE_LEDGER.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (output/'summarize.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'rows': len(rows), 'known_cpu_lower_bound': cpu,
                      'failed_checks': payload['failed_checks'], 'pending': payload['pending'],
                      'ledger_cpu_seconds': payload['ledger_cpu_seconds']}, ensure_ascii=False))
    if changed or payload['failed_checks']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-file', action='append', default=[])
    args = parser.parse_args()
    collect(args.output, args.require_file)
