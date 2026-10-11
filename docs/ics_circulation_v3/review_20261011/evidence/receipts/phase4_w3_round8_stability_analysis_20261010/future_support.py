"""Exact finite synthetic-law probability mass, without physical simulation.

Seen support mass is coverage, not a Monte Carlo accuracy certificate. Only
exhaustive support permits an exact law expectation from the existing outcomes.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'phase4_w3_same_zone_stability_20261010'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bag_support(original, now):
    if original['arrival'] <= now:
        raise ValueError('not an original pending task')
    if original['protected']:
        return [(original, Fraction(1))]
    jitters = [j for j in (-2, 0, 2) if original['arrival'] + j > now]
    denominator = 3 + 7 * len(jitters)
    return [(None, Fraction(3, denominator))] + [
        ({**original, 'arrival': original['arrival'] + j, 'deadline': original['deadline'] + j}, Fraction(7, denominator))
        for j in jitters]


def exact_mass(original, sampled, now):
    original_ids = {b['bag_id'] for b in original}
    by_id = {b['bag_id']: b for b in sampled}
    if len(original_ids) != len(original) or len(by_id) != len(sampled) or set(by_id) - original_ids:
        raise ValueError('bad task identities')
    probability, size = Fraction(1), 1
    for bag in original:
        support = bag_support(bag, now)
        mass = [p for value, p in support if value == by_id.get(bag['bag_id'])]
        if len(mass) != 1:
            raise ValueError('sample outside declared support')
        probability *= mass[0]
        size *= len(support)
    return probability, size


def rational(value):
    return {'numerator': value.numerator, 'denominator': value.denominator, 'float': float(value)}


def main():
    cpu, wall = process_time(), perf_counter()
    checks = []
    bag = {'bag_id': 'a', 'arrival': 2, 'deadline': 9, 'protected': False, 'origin': 'A', 'destination': 'B'}
    for now in (0, 1):
        values = bag_support(bag, now)
        checks.append(sum(p for b, p in values) == 1)
        checks.append(all(exact_mass([bag], [] if b is None else [b], now) == (p, len(values)) for b, p in values))
    protected = {**bag, 'protected': True}
    checks.append(bag_support(protected, 1) == [(protected, Fraction(1))])
    checks.append(exact_mass([], [], 0) == (Fraction(1), 1))
    try:
        exact_mass([protected], [], 1)
    except ValueError:
        checks.append(True)
    else:
        checks.append(False)
    assert all(checks)
    details = json.loads((SOURCE / 'selected_details.json').read_bytes())
    rows, bindings = [], {}
    for detail in details:
        path = SOURCE / detail['future_file']
        assert sha(path) == detail['future_file_sha256']
        future = json.loads(path.read_bytes())
        masses, tapes = {}, {}
        for block in future['blocks']:
            for tape in block['tapes']:
                p, support_size = exact_mass(future['original_future'], tape['bags'], future['now'])
                if tape['sha256'] in tapes:
                    assert tapes[tape['sha256']] == tape['bags']
                masses[tape['sha256']], tapes[tape['sha256']] = p, tape['bags']
        total = sum(masses.values(), Fraction(0))
        exhaustive = len(masses) == support_size
        assert total <= 1 and (total == 1) == exhaustive
        rows.append({'state_key': detail['state_key'], 'candidate_count': detail['candidate_count'],
            'support_size': support_size, 'sampled_distinct_tapes': len(masses),
            'sampled_support_mass': rational(total), 'unsampled_support_mass': rational(1 - total),
            'exhaustive_support': exhaustive, 'tape_probabilities': {k: rational(v) for k, v in sorted(masses.items())}})
        bindings[str(path)] = sha(path)
    result = {'states': rows, 'analytical_checks_passed': len(checks), 'source_sha256': sha(Path(__file__)),
        'input_binding': bindings, 'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'physical_simulations': 0,
        'scope': 'Exact probability only under the declared independent per-task conditional synthetic law; low seen mass alone is not a Monte Carlo validity failure. Unseen outcomes remain unknown. Primary nested estimates keep draw weights.'}
    with (HERE / 'future_support.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ('states', 'input_binding')}))
    for row in rows:
        print(row['state_key'], row['support_size'], row['sampled_distinct_tapes'], row['sampled_support_mass']['float'], row['exhaustive_support'])


if __name__ == '__main__':
    main()
