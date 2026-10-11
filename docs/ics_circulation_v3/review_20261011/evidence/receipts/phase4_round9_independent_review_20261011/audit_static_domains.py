"""Independently check reported static domains using transitive closure/Floyd."""
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
OUT = BASE / 'static_review_002'
OUT.mkdir(exist_ok=False)
cpu, wall = process_time(), perf_counter()
bindings = {}
def read(path):
    data = path.read_bytes()
    bindings[str(path.relative_to(ROOT))] = sha256(data).hexdigest()
    return data
report = {'status': 'running', 'physical_runs': 0, 'exception': None}
try:
    source = BASE.parent / 'phase4_round9_resource_ledger_20261011/static_domains_001/analysis.json'
    author = json.loads(read(source))
    profile = json.loads(read(ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'), parse_float=Decimal)
    records = [json.loads(line) for line in gzip.decompress(read(BASE.parent / 'phase4_w3_round8_business_input_research_repaired_20261010/business_tasks_1x.jsonl.gz')).splitlines()]
    nodes = {str(v) for edge in profile['edges'] for v in (edge['start'], edge['end'])}
    inf = 10**12
    ticks = {a: {b: 0 if a == b else inf for b in nodes} for a in nodes}
    for edge in profile['edges']:
        if edge['capacity'] > 0:
            duration = Fraction(str(edge['length'])) / Fraction(str(edge['speed']))
            value = -(-duration.numerator // duration.denominator)
            a, b = str(edge['start']), str(edge['end'])
            ticks[a][b] = min(ticks[a][b], value)
    for k in nodes:
        for a in nodes:
            if ticks[a][k] == inf:
                continue
            for b in nodes:
                ticks[a][b] = min(ticks[a][b], ticks[a][k] + ticks[k][b])
    roles = profile['business_roles']
    loaders = set(map(str, roles['source_candidate_ids']))
    goals = set(map(str, roles['sink_candidate_ids']))
    can_return = {g: any(ticks[g][s] < inf for s in loaders) for g in goals}
    groups = defaultdict(list)
    for record in records:
        flight_key = record['source']['flight_surrogate']
        groups[str(flight_key[0]), int(flight_key[1]), str(flight_key[2])].append(record)
    assert len(groups) == 360 and len(records) == 28506
    assert len(author['flight_rows']) == len(groups)
    outside = []
    def ceil(value):
        value = Fraction(str(value))
        return -(-value.numerator // value.denominator)
    for flight in author['flight_rows']:
        rows = groups[tuple(flight['flight_surrogate'])]
        assert len(rows) == flight['business_count']
        assert sorted(r['source']['raw_task_id'] for r in rows) == flight['raw_task_ids']
        domain, timed = set(), set()
        for goal in goals:
            valid, feasible = can_return[goal], True
            for row in rows:
                origin = row['origin']
                if row['lifecycle'] == 'early_storage':
                    valid &= ticks[origin]['53'] < inf and ticks['53'][goal] < inf
                    earliest = max(ceil(row['arrival_seconds']) + ticks[origin]['53'], ceil(row['scheduled_release_seconds'])) + ticks['53'][goal] + 1
                else:
                    valid &= ticks[origin][goal] < inf
                    earliest = ceil(row['arrival_seconds']) + ticks[origin][goal] + 1
                feasible &= earliest <= Fraction(str(row['std_seconds']))
            if valid:
                domain.add(goal)
                if feasible:
                    timed.add(goal)
        assert domain == set(flight['static_reachability_and_return_domain'])
        assert timed == set(flight['static_deadline_necessary_domain'])
        if flight['original_destination'] not in domain:
            outside.extend(rows)
    first = min(Decimal(str(r['arrival_seconds'])) for r in records)
    window = {r['business_bag_id']: r for r in records if first <= Decimal(str(r['arrival_seconds'])) < first + 3600}
    assert set(window) == {r['business_bag_id'] for r in author['window_rows']} and len(window) == 44
    for row in author['window_rows']:
        raw = window[row['business_bag_id']]
        for field in ['origin_to_storage', 'storage_to_final', 'origin_to_original_final']:
            segment = row[field]
            distance = ticks[segment['origin']][segment['destination']]
            assert segment['reachable'] == (distance < inf)
            assert segment['ticks'] == (distance if distance < inf else None)
        assert row['raw_task_id'] == raw['source']['raw_task_id']
        assert row['final_to_any_loader']['reachable'] == can_return[raw['final_destination']]
    report.update(status='passed', full_source_bags=len(records), whole_flight_groups=len(groups),
        window_bags=len(window), window_storage_to_final_unreachable=sum(ticks['53'][r['final_destination']] == inf for r in window.values()),
        original_destination_outside_domain_bags=len(outside), original_outside_goals=sorted({r['final_destination'] for r in outside}),
        qualification='Necessary static directed positive-capacity topology and per-bag protected travel bounds only. No assignment, deletion, capacity scheduling or physical run. Reachability/tick lengths independently derived by Floyd; fraction-seconds shortest paths not recomputed.')
    for path, digest in bindings.items():
        assert sha256((ROOT / path).read_bytes()).hexdigest() == digest
except Exception:
    report['status'], report['exception'] = 'failed', traceback.format_exc()
finally:
    report.update(cpu_seconds=process_time() - cpu, wall_seconds=perf_counter() - wall,
        resource_scope='All data reads, Floyd/domain enumeration and checks; imports and final writes excluded.')
    (OUT / 'results.json').write_text(json.dumps(report, indent=2))
    (OUT / 'manifest.json').write_text(json.dumps({'inputs_sha256': bindings, 'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'results_sha256': sha256((OUT / 'results.json').read_bytes()).hexdigest()}, indent=2))
    print(json.dumps(report, indent=2))
