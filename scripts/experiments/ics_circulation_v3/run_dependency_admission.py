"""Dependency-cycle admission counterexamples and explicit non-solvable proposals."""
import argparse
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import shutil
from time import perf_counter, process_time

from .dependency_admission import execute_dependencies, plan_dependencies, propose_loaded_departures
from .experiment_protocol import create_output_directory
from .model import Bag, Edge, Network, Node, Snapshot, Tray
from .routing import RegionalCandidateGenerator
from .run_joint_feedback import save
from .runtime import Simulation


def ring(size, capacity=1):
    nodes = {str(i): Node(str(i), str(i), str(i), capacity=capacity) for i in range(size)}
    edges = {str(i): Edge(str(i), str(i), str((i + 1) % size), 1) for i in range(size)}
    bags = {str(i): Bag(str(i), str(i), str((i + 1) % size), 0, 5) for i in range(size)}
    trays = {str(i): Tray(str(i), str(i), 'loaded', str(i)) for i in range(size)}
    return Snapshot(0, Network(nodes, edges), trays, bags)


def fixtures():
    items = [(f'ring{size}_capacity{capacity}', ring(size, capacity), False)
             for size in (2, 3, 4, 6) for capacity in (1, 2)]
    blocked = ring(3)
    blocked.trays['2'] = Tray('2', '2', 'holding', available_at=100)
    del blocked.bags['2']
    items.append(('nonparticipating_held_blocker', blocked, False))
    late = ring(3)
    items.append(('incompatible_supplied_departure_windows', late, True))
    protected = ring(3)
    protected.bags['0'] = replace(protected.bags['0'], protected=True, deadline=0)
    items.append(('protected_deadline_cannot_be_relaxed', protected, False))
    closed = ring(3)
    closed.network.edges['1'] = replace(closed.network.edges['1'], capacity=0)
    items.append(('closed_edge_not_reopened', closed, False))
    return items


def factory(horizon=24):
    return RegionalCandidateGenerator(horizon=horizon, dynamic_local=True, deadline_ms=None)


def run(output):
    output = create_output_directory(output)
    source = Path(__file__).parent
    names = ('run_dependency_admission.py', 'dependency_admission.py', 'joint_transactions.py',
             'runtime.py', 'model.py', 'routing.py', 'routing_reference.py', 'experiment_protocol.py', 'run_joint_feedback.py')
    hashes = {n: sha256((source / n).read_bytes()).hexdigest() for n in names}
    (output / 'source_snapshot').mkdir()
    for name in names:
        shutil.copyfile(source / name, output / 'source_snapshot' / name)
    cases = fixtures()
    save(output / 'protocol.json', {'scope': 'structural_admission_development_counterexamples_not_airport_distribution',
         'source_sha256': hashes, 'cases': [name for name, _, _ in cases], 'horizon': 5,
         'permissions_comparison': 'same physical rules; sequential-only vs explicitly added atomic bundle admission',
         'not_claimed': 'No advantage from route search or scoring is inferred from enabling the new admission operator.',
         'failure_semantics': 'Rejected supplied proposal set is not proof of global physical infeasibility.',
         'future_visibility': 'no future bags in these structural fixtures'})
    metrics = []
    for name, initial, force_late in cases:
        start, cpu = perf_counter(), process_time()
        sequential = Simulation(initial, generator_factory=factory, search_horizon=5).advance(5)
        sequential_wall, sequential_cpu = perf_counter() - start, process_time() - cpu
        engine = Simulation(initial, control_mode='external')
        observation = engine.observe()
        start, cpu = perf_counter(), process_time()
        actions, proposal_log = propose_loaded_departures(observation, horizon=5)
        if force_late:
            last = actions[-1]
            actions = actions[:-1] + (replace(last,
                legs=tuple(replace(l, depart=l.depart + 2, arrive=l.arrive + 2) for l in last.legs),
                unload_complete=last.unload_complete + 2, usable_at=last.usable_at + 2),)
        plan = plan_dependencies(observation, actions)
        execute_dependencies(engine, plan)
        joint = engine.advance(5)
        row = {'case': name, 'scheduled': len(initial.bags), 'sequential_completed': len(sequential.completed),
               'joint_completed': len(joint.completed), 'sequential_cost': sequential.total_cost,
               'joint_cost': joint.total_cost, 'joint_components': plan.diagnostics['joint_component_count'],
               'rejected_components': len(plan.diagnostics['rejected_components']),
               'sequential_cpu_seconds': sequential_cpu, 'joint_cpu_seconds': process_time() - cpu,
               'sequential_wall_seconds': sequential_wall, 'joint_wall_seconds': perf_counter() - start}
        metrics.append(row)
        save(output / f'{name}.json', {'initial': asdict(initial), 'proposal_log': proposal_log,
             'submitted_proposals': [asdict(p) for p in actions], 'dependency_plan': asdict(plan),
             'sequential_result': asdict(sequential), 'joint_result': asdict(joint), 'metrics': row})
    summary = {'case_count': len(cases), 'metrics': metrics, 'source_sha256': hashes,
               'source_changed_during_run': any(sha256((source / n).read_bytes()).hexdigest() != h for n, h in hashes.items())}
    save(output / 'summary.json', summary)
    print({'cases': len(cases), 'source_changed_during_run': summary['source_changed_during_run']})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    raise SystemExit(int(result['source_changed_during_run']))
