"""Meter same-process projection tests; keep all attempts and source snapshots."""
from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
sys.path.insert(0, str(ROOT))
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
import json
from time import process_time, perf_counter
import traceback
import pytest

HERE = Path(__file__).parent
out = HERE / sys.argv[1]
out.mkdir()
sources = [ROOT / 'scripts/experiments/ics_circulation_v3' / n for n in
    ('business_inputs.py', 'business_runtime.py', 'business_projection.py')]
sources += [ROOT / 'tests/test_ics_circulation_v3_business_projection.py', Path(__file__).resolve()]
before = {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sources}
(out / 'source_snapshot').mkdir()
for p in sources:
    (out / 'source_snapshot' / p.name).write_bytes(p.read_bytes())
cpu, wall = process_time(), perf_counter()
result = dict(status='running', physical_calls=0, source_sha256_before=before)
try:
    with (out / 'pytest.txt').open('w', encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        result['pytest_exit'] = pytest.main(['-q', 'tests/test_ics_circulation_v3_business_projection.py',
            '--basetemp', str(out / 'pytest_tmp')])
    result['status'] = 'passed' if result['pytest_exit'] == 0 else 'failed'
except BaseException:
    result['status'] = 'failed'
    result['exception'] = traceback.format_exc()
finally:
    result.update(cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        scope='Same process pytest interval includes pytest; imports, initial source snapshot and final writes excluded.',
        unmetered_auxiliary='Initial source reads/snapshot/imports and final seal writes; no physics anywhere in this test suite.',
        source_sha256_after={p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sources})
    result['source_changed'] = result['source_sha256_after'] != before
    (out / 'resource.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps({p.relative_to(out).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in out.rglob('*') if p.is_file() and 'pytest_tmp' not in p.parts}, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(result.get('pytest_exit', 1))
