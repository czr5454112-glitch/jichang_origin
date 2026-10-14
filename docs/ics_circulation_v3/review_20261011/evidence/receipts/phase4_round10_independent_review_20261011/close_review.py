"""Read-only source/evidence closure; no simulation or test execution."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
cpu, wall = process_time(), perf_counter()
out = BASE / 'closure_001'
out.mkdir(exist_ok=False)
baseline = json.loads((BASE / 'baseline.json').read_bytes())['round9_files_sha256']
frozen = json.loads((BASE / 'attempt_006/before.json').read_bytes())
after = json.loads((BASE / 'attempt_006/after.json').read_bytes())
assert frozen == after
live = {relative: sha256((ROOT / relative).read_bytes()).hexdigest() for relative in frozen}
drift = [relative for relative in frozen if live[relative] != frozen[relative]]
assert not drift, drift
archive_drift = [relative for relative, digest in baseline.items()
                 if sha256((BASE / 'round9_frozen' / relative).read_bytes()).hexdigest() != digest]
assert not archive_drift, archive_drift
changed = {relative: {'round9': digest, 'round10': live[relative]}
           for relative, digest in baseline.items() if relative in live and live[relative] != digest}
new = {relative: digest for relative, digest in live.items() if relative not in baseline}
missing = [relative for relative in baseline if relative not in live]
assert not missing, missing
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
receipts = [BASE / 'baseline.json'] + sorted(BASE.glob('attempt_*/results.json'))
receipts += sorted(BASE.glob('mechanism_review_*/results.json'))
receipts += sorted(BASE.glob('projection_boundary_*/results.json'))
receipts += sorted(BASE.glob('window_review_*/results.json'))
known_cpu = 0
for receipt in receipts:
    data = json.loads(receipt.read_bytes())
    known_cpu += data['cpu_seconds'] + data.get('bridge_child_cpu_seconds', 0)
evidence = {}
for path in sorted(BASE.rglob('*')):
    if not path.is_file() or out in path.parents or '__pycache__' in path.parts:
        continue
    evidence[path.relative_to(BASE).as_posix()] = sha256(path.read_bytes()).hexdigest()
result = {
    'status': 'passed', 'physical_runs': 0, 'head': head,
    'round9_file_count': len(baseline), 'round10_file_count': len(frozen),
    'changed_existing_files': changed, 'new_files': new,
    'source_drift_since_full_regression': drift, 'round9_archive_drift': archive_drift,
    'cpp_sha256': live['cpp/ics_core/runtime/bounded_local_pibt.hpp'],
    'source_sha256': live, 'known_previous_audit_cpu_seconds': known_cpu,
    'explicit_audit_physical_runs': 52,
    'exact_full_test_physical_total': None,
    'qualification': '52 explicitly instrumented audit physical calls across retained attempts and ordinary bridge; other full-test calls unknown. Root mechanism/window calls belong to their own receipts. Known previous CPU excludes this closure and unmetered reading/editing/shell helpers.',
    'cpu_seconds': process_time()-cpu, 'wall_seconds': perf_counter()-wall,
    'resource_scope': 'Read/hash source and artifacts plus git HEAD read; zero simulation/test calls; initial imports and final writes excluded.',
    'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
}
(out / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
evidence['closure_001/results.json'] = sha256((out / 'results.json').read_bytes()).hexdigest()
(out / 'manifest.json').write_text(json.dumps({'sha256': evidence}, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('source_sha256',)}, indent=2))
