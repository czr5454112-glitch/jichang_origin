"""Independent exact Cartesian support-set check for the six exhaustive states."""
import hashlib
from itertools import product
import json
from pathlib import Path
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'phase4_w3_same_zone_stability_20261010'


def canonical(bags):
    return json.dumps(sorted(bags, key=lambda b: (b['arrival'], b['bag_id'])), sort_keys=True, separators=(',', ':'), allow_nan=False)


def main():
    cpu, wall = process_time(), perf_counter()
    support = json.loads((HERE / 'future_support.json').read_bytes())
    rows = []
    for row in support['states']:
        path = SOURCE / 'futures' / (row['state_key'] + '.json')
        data = json.loads(path.read_bytes())
        seen = {canonical(t['bags']) for b in data['blocks'] for t in b['tapes']}
        assert len(seen) == row['sampled_distinct_tapes']
        for b in data['blocks']:
            for t in b['tapes']:
                assert hashlib.sha256(canonical(t['bags']).encode()).hexdigest() == t['sha256']
        expected = None
        if row['exhaustive_support']:
            options = []
            for bag in data['original_future']:
                if bag['protected']:
                    options.append([bag])
                else:
                    options.append([None] + [{**bag, 'arrival': bag['arrival'] + j, 'deadline': bag['deadline'] + j}
                        for j in (-2, 0, 2) if bag['arrival'] + j > data['now']])
            expected = {canonical([b for b in tape if b is not None]) for tape in product(*options)}
            assert expected == seen and len(expected) == row['support_size']
        rows.append({'state_key': row['state_key'], 'canonical_seen': len(seen),
                     'cartesian_exact': None if expected is None else expected == seen,
                     'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {'rows': rows, 'failures': [], 'physical_simulations': 0,
        'support_file_sha256': hashlib.sha256((HERE / 'future_support.json').read_bytes()).hexdigest(),
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'scope': 'All 1472 canonical tape SHA values checked; six claimed exhaustive supports independently enumerated. No outcome cost read.'}
    with (HERE / 'support_set_validation.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
