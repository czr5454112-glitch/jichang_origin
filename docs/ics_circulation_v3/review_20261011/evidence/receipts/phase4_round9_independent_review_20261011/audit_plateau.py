"""Independent saved-query replay, heap ordering and physical witness review."""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
import difflib
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import pickle
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
INPUT = BASE.parent / 'phase4_round9_storage_release_plateau_20261011'
OUT = BASE / 'plateau_review_001'
OUT.mkdir(exist_ok=False)
cpu, wall = process_time(), perf_counter()
sys.path.insert(0, str(ROOT))
bindings = {}

def read(path):
    data = path.read_bytes()
    bindings[str(path.relative_to(ROOT))] = sha256(data).hexdigest()
    return data

result = {'status': 'running', 'physical_runs': 0, 'standalone_queries': 0, 'queries': {}, 'exception': None}
try:
    oldfile = INPUT / 'baseline_001/storage_routing.py'
    newfile = ROOT / 'scripts/experiments/ics_circulation_v3/storage_routing.py'
    oldtext, newtext = read(oldfile).decode(), read(newfile).decode()
    (OUT / 'source_diff.txt').write_text(''.join(difflib.unified_diff(oldtext.splitlines(True), newtext.splitlines(True), fromfile='old', tofile='new')))
    assert read(newfile) == read(INPUT / 'comparison_001/storage_routing.py')
    statebytes = read(INPUT / 'baseline_001/query_state.pickle')
    generatorbytes = read(INPUT / 'baseline_001/query_generator.pickle')
    saved_old = json.loads(read(INPUT / 'baseline_001/result.json'))
    saved_new = json.loads(read(INPUT / 'comparison_001/result.json'))
    state = pickle.loads(statebytes)
    delegate = pickle.loads(generatorbytes).generator
    assert state.now == 8876 and delegate.horizon == 21600 and delegate.expansion_limit == 10000
    assert delegate.deadline_ms is None
    for label, file in [('old', oldfile), ('new', newfile)]:
        spec = importlib.util.spec_from_file_location('scripts.experiments.ics_circulation_v3.audit_' + label, file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        pops = []
        raw_pop = module.heappop
        def pop(queue):
            value = raw_pop(queue)
            # Confirm every chosen primary f is the minimum present. Secondary
            # ordering is allowed to change bounded K labels, not the primary.
            assert not queue or value[0] <= min(item[0] for item in queue)
            pops.append(value[:4] if label == 'new' else value[:2])
            return value
        module.heappop = pop
        planner = module.StorageCandidateGenerator(deepcopy(delegate))
        qcpu, qwall = process_time(), perf_counter()
        candidates = planner.generate(state, saved_old['bag_id'], saved_old['tray_id'], saved_old['k'])
        result['standalone_queries'] += 1
        result['queries'][label] = {
            'cpu_seconds_nested': process_time() - qcpu, 'wall_seconds_nested': perf_counter() - qwall,
            'status': planner.last_search_status, 'expansions': planner.last_expansions,
            'pop_count': len(pops), 'popped_primary_f_counts': dict(Counter(v[0] for v in pops)),
            'work_units': planner.last_diagnostics['work_units_by_stage'],
            'candidate_count': len(candidates),
        }
        expected = saved_new['new']['candidates'] if label == 'new' else saved_old['candidates']
        assert json.loads(json.dumps([asdict(c) for c in candidates])) == expected
        assert asdict(state) == asdict(pickle.loads(statebytes))
        if label == 'old':
            assert len(pops) == 9317 and set(v[0] for v in pops) == {19749} and not candidates
        else:
            assert len(candidates) == 4 and planner.last_expansions == 670
            # This saved state has no previous reservations or active flight.
            # That lets us construct its complete competing occupancy directly
            # without calling effective_reservations or the author's validator.
            assert not state.reservations and not state.plans and not state.old_in_transit
            witness_rows = []
            for candidate in candidates:
                bag, tray = state.bags[candidate.bag_id], state.trays[candidate.tray_id]
                contract = bag.storage
                assert candidate.dependency_version == state.version
                assert not candidate.prefix_only and candidate.destination_node == bag.destination
                assert tray.mode == 'loaded' and tray.bag_id == bag.bag_id
                node, tick = tray.node, state.now
                entered, left = None, None
                slots = []
                for other in state.trays.values():
                    if other.tray_id != tray.tray_id:
                        assert other.node is not None
                        slots.append(('node:' + other.node, state.now, 10**12, other.tray_id))
                for leg in candidate.legs:
                    edge = state.network.edges[leg.edge_id]
                    assert edge.source == node and leg.depart >= tick
                    assert leg.arrive - leg.depart == edge.travel_time
                    assert leg.depart == tick or state.network.nodes[node].can_wait
                    slots.extend([('node:' + node, tick, leg.depart, tray.tray_id),
                                  ('edge:' + edge.edge_id, leg.depart, leg.arrive, tray.tray_id)])
                    if node == contract.node_id:
                        assert entered is not None and leg.depart >= contract.release_at
                        left = leg.depart
                    node, tick = edge.target, leg.arrive
                    if node == contract.node_id:
                        entered = tick
                assert node == bag.destination and entered is not None and left is not None
                assert candidate.unload_complete == tick + state.module.unload_ticks
                assert candidate.usable_at == candidate.unload_complete + state.module.hold_ticks(node)
                assert candidate.unload_complete <= bag.deadline and tick <= state.now + delegate.horizon
                slots.extend([('node:' + node, tick, 10**12, tray.tray_id),
                              ('reception:' + node, tick, candidate.unload_complete, tray.tray_id)])
                changes = defaultdict(lambda: defaultdict(int))
                for resource, start, end, owner in slots:
                    if start < end:
                        changes[resource][start] += 1
                        changes[resource][end] -= 1
                maxima = {}
                for resource, events in changes.items():
                    kind, key = resource.split(':', 1)
                    cap = (state.network.nodes[key].capacity if kind == 'node' else
                           state.network.edges[key].capacity if kind == 'edge' else state.module.reception_capacity)
                    count = maximum = 0
                    for at, delta in sorted(events.items()):
                        count += delta
                        assert 0 <= count <= cap, (resource, at, count, cap)
                        maximum = max(maximum, count)
                    maxima[resource] = maximum
                witness_rows.append({'candidate_id': candidate.candidate_id, 'ingress': entered,
                    'release': left, 'final_arrival': tick, 'unload': candidate.unload_complete,
                    'storage_capacity_maximum': maxima['node:' + contract.node_id]})
            result['independent_witnesses'] = witness_rows
    for label in ['old', 'new']:
        work = result['queries'][label]['work_units']
        assert work['topology_edges'] == 227 and work['reverse_lower_bound'] == 341
    for path, digest in bindings.items():
        assert sha256((ROOT / path).read_bytes()).hexdigest() == digest
    result['status'] = 'passed'
except Exception:
    result['status'] = 'failed'
    result['exception'] = traceback.format_exc()
finally:
    result.update(cpu_seconds=process_time() - cpu, wall_seconds=perf_counter() - wall,
        limitations='One genuine saved query only. Instrumented heap minimum checks add audit CPU, so timings are not algorithm performance. K/state caps make ordering affect candidate set; capacity-induced smaller-f plateaus may remain. No completeness or global optimality claim.',
        resource_scope='Parent CPU includes imports, hash/diff, two standalone query replays, instrumentation and independent witness checks; query CPU nested. No physical simulation. Initial imports/final write excluded.')
    (OUT / 'results.json').write_text(json.dumps(result, indent=2))
    (OUT / 'manifest.json').write_text(json.dumps({'inputs_sha256': bindings, 'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'results_sha256': sha256((OUT / 'results.json').read_bytes()).hexdigest()}, indent=2))
    print(json.dumps(result, indent=2))
sys.exit(0 if result['status'] == 'passed' else 1)
