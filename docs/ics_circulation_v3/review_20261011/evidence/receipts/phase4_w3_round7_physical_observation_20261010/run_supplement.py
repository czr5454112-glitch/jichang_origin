"""Frozen three-scene dual-observation supplement, never overwrites old data."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter, process_time
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.experiment_resources import memory_snapshot
from scripts.experiments.ics_circulation_v3.network_role_labels import SPEC
from scripts.experiments.ics_circulation_v3.phase4_control import build_engine
from scripts.experiments.ics_circulation_v3.physical_observation import InstantPhysicalCursorSimulation
from scripts.experiments.ics_circulation_v3.routing_cache_contract import enable_replay_cache
from scripts.experiments.ics_circulation_v3.run_same_zone_supply import exact_original_scene
from scripts.experiments.ics_circulation_v3.same_zone_experiment import install_supply_policy
from scripts.experiments.ics_circulation_v3.same_zone_labels import (
    COLLECTION_BUDGET, METHOD, compare_collection, comparison_passes, run_cycle)

BASE = ROOT / 'outputs/experiments/ics_circulation_v3'
LABELS = BASE / 'phase4_w3_same_zone_labels_20261010'
REFERENCE = BASE / 'phase4_w3_same_zone_supply_repaired_20261010'
OUTPUT = Path(__file__).parent / 'supplement'
SOURCE = ROOT / 'scripts/experiments/ics_circulation_v3'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.name.endswith('.gz') else data)


def write(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def prepare():
    OUTPUT.mkdir(exist_ok=False)
    prior = load(LABELS / 'protocol.json')
    source = {name: value for name, value in prior['source_sha256'].items()}
    source['physical_observation.py'] = sha(SOURCE / 'physical_observation.py')
    inputs = dict(prior['input_sha256'])
    inputs[str(LABELS / 'protocol.json')] = sha(LABELS / 'protocol.json')
    inputs[str(ROOT / 'tests/test_ics_circulation_v3_physical_observation.py')] = sha(ROOT / 'tests/test_ics_circulation_v3_physical_observation.py')
    protocol = {'schema': 'ics_v3_detached_physical_observation_supplement_v1',
        'scenes': list(prior['scene_names']), 'workers': 3, 'source_sha256': source,
        'input_sha256': inputs, 'runner_sha256': sha(Path(__file__)),
        'intervention': 'replace only offline driver class with one-tick observer; no control change, same original policy/tape/clock/cache',
        'method': METHOD, 'budget': asdict(COLLECTION_BUDGET),
        'comparison': 'strict original collection result/non-ms/search/opportunities/cache/clocks/events/selectors and legacy compatibility projection',
        'instant_contract': 'deepcopy at each actual returned physical tick before later advance; immutable value independent of live engine',
        'task_clock_semantics': 'advance(t) prepares events at t before controller loading at t; completed <= t, non-initial loads < t',
        'reuse': 'zero new independent source groups; three additional physical deployments explicitly counted; old labels unchanged'}
    write(OUTPUT / 'protocol.json', protocol)
    verify()


def verify():
    protocol = load(OUTPUT / 'protocol.json')
    assert sha(Path(__file__)) == protocol['runner_sha256']
    for name, expected in protocol['source_sha256'].items():
        assert sha(SOURCE / name) == expected, name
    for path, expected in protocol['input_sha256'].items():
        assert sha(Path(path)) == expected, path
    return protocol


def run_scene(scene_name):
    cpu, wall = process_time(), perf_counter()
    outcome = None
    try:
        verify()
        scene = exact_original_scene(scene_name)
        base = build_engine(scene.initial, scene.forecasts, scene.future_bags, SPEC)
        enable_replay_cache(base)
        engine = InstantPhysicalCursorSimulation.from_base_checkpoint(base.checkpoint(), contract=base.control_contract)
        install_supply_policy(engine, METHOD)
        initial_loads = dict(engine.state.load_times)
        outcome = run_cycle(engine, {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}},
            minimum_observation_at=scene.horizon, budget=COLLECTION_BUDGET, retain_physical_ticks=True)
        comparison = compare_collection(load(REFERENCE / 'full' / f'{scene_name}__nominal__{METHOD}.json.gz'), outcome)
        assert comparison_passes(comparison), comparison
        assert outcome['status'] == 'controller_quiescent'
        instant = engine.instant_physical_ticks
        legacy = outcome['physical_tick_trace']
        assert len(instant) == len(legacy)
        maps = ('completed', 'load_times', 'empty_targets')
        mismatches = {key: 0 for key in maps}
        final = outcome['result']['final_snapshot']
        for current, historical in zip(instant, legacy):
            assert {k: v for k, v in current.items() if k not in maps} == {k: v for k, v in historical.items() if k not in maps}
            for key in maps:
                mismatches[key] += current[key] != historical[key]
            assert current['completed'] == {k: v for k, v in final['completed'].items() if v <= current['time']}
            assert current['load_times'] == {**initial_loads,
                **{k: v for k, v in final['load_times'].items() if v < current['time']}}
        assert instant[-1] == legacy[-1]
        before = json.dumps(instant, sort_keys=True)
        # Deliberately mutate only after evaluation to prove no post-run alias;
        # never continue or use this destroyed audit engine for another action.
        engine.state.completed['__observer_alias_negative_probe__'] = engine.state.now + 100
        engine.state.load_times['__observer_alias_negative_probe__'] = engine.state.now + 99
        engine.state.empty_targets['__observer_alias_negative_probe__'] = '__audit_only__'
        assert json.dumps(instant, sort_keys=True) == before
        # Restore audit probes because legacy result references some mappings.
        for values in (engine.state.completed, engine.state.load_times, engine.state.empty_targets):
            del values['__observer_alias_negative_probe__']
        verify()
        target = OUTPUT / f'{scene_name}.json.gz'
        with target.open('xb') as stream:
            stream.write(gzip.compress(json.dumps({'scene': scene_name, 'legacy_result': outcome,
                'instant_physical_ticks': instant, 'replication': comparison,
                'legacy_alias_mismatch_ticks': mismatches}, ensure_ascii=False).encode('utf-8'), mtime=0))
        return {'scene': scene_name, 'status': 'passed', 'physical_calls': 1,
            'ticks': len(instant), 'legacy_alias_mismatch_ticks': mismatches,
            'replication': comparison, 'file': target.name, 'sha256': sha(target),
            'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
            'memory': memory_snapshot()}
    except Exception as error:
        failure = {'scene': scene_name, 'status': 'failure', 'error': str(error), 'traceback': traceback.format_exc(),
            'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
            'outcome_status': None if outcome is None else outcome['status']}
        write(OUTPUT / f'{scene_name}.failure.json', failure)
        return failure


def run():
    cpu, wall = process_time(), perf_counter()
    protocol = verify()
    rows = []
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        for future in as_completed([pool.submit(run_scene, name) for name in protocol['scenes']]):
            row = future.result()
            rows.append(row)
            print(json.dumps(row), flush=True)
    verify()
    summary = {'rows': rows, 'case_cpu_seconds': sum(r['cpu_seconds'] for r in rows),
        'parent_cpu_seconds': process_time() - cpu, 'wall_makespan_seconds': perf_counter() - wall,
        'all_passed': all(r['status'] == 'passed' for r in rows)}
    write(OUTPUT / 'summary.json', summary)
    write(OUTPUT / 'manifest.json', {p.name: sha(p) for p in OUTPUT.iterdir() if p.is_file()})
    return 0 if summary['all_passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare', 'run'), required=True)
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare()
    else:
        raise SystemExit(run())
