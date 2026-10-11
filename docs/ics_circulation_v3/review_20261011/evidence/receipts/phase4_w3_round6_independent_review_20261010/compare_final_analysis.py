"""Compare final aggregates with the separately audited physical JSON evidence.

No simulation, controller import, or additional raw-physics pass. All episode
costs below came from the independent audit's actual load/trace/task ledger.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
import sys


HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def run(analysis_directory):
    wall0, cpu0 = perf_counter(), process_time()
    bound, errors, checks = {}, [], 0

    def read(path):
        content = path.read_bytes()
        bound[str(path)] = sha256(content).hexdigest()
        return json.loads(content)

    def check(condition, description):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(description)

    independent = read(HERE / 'formal_artifact_audit.json')
    primary = read(BASE / analysis_directory / 'analysis.json')
    requested = read(BASE / 'phase4_w3_same_zone_supply_repaired_20261010/full/requested_cases.json')
    definitions = {r['case_id']: r for r in requested}
    audited = {r['case_id']: r for r in independent['rows']}
    reported = {r['case_id']: r for r in primary['rows'] if r['stage'] == 'full'}
    check(not independent['errors'], 'independent full physical audit must pass')
    check(not primary['errors'] and not primary['input_drift'], 'primary analysis reports no errors or drift')
    check(len(definitions) == len(audited) == len(reported) == 81, 'complete unique 81 episode denominator')
    check(definitions.keys() == audited.keys() == reported.keys(), 'same 81 identities')
    for identity, row in audited.items():
        claim = reported[identity]
        check(claim['status'] == row['physical_status'] == 'controller_quiescent', identity + ':status')
        check(abs(claim['total_cost'] - row['cost']) < 1e-8, identity + ':actual objective')
        check(claim['task_ledger_count'] == claim['completed'] == row['physical_task_count'], identity + ':actual complete task denominator')
        for metric in ('on_time', 'protected_expected', 'protected_on_time'):
            check(claim[metric] == row['metrics'][metric], identity + ':' + metric)
        check(claim['actual_loaded_generation_attempts'] == row['actual_loaded_opportunities'], identity + ':all loaded attempts')
        check(claim['loaded_zero_candidate_attempts'] == row['zero_candidate_opportunities'], identity + ':zero pool attempts')
    by_scene_tape_policy = {(r['scene'], r['tape_id'], r['policy']): audited[identity]
                            for identity, r in definitions.items()}
    pairs = []
    for (scene, tape, policy), row in sorted(by_scene_tape_policy.items()):
        if policy == 'old32':
            continue
        before = by_scene_tape_policy[scene, tape, 'old32']
        delta = row['cost'] - before['cost']
        match = [p for p in primary['pairs'] if p['stage'] == 'full' and
                 (p['scene'], p['tape_id'], p['method']) == (scene, tape, policy)]
        check(len(match) == 1 and abs(match[0]['delta_cost'] - delta) < 1e-8,
              f'{scene}/{tape}/{policy}: paired actual objective')
        pairs.append(dict(scene=scene, tape=tape, policy=policy,
                          before_cost=before['cost'], after_cost=row['cost'], delta_cost=delta,
                          sign='better' if delta < -1e-8 else 'worse' if delta > 1e-8 else 'equal'))
    summaries = []
    for scene in ('all', 'counterflow', 'cross_cycle', 'near_full'):
        for policy in ('old32', 'old64', 'same_zone32plus32'):
            members = [row for identity, row in audited.items() if definitions[identity]['policy'] == policy
                       and (scene == 'all' or definitions[identity]['scene'] == scene)]
            total = sum(row['cost'] for row in members)
            task_count = sum(row['physical_task_count'] for row in members)
            selected_pairs = [p for p in pairs if p['policy'] == policy and (scene == 'all' or p['scene'] == scene)]
            signs = dict(Counter(p['sign'] for p in selected_pairs))
            aggregate = [a for a in primary['aggregates'] if
                         (a['stage'], a['scope'], a['policy']) == ('full', scene, policy)]
            check(len(aggregate) == 1, f'{scene}/{policy}: one complete aggregate')
            claim = aggregate[0]
            check(claim['runs'] == len(members) and abs(claim['total_cost'] - total) < 1e-8,
                  f'{scene}/{policy}: episode count and actual cost sum')
            check(claim['task_ledger_count'] == claim['completed'] == task_count,
                  f'{scene}/{policy}: request-weighted task count')
            check(claim['paired_signs_against_old32'] == signs, f'{scene}/{policy}: signs')
            summaries.append(dict(scene=scene, policy=policy, episodes=len(members),
                total_cost=total, mean_cost=total / len(members), task_count=task_count,
                paired_signs=signs, paired_total_delta=sum(p['delta_cost'] for p in selected_pairs)))
    for path, digest in bound.items():
        check(sha256(Path(path).read_bytes()).hexdigest() == digest, 'unchanged:' + path)
    output = dict(schema='ics_v3_round6_independent_aggregate_comparison_v1',
        new_physical_simulations=0, checks=checks, errors=errors, pairs=pairs, aggregates=summaries,
        bound_files=bound, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        cpu_seconds=process_time() - cpu0, wall_seconds=perf_counter() - wall0,
        resource_scope='Pure file comparison through input rehash; final serialization and bootstrap excluded.',
        qualifications='Per-episode actual costs from separately audited physics. Paired sums summarize the fixed correlated development cohort, not additional realizable savings or independent new-scene confirmation.')
    with (HERE / 'final_analysis_comparison.json').open('x', encoding='utf-8') as stream:
        json.dump(output, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in output.items() if k not in ('bound_files', 'pairs')}, ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1]))
