"""Independent raw artifact read: zero production imports, adapters or physics."""
from collections import Counter
from fractions import Fraction
import gzip
from hashlib import sha256
from itertools import zip_longest
import json
from pathlib import Path
from time import process_time, perf_counter
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
OLD = BASE.parent / 'phase4_round10_business_projection_20261011/full_audit_002'
NEW = BASE.parent / 'phase4_round11_projection_runtime_20261011/full_adapter_002'
OUT = BASE / 'full_adapter_review_001'
OUT.mkdir(exist_ok=False)
cpu, wall = process_time(), perf_counter()
bindings, checks, rows = {}, 0, []


def read(path):
    value = path.read_bytes()
    bindings[path.relative_to(ROOT).as_posix()] = sha256(value).hexdigest()
    return value


def check(value, reason):
    global checks
    checks += 1
    if not value:
        raise AssertionError(reason)


def ceiling(value):
    return -(-value.numerator // value.denominator)


report = {'status': 'running', 'physical_runs': 0, 'adapter_calls': 0, 'rows': rows}
try:
    resource = json.loads(read(NEW / 'resource.json'))
    check(resource['status'] == 'passed' and not resource['source_changed'], 'sealed adapter execution')
    check(resource['source_sha256_before'] == resource['source_sha256_after'], 'unchanged execution sources')
    frozen = json.loads(read(BASE / 'attempt_003/before.json'))
    for path, digest in resource['source_sha256_before'].items():
        if path in frozen:
            check(frozen[path] == digest, 'full-regression source identity ' + path)
        check(sha256(read(ROOT / path)).hexdigest() == digest, 'bound execution source ' + path)
    previous_groups = None
    for scale in (1, 2):
        metadata = json.loads(read(OLD / f'projection_metadata_{scale}x.json'))
        groups = json.loads(read(OLD / f'flight_projection_{scale}x.json'))
        by_group = {group['group_id']: group for group in groups}
        selected = {gid: group['projected_destination'] for gid, group in by_group.items()}
        check(len(by_group) == 360, 'full parent group denominator')
        if previous_groups is not None:
            check(selected == previous_groups, 'whole-parent mapping preserved across scale')
        previous_groups = selected
        for source, digest in metadata['source_input_sha256']:
            check(sha256(read(Path(source))).hexdigest() == digest, 'original input bytes bound')
        raw_path = next(Path(source) for source, _ in metadata['source_input_sha256'] if source.endswith(f'nanning_{scale}x_raw.txt'))
        source_rows = {int(row[0]): row for line in read(raw_path).decode('utf-8-sig').splitlines()[1:] if (row := line.split())}
        contract = metadata['source_operation_contract']
        tick, lead = Fraction(contract['tick_seconds']), Fraction(contract['deadline_lead_seconds'])
        check(len(contract['initial_trays']) == 11, 'finite original inventory')
        run = json.loads(read(NEW / f'run_contract_{scale}x.json'))
        canonical = json.dumps(run, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
        run_sha = sha256(canonical.encode()).hexdigest()
        check(run['source_workload_sha256'] == metadata['contract']['source_workload_sha256'], 'fixed source workload')
        check(run['projection_sha256'] == metadata['content_sha256'], 'fixed Round10 projection content')
        check(run['projection_contract_sha256'] == metadata['contract']['canonical_sha256'], 'fixed external projection declaration')
        before_path = OLD / f'projected_tasks_{scale}x.jsonl.gz'
        after_path = NEW / f'private_runtime_tape_{scale}x.jsonl.gz'
        read(before_path)
        read(after_path)
        seen, membership, counts = set(), {}, Counter()
        with gzip.open(before_path, 'rt', encoding='utf-8') as before, gzip.open(after_path, 'rt', encoding='utf-8') as after:
            for old_line, new_line in zip_longest(before, after):
                check(old_line is not None and new_line is not None, 'full input/runtime row count')
                original_record, runtime_record = json.loads(old_line), json.loads(new_line)
                check({k:v for k,v in runtime_record.items() if k not in ('runtime_bag', 'run_contract_sha256')} == original_record,
                      'all original task and projected parent metadata retained')
                check(runtime_record['run_contract_sha256'] == run_sha, 'every private row run binding')
                task = runtime_record['original']
                ident = task['business_bag_id']
                check(ident not in seen, 'unique original identity')
                seen.add(ident)
                source = source_rows[task['source']['raw_task_id']]
                check(ident == f"projected:{scale}x:{source[0]}", 'raw identity namespace')
                check(Fraction(task['arrival_seconds']) == Fraction(source[1]) and Fraction(task['std_seconds']) == Fraction(source[2]), 'exact raw seconds')
                check((task['origin'], task['final_destination']) == (source[3], source[4]), 'original raw OD')
                arrival = ceiling(Fraction(source[1])/tick)
                deadline_fraction = (Fraction(source[2])-lead)/tick
                deadline = deadline_fraction.numerator // deadline_fraction.denominator
                protected = contract['protection_policy'] == 'all' or ident in contract['protected_business_ids']
                expected = dict(bag_id=ident, origin=source[3], destination=selected[runtime_record['group_id']],
                                arrival=arrival, deadline=deadline, protected=protected)
                early = Fraction(source[2])-Fraction(source[1]) >= 4800
                if early:
                    expected['storage'] = dict(node_id=contract['storage']['node_id'],
                        release_at=ceiling((Fraction(source[2])-2700)/tick), published_at=arrival,
                        evidence_status='proxy', carrier_policy='on_carrier')
                check(runtime_record['runtime_bag'] == expected, 'runtime bag independently derived from raw seconds and frozen mapping')
                check(task['arrival'] == arrival and task['deadline'] == deadline and task['protected'] == protected, 'original conservative clocks and protection')
                membership.setdefault(runtime_record['group_id'], set()).add(ident)
                counts.update(business=1, early=int(early), derived=int(task['source']['synthetic_inserted']),
                              old_segments=len(task['old_segment_ids']), changed=int(source[4] != expected['destination']))
        check(len(seen) == len(source_rows) == scale*28506, 'complete raw denominator')
        check(counts['old_segments'] == scale*43603 and counts['early'] == scale*15097 and counts['changed'] == scale*4001, 'full source and changed-final counts')
        check(counts['derived'] == (scale-1)*28506, 'full derived denominator')
        check(all(membership[gid] == set(group['business_bag_ids']) for gid, group in by_group.items()), 'exact complete parent family membership')
        rows.append(dict(scale=scale, counts=dict(counts), groups=len(membership), run_contract_sha256=run_sha))
    for relative, digest in bindings.items():
        check(sha256((ROOT / relative).read_bytes()).hexdigest() == digest, 'audit source remained unchanged')
    report['status'] = 'passed'
except Exception:
    report.update(status='failed', exception=traceback.format_exc())
report.update(checks=checks, cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
              input_sha256=bindings, script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
              qualification='Independent record/raw/clock audit of both full tapes; no production adapter, source loader, projection helper or simulation import. Necessary projection domain was audited separately in Round10; not a joint-capacity certificate.',
              resource_scope='Read/decode/compare/hash only; initial imports and final receipt writes excluded.')
(OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
(OUT / 'audit_full_adapter.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({k:v for k,v in report.items() if k != 'input_sha256'}, indent=2))
raise SystemExit(0 if report['status'] == 'passed' else 1)
