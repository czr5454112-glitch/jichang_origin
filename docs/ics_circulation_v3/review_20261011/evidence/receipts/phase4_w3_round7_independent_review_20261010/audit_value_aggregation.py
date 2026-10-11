"""Recompute all value/service aggregations; reuse certified cost extraction."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import process_time, perf_counter
from audit_collection import HERE, BASE


def main():
    cpu, wall = process_time(), perf_counter()
    root = BASE / 'phase4_w3_round7_value_analysis_20261010/results'
    run = BASE / 'phase4_w3_same_zone_labels_20261010'
    bound, checks, errors = {}, 0, []

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok: errors.append(label)

    def read(path, expected=None):
        path = Path(path).resolve()
        value = path.read_bytes()
        h = sha256(value).hexdigest()
        check(expected is None or h == expected, 'SHA:' + str(path))
        if expected is not None and h != expected: raise ValueError('mismatching artifact')
        bound[str(path)] = h
        return json.loads(gzip.decompress(value) if path.name.endswith('.gz') else value)

    for p, expected in read(root / 'manifest.json').items(): read(root / p, expected) if p.endswith('.json') else check(sha256((root / p).read_bytes()).hexdigest() == expected, 'manifest:' + p)
    analysis, services = read(root / 'analysis.json'), read(root / 'service_changes.json')
    check(sha256((root.parent / 'analyze.py').read_bytes()).hexdigest() == analysis['analysis_source_sha256'], 'reviewed aggregation implementation')
    full_audit = read(HERE / 'full_artifact_audit_v2.json')
    history_audit = read(HERE / 'old12_artifact_audit_v2.json')
    check(not full_audit['errors'] and full_audit['chosen_branch_prefix_checks'] == 174 and not history_audit['errors'], 'complete independent primary audits passed')
    original_costs = {r['request_key']:r['independently_recomputed_cost'] for r in full_audit['rows'] + history_audit['rows']}
    full = read(run / 'full/summary.json')
    definitions = {(r['scene'], r['decision_index'], r['candidate']):r for r in full['rows']}
    collections, attempts = {}, {}
    for row in read(run / 'collection_run/summary.json')['rows']:
        collections[row['scene']] = read(run / row['file'], row['sha256'])
        for a in collections[row['scene']]['attempts']:
            attempts[row['scene'], a['decision_index']] = a
    service_map = {(r['scene'], r['decision_index']):r for r in services}
    rebuilt = []
    EPS = 1e-8
    for pool in analysis['pools']:
        key = pool['scene'], pool['decision_index']
        attempt = attempts[key]
        bag = collections[key[0]]['result']['final_snapshot']['bags'][attempt['bag_id']]
        role = 'origin' if attempt['node'] == bag['origin'] else 'continuation'
        check(pool['role'] == role and pool['candidate_count'] == attempt['candidate_count'], str(key) + ':actual geometric role and pool denominator')
        if not pool['candidate_count']:
            check(not pool['complete'] and key not in service_map, str(key) + ':zero preserved without invented value')
            rebuilt.append(pool)
            continue
        costs = {int(k):v for k,v in pool['values'].items()}
        check(set(costs) == set(range(pool['candidate_count'])), str(key) + ':every candidate present')
        for candidate, cost in costs.items():
            request = definitions[*key, candidate]
            check(cost == original_costs[request['request_key']], request['request_key'] + ':cost from independent full raw audit')
        chosen = attempt['actual_chosen_index']
        optimal = {i for i, v in costs.items() if abs(v - min(costs.values())) <= EPS}
        check(pool['actual_chosen_index'] == chosen and set(pool['optimal_indices']) == optimal and
              abs(pool['spread'] - max(costs.values()) + min(costs.values())) < EPS and
              abs(pool['actual_choice_regret'] - costs[chosen] + min(costs.values())) < EPS, str(key) + ':independent entire cost ranking')
        service = service_map[key]
        check(service['chosen'] == chosen and set(service['optimal_indices']) == optimal, str(key) + ':service uses actual chosen reference')
        base_state = collections[key[0]]['result']['final_snapshot']
        base = base_state['completed']
        vectors, late, nondegrading = {}, set(), set()
        for candidate, changes in service['candidate_service_changes'].items():
            candidate = int(candidate)
            vector = dict(base)
            details = changes['details']
            check(len({r['bag_id'] for r in details}) == len(details), str(key) + ':unique task deltas')
            check(changes['earlier'] == sum(r['delta_completion'] < 0 for r in details) and changes['later'] == sum(r['delta_completion'] > 0 for r in details), str(key) + ':all positive and negative delta counts')
            for detail in details:
                name = detail['bag_id']
                check(detail['completion'] - base[name] == detail['delta_completion'] and detail['delta_completion'] != 0 and
                      detail['deadline'] == base_state['bags'][name]['deadline'] and detail['protected'] == base_state['bags'][name]['protected'], str(key) + ':actual task delta reference')
                vector[name] = detail['completion']
            vectors[candidate] = tuple(sorted(vector.items()))
            if changes['later']: late.add(candidate)
            else: nondegrading.add(candidate)
        count = len(set(vectors.values()))
        check(set(vectors) == set(costs) and dict(vectors[chosen]) == base, str(key) + ':all reconstructed vectors and zero chosen delta')
        check(pool['different_completion_vectors'] == count and pool['same_cost_different_service'] == (max(costs.values()) - min(costs.values()) <= EPS and count > 1) and
              set(pool['optimal_actions_with_later_tasks']) == optimal & late and set(pool['no_later_completion_indices']) == nondegrading and
              abs(pool['no_later_completion_oracle_gap'] - costs[chosen] + min(costs[i] for i in nondegrading)) < EPS, str(key) + ':service-safe subset and cost-flat physical classification')
        rebuilt.append(pool)
    for group_name, group in analysis['groups'].items():
        scene, role = group_name.split(':')
        selected = [r for r in rebuilt if (scene == 'all' or r['scene'] == scene) and (role == 'all' or r['role'] == role)]
        complete = [r for r in selected if r['complete']]
        expected = {'attempts':len(selected), 'zero':sum(r['candidate_count'] == 0 for r in selected),
            'nonempty':sum(r['candidate_count'] > 0 for r in selected), 'complete_pools':len(complete),
            'unknown_nonempty_pools':sum(r['candidate_count'] > 0 and not r['complete'] for r in selected),
            'candidate_count_distribution':dict(Counter(str(r['candidate_count']) for r in selected)),
            'nonflat_pools':sum(r['spread'] > EPS for r in complete),
            'actual_choice_suboptimal':sum(r['actual_choice_regret'] > EPS for r in complete),
            'max_actual_choice_regret':max((r['actual_choice_regret'] for r in complete), default=None),
            'correlated_local_regret_sum_not_deployment_gain':sum(r['actual_choice_regret'] for r in complete),
            'different_completion_vector_pools':sum(r['different_completion_vectors'] > 1 for r in complete),
            'flat_cost_but_different_service_pools':sum(r['same_cost_different_service'] for r in complete),
            'pools_with_optimal_action_delaying_some_task':sum(bool(r['optimal_actions_with_later_tasks']) for r in complete),
            'no_later_completion_oracle_improvement_pools':sum(r['no_later_completion_oracle_gap'] > EPS for r in complete),
            'max_no_later_completion_oracle_gap':max((r['no_later_completion_oracle_gap'] for r in complete), default=None)}
        check(expected == group, group_name + ':all aggregates independently recomputed')
    # Feature-only spot selection fixed before looking at service magnitude:
    # first nonempty origin and continuation in each scene, every candidate.
    spot_keys = set()
    for scene in sorted(collections):
        for role in ('origin', 'continuation'):
            eligible = [r for r in rebuilt if r['scene'] == scene and r['role'] == role and r['complete']]
            first = min(eligible, key=lambda r:r['decision_index'])
            spot_keys.add((scene, first['decision_index']))
    spot_count = 0
    for key in sorted(spot_keys):
        base = collections[key[0]]['result']['final_snapshot']['completed']
        for i, changes in service_map[key]['candidate_service_changes'].items():
            request = definitions[*key, int(i)]
            raw = read(run / request['file'], request['sha256'])
            predicted = dict(base)
            predicted.update({r['bag_id']:r['completion'] for r in changes['details']})
            check(raw['result']['final_snapshot']['completed'] == predicted, request['request_key'] + ':feature-selected raw service vector spot check')
            spot_count += 1
    history = read(run / 'old12/summary.json')
    for item in analysis['historical_old12']:
        index = item['decision_index']
        rows = [r for r in history['rows'] if r['decision_index'] == index]
        vectors = {}
        for row in rows:
            raw = read(run / row['file'], row['sha256'])
            vectors[row['candidate']] = raw['result']['final_snapshot']['completed']
            check(item['new_values'][str(row['candidate'])] == original_costs[row['request_key']], row['request_key'] + ':historical independently audited cost')
        reference = vectors[item['old_actual_chosen_index']]
        allowed = {i for i, v in vectors.items() if all(v[name] <= time for name, time in reference.items())}
        check(set(item['new_no_later_completion_indices']) == allowed == {0} and item['new_no_later_completion_oracle_gap'] == 0, str(index) + ':all historical raw service-safe sets')
    for p, expected in bound.items(): check(sha256(Path(p).read_bytes()).hexdigest() == expected, 'final unchanged:' + p)
    report = dict(schema='round7_independent_value_aggregation_audit_v1', checks=checks, errors=errors,
        all_group=analysis['groups']['all:all'], feature_selected_raw_service_checks=spot_count,
        feature_selected_states=[list(k) for k in sorted(spot_keys)], historical_raw_service_checks=48,
        bound_files=bound, new_physical_simulations=0, cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='All692 costs reused from independent primary raw audit; all174 extracted service delta vectors and every scene/role aggregation recomputed. Raw service vectors additionally checked at six feature-selected states and all48 historical branches. Remaining alternative-vector extraction reviewed in bound analyze.py, not independently reparsed a second time.')
    with (HERE / 'value_aggregation_audit.json').open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != 'bound_files'}))
    return bool(errors)


if __name__ == '__main__': raise SystemExit(main())
