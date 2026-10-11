"""Full actual-decision census; no counterfactual values or outcome selection."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
from time import process_time, perf_counter
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.experiment_protocol import write_new_json as save
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    SPEC, SearchBudget, bind_accounting, observed_role, physical_prefix_signature)
from scripts.experiments.ics_circulation_v3.network_full_cycle import compare_old_result
from scripts.experiments.ics_circulation_v3.phase4_control import build_engine, digest
from scripts.experiments.ics_circulation_v3.phase4_network_workloads import load_network, make_workload, file_sha
from scripts.experiments.ics_circulation_v3.role_coverage import CursorSimulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, actual_action_key
from scripts.experiments.ics_circulation_v3.run_network_role_labels import SOURCES

OUT = Path(__file__).parent
PRIOR = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_network_role_labels_parallel_20261009'
CODE = ROOT / 'scripts/experiments/ics_circulation_v3'
SCENES = ('cross_cycle', 'counterflow', 'near_full')


def worker(name):
    started, cpu = perf_counter(), process_time()
    folder = PRIOR / name
    old = json.loads((folder / (name + '_collection.json')).read_text())
    network, provenance = load_network(folder / 'original_profile.json')
    scene = make_workload(name, network, provenance, rounds=3)
    old_inputs = json.loads((folder / (name + '_input.json')).read_text())
    actual_inputs = json.loads(json.dumps({'initial': asdict(scene.initial),
        'forecasts': [asdict(f) for f in scene.forecasts],
        'future_engine_only': [asdict(b) for b in scene.future_bags], 'horizon': scene.horizon}))
    assert all(old_inputs[k] == v for k, v in actual_inputs.items())
    sampled = {r['identity'] for r in old['opportunities'] if r['sampled']}
    base = build_engine(scene.initial, scene.forecasts, scene.future_bags, SPEC)
    enable_replay_cache(base)
    engine = CursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
    counter = bind_accounting(engine, SearchBudget())
    rows = []

    def record(current, tray, options):
        state = current.state
        bag = state.bags[tray.bag_id]
        prefixes = [ExecutionValidator._safe_prefix(state, p) for p in options]
        # Geometry and timestamps are deliberately separated. A legal wait
        # is a real action, but not evidence of a different spatial route.
        geometry = [tuple(leg.edge_id for leg in p.legs) for p in prefixes]
        timed = [physical_prefix_signature(state, p) for p in options]
        witnesses = [tuple(leg.edge_id for leg in p.legs) for p in options]
        identity = f'{name}:network_timed:d{len(rows)}:t{state.now}:{bag.bag_id}:{tray.node}'
        rows.append({'identity': identity, 'time': state.now, 'source_node': tray.node,
            'role': observed_role(state, tray), 'protected': bag.protected,
            'bag_id': bag.bag_id, 'tray_id': tray.tray_id,
            'original_role_sample': identity in sampled,
            'candidate_count': len(options),
            'actual_action_distinct': len({actual_action_key(state, p, route_mode='next_edge') for p in options}),
            'timed_prefix_distinct': len(set(timed)), 'prefix_geometry_distinct': len(set(geometry)),
            'full_witness_geometry_distinct': len(set(witnesses)),
            'positive_outdegree': sum(e.source == tray.node and e.capacity > 0 for e in network.edges.values()),
            'loaded_trays': sum(t.bag_id is not None for t in state.trays.values()),
            'empty_plan_count': sum(p.bag_id is None for p in state.plans.values()),
            'waiting_bags': sum(b not in state.load_times and b not in state.completed for b in state.bags),
            'state_sha256': digest(asdict(state)),
            'prefix_geometries': geometry, 'candidate_first_departures': [p.legs[0].depart if p.legs else state.now for p in options],
            'candidates': [asdict(p) for p in options]})

    engine._decision_callback = record
    while engine.state.now < scene.horizon:
        counter.check()
        engine.advance(engine.state.now + 1)
    equal = compare_old_result(old['result'], engine.result())
    assert equal['equal'], equal
    assert [r['identity'] for r in rows] == [r['identity'] for r in old['opportunities']]
    assert len(sampled) == sum(r['original_role_sample'] for r in rows)
    groups = {}
    for role in ('origin', 'continuation', 'arrival_at_destination', 'all'):
        for selected in (False, True):
            subset = [r for r in rows if (role == 'all' or r['role'] == role)
                      and (not selected or r['original_role_sample'])]
            groups[f'{role}:original_sample_only={selected}'] = {
                'attempts': len(subset), 'zero_candidates': sum(r['candidate_count'] == 0 for r in subset),
                'protected_attempts': sum(r['protected'] for r in subset),
                'multiple_actions': sum(r['actual_action_distinct'] > 1 for r in subset),
                'multiple_timed_prefixes': sum(r['timed_prefix_distinct'] > 1 for r in subset),
                'multiple_prefix_geometries': sum(r['prefix_geometry_distinct'] > 1 for r in subset),
                'multiple_witness_geometries': sum(r['full_witness_geometry_distinct'] > 1 for r in subset),
                'nodes_with_spatial_choice': sorted({r['source_node'] for r in subset if r['prefix_geometry_distinct'] > 1})}
    result = {'scene': name, 'rows': rows, 'groups': groups, 'old_episode_result_comparison': equal,
        'search_calls': len(counter.rows), 'search_work': counter.work,
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - started}
    save(OUT / (name + '.json'), result)
    return {k: v for k, v in result.items() if k != 'rows'}


def main():
    start, cpu = perf_counter(), process_time()
    names = sorted(set(SOURCES) | {'network_full_cycle.py'})
    hashes = {name: file_sha(CODE / name) for name in names}
    inputs = {str((PRIOR / scene / file).relative_to(ROOT)): file_sha(PRIOR / scene / file)
        for scene in SCENES for file in (scene + '_collection.json', scene + '_input.json', 'original_profile.json')}
    save(OUT / 'protocol.json', {'purpose': 'separate conditional witness diversity, timed physical prefix diversity and spatial routing diversity over every actual decision',
        'source_sha256': hashes, 'input_sha256': inputs, 'script_sha256': file_sha(__file__),
        'scenes': SCENES, 'spec': asdict(SPEC), 'selection': 'all actual attempts including zero and protected; original18 sample marks retained',
        'no_new_labels': True, 'no_policy_change': True, 'no_outcome_based_sampling': True})
    with ProcessPoolExecutor(max_workers=3) as pool:
        cases = list(pool.map(worker, SCENES))
    save(OUT / 'summary.json', {'scenes': cases, 'source_unchanged': all(file_sha(CODE / n) == h for n, h in hashes.items()),
        'input_unchanged': all(file_sha(ROOT / n) == h for n, h in inputs.items()),
        'parent_cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - start,
        'worker_cpu_seconds': sum(r['cpu_seconds'] for r in cases)})
    save(OUT / 'manifest.json', {p.name: file_sha(p) for p in OUT.iterdir() if p.is_file()})


if __name__ == '__main__':
    main()
