"""Bounded cache-contract reproduction; no learning or performance claim.

Run with ``python -m scripts.experiments.ics_circulation_v3.run_routing_cache_contract
--output outputs/experiments/ics_circulation_v3/phase4_w3_cache_contract_20261009/isolated_replay``.
An existing nonempty output is refused. Historical legacy_initial is untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time

from . import routing_reference  # Preload the actual dynamic search dependency.
from .experiment_resources import memory_snapshot
from .label_stability import sustained_scenes
from .model import Bag, Edge, Network, Node, Reservation, Snapshot, Tray
from .phase4_control import ControlSpec
from .role_coverage import CursorSimulation, RoleQuota, branch_role_decision, collect_role_decisions
from .routing import RegionalCandidateGenerator, clear_static_cache
from .routing_cache_contract import CACHE_CONTRACT, routing_cache_state
from .runtime import ExecutionValidator


def fixture(complex=False, empty=False):
    nodes = {n: Node(n, 'z', 'p') for n in ('A', 'B')}
    edges = {'AB': Edge('AB', 'A', 'B', 1)}
    if complex:
        nodes.update(C=Node('C', 'z', 'p', can_wait=False), D=Node('D', 'z', 'q'))
        edges.update(AC=Edge('AC', 'A', 'C', 1), CB=Edge('CB', 'C', 'B', 1),
                     AD=Edge('AD', 'A', 'D', 2), DB=Edge('DB', 'D', 'B', 1))
    state = Snapshot(0, Network(nodes, edges), {'t': Tray('t', 'A') if empty else Tray('t', 'A', 'loaded', 'b')},
                     {} if empty else {'b': Bag('b', 'A', 'B', 0, 20)})
    if complex:
        state.trays['other'] = Tray('other', 'B')
        state.reservations = (Reservation('edge:AB', 0, 3, 'other'), Reservation('edge:CB', 0, 3, 'other'))
    return state


def factory(budget=1000, *, dynamic=True, isolated=True):
    return RegionalCandidateGenerator(horizon=8, expansion_limit=budget, deadline_ms=None,
        dynamic_local=dynamic, cache_contract=CACHE_CONTRACT if isolated else None)


def query(generator, state, *, empty=False, k=4):
    candidates = (generator.generate_empty(state, 't', 'B', k=k) if empty
                  else generator.generate(state, 'b', 't', k=k))
    legality = [asdict(ExecutionValidator().validate(state, item)) for item in candidates]
    if any(not entry['accepted'] for entry in legality):
        raise AssertionError('Generator returned an illegal candidate')
    return {'semantic': {'candidates': [asdict(c) for c in candidates],
        'status': generator.last_search_status, 'logical_work': generator.last_expansions,
        'logical_work_by_stage': deepcopy(generator.last_diagnostics['work_units_by_stage'])},
        'diagnostics': deepcopy(generator.last_diagnostics), 'validator': legality}


def run(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing nonempty output directory')
    output.mkdir(parents=True, exist_ok=True)
    sources = {Path(module.__file__).resolve() for name, module in tuple(sys.modules.items())
               if name.startswith('scripts.experiments.ics_circulation_v3.') and getattr(module, '__file__', None)}
    sources.add(Path(__file__).resolve())
    frozen = {path.name: path.read_bytes() for path in sorted(sources)}
    archive = output / 'source_snapshot'
    archive.mkdir()
    for name, content in frozen.items():
        (archive / name).write_bytes(content)
    before_memory = memory_snapshot()
    started, cpu = perf_counter(), process_time()
    legacy, boundaries = [], []
    query_count = 0
    for dynamic in (False, True):
        state = fixture()
        clear_static_cache()
        cold = query(factory(5, dynamic=dynamic, isolated=False), state, k=1)
        query(factory(dynamic=dynamic, isolated=False), state, k=1)
        warm = query(factory(5, dynamic=dynamic, isolated=False), state, k=1)
        query_count += 3
        legacy.append({'dynamic_local': dynamic, 'budget': 5, 'cold': cold, 'foreign_warmed': warm})
        assert len(cold['semantic']['candidates']) == 0 and len(warm['semantic']['candidates']) == 1
        for complex in (False, True):
            for empty in (False, True):
                state = fixture(complex, empty)
                generator = factory(dynamic=dynamic)
                full = query(generator, state, empty=empty)
                query_count += 1
                assert full['semantic']['candidates']
                for budget in range(1, full['semantic']['logical_work'] + 2):
                    generator.expansion_limit = budget
                    cold = query(factory(budget, dynamic=dynamic), state, empty=empty)
                    warm = query(generator, state, empty=empty)
                    query_count += 2
                    boundaries.append({'dynamic_local': dynamic, 'complex': complex, 'empty': empty,
                        'budget': budget, 'equal': cold['semantic'] == warm['semantic'],
                        'cold': cold, 'warm': warm})
    scene = replace(sustained_scenes()[0], horizon=9)
    collection = collect_role_decisions(scene, ControlSpec(planning_horizon=20),
        quota=RoleQuota(max_samples=1), cache_contract=CACHE_CONTRACT)
    sample = collection.samples[0]
    cache_before = routing_cache_state(CursorSimulation.from_checkpoint(sample['checkpoint']))
    first = branch_role_decision(sample['checkpoint'], sample['pool'][0], (), 20)
    query(factory(isolated=False), fixture(True))
    query(factory(), fixture(True))
    query_count += 2
    second = branch_role_decision(sample['checkpoint'], sample['pool'][0], (), 20)
    physical = lambda result: asdict(result.final_snapshot)
    branch_equal = (physical(first) == physical(second) and first.trace == second.trace
                    and first.cost_components == second.cost_components and first.total_cost == second.total_cost)
    branch = {'branch_calls': 2, 'equal_physical_trace_cost': branch_equal,
              'first_cost': first.total_cost, 'second_cost': second.total_cost,
              'first_components': first.cost_components, 'second_components': second.cost_components,
              'cache_unchanged': cache_before == routing_cache_state(CursorSimulation.from_checkpoint(sample['checkpoint'])),
              'sample_cache': sample['routing_cache_checkpoint'], 'collection_metadata': collection.metadata}
    result = {'contract': CACHE_CONTRACT, 'schema': 'routing_cache_diagnostic_v1',
        'legacy_counterexamples': legacy, 'cutoff_pair_count': len(boundaries),
        'cutoff_pairs_equal': sum(row['equal'] for row in boundaries), 'cutoff_records': boundaries,
        'explicit_query_calls': query_count, 'collection_episode_calls': 1, 'cursor_branch': branch,
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - started,
        'memory_before': before_memory, 'memory_after': memory_snapshot(),
        'source_sha256': {name: sha256(content).hexdigest() for name, content in frozen.items()},
        'source_changed': any(path.read_bytes() != frozen[path.name] for path in sources),
        'limitations': ['This tests logical integer-work repeatability, not bit-identical wall timing.',
            'Legacy default remains process-global and can differ from the new cold-equivalent budget contract.',
            'Wall deadline_ms and slow planning_budget_ms must be None.',
            'Only RegionalCandidateGenerator and declared fast/slow/public-projection entrances are covered.',
            'CoverageCheckpoint audit fingerprints still contain timing statistics; do not use for cross-run semantic caches.',
            'VisibleDecisionContext adds optional cache_contract=None; old controller behavior remains default.',
            'Cache audit exports are JSON, but restoring cache uses trusted in-memory deepcopy checkpoints.',
            'Preprocessing accounting counts algorithmic logical units, not every Python instruction.',
            'No completeness or solver-performance improvement is claimed.']}
    (output / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    if result['source_changed'] or result['cutoff_pairs_equal'] != len(boundaries) or not branch_equal or not branch['cache_unchanged']:
        raise AssertionError('Cache contract diagnostic failed; evidence retained')
    return {key: result[key] for key in ('cutoff_pair_count', 'cutoff_pairs_equal', 'explicit_query_calls',
        'source_changed', 'cpu_seconds', 'wall_seconds')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.output)))
