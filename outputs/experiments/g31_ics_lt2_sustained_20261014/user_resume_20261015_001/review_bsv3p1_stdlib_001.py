"""Saved-only supplement to the generic 42-case root readback; no imports of project code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(r'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree')
OUT = ROOT/'outputs/bsv3p1'
PINS = {
    'plan.json': '7f1516c956fe036beac8b2cbdc68b33084ab6389a3cb7832a8b3a5f4967e434b',
    'receipt.json': 'ad2b3bfd17abf1590b3de5fa825ce3b1d418ef6051b038af836dcdc45d1f1c41',
    'external_application_wall.json': '8e443c5655e2b1be863ecf8ed75b6036ad1e45c2188e90fc3ea0e67e85d216ff',
    'root_saved_review_001.json': 'ee9e546aff146fdd1550893222648f46fb2a0a184864fe1b7a2fcacca1169187',
}
FEATURE = Path(r'C:\PROGRAMING\python3.11.9\Lib\__future__.py')
FEATURE_SHA = 'bf11d13b6c9b2b8706be425addf399965738622bb4cc553217be16399c51d51a'

def require(ok, label):
    if not ok:
        raise ValueError(label)

def read(path, expected):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'hash:' + str(path))
    return raw

def main():
    values = {name: json.loads(read(OUT/name, digest)) for name, digest in PINS.items()}
    plan, receipt, ext = [values[name] for name in ('plan.json', 'receipt.json', 'external_application_wall.json')]
    fixture = {'path': str(FEATURE), 'sha256': FEATURE_SHA,
               'archive': 'stdlib_fixture/__future__.py', 'archive_sha256': FEATURE_SHA}
    require(plan['stdlib_feature_fixture'] == receipt['stdlib_feature_fixture_exit'] == fixture,
            'paired_stdlib_records')
    require('stdlib_feature_fixture_error' not in receipt, 'no_stdlib_error')
    live = read(FEATURE, FEATURE_SHA)
    require(read(OUT/fixture['archive'], FEATURE_SHA) == live, 'stdlib_whole_bytes_equal')
    require(ext['outputs'][fixture['archive']] == {
        'path': str(OUT/fixture['archive']), 'sha256': FEATURE_SHA}, 'external_stdlib_output')
    for name in ('expected_pins', 'pins_before', 'pins_after'):
        require(ext[name][str(FEATURE)] == FEATURE_SHA, 'external_stdlib_entry_exit:' + name)
    require(receipt['monitor_active_after_tests'] is True and receipt['blocked_real_calls'] == [],
            'sticky_monitor')
    for key in ('real_original_proof_calls', 'model_entry_calls', 'native_calls', 'custom_data_C_loads'):
        require(type(receipt[key]) is int and receipt[key] == 0, 'exact_zero:' + key)
    loaded = [receipt[k] for k in ('loaded_entry', 'loaded_exit', 'loaded_exit_final')]
    require(set(loaded[0]) <= set(loaded[1]) <= set(loaded[2]), 'loaded_monotonic')
    for rows in loaded:
        require(rows and all(plan['source_sha256'].get(k) == v for k,v in rows.items()), 'loaded_pins')
    for name, digest in PINS.items():
        read(OUT/name, digest)
    read(FEATURE, FEATURE_SHA)
    read(OUT/fixture['archive'], FEATURE_SHA)
    result = {'schema': 'g31.bsv3p1.root_stdlib_readback.v1', 'status': 'passed_saved_bindings',
        'pins': PINS, 'stdlib_feature_fixture': fixture, 'loaded_counts': list(map(len, loaded)),
        'tests': 42, 'source_count': 213, 'whole_python_seconds': ext['external_application_seconds'],
        'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'tests_rerun': 0, 'model_calls': 0, 'native_calls': 0,
        'scope': 'Saved test/monitor/source bindings only; real dependency-domain acceptance remains pending.'}
    target = OUT/'root_stdlib_review_001.json'
    with target.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                      'status': result['status']}))

if __name__ == '__main__':
    main()
