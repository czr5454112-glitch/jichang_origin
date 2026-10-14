"""Emit ordinary-bag semantics using a selectable frozen source tree."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from time import process_time, perf_counter

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
cpu, wall = process_time(), perf_counter()
sys.path.insert(0, str(Path(args.source).resolve()))

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.runtime import Simulation
from scripts.experiments.ics_circulation_v3.request_service import summarize


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not k.endswith('_ms')}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


cases = []
for route_mode in ('whole_route', 'next_edge'):
    for future in (False, True):
        network = Network({n: Node(n, 'z', 'p', 2) for n in 'ASD'}, {
            e.edge_id: e for e in (Edge('AS', 'A', 'S', 2), Edge('SD', 'S', 'D', 2),
                                  Edge('DA', 'D', 'A', 2), Edge('SA', 'S', 'A', 2))})
        initial = Snapshot(0, network, {'t0': Tray('t0', 'A'), 't1': Tray('t1', 'A')},
                           {'b0': Bag('b0', 'A', 'D', 0, 12, True)},
                           module=FixedLocalModule(unload_ticks=1, hold_by_node={'D': 2}))
        tape = (Bag('b1', 'A', 'D', 3, 15), Bag('b2', 'D', 'A', 8, 24)) if future else ()
        engine = Simulation(initial, tape, route_mode=route_mode, search_horizon=30)
        observations = []
        checkpoint = None
        for tick in range(25):
            engine.advance(tick)
            visible = engine.observe()
            observations.append({'state': asdict(visible), 'dependency_summary': asdict(summarize(visible))})
            if tick == 3:
                checkpoint = engine.checkpoint()
        replay = Simulation.from_checkpoint(checkpoint)
        replay.advance(24)
        replay.observe()
        assert clean(asdict(replay.result())) == clean(asdict(engine.result())), 'ordinary resume changed semantics'
        cases.append({'route_mode': route_mode, 'future': future,
                      'observations': observations, 'result': clean(asdict(engine.result()))})

data = {'cases': cases, 'cpu_seconds': process_time() - cpu,
        'wall_seconds': perf_counter() - wall,
        'scope': 'Four fixed ordinary direct-bag cases plus four checkpoint continuations; no EBS physics. Timing fields ending _ms excluded; other state, summary, objective, trace and counter fields compared.',
        'physical_runs': 8}
Path(args.output).write_text(json.dumps(data, indent=2), encoding='utf-8')
