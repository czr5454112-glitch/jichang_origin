"""One closing check of the sealed ledger; its own cost stays separate."""
from pathlib import Path
import hashlib
import json
import math
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LEDGER = HERE.parent / 'phase4_w3_round8_resource_ledger_20261010'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    bound, failures, checks = {}, [], []

    def check(value, label):
        checks.append({'name': label, 'okay': bool(value)})
        if not value:
            failures.append(label)

    def read(path):
        path = Path(path)
        bound[str(path)] = sha(path)
        return json.loads(path.read_text(encoding='utf8'))

    data = read(LEDGER / 'final/ledger.json')
    manifest = read(LEDGER / 'final/manifest.json')
    check(manifest['bound_inputs'] == data['bound_inputs'] and manifest['source_sha256'] == data['source_sha256'],
          'manifest source and input chain')
    for name, expected in manifest['outputs'].items():
        path = LEDGER / 'final' / name
        check(sha(path) == expected, 'ledger manifest:' + name)
        bound[str(path)] = expected
    for name, expected in data['bound_inputs'].items():
        path = ROOT / name
        check(sha(path) == expected, 'input unchanged:' + name)
        bound[str(path)] = expected
    check(sha(LEDGER / 'summarize.py') == data['source_sha256'], 'ledger generator unchanged')
    bound[str(LEDGER / 'summarize.py')] = data['source_sha256']
    rows = data['rows']
    by_id = {r['id']: r for r in rows}
    check(len(by_id) == len(rows), 'invocation IDs unique')
    components = [c for r in rows for c in r['cpu_components']]
    known = math.fsum(c['cpu_seconds'] for c in components if c['cpu_seconds'] is not None)
    unknown = sum(c['cpu_seconds'] is None for c in components)
    check(known == data['known_cpu_seconds_lower_bound'] == 45699.28125, 'known nonoverlap arithmetic')
    check(unknown == data['unknown_cpu_components'] == 8, 'unknown kept distinct from zero')
    check(data['pending_rows'] == 0 and not any(r['status'] == 'pending' for r in rows), 'no pending denominator')
    check(data['global_wall_seconds'] is None, 'parallel wall not summed')
    check(not data['failed_checks'] and all(c['okay'] for c in data['checks']), 'author checks all pass')
    seen = set()
    for row in rows:
        receipt = None
        if row['source'] != 'unmetered':
            receipt = read(ROOT / row['source'])
        for component in row['cpu_components']:
            value = component['cpu_seconds']
            if value is None:
                continue
            signature = (row['source'], component['source_field'])
            check(signature not in seen, 'measured receipt field counted once:' + str(signature))
            seen.add(signature)
            if receipt is not None and component['source_field'] in receipt:
                check(value == receipt[component['source_field']], 'direct measured value:' + str(signature))
    for stage in ('pilot', 'formal'):
        row = by_id['performance_' + stage]
        receipt = read(ROOT / row['source'])
        check(sum(c['cpu_seconds'] for c in row['cpu_components']) ==
              receipt['worker_final_process_cpu_seconds_sum'] + receipt['parent_cpu_seconds'],
              'performance includes only whole child CPU and parent:' + stage)
        check(len(row['cpu_components']) == 2, 'no nested query/simulation CPU added:' + stage)
    row = by_id['stability_full']
    os_record = read(ROOT / row['OS_monitor_source'])
    check(row['OS_monitor_replaces_nested_invocation_timers'], 'full OS replaces old intervals')
    check(sum(c['cpu_seconds'] for c in row['cpu_components']) ==
          os_record['known_worker_lifetime_cpu_seconds'] + os_record['known_parent_lifetime_cpu_seconds'] == 38253.5625,
          'six worker and coordinator OS CPU')
    check(sum(row['nested_original_intervals_excluded_from_addition'].values()) == 38185.234375,
          'old nested full intervals excluded')
    check(len(row['cpu_components']) == 2, 'no nested full timers re-added')
    check(by_id['stability_os_cpu_monitor_final_own_interval']['cpu_components'][0]['source_field'] == 'observer_cpu_seconds',
          'monitor counts own CPU only')
    check(by_id['resource_preview']['cpu_components'][0]['source_field'] == 'ledger_cpu_seconds_separate',
          'preview counts generator only')
    required_failed = ('future_initial', 'future_repaired', 'validation_meter_failure.json',
                       'business_input_research_20261010\\failure.json', 'finalization_failure.json')
    for fragment in required_failed:
        matching = [r for r in rows if fragment in r['id']]
        check(matching and all(r['status'] == 'failed' for r in matching), 'failure evidence retained:' + fragment)
    expected_stages = {'performance_pilot': 12, 'performance_formal': 108,
                       'stability_bridge': 17, 'stability_pilot': 24, 'stability_full': 2468,
                       'conditional_boundary_bridge': 2, 'conditional_boundary_full': 24}
    for name, expected in expected_stages.items():
        counts = by_id[name]['counts']
        actual = counts.get('physical_calls_recorded', counts.get('actual_physical_calls_recorded'))
        check(actual == expected, 'separate physical stage:' + name)
    check(sum(expected_stages.values()) == data['physical_summary']['recorded_original_network_invocations'] ==
          data['physical_summary']['planned_original_network_invocations'] == 2655, 'all physical calls retained')
    check(data['physical_summary']['memo_aliases_excluded'] == 1884 and
          data['physical_summary']['unknown_physical_call_statuses'] == 0 and
          data['physical_summary']['pending_planned_invocations'] == 0, 'memo/unknown physical separation')
    for name, expected in [('stability_full_artifact_audit.json', 543.65625),
                           ('stability_aggregate_comparison.json', .46875),
                           ('stability_support_expectation_comparison.json', .34375)]:
        matches = [r for r in rows if r['id'].endswith(name)]
        check(len(matches) == 1 and sum(c['cpu_seconds'] for c in matches[0]['cpu_components']) == expected,
              'final independent audit counted once:' + name)
    drift = [name for name, expected in bound.items() if sha(name) != expected]
    check(not drift, 'all closing audit inputs unchanged')
    result = {'schema': 'round8_independent_sealed_resource_ledger_audit_v1',
              'checks': len(checks), 'check_details': checks, 'failures': failures, 'drift': drift,
              'ledger_known_cpu_lower_bound': known, 'unknown_components': unknown,
              'ledger_rows': len(rows), 'physical_calls': 2655, 'memo_aliases_excluded': 1884,
              'nonblocking_text_erratum': 'The stability_full generic note about startup/initializer CPU being unknown is stale. Its later explicit OS replacement note and the two actual components govern: six worker plus coordinator full lifetimes are included, and 38185.234375 nested interval CPU is excluded. The stale note causes no arithmetic double count.',
              'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - wall,
              'resource_scope': 'This final pure-file audit interval is separate after ledger sealing; neither it nor the ledger generator interval is recursively added to the sealed headline.',
              'files_sha256': bound, 'source_sha256': sha(__file__), 'physical_simulations': 0}
    target = HERE / 'resource_ledger_audit.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('files_sha256', 'check_details')}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
