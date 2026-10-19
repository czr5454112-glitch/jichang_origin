"""Read-only source/projection audit. No controller, model or native imports."""
from collections import Counter, defaultdict, deque
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
RUN = OUT.parent / 'C00_calibration_001'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    return {'path': str(path), 'sha256': digest(path)}


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def workbook_rows(path, sheet_name):
    with zipfile.ZipFile(path) as archive:
        shared = [''.join(row.itertext()) for row in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        relations = {row.attrib['Id']: row.attrib['Target'] for row in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheet = next(row for row in ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet', NS) if row.attrib['name'] == sheet_name)
        target = relations[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']].lstrip('/')
        if not target.startswith('xl/'):
            target = 'xl/' + target
        result = {}
        for row in ET.fromstring(archive.read(target)).findall('.//s:row', NS):
            cells = {}
            for cell in row.findall('s:c', NS):
                value = cell.find('s:v', NS)
                text = value.text if value is not None else None
                kind = cell.attrib.get('t')
                value = shared[int(text)] if kind == 's' and text is not None else text
                if kind not in ('s', 'str', 'inlineStr') and text is not None:
                    numeric = float(text)
                    value = int(numeric) if numeric.is_integer() else numeric
                formula = cell.find('s:f', NS)
                cells[re.match('[A-Z]+', cell.attrib['r']).group()] = {
                    'cell': cell.attrib['r'], 'value': value,
                    'formula': None if formula is None else {'text': formula.text, **formula.attrib},
                    'xml': ET.tostring(cell, encoding='unicode'),
                }
            result[int(row.attrib['r'])] = cells
        return result


def parents(adjacent, source):
    previous, queue = {source: None}, deque([source])
    while queue:
        for target in adjacent[queue.popleft()]:
            if target not in previous:
                previous[target] = source  # only set membership is needed here
                queue.append(target)
    return set(previous)


def main():
    profile_path = ROOT / 'data/processed/maps/nanning_airport_profile.json'
    raw_path = ROOT / 'legacy/jichang_origin_readonly/inputdata.txt'
    profile = read(profile_path)
    original = read(RUN / 'inputs/C00.json')
    crosswalk = json.loads(gzip.decompress((RUN / 'business_crosswalk.json.gz').read_bytes()))
    assert len(original['jobs']) == len(crosswalk) == 28506
    workbooks = {name: ROOT / 'map_nanning' / name for name in {edge['source']['workbook'] for edge in profile['edges']}}
    tables = {name: workbook_rows(path, '邻接表') for name, path in workbooks.items()}
    assert len(profile['edges']) == 227
    for edge in profile['edges']:
        row = tables[edge['source']['workbook']][edge['source']['row']]
        assert [row[col]['value'] for col in ('A', 'B', 'C', 'D', 'F')] == [
            edge['source']['raw_start'], edge['source']['raw_end'], edge['length'], edge['speed'], edge['pallet_capacity']]
        assert edge['pallet_capacity'] == math.floor(edge['length'] / 2)
    zero = [edge for edge in profile['edges'] if edge['pallet_capacity'] == 0]
    assert len(zero) == 1 and (zero[0]['start'], zero[0]['end']) == (97, 98)
    zero_row = tables[zero[0]['source']['workbook']][7]
    anchor = tables[zero[0]['source']['workbook']][5]['F']
    assert zero_row['C']['value'] == .6 and zero_row['F']['value'] == 0
    assert zero_row['F']['formula'] == {'text': None, 't': 'shared', 'si': '0'}
    assert anchor['formula'] == {'text': 'FLOOR(C5/2,1)', 't': 'shared', 'ref': 'F5:F36', 'si': '0'}
    adjacent = defaultdict(list)
    capacities = {(row['from'], row['to']): row['capacity'] for row in original['edge_contracts']}
    for edge in profile['edges']:
        assert capacities[edge['start'], edge['end']] == edge['pallet_capacity']
        if edge['pallet_capacity'] > 0:
            adjacent[edge['start']].append(edge['end'])
    reach = {node: parents(adjacent, node) for node in range(151)}
    roles = profile['business_roles']
    loaders = roles['standard_loader_nodes'] + roles['transfer_loader_nodes']
    goals = roles['unloader_nodes']
    storage = 53
    main_scc = sorted(node for node in reach[storage] if storage in reach[node])
    cyclic_loaders = sorted(set(loaders) & set(main_scc))
    cyclic_goals = sorted(set(goals) & set(main_scc))
    assert len(main_scc) == 134 and len(cyclic_loaders) == 10 and len(cyclic_goals) == 36
    source92_upstream = {node for node in range(151) if 92 in reach[node]}
    initial92_possible = [tray for tray in original['trays'] if tray['node'] in source92_upstream]
    assert len(initial92_possible) == 2 and all(tray['node'] == 92 for tray in initial92_possible)
    assert reach[92] & source92_upstream == {92}
    assert not any(goal in reach[92] and 92 in reach[goal] for goal in goals)
    raw = {}
    for line in raw_path.read_text(encoding='utf8').splitlines()[1:]:
        if not line.strip():
            continue
        identity, entry, std, source, goal, unloader, loader = line.split()
        raw[int(identity)] = {'lane': (loader, int(source)), 'flight': (float(std), int(goal), unloader)}
    by_id = {row['business_bag_id']: raw[row['original_task_id']] for row in crosswalk}
    bad_destinations = sorted(set(goals) - set(cyclic_goals))
    bad_jobs = [job for job in original['jobs'] if job['destination'] in bad_destinations]
    source92_jobs = [job for job in original['jobs'] if job['origin'] == 92]
    lanes = Counter(by_id[job['business_bag_id']]['lane'] for job in source92_jobs)
    bad_flights = {by_id[job['business_bag_id']]['flight'] for job in bad_jobs}
    assert len(bad_jobs) == 4001 and len(bad_flights) == 48 and len(source92_jobs) == 3102
    # Static review proposal only. This never emits an executable input file.
    origin_map = {92: 95}
    goal_map = {99: 114, 101: 116, 103: 118, 106: 120, 108: 122, 110: 124}
    proposal = copy.deepcopy(original)
    changes = Counter()
    lane_origins, flight_goals = defaultdict(set), defaultdict(set)
    for old, job in zip(original['jobs'], proposal['jobs'], strict=True):
        job['origin'] = origin_map.get(old['origin'], old['origin'])
        job['destination'] = goal_map.get(old['destination'], old['destination'])
        keys = {key for key in old if old[key] != job[key]}
        assert keys <= {'origin', 'destination'}
        for key in keys:
            changes[key] += 1
        changes['any'] += bool(keys)
        changes['both'] += len(keys) == 2
        lineage = by_id[job['business_bag_id']]
        if lineage['lane'][0] != 'T':
            lane_origins[lineage['lane']].add(job['origin'])
        flight_goals[lineage['flight']].add(job['destination'])
        assert job['origin'] in cyclic_loaders and job['destination'] in cyclic_goals
        stages = [(job['origin'], job['destination'])] if job['storage_node'] < 0 else [
            (job['origin'], job['storage_node']), (job['storage_node'], job['destination'])]
        assert all(destination in reach[source] for source, destination in stages)
        assert all(source in reach[job['destination']] for source in cyclic_loaders)
    assert len(flight_goals) == 360 and all(len(values) == 1 for values in flight_goals.values())
    assert all(len(values) == 1 for values in lane_origins.values())
    assert {k: v for k, v in proposal.items() if k != 'jobs'} == {k: v for k, v in original.items() if k != 'jobs'}
    report = {
        'schema': 'g31.independent.airport_source_contract_review.v1',
        'status': 'read_only_static_feasibility_proposal_not_native_validation',
        'sources': [reference(profile_path), reference(raw_path), reference(RUN / 'inputs/C00.json'),
            reference(RUN / 'business_crosswalk.json.gz'), *[reference(path) for path in workbooks.values()],
            reference(ROOT / 'scripts/eval/run_g4irsf31_nanning_map.py'),
            reference(ROOT / 'scripts/eval/run_g4irsf31_nanning_workload.py'),
            reference(ROOT / 'scripts/experiments/g31_ics_circulation/original_workload.py')],
        'workbook_to_profile_exact_edges': 227,
        'capacity_formula_consistent_edges': 227,
        'zero_edge': {'profile_edge': zero[0], 'row_cells': zero_row, 'shared_formula_anchor': anchor,
            'expanded_formula': 'FLOOR(C7/2,1)', 'exact_value': 0,
            'finding': 'faithful source formula/cached value; no parser or missing-to-zero error; source does not prove intentional closure or authorize capacity=1'},
        'projection_defect': {'function': 'run_g4irsf31_nanning_workload.build_original_projection',
            'finding': 'independent whole-group load balancing across role lists without positive-capacity reachability or empty-return-cycle constraints',
            'storage_selector': '_service_aware_distances also includes zero-capacity edges; original input separately preserves literal capacities'},
        'original': {'offered_jobs': 28506, 'flight_groups': 360, 'trays': 22,
            'unreachable_jobs': 4001, 'unreachable_complete_flight_groups': 48, 'unreachable_destinations': bad_destinations,
            'main_positive_capacity_scc': main_scc, 'cyclic_loaders': cyclic_loaders, 'cyclic_unloaders': cyclic_goals,
            'source92': {'business_count': 3102, 'early_storage_count': sum(job['storage_node'] >= 0 for job in source92_jobs),
                'scc': [92], 'upstream_nodes': sorted(source92_upstream),
                'initial_trays_with_any_path_to_92': [row['tray_id'] for row in initial92_possible],
                'unloader_roundtrips_to_92': 0, 'business_completion_upper_bound_from_physical_supply': 2,
                'incomplete_business_lower_bound_if_origin_kept': 3100,
                'legacy_lanes': [{'loader': lane[0], 'original_start': lane[1], 'count': count} for lane, count in sorted(lanes.items())]}},
        'review_proposal': {'operational_input_emitted': False, 'implemented': False, 'native_executed': False,
            'name': 'explicit_static_same_role_cyclic_projection_new_business_version',
            'origin_map': origin_map, 'destination_map': goal_map, 'changed_job_fields': dict(changes),
            'offered_jobs_preserved': 28506, 'atomic_flight_groups_preserved': 360,
            'all_original_arrivals_std_storage_release_service_deadline_ids_preserved': True,
            'all_non_job_input_fields_and_22_initial_trays_preserved': True,
            'all_loaded_business_paths_positive_capacity_reachable': True,
            'all_new_business_unloaders_can_return_to_all_10_used_loaders': True,
            'origin_loads': dict(sorted(Counter(job['origin'] for job in proposal['jobs']).items())),
            'destination_loads': dict(sorted(Counter(job['destination'] for job in proposal['jobs']).items())),
            'selection_rule': 'fixed same-role domestic substitution, independent of learned predictions, observed completion, or branch performance; no deleted jobs',
            'authorization_boundary': 'candidate new research business projection only under explicitly accepted new-domain scope; never relabel C00/C10, never claim same-scenario gain; physical interpretation of 0 capacity needs external source-owner evidence',
            'limitations': ['static paths are necessary, not sufficient for finite-buffer FIFO throughput or no-gridlock',
                'increased same-role endpoint load can create different bottlenecks; no measured benefit asserted',
                'new baseline and all methods must share new input; full 28506 evaluator and strict per-item checks remain',
                'role-uniform forecast mapping must separately version away inactive origin92 or remain explicit unknown; no historical group-size leakage to actor']},
    }
    for item in report['sources']:
        assert digest(Path(item['path'])) == item['sha256']
    with (OUT / 'report.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'changed_job_fields': dict(changes),
        'source92_unserved_lower_bound': 3100, 'workbook_edges_verified': 227}))


if __name__ == '__main__':
    main()
