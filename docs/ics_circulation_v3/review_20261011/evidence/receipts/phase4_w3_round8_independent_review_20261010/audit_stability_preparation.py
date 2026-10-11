"""Independent file-only recomputation of stratification, law, tapes and memo."""
from pathlib import Path
from dataclasses import asdict
import gzip
import hashlib
import json
import pickle
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent
BASE = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_same_zone_stability_20261010'
bound = {}
failures = []
checks = 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    bound[str(path)] = sha(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf8') as stream:
        return json.load(stream)


def check(value, message):
    global checks
    checks += 1
    if not value:
        failures.append(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def main():
    start, cpu = time.perf_counter(), time.process_time()
    protocol = read(BASE / 'protocol.json')
    for key, directory in [('source_sha256', ROOT / 'scripts/experiments/ics_circulation_v3'),
                           ('test_sha256', ROOT / 'tests'), ('input_sha256', None)]:
        for name, expected in protocol[key].items():
            path = Path(name) if directory is None else directory / name
            check(sha(path) == expected, 'binding:' + str(path))
            bound[str(path)] = expected
    for name, expected in read(BASE / 'preparation_manifest.json').items():
        check(sha(BASE / name) == expected, 'preparation:' + name)
        bound[str(BASE / name)] = expected
    prior = Path(protocol['source'])
    inventory = read(BASE / 'inventory.json')
    details = read(BASE / 'selected_details.json')
    requests = read(BASE / 'requested_rows.json')
    unique = read(BASE / 'unique_rows.json')
    bridges = read(BASE / 'bridge_rows.json')
    pilots = read(BASE / 'pilot_rows.json')
    scenes = {'cross_cycle': 23011, 'counterflow': 23029, 'near_full': 23041}
    selected, original_rows = {}, []
    for scene in scenes:
        collection = read(prior / 'collections' / scene / 'collection.json.gz')
        attempts = sorted(collection['attempts'], key=lambda r: (r['time'], r['decision_index']))
        original_rows += [(scene, row) for row in attempts]
        for role in ('origin', 'continuation'):
            for low, high in [(0, 40), (40, 80), (80, None)]:
                eligible = [r for r in attempts if r['role'] == role and r['time'] >= low and (high is None or r['time'] < high)]
                cell = next(c for c in inventory['cells'] if (c['scene'], c['role'], c['time_low']) == (scene, role, low))
                expected = None if not eligible else f"{scene}_d{eligible[0]['decision_index']:04d}"
                check(cell['selected_state'] == expected and cell['eligible_attempts'] == len(eligible), 'stratum:' + str(cell))
                if eligible:
                    selected[expected] = eligible[0]
        for row in attempts:
            if row['candidate_count'] == 0:
                selected.setdefault(f"{scene}_d{row['decision_index']:04d}", row)
    check(len(original_rows) == 180, 'all attempts')
    check(sum(r['candidate_count'] == 0 for _, r in original_rows) == 6, 'all zero attempts')
    check(set(selected) == {r['state_key'] for r in details}, 'selected identity set')
    check(len(details) == 23 and sum(r['candidate_count'] > 0 for r in details) == 17, 'selected count')
    expected_requests = {}
    tape_count = 0
    for row in details:
        source_row = selected[row['state_key']]
        check(all(row[k] == v for k, v in source_row.items()), 'selected metadata:' + row['state_key'])
        metadata = read(prior / row['metadata_file'])
        checkpoint_path = prior / row['checkpoint_file']
        check(sha(checkpoint_path) == row['checkpoint_sha256'], 'checkpoint bytes:' + row['state_key'])
        bound[str(checkpoint_path)] = row['checkpoint_sha256']
        with checkpoint_path.open('rb') as stream:
            payload = pickle.load(stream)
        cp = payload['checkpoint']
        original = sorted([asdict(b) for b in payload['future']], key=lambda b: (b['arrival'], b['bag_id']))
        pending = sorted([asdict(b) for values in cp.base.pending_arrivals.values() for b in values], key=lambda b: (b['arrival'], b['bag_id']))
        check(original == pending, 'true event queue:' + row['state_key'])
        check(all(b['arrival'] > cp.state.now and b['bag_id'] not in cp.state.bags for b in original), 'unobserved pending:' + row['state_key'])
        check(cp.base.phase == 'routes' and cp.cursor.pending_options is not None, 'prepared cursor:' + row['state_key'])
        check(row['continuation_sha256'] == metadata['active_continuation']['sha256'], 'continuation:' + row['state_key'])
        check(row['candidate_keys'] == metadata['candidate_keys'] and len(payload['pool']) == row['candidate_count'], 'pool:' + row['state_key'])
        actual_role = 'origin' if cp.state.trays[row['tray_id']].node == cp.state.bags[row['bag_id']].origin else 'continuation'
        check(actual_role == row['role'], 'actual role:' + row['state_key'])
        future = read(BASE / row['future_file'])
        check(future['original_future'] == original and digest(original) == future['original_future_sha256'], 'original tape:' + row['state_key'])
        supports = {}
        for bag in original:
            if bag['protected']:
                support = {'protected': True, 'total_mass': 1, 'outcomes': [{'cancel': False, 'jitter': 0, 'mass': 1}]}
            else:
                outcomes = [{'cancel': True, 'jitter': None, 'mass': 3}] + [
                    {'cancel': False, 'jitter': j, 'mass': 7} for j in (-2, 0, 2) if bag['arrival'] + j > cp.state.now]
                support = {'protected': False, 'prior_total_mass': 24, 'total_mass': sum(o['mass'] for o in outcomes), 'outcomes': outcomes}
            supports[bag['bag_id']] = support
        check(supports == future['conditional_support'], 'conditional law:' + row['state_key'])
        distinct = set()
        for block in range(2):
            seed = scenes[row['scene']] + 1000003 * block + 101 * row['decision_index']
            rng = random.Random(seed)
            saved_block = future['blocks'][block]
            check(saved_block['block'] == block and saved_block['seed'] == seed, 'block seed:' + row['state_key'])
            check(len(saved_block['tapes']) == 32, 'block size:' + row['state_key'])
            for i in range(32):
                sampled = []
                for bag in sorted(original, key=lambda b: b['bag_id']):
                    if bag['protected']:
                        sampled.append(dict(bag))
                        continue
                    support = supports[bag['bag_id']]
                    draw = rng.randrange(support['total_mass'])
                    position = 0
                    chosen = None
                    for outcome in support['outcomes']:
                        position += outcome['mass']
                        if draw < position:
                            chosen = outcome
                            break
                    if not chosen['cancel']:
                        sampled.append({**bag, 'arrival': bag['arrival'] + chosen['jitter'], 'deadline': bag['deadline'] + chosen['jitter']})
                sampled.sort(key=lambda b: (b['arrival'], b['bag_id']))
                entry = saved_block['tapes'][i]
                check(entry['index'] == i and entry['bags'] == sampled and entry['sha256'] == digest(sampled),
                      f"exact sampled tape:{row['state_key']}:{block}:{i}")
                tape_count += 1
                distinct.add(digest(sampled))
                for candidate, key in enumerate(row['candidate_keys']):
                    memo = digest({'checkpoint_sha256': row['checkpoint_sha256'], 'candidate_index': candidate,
                        'candidate_key': key, 'future_sha256': digest(sampled), 'continuation_sha256': row['continuation_sha256'],
                        'evaluation_contract': protocol['evaluation']})
                    request_key = f"{row['state_key']}_b{block}_f{i:02d}_c{candidate}"
                    expected_requests[request_key] = (row['state_key'], block, i, candidate, key, digest(sampled), memo, row['time'] + 80)
        check(len(distinct) == row['distinct_tapes'], 'distinct tape denominator:' + row['state_key'])
        check(row['logical_requests'] == row['candidate_count'] * 64 and row['unique_physical_requests'] == row['candidate_count'] * len(distinct), 'weighted denominators:' + row['state_key'])
    check(len(requests) == len(expected_requests) == 4352, 'logical requests')
    check(len({r['request_key'] for r in requests}) == len(requests), 'no duplicate logical identities')
    for request in requests:
        actual = tuple(request[k] for k in ('state_key', 'block', 'future_index', 'candidate', 'candidate_key', 'sampled_future_sha256', 'memo_key', 'minimum_observation_at'))
        check(actual == expected_requests.get(request['request_key']), 'request binding:' + request['request_key'])
        check(request['physical_key'] == 'p_' + request['memo_key'], 'physical identity:' + request['request_key'])
    check({r['memo_key'] for r in unique} == {r['memo_key'] for r in requests} and len(unique) == 2468, 'exact unique physical set')
    check(len(bridges) == 17 and {r['state_key'] for r in bridges} == {r['state_key'] for r in details if r['candidate_count']}, 'identity bridge coverage')
    check(all(r['candidate'] == r['actual_chosen_index'] for r in bridges), 'bridge actual selection')
    first = {min((r for r in details if r['scene'] == scene and r['candidate_count']), key=lambda r: (r['time'], r['decision_index']))['state_key'] for scene in scenes}
    expected_pilot = {r['request_key'] for r in requests if r['state_key'] in first and r['block'] == 0 and r['future_index'] < 2}
    check({r['request_key'] for r in pilots} == expected_pilot and len(pilots) == 24, 'fixed feature-only pilot')
    drift = [p for p, h in bound.items() if sha(p) != h]
    check(not drift, 'all read evidence unchanged')
    result = {'schema': 'ics_round8_stability_preparation_independent_audit_v1', 'checks': checks, 'failures': failures,
        'frozen_sources': len(protocol['source_sha256']), 'frozen_tests': len(protocol['test_sha256']),
        'full_attempts': len(original_rows), 'selected_with_zero_appendix': len(details), 'saved_tapes_recomputed': tape_count,
        'logical_requests': len(requests), 'unique_physical': len(unique), 'aliases_retaining_weight': len(requests) - len(unique),
        'bound_files': len(bound), 'drift': drift, 'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - start,
        'scope': 'Independent file-only stratification, seed-law/tape regeneration, actual checkpoint event queue and role, memo/request denominator recomputation. No physical replay.',
        'files_sha256': bound}
    (OUT / 'stability_preparation_audit.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'files_sha256'}))


if __name__ == '__main__':
    main()
