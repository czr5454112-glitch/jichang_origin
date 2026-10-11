"""Pure-file, outcome-blind inventory of real conditional-support boundaries."""
from pathlib import Path
from time import process_time, perf_counter
from hashlib import sha256
from dataclasses import asdict, replace
import json
import pickle
import sys
import traceback

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'scripts/experiments/ics_circulation_v3').is_dir())
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.role_coverage import digest
from scripts.experiments.ics_circulation_v3.network_role_labels import observed_role
from scripts.experiments.ics_circulation_v3.same_zone_stability import (
    conditional_support, validate_original_pending, validate_sampled_future, tape_sha)

BASE = ROOT / 'outputs/experiments/ics_circulation_v3'
LABELS = BASE / 'phase4_w3_same_zone_labels_20261010'
STABILITY = BASE / 'phase4_w3_same_zone_stability_20261010'
HERE = Path(__file__).parent
SCENES = ('cross_cycle', 'counterflow', 'near_full')
ROLES = ('origin', 'continuation')


def main():
    cpu, wall = process_time(), perf_counter()
    result_path = HERE / 'analysis.json'
    if result_path.exists():
        raise FileExistsError(result_path)
    bindings, checks = {}, []

    def bound_bytes(path, expected=None):
        raw = path.read_bytes()
        actual = sha256(raw).hexdigest()
        if expected is not None and actual != expected:
            raise ValueError('SHA binding failed: ' + str(path))
        bindings[str(path.relative_to(ROOT))] = actual
        return raw

    def read(path, expected=None):
        return json.loads(bound_bytes(path, expected).decode('utf-8-sig'))

    def check(name, condition):
        checks.append({'name': name, 'okay': bool(condition)})
        if not condition:
            raise ValueError(name)

    try:
        bound_bytes(Path(__file__))
        bound_bytes(HERE / 'SELECTION_RULE.md')
        prep = read(STABILITY / 'preparation_manifest.json')
        protocol = read(STABILITY / 'protocol.json', prep['protocol.json'])
        manifest = read(LABELS / 'collection_run/manifest.json')
        inventory = read(STABILITY / 'inventory.json', prep['inventory.json'])
        # The imported objects are from the exact frozen source closure. No
        # simulation method is invoked; unpickling only reads trusted originals.
        for name, expected in protocol['source_sha256'].items():
            bound_bytes(ROOT / 'scripts/experiments/ics_circulation_v3' / name, expected)
        for name, expected in protocol['test_sha256'].items():
            bound_bytes(ROOT / 'tests' / name, expected)
        cpp = ROOT / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
        bound_bytes(cpp, protocol['input_sha256'][str(cpp)])
        for file in ('collection_run/summary.json',):
            # Bytes only: the summary's results are not selection inputs.
            bound_bytes(LABELS / file, manifest[file.replace('/', '\\')])

        rows, materials = [], {}
        attempts = inventory['attempts']
        check('all_original_attempts', len(attempts) == 180)
        check('unique_attempts', len({(a['scene'], a['decision_index']) for a in attempts}) == 180)
        allowed = ('scene', 'decision_index', 'time', 'node', 'bag_id', 'tray_id',
                   'role', 'candidate_count', 'metadata_file', 'metadata_sha256',
                   'checkpoint_file', 'checkpoint_sha256', 'future_sha256')
        for original in sorted(attempts, key=lambda a: (SCENES.index(a['scene']), a['time'], a['decision_index'])):
            row = {k: original[k] for k in allowed}
            key = row['state_key'] = f"{row['scene']}_d{row['decision_index']:04d}"
            for field in ('metadata', 'checkpoint'):
                check(key + ':' + field + '_source_manifest',
                      manifest[row[field + '_file']] == row[field + '_sha256'])
            metadata = read(LABELS / row['metadata_file'], row['metadata_sha256'])
            payload = pickle.loads(bound_bytes(LABELS / row['checkpoint_file'], row['checkpoint_sha256']))
            checkpoint, pending = payload['checkpoint'], tuple(payload['future'])
            state, cursor = checkpoint.state, checkpoint.cursor
            pending = validate_original_pending(state, pending)
            queued = tuple(sorted((b for bags in checkpoint.base.pending_arrivals.values() for b in bags),
                                  key=lambda b: (b.arrival, b.bag_id)))
            check(key + ':pending_queue_exact', queued == pending)
            check(key + ':pending_sha', tape_sha(pending) == row['future_sha256'] == metadata['future_sha256'])
            check(key + ':actual_loaded_cursor', checkpoint.phase == 'routes' and cursor.pending_options is not None
                  and cursor.pending_tray_id == row['tray_id'] and state.now == row['time'])
            check(key + ':state_sha', digest(asdict(state)) == metadata['state_sha256'])
            check(key + ':cursor_exact', digest(asdict(cursor)) == digest(metadata['cursor']))
            check(key + ':pool_exact', digest([asdict(p) for p in payload['pool']]) == digest(metadata['candidates'])
                  == digest([asdict(p) for p in cursor.pending_options]))
            check(key + ':candidate_count', len(cursor.pending_options) == row['candidate_count'])
            tray = state.trays[row['tray_id']]
            check(key + ':public_role', observed_role(state, tray) == row['role'])
            check(key + ':current_loaded_identity', tray.bag_id == row['bag_id'])
            boundary = [b for b in pending if not b.protected and b.arrival - state.now in (1, 2)]
            row.update(pending_count=len(pending), protected_pending_count=sum(b.protected for b in pending),
                soft_pending_count=sum(not b.protected for b in pending),
                boundary_tasks=[{'bag_id': b.bag_id, 'arrival': b.arrival, 'arrival_minus_now': b.arrival-state.now}
                                for b in boundary],
                eligible=bool(row['candidate_count'] and boundary),
                cursor={'phase': checkpoint.phase, **asdict(cursor)})
            # Avoid copying candidate dataclasses into the compact inventory.
            row['cursor']['pending_options'] = {'candidate_count': len(cursor.pending_options)}
            rows.append(row)
            if row['eligible']:
                materials[key] = (pending, state, metadata, boundary[0])

        cells, selected = [], []
        for scene in SCENES:
            for role in ROLES:
                all_rows = [r for r in rows if r['scene'] == scene and r['role'] == role]
                eligible = [r for r in all_rows if r['eligible']]
                first = eligible[0] if eligible else None
                cells.append({'scene': scene, 'role': role, 'attempts': len(all_rows),
                    'nonempty_attempts': sum(r['candidate_count'] > 0 for r in all_rows),
                    'zero_candidate_attempts': sum(r['candidate_count'] == 0 for r in all_rows),
                    'attempts_with_boundary_tasks': sum(bool(r['boundary_tasks']) for r in all_rows),
                    'eligible_attempts': len(eligible),
                    'eligible_state_keys': [r['state_key'] for r in eligible],
                    'selected_state_key': None if first is None else first['state_key'],
                    'missing_reason': 'no_nonempty_actual_cursor_with_soft_pending_offset_1_or_2' if first is None else None})
                if first is None:
                    continue
                pending, state, meta, target = materials[first['state_key']]
                support = conditional_support(target, state.now)
                expected = [{'cancel': True, 'jitter': None, 'mass': 3},
                            {'cancel': False, 'jitter': 0, 'mass': 7},
                            {'cancel': False, 'jitter': 2, 'mass': 7}]
                check(first['state_key'] + ':exact_3_17_support', support['total_mass'] == 17 and support['outcomes'] == expected)
                outcomes = []
                for outcome in expected:
                    tape = [b for b in pending if b.bag_id != target.bag_id]
                    if not outcome['cancel']:
                        j = outcome['jitter']
                        tape.append(replace(target, arrival=target.arrival+j, deadline=target.deadline+j))
                    tape = validate_sampled_future(state, pending, tape)
                    same_other = tuple(b for b in tape if b.bag_id != target.bag_id) == tuple(b for b in pending if b.bag_id != target.bag_id)
                    same_protected = tuple(b for b in tape if b.protected) == tuple(b for b in pending if b.protected)
                    check(first['state_key'] + ':' + str(outcome) + ':non_target_exact', same_other)
                    check(first['state_key'] + ':' + str(outcome) + ':protected_exact', same_protected)
                    outcomes.append({**outcome, 'probability_fraction': f"{outcome['mass']}/17",
                        'future_sha256': tape_sha(tape), 'pending': [asdict(b) for b in tape],
                        'non_target_exact': same_other, 'protected_exact': same_protected,
                        'legal_pending_future': True})
                selected.append({**first, 'target': asdict(target),
                    'original_pending': [asdict(b) for b in pending],
                    'candidate_keys': meta['candidate_keys'],
                    'checkpoint_fingerprint': meta['checkpoint_fingerprint'],
                    'continuation_sha256': meta['active_continuation']['sha256'],
                    'published_slow_forecasts_sha256': digest(meta['published_slow_forecasts']),
                    'forecast_publications_sha256': digest(meta['active_continuation']['forecast_publications']),
                    'routing_forecast_publications_sha256': digest(meta['active_continuation']['routing_forecast_publications']),
                    'conditional_support': support, 'finite_outcomes': outcomes,
                    'prospective_physical_continuations': 3 * first['candidate_count']})
        check('all_six_cells_retained', len(cells) == 6)
        check('all_zero_attempts_retained', sum(r['candidate_count'] == 0 for r in rows) == 6)
        # All source/input bytes are checked again, without invoking controllers.
        for path, expected in list(bindings.items()):
            check('unchanged:' + path, sha256((ROOT / path).read_bytes()).hexdigest() == expected)
        result = {'schema': 'ics_round8_single_pending_boundary_inventory_v1',
            'scope': 'public time/role plus original engine-only pending metadata; no costs, labels, regret or branch outcomes',
            'selection_rule': 'SELECTION_RULE.md', 'attempts': rows, 'cells': cells,
            'selected': selected, 'zero_candidate_inventory': [r for r in rows if not r['candidate_count']],
            'counts': {'attempts': len(rows), 'nonempty': sum(bool(r['candidate_count']) for r in rows),
                'zero': sum(not r['candidate_count'] for r in rows), 'cells': len(cells),
                'missing_cells': sum(c['selected_state_key'] is None for c in cells),
                'selected_states': len(selected), 'prospective_tapes': 3*len(selected),
                'prospective_physical_continuations': sum(r['prospective_physical_continuations'] for r in selected)},
            'physical_calls': 0, 'routing_search_calls': 0, 'engine_advance_calls': 0,
            'checks': checks, 'failed_checks': sum(not c['okay'] for c in checks),
            'source_input_unchanged': True, 'bound_inputs': bindings,
            'cpu_seconds': process_time()-cpu, 'wall_seconds': perf_counter()-wall,
            'resource_scope': 'Pure file hash/read/unpickle/structural validation/finite tape construction; measured after imports and before final JSON/MD/manifest writes. No physical replay.'}
        result_path.write_text(json.dumps(result, indent=2), encoding='utf8')
        lines = ['# Real conditional-boundary inventory', '',
            'Fixed outcome-blind selection over all 180 actual Round7 loaded attempts. No simulation or routing search was run. The original 4,352-request main stability experiment is unchanged.', '',
            '| Scene | Role | Attempts | K=0 | Eligible | Selected | Time | K | Boundary task | Offset |',
            '|---|---|---:|---:|---:|---|---:|---:|---|---:|']
        by_key = {r['state_key']: r for r in selected}
        for cell in cells:
            row = by_key.get(cell['selected_state_key'])
            values = ['—']*5 if row is None else [row['state_key'], row['time'], row['candidate_count'], row['target']['bag_id'], row['target']['arrival']-row['time']]
            lines.append('| ' + ' | '.join(map(str, [cell['scene'],cell['role'],cell['attempts'],cell['zero_candidate_attempts'],cell['eligible_attempts'],*values])) + ' |')
        lines += ['', f"Selected {len(selected)} states; missing cells {result['counts']['missing_cells']}; all six K=0 attempts are preserved in analysis.json. Prospective grid: {result['counts']['prospective_physical_continuations']} full-candidate physical continuations over {3*len(selected)} distinct per-state finite tapes, if authorized separately. Actual physical calls: **0**.", '',
            'At each selected post-arrivals loaded cursor, target arrival minus now is 1 or 2. The −2 outcome would already have been observed (arrival ≤ now), so it is excluded; cancellation has mass 3/17, unchanged arrival 7/17, and +2 arrival/deadline 7/17. All other pending tasks remain their exact original entries, including every protected task. No forecast or controller state was modified.', '',
            'This finite single-task conditional slice is a mechanism supplement. It is neither the original 64-draw joint sampling experiment nor a calibrated new joint future law; 3*K is an execution plan, not independent business sample count. Missing cells remain missing, and no costs or old regret were consulted.', '',
            f"Read-only measured CPU {result['cpu_seconds']:.6f}s / wall {result['wall_seconds']:.6f}s; {len(checks)} checks, {result['failed_checks']} errors. Imports, authoring and final output writes are outside the measured interval. All checkpoint/metadata/input/source hashes and full legal tapes are in analysis.json."]
        (HERE / 'INVENTORY.md').write_text('\n'.join(lines)+'\n', encoding='utf8')
        (HERE / 'manifest.json').write_text(json.dumps({p.name: sha256(p.read_bytes()).hexdigest()
            for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'manifest.json'}, indent=2), encoding='utf8')
        print(json.dumps({**result['counts'], 'cpu_seconds': result['cpu_seconds'], 'failed_checks': result['failed_checks']}))
    except Exception as error:
        failure = {'status': 'failed', 'failure': {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()},
            'checks': checks, 'bound_inputs': bindings, 'physical_calls': 0,
            'cpu_seconds': process_time()-cpu, 'wall_seconds': perf_counter()-wall}
        (HERE / 'failure.json').write_text(json.dumps(failure, indent=2), encoding='utf8')
        raise


if __name__ == '__main__':
    main()
