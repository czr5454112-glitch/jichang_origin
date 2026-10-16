"""Read saved pure discovery and check the entire finite comparison graph."""
from __future__ import annotations
import argparse
from collections import Counter, deque
import gzip
import json
from pathlib import Path
import time

from . import research_public_interaction_discovery as model


def reachable(rows, *, strict):
    base = (0, 0, 0, 0)
    allowed = {key for key, row in rows.items() if model.protected(row, rows[base]) is True}
    paths = {base: [list(base)]} if base in allowed else {}
    queue = deque(paths)
    while queue:
        current = queue.popleft()
        for candidate in sorted(allowed):
            if candidate in paths or sum(a != b for a, b in zip(current, candidate)) != 1: continue
            x = rows[current]['prediction']['completion_sum']
            y = rows[candidate]['prediction']['completion_sum']
            if not (y < x if strict else y <= x): continue
            paths[candidate] = paths[current] + [list(candidate)]
            queue.append(candidate)
    return paths


def audit(directory, output):
    started = time.perf_counter()
    plan_path = directory / 'preregistered_protocol.json'
    receipt_path = directory / 'receipt.json'
    ledger_path = directory / 'ledger.json'
    plan = json.loads(plan_path.read_text()); receipt = json.loads(receipt_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    if (receipt['status'] != 'completed_pure_discovery' or receipt['source_changed'] != []
            or receipt['native_calls'] != 0 or receipt['discovery_cells'] != 256
            or receipt['validation_unexecuted_cells'] != 256
            or receipt['preregistered_protocol_sha256'] != model.sha(plan_path)):
        raise ValueError('incomplete_or_changed_discovery')
    pins = {str(p.resolve()): model.sha(p) for p in (plan_path, receipt_path, ledger_path)}
    for name, digest in plan['source_sha256'].items():
        archive = directory / 'source' / Path(name).relative_to(model.ROOT)
        if model.sha(name) != digest or model.sha(archive) != digest: raise ValueError('source_drift')
        pins[name] = digest; pins[str(archive.resolve())] = digest
    expected_rows = {case['case_id'] + '/' + '_'.join(map(str, key)): (case, key, action)
                     for case in model.parameters('discovery') + model.parameters('validation')
                     for key, action in model.actions(case).items()}
    if set(ledger) != set(expected_rows): raise ValueError('incomplete_ledger')
    for name, (case, key, action) in expected_rows.items():
        row = ledger[name]
        if row['case'] != case or row['key'] != list(key) or row['action'] != action:
            raise ValueError('misbound_ledger')
        if case['stage'] == 'validation' and row['status'] != 'unknown_unexecuted':
            raise ValueError('validation_was_executed')
    if [r['case'] for r in receipt['reports']] != model.parameters('discovery'):
        raise ValueError('missing_or_duplicate_case')
    summaries = []; totals = Counter()
    for saved in receipt['reports']:
        case = saved['case']; path = Path(saved['raw'])
        if model.sha(path) != saved['sha256']: raise ValueError('changed_raw')
        pins[str(path.resolve())] = saved['sha256']
        raw = json.loads(gzip.decompress(path.read_bytes()))
        input_path = directory / (case['case_id'] + '.input.json')
        if (raw['case'] != case or raw['input_sha256'] != model.sha(input_path)
                or model.canonical(json.loads(input_path.read_text())) != model.canonical(model.bundle(case))):
            raise ValueError('changed_input')
        pins[str(input_path.resolve())] = model.sha(input_path)
        cells = raw['cells']; rows = {tuple(r['key']): r for r in cells}; domain = model.actions(case)
        if len(cells) != 32 or set(rows) != set(domain): raise ValueError('incomplete_factorial')
        for key, row in rows.items():
            if row['action'] != domain[key] or row['evidence'] != model.physical_evidence(row['prediction'], row['action']):
                raise ValueError('misbound_projection')
            ledger_row = ledger[case['case_id'] + '/' + '_'.join(map(str, key))]
            if (ledger_row['status'] != row['evidence']['status']
                    or ledger_row['prediction_status'] != row['prediction']['status']):
                raise ValueError('ledger_does_not_match_raw')
        cubes = [model.cube({(i, l): rows[i, w, r, l] for i in (0, 1) for l in (0, 1)})
                 for w in range(4) for r in range(2)]
        for w in range(4):
            for r in range(2):
                expected = {'window_index': w, 'return_index': r, **cubes[w * 2 + r]}
                if raw['assessment']['cubes'][w * 2 + r] != expected: raise ValueError('changed_cube_assessment')
        protected = [k for k in rows if model.protected(rows[k], rows[0, 0, 0, 0]) is True]
        optimum = min(protected, key=lambda k: (rows[k]['prediction']['completion_sum'], k), default=None)
        strict_paths, plateau_paths = reachable(rows, strict=True), reachable(rows, strict=False)
        methods = raw['assessment']['methods']
        winners = {}
        for name, method in methods.items():
            if method['evaluation_budget'] != 32 or method['candidate_denominator'] != 32 or method['evaluations'] > 32:
                raise ValueError('changed_method_budget')
            chosen = next((k for k, action in domain.items() if action == method['selected_action']), None)
            winners[name] = list(chosen) if chosen is not None else None
            if chosen is not None and (chosen not in protected or method['selected_prediction']['completion'] != rows[chosen]['prediction']['completion']):
                raise ValueError('unprotected_or_misbound_selection')
        counts = Counter(known_cells=sum(model.known(row) for row in rows.values()),
                         unknown_cells=sum(not model.known(row) for row in rows.values()),
                         cubes=len(cubes), barriers=sum(c.get('barrier') is True for c in cubes),
                         projected_chain_candidates=sum(c.get('projected_chain_candidate') is True for c in cubes))
        initial_regrets = [c['regressed_jobs']['(1, 0)'] for c in cubes
                           if c.get('strict_protection', {}).get('(1, 0)') is False]
        counts['initial_regression_cubes'] = len(initial_regrets)
        counts['initial_regret_includes_already_completed_loaded'] = sum('loaded' in jobs for jobs in initial_regrets)
        totals.update(counts)
        summaries.append({'case': case, 'counts': dict(counts), 'method_selected_keys': winners,
            'same_four_method_completion_vector': len({model.canonical(m['selected_prediction']['completion']) for m in methods.values() if m['selected_prediction']}) == 1,
            'finite_optimum_key': list(optimum) if optimum is not None else None,
            'ordinary_strict_path_to_finite_optimum': strict_paths.get(optimum),
            'ordinary_plateau_path_to_finite_optimum': plateau_paths.get(optimum),
            'fixed_reference': raw['assessment']['fixed_initial_reference'],
            'prefix_fact': 'Changing first-reuse routing occurs after loaded completion and cannot undo a loaded-job regression.'})
    if any(model.sha(name) != digest for name, digest in pins.items()): raise ValueError('audit_input_drift')
    result = {'status': 'saved_pure_discovery_revalidated', 'source_sha256': model.sha(__file__),
        'pins': pins, 'native_calls': 0, 'new_projection_calls': 0, 'wall_seconds': time.perf_counter() - started,
        'counts': dict(totals), 'validation_cells_still_unexecuted': 256, 'cases': summaries,
        'interpretation': 'No protection-barrier candidate found in this preregistered domain. Ordinary coordinate paths reach every finite modeled optimum. All initial-only regression cubes also regress the already completed loaded job, which later R1 cannot repair.',
        'limits': 'Pure hypothetical model evidence only. No native authority, new-domain conformance, per-job physical protection, solver novelty or100ms claim.'}
    model.write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    audit(args.directory, args.output)


if __name__ == '__main__': main()
