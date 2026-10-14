"""Read-only diagnosis; no physical advance or controller call."""
import gzip
import json
from pathlib import Path
from time import process_time, perf_counter
import sys
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiments.ics_circulation_v3.run_same_zone_supply import restored_d40
from scripts.experiments.ics_circulation_v3.routing_cache_contract import routing_cache_state

started, cpu = perf_counter(), process_time()
base = ROOT / 'outputs/experiments/ics_circulation_v3'
original = base / 'phase4_w3_network_nominal_opportunities_repaired_20261010/full'
attempt = base / 'phase4_w3_same_zone_supply_20261010/mechanism'
out = base / 'phase4_w3_same_zone_supply_repair_diagnostic_20261010'
out.mkdir()
engine, payload, metadata, binding = restored_d40()
memory = routing_cache_state(engine)
rows, inputs = [], {}
for c in (0, 1):
    prior_path = original / f'counterflow_d0040_c{c}.json.gz'
    attempt_path = attempt / f'counterflow_d0040_c{c}__old32.json.gz'
    for path in (prior_path, attempt_path):
        inputs[str(path)] = sha256(path.read_bytes()).hexdigest()
    with gzip.open(prior_path, 'rt') as stream:
        prior = json.load(stream)
    with gzip.open(attempt_path, 'rt') as stream:
        new = json.load(stream)
    rows.append({'candidate': c, 'recorded_comparison': new['old32_replication'],
        'all_serialized_cache_fields_equal': prior['cache_before'] == new['cache_before'],
        'memory_direct_equals_prior_json': memory == prior['cache_before'],
        'memory_json_roundtrip_equals_prior_json': json.loads(json.dumps(memory)) == prior['cache_before'],
        'all_cache_sha256_equal': len({prior['cache_before']['fast_cache_sha256'],
            new['cache_before']['fast_cache_sha256'], memory['fast_cache_sha256']}) == 1})
result = {'scope': 'read-only Python-vs-JSON representation diagnosis; no simulation advances, no new actions',
    'binding': binding, 'rows': rows, 'input_sha256': inputs,
    'input_unchanged': all(sha256(Path(p).read_bytes()).hexdigest() == h for p, h in inputs.items()),
    'physical_calls': 0, 'cpu_seconds': process_time()-cpu, 'wall_seconds': perf_counter()-started,
    'planned_repair': 'strict JSON-value equality for cache comparison, no fields excluded; regression must reject changed cache contents'}
with (out / 'diagnosis.json').open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2)
(out / 'diagnose_source.py').write_bytes(Path(__file__).read_bytes())
with (out / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump({p.name: sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}, stream, indent=2)
print(json.dumps(result, indent=2))
