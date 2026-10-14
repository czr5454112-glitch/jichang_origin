"""Static necessary-condition inventory, without assigning or deleting a bag.

The proxy permits all positive-capacity directed edges in either carrier mode.
Actual mode/owner permissions and EBS capability remain unknown. This is not
an operational feasibility certificate, a new task projection, or a simulation.
"""
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter, process_time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE.parent / 'phase4_w3_round8_business_input_research_repaired_20261010'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def main():
    cpu, wall = process_time(), perf_counter()
    output = HERE / 'projection_domains'
    output.mkdir(exist_ok=False)
    profile_path = ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'
    bags_path = SOURCE / 'business_tasks_1x.jsonl.gz'
    manifest_path = SOURCE / 'manifest.json'
    binding = {str(p): sha(p) for p in (profile_path, bags_path, manifest_path)}
    manifest = json.loads(manifest_path.read_bytes())
    assert binding[str(profile_path)] == manifest['input_sha256'][str(profile_path)]
    assert binding[str(bags_path)] == manifest['outputs'][bags_path.name]
    profile = json.loads(profile_path.read_bytes())
    nodes = sorted(n['location'] for n in profile['nodes'])
    assert nodes == list(range(len(nodes)))
    adjacency = {n: set() for n in nodes}
    closed = []
    for edge in profile['edges']:
        assert edge['capacity'] >= 0
        if edge['capacity']:
            adjacency[edge['start']].add(edge['end'])
        else:
            closed.append([edge['start'], edge['end']])
    reachable = {}
    for origin in nodes:
        seen, queue = {origin}, [origin]
        for node in queue:
            for successor in adjacency[node] - seen:
                seen.add(successor)
                queue.append(successor)
        reachable[origin] = seen
    # Separately derive the transitive closure through bitset Warshall updates.
    masks = [(1 << n) | sum(1 << j for j in adjacency[n]) for n in nodes]
    for middle in nodes:
        for origin in nodes:
            if masks[origin] & (1 << middle):
                masks[origin] |= masks[middle]
    assert all(reachable[n] == {j for j in nodes if masks[n] & (1 << j)} for n in nodes)
    loaders = set(profile['business_roles']['source_candidate_ids'])
    unloaders = set(profile['business_roles']['sink_candidate_ids'])
    valid_return = {u for u in unloaders if reachable[u] & loaders}
    with gzip.open(bags_path, 'rt', encoding='utf-8') as stream:
        bags = [json.loads(line) for line in stream]
    assert len(bags) == len({b['business_bag_id'] for b in bags}) == 28506
    groups = defaultdict(list)
    for bag in bags:
        assert not bag['source']['synthetic_inserted']
        assert bag['source']['time_shift_seconds'] == 0
        assert int(bag['origin']) in loaders and int(bag['final_destination']) in unloaders
        groups[tuple(bag['source']['flight_surrogate'])].append(bag)
    assert len(groups) == 360
    rows, reasons, affected_origins = [], Counter(), Counter()
    old_outbound_unreachable = 0
    for key, members in sorted(groups.items()):
        domain = set(valid_return)
        demands = Counter((int(b['origin']), b['lifecycle'], b['storage_node_proxy']) for b in members)
        rejected = []
        for (origin, lifecycle, storage), count in sorted(demands.items(), key=str):
            if lifecycle == 'early_storage':
                storage = int(storage)
                candidate_domain = reachable[storage] & valid_return if storage in reachable[origin] else set()
                reason = 'origin_to_storage_unreachable' if storage not in reachable[origin] else 'storage_to_unloader_or_return_unreachable'
            else:
                assert lifecycle == 'direct'
                candidate_domain = reachable[origin] & valid_return
                reason = 'origin_to_unloader_or_return_unreachable'
            domain &= candidate_domain
            if not candidate_domain:
                rejected.append({'origin': origin, 'lifecycle': lifecycle, 'storage_proxy': storage,
                                 'bag_count': count, 'reason': reason})
                reasons[reason] += count
                affected_origins[origin] += count
        old_destinations = {int(b['final_destination']) for b in members}
        assert len(old_destinations) == 1
        old_outbound_unreachable += sum(int(b['final_destination']) not in reachable[int(b['origin'])] for b in members)
        rows.append({'flight_surrogate': list(key), 'bag_count': len(members),
                     'old_destination': next(iter(old_destinations)), 'feasible_destination_domain': sorted(domain),
                     'individual_empty_domains': rejected,
                     'joint_empty_without_individual_empty': not domain and not rejected})
    assert old_outbound_unreachable == 4001
    totals = {'business_bags': len(bags), 'atomic_flight_groups': len(rows),
              'nonempty_flight_domains': sum(bool(r['feasible_destination_domain']) for r in rows),
              'empty_flight_domains': sum(not r['feasible_destination_domain'] for r in rows),
              'bags_in_empty_flight_groups': sum(r['bag_count'] for r in rows if not r['feasible_destination_domain']),
              'individual_empty_domain_bags': sum(reasons.values()), 'individual_empty_reasons': dict(reasons),
              'individual_empty_origins': dict(affected_origins),
              'old_destination_outside_nonempty_domain_groups': sum(bool(r['feasible_destination_domain']) and r['old_destination'] not in r['feasible_destination_domain'] for r in rows),
              'empty_intersection_only_groups': sum(r['joint_empty_without_individual_empty'] for r in rows),
              'old_outbound_unreachable': old_outbound_unreachable,
              'all_unloaders_with_any_loader_return': len(valid_return), 'closed_edges_preserved': closed}
    write(output / 'analysis.json', {'totals': totals, 'groups': rows,
        'input_sha256': binding, 'scope': __doc__, 'permissions': 'positive-capacity graph proxy only',
        'physical_simulations': 0, 'assignment_changes': 0, 'discarded_bags': 0})
    assert all(sha(Path(p)) == expected for p, expected in binding.items())
    write(output / 'resource.json', {'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'source_sha256': sha(Path(__file__)), 'physical_simulations': 0,
        'scope': 'Read-only static domains; excludes imports, code writing and final receipt/manifest writes.'})
    write(output / 'manifest.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(totals))


if __name__ == '__main__':
    main()
