"""Seal the author adapter delivery after all author runs; no physics."""
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'pyproject.toml').exists())
cpu, wall = process_time(), perf_counter()
closure = HERE / 'closure.json'
assert not closure.exists()
expected = json.loads((HERE / 'full_adapter_002/resource.json').read_bytes())['source_sha256_after']
actual = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in expected}
assert actual == expected
receipts = {}
for name in ('author_tests_001', 'full_adapter_001', 'full_adapter_002'):
    data = json.loads((HERE / name / 'resource.json').read_bytes())
    receipts[name] = dict(cpu_seconds=data['cpu_seconds'], wall_seconds=data['wall_seconds'],
        physical_calls=data['physical_calls'], status=data['status'])
result = dict(status='passed', source_sha256=actual, receipts=receipts,
    known_previous_cpu_seconds=sum(r['cpu_seconds'] for r in receipts.values()),
    physical_calls=0, cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
    scope='Current hash/receipt closure only; previous receipt CPU is a duplicate aggregate, not extra work.',
    unmetered_auxiliary='Interpreter/imports, source editing/reading, failed process inventory query, final closure/manifest writes remain unknown.')
closure.write_text(json.dumps(result, indent=2), encoding='utf-8')
bindings = {p.relative_to(HERE).as_posix(): sha256(p.read_bytes()).hexdigest() for p in HERE.rglob('*')
            if p.is_file() and 'pytest_tmp' not in p.parts and '__pycache__' not in p.parts and p != HERE / 'manifest.json'}
(HERE / 'manifest.json').write_text(json.dumps(dict(source_sha256=actual, outputs=bindings), indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
