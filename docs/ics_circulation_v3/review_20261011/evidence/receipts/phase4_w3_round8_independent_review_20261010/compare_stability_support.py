"""Independent exact finite-support checks from original bags and audited costs.

No author sampler/statistics imports and no physical replay. Decimal fractions
below are exact for the recorded decimal costs, not exact real-world costs.
"""
from pathlib import Path
from fractions import Fraction
from itertools import product
import hashlib
import json
import math
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'phase4_w3_same_zone_stability_20261010'
AUTHOR = HERE.parent / 'phase4_w3_round8_stability_analysis_20261010'
bound, failures = {}, []
checks = 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    bound[str(path)] = sha(path)
    return json.loads(path.read_text(encoding='utf8'))


def check(value, label):
    global checks
    checks += 1
    if not value:
        failures.append(label)


def compare(expected, actual, label):
    if isinstance(expected, dict):
        for key, value in expected.items():
            check(key in actual, label + ':' + key + ':present')
            if key in actual:
                compare(value, actual[key], label + ':' + key)
    elif isinstance(expected, list):
        check(len(expected) == len(actual), label + ':length')
        for i, (a, b) in enumerate(zip(expected, actual)):
            compare(a, b, label + ':' + str(i))
    elif isinstance(expected, float):
        check(isinstance(actual, (int, float)) and math.isfinite(actual)
              and math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-8), label)
    else:
        check(expected == actual, label)


def canonical(bags):
    return json.dumps(sorted(bags, key=lambda b: (b['arrival'], b['bag_id'])),
                      sort_keys=True, separators=(',', ':'), allow_nan=False)


def tape_sha(bags):
    return hashlib.sha256(canonical(bags).encode()).hexdigest()


def fraction_record(value):
    return {'numerator': value.numerator, 'denominator': value.denominator,
            'float': float(value)}


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    target = HERE / 'stability_support_expectation_comparison.json'
    if target.exists():
        raise FileExistsError(target)
    raw_audit = read(HERE / 'stability_full_artifact_audit.json')
    check(not raw_audit['failures'] and not raw_audit['drift'], 'complete stable raw audit')
    costs = {r['physical_key']: r['cost'] for r in raw_audit['rows'] if r['cost_known']}
    details = read(SOURCE / 'selected_details.json')
    resolved = read(SOURCE / 'full/resolved_requests.json')
    author_support = read(AUTHOR / 'future_support.json')
    author_rows = {r['state_key']: r for r in author_support['states']}
    check(set(author_rows) == {r['state_key'] for r in details}, 'all selected identities')
    for name, expected in author_support['input_binding'].items():
        check(sha(name) == expected, 'support binding:' + name)
        bound[name] = expected
    own_rows, exact_rows = [], []
    for detail in details:
        key, now = detail['state_key'], detail['time']
        future_path = SOURCE / detail['future_file']
        check(sha(future_path) == detail['future_file_sha256'], 'original future binding:' + key)
        future = read(future_path)
        original = future['original_future']
        original_ids = {b['bag_id'] for b in original}
        check(len(original_ids) == len(original), 'original identities unique:' + key)
        check(all(b['arrival'] > now for b in original), 'strictly unobserved original pending:' + key)
        alternatives = []
        for bag in original:
            if bag['protected']:
                alternatives.append([(bag, Fraction(1))])
            else:
                legal_jitter = [j for j in (-2, 0, 2) if bag['arrival'] + j > now]
                denominator = 3 + 7 * len(legal_jitter)
                outcomes = [(None, Fraction(3, denominator))]
                outcomes.extend(({**bag, 'arrival': bag['arrival'] + j,
                                  'deadline': bag['deadline'] + j}, Fraction(7, denominator))
                                for j in legal_jitter)
                alternatives.append(outcomes)
        cardinality = math.prod(len(a) for a in alternatives)
        seen, probabilities = {}, {}
        tapes = [t for block in future['blocks'] for t in block['tapes']]
        check(len(tapes) == 64, 'all two-block sample occurrences:' + key)
        for tape in tapes:
            bags = tape['bags']
            proposed = {b['bag_id']: b for b in bags}
            check(len(proposed) == len(bags) and set(proposed) <= original_ids,
                  'sample identities:' + key)
            probability = Fraction(1)
            for bag, choices in zip(original, alternatives):
                observed = proposed.get(bag['bag_id'])
                matches = [p for value, p in choices if value == observed]
                check(len(matches) == 1, 'sample exactly legal outcome:' + key + ':' + bag['bag_id'])
                probability *= matches[0] if matches else Fraction(0)
            digest = tape_sha(bags)
            check(digest == tape['sha256'], 'canonical tape digest:' + key)
            if digest in seen:
                check(seen[digest] == canonical(bags) and probabilities[digest] == probability,
                      'repeat means same tape and probability:' + key)
            seen[digest], probabilities[digest] = canonical(bags), probability
        mass = sum(probabilities.values(), Fraction(0))
        exhaustive = len(seen) == cardinality and mass == 1
        row = {'state_key': key, 'candidate_count': detail['candidate_count'],
               'support_size': cardinality, 'sampled_distinct_tapes': len(seen),
               'sampled_support_mass': fraction_record(mass),
               'unsampled_support_mass': fraction_record(1 - mass),
               'exhaustive_support': exhaustive,
               'tape_probabilities': {k: fraction_record(p) for k, p in probabilities.items()}}
        compare(row, author_rows[key], 'independent finite support:' + key)
        author_state = read(AUTHOR / 'results/states' / (key + '.json'))
        compare({k: v for k, v in row.items() if k != 'tape_probabilities'},
                author_state['finite_support'], 'state finite support:' + key)
        own_rows.append({k: v for k, v in row.items() if k != 'tape_probabilities'})
        if not exhaustive or not detail['candidate_count']:
            check(author_state['exhaustive_law_cost'] is None, 'no unseen future zero-imputation:' + key)
            continue
        exact = {}
        for combination in product(*alternatives):
            bags = [value for value, _ in combination if value is not None]
            probability = math.prod(p for _, p in combination)
            digest = tape_sha(bags)
            check(digest not in exact, 'Cartesian support outcome unique:' + key)
            exact[digest] = probability
        check(exact == probabilities and sum(exact.values(), Fraction(0)) == 1,
              'independent complete Cartesian support:' + key)
        state_requests = [r for r in resolved if r['state_key'] == key]
        by_action_tape = {}
        for request in state_requests:
            pair = (request['candidate'], request['sampled_future_sha256'])
            value = costs[request['physical_key']]
            if pair in by_action_tape:
                check(by_action_tape[pair] == value, 'same action/tape has same cost:' + key)
            by_action_tape[pair] = value
        check(set(by_action_tape) == {(c, t) for c in range(detail['candidate_count']) for t in exact},
              'every support action physically evaluated:' + key)
        fractional_means = [sum((p * Fraction(str(by_action_tape[c, t]))
                                for t, p in exact.items()), Fraction(0))
                            for c in range(detail['candidate_count'])]
        means = list(map(float, fractional_means))
        optimum = min(means)
        expected = {'means': means,
                    'optimal_indices': [c for c, value in enumerate(means) if abs(value - optimum) <= 1e-8],
                    'actual_regret': means[detail['actual_chosen_index']] - optimum}
        compare(expected, author_state['exhaustive_law_cost'], 'independent finite-law expectation:' + key)
        exact_rows.append({'state_key': key, 'support_size': cardinality, **expected,
                           'decimal_cost_exact_means': [fraction_record(v) for v in fractional_means]})
    drift = [name for name, expected in bound.items() if sha(name) != expected]
    check(not drift, 'read files unchanged')
    result = {'schema': 'round8_independent_finite_support_expectation_v1',
              'checks': checks, 'failures': failures, 'drift': drift,
              'states': own_rows, 'exhaustive_expectations': exact_rows,
              'exhaustive_evaluated_state_count': len(exact_rows),
              'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - wall,
              'files_sha256': bound, 'source_sha256': sha(__file__), 'physical_simulations': 0,
              'scope': 'All 23 selected records and 1472 sampled occurrence tapes checked against independently constructed exact conditional outcomes; Cartesian sets and recorded-decimal-cost expectations checked for every exhaustive evaluated state. Auxiliary synthetic-law evidence only; primary Monte Carlo occurrence weights unchanged.'}
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('states', 'files_sha256')}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
