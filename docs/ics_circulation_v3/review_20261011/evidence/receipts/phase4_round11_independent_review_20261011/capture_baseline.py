"""Freeze the exact reviewed Round10 source/test/Cpp without executing physics."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import process_time, perf_counter

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
cpu, wall = process_time(), perf_counter()
prior = BASE.parent / 'phase4_round10_independent_review_20261011/closure_001/results.json'
closed = json.loads(prior.read_bytes())
hashes = closed['source_sha256']
copy = BASE / 'round10_frozen'
copy.mkdir(exist_ok=False)
changed = []
for relative, digest in hashes.items():
    raw = (ROOT / relative).read_bytes()
    if sha256(raw).hexdigest() != digest:
        changed.append(relative)
    target = copy / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
result = {'status': 'passed' if not changed and head == closed['head'] else 'failed',
          'round10_file_count': len(hashes), 'round10_files_sha256': hashes,
          'changed_since_round10': changed, 'head': head, 'round10_head': closed['head'],
          'cpp_sha256': hashes['cpp/ics_core/runtime/bounded_local_pibt.hpp'],
          'round10_closure_sha256': sha256(prior.read_bytes()).hexdigest(),
          'cpu_seconds': process_time()-cpu, 'wall_seconds': perf_counter()-wall,
          'physical_runs': 0, 'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
          'scope': 'Read/hash/copy 206 prior frozen files and git HEAD; initial imports and final writes excluded.'}
(BASE / 'baseline.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k != 'round10_files_sha256'}, indent=2))
raise SystemExit(0 if result['status'] == 'passed' else 1)
