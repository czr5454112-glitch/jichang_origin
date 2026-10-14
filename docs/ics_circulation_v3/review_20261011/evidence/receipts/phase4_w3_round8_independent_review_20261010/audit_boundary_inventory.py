"""Outcome-blind independent reconstruction of the six boundary cells."""
from pathlib import Path
from dataclasses import asdict, replace
from fractions import Fraction
import hashlib
import json
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).parent
BASE = HERE.parent
INVENTORY = BASE / 'phase4_w3_round8_conditional_boundary_inventory_20261010'
STABILITY = BASE / 'phase4_w3_same_zone_stability_20261010'
LABELS = BASE / 'phase4_w3_same_zone_labels_20261010'
bound, failures, checks = {}, [], 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check(okay, message):
    global checks
    checks += 1
    if not okay:
        failures.append(message)


def read(path, expected=None):
    path = Path(path)
    actual = sha(path)
    if expected is not None:
        check(actual == expected, 'SHA:' + str(path))
    bound[str(path)] = actual
    return json.loads(path.read_text(encoding='utf8'))


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    manifest = read(INVENTORY / 'manifest.json')
    for name, expected in manifest.items():
        path = INVENTORY / name
        check(sha(path) == expected, 'inventory frozen:' + name)
        bound[str(path)] = expected
    inventory = read(INVENTORY / 'analysis.json')
    prep = read(STABILITY / 'preparation_manifest.json')
    protocol = read(STABILITY / 'protocol.json', prep['protocol.json'])
    old_manifest_path = LABELS / 'collection_run/manifest.json'
    old_manifest = read(old_manifest_path, protocol['input_sha256'][str(old_manifest_path)])
    attempts = read(STABILITY / 'inventory.json', prep['inventory.json'])['attempts']
    for name, expected in inventory['bound_inputs'].items():
        path = ROOT / name
        check(sha(path) == expected, 'retained source/input:' + name)
        bound[str(path)] = expected
    check(len(attempts) == 180 and len({(r['scene'], r['decision_index']) for r in attempts}) == 180,
          'complete unique source attempt denominator')
    indexed = {r['state_key']: r for r in inventory['attempts']}
    calculated, materials = [], {}
    for row in attempts:
        key = f"{row['scene']}_d{row['decision_index']:04d}"
        metadata = read(LABELS / row['metadata_file'], old_manifest[row['metadata_file']])
        path = LABELS / row['checkpoint_file']
        check(sha(path) == row['checkpoint_sha256'] == old_manifest[row['checkpoint_file']], key + ':checkpoint original bytes')
        bound[str(path)] = row['checkpoint_sha256']
        with path.open('rb') as stream:
            payload = pickle.load(stream)
        cp, pending = payload['checkpoint'], sorted(payload['future'], key=lambda b: (b.arrival, b.bag_id))
        state, cursor = cp.state, cp.cursor
        queued = sorted((b for bs in cp.base.pending_arrivals.values() for b in bs), key=lambda b: (b.arrival, b.bag_id))
        check(pending == queued and len({b.bag_id for b in pending}) == len(pending), key + ':entire queue')
        check(all(b.arrival > state.now and b.bag_id not in state.bags for b in pending), key + ':strictly unobserved')
        check(cp.phase == 'routes' and cursor.pending_options is not None, key + ':genuine routing callback')
        tray = state.trays[cursor.pending_tray_id]
        bag = state.bags[tray.bag_id]
        role = 'arrival_at_destination' if tray.node == bag.destination else 'origin' if tray.node == bag.origin else 'continuation'
        check(role == row['role'] and state.now == row['time'], key + ':public role and time')
        check(digest(asdict(state)) == metadata['state_sha256'] and digest(asdict(cursor)) == digest(metadata['cursor']), key + ':actual state/cursor')
        k = len(cursor.pending_options)
        check(k == row['candidate_count'] and tuple(cursor.pending_options) == tuple(payload['pool']), key + ':K/pool')
        boundary = [b for b in pending if not b.protected and b.arrival in (state.now + 1, state.now + 2)]
        calculated.append({'state_key': key, 'scene': row['scene'], 'role': role, 'time': state.now,
                           'decision_index': row['decision_index'], 'candidate_count': k,
                           'boundary': boundary, 'eligible': bool(k and boundary)})
        observed = indexed[key]
        check(observed['eligible'] == bool(k and boundary), key + ':eligibility independently reconstructed')
        check(observed['boundary_tasks'] == [{'bag_id': b.bag_id, 'arrival': b.arrival, 'arrival_minus_now': b.arrival-state.now} for b in boundary], key + ':all boundary identities')
        materials[key] = (state, pending, metadata)
    cells, selected = [], []
    for scene in ('cross_cycle', 'counterflow', 'near_full'):
        for role in ('origin', 'continuation'):
            rows = sorted((r for r in calculated if r['scene'] == scene and r['role'] == role), key=lambda r: (r['time'], r['decision_index']))
            eligible = [r for r in rows if r['eligible']]
            cell = {'scene': scene, 'role': role, 'attempts': len(rows),
                    'nonempty_attempts': sum(r['candidate_count'] > 0 for r in rows),
                    'zero_candidate_attempts': sum(r['candidate_count'] == 0 for r in rows),
                    'attempts_with_boundary_tasks': sum(bool(r['boundary']) for r in rows),
                    'eligible_attempts': len(eligible), 'eligible_state_keys': [r['state_key'] for r in eligible],
                    'selected_state_key': eligible[0]['state_key'] if eligible else None,
                    'missing_reason': None if eligible else 'no_nonempty_actual_cursor_with_soft_pending_offset_1_or_2'}
            cells.append(cell)
            if eligible:
                selected.append(eligible[0])
    check(cells == inventory['cells'], 'all six cells and missing denominations')
    check([r['state_key'] for r in selected] == [r['state_key'] for r in inventory['selected']], 'earliest eligible selection')
    for row, saved in zip(selected, inventory['selected']):
        state, pending, metadata = materials[row['state_key']]
        target = row['boundary'][0]
        check(asdict(target) == saved['target'], row['state_key'] + ':earliest boundary task')
        check(not target.protected and target.arrival - 2 <= state.now, row['state_key'] + ':minus two excluded')
        check([asdict(b) for b in pending] == saved['original_pending'], row['state_key'] + ':other pending exact')
        denominator = Fraction(3, 24) + sum(Fraction(7, 24) for j in (-2, 0, 2) if target.arrival+j > state.now)
        check(denominator == Fraction(17, 24), row['state_key'] + ':condition event mass')
        for outcome, shift, mass in zip(saved['finite_outcomes'], (None, 0, 2), (3, 7, 7)):
            tape = [b for b in pending if b.bag_id != target.bag_id]
            if shift is not None:
                tape.append(replace(target, arrival=target.arrival+shift, deadline=target.deadline+shift))
            tape = [asdict(b) for b in sorted(tape, key=lambda b: (b.arrival, b.bag_id))]
            check(outcome['pending'] == tape and digest(tape) == outcome['future_sha256'], row['state_key'] + ':' + str(shift) + ':finite tape')
            check(outcome['mass'] == mass and Fraction(outcome['probability_fraction']) == Fraction(mass, 24) / denominator,
                  row['state_key'] + ':' + str(shift) + ':conditional fraction')
    counts = {'attempts': len(calculated), 'nonempty': sum(bool(r['candidate_count']) for r in calculated),
              'zero': sum(not r['candidate_count'] for r in calculated), 'cells': len(cells),
              'missing_cells': sum(r['selected_state_key'] is None for r in cells),
              'selected_states': len(selected), 'prospective_tapes': 3*len(selected),
              'prospective_physical_continuations': sum(3*r['candidate_count'] for r in selected)}
    check(counts == inventory['counts'], 'complete denominators')
    drift = [p for p, expected in bound.items() if sha(p) != expected]
    check(not drift, 'all files unchanged')
    result = {'schema': 'round8_boundary_inventory_independent_audit_v1', 'checks': checks, 'failures': failures,
              'counts': counts, 'cells': cells, 'drift': drift, 'physical_simulations': 0,
              'cpu_seconds': time.process_time()-cpu, 'wall_seconds': time.perf_counter()-wall,
              'files_sha256': bound, 'source_sha256': sha(__file__),
              'scope': 'All 180 original checkpoint queues and public roles independently reconstructed. Exact finite fractions/tapes, six cells and four missing cells; no J, regret, branch outcome, routing search or advance read/invoked. Original collection manifest additionally matched to frozen stability input SHA.'}
    target = HERE / 'boundary_inventory_audit.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files_sha256', 'cells')}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
