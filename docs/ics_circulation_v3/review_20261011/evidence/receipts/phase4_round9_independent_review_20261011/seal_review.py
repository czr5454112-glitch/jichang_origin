"""Read-only source closure and output hash seal; no tests or physical runs."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
cpu, wall = process_time(), perf_counter()
def digest(path):
    return sha256(path.read_bytes()).hexdigest()
initial = json.loads((BASE / 'round9_before.json').read_bytes())
before = json.loads((BASE / 'attempt_018/before.json').read_bytes())
after = json.loads((BASE / 'attempt_018/after.json').read_bytes())
assert before == after and all(digest(ROOT / p) == h for p, h in after.items())
assert all(digest(BASE / 'attempt_018/source_snapshot' / p) == h for p, h in before.items())
round8_snapshot = BASE.parent / 'phase4_w3_round8_independent_review_20261010/full_validation/source_snapshot'
assert all(digest(round8_snapshot / p) == h for p, h in initial['files_sha256'].items())
current_old = {p: digest(ROOT / p) for p in initial['files_sha256']}
changed = [p for p, h in initial['files_sha256'].items() if current_old[p] != h]
assert {Path(p).name for p in changed} == {'runtime.py', 'prebalance.py', 'request_service.py', 'partition_observation.py', 'distributed_clock.py', 'joint_reference.py', 'joint_bundle_reference.py'}
cpp = 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert current_old[cpp] == initial['files_sha256'][cpp]
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
assert head == initial['head']
closure = {'status': 'passed', 'head': head, 'round8_file_count': len(current_old),
           'round8_original_archive_unchanged': True, 'intentional_changed_round8_files': changed,
           'all_round9_source_and_selected_tests_match_final_regression': True,
           'final_files_sha256': after, 'cpp_sha256': current_old[cpp],
           'new_relative_to_round8': sorted(set(after) - set(initial['files_sha256'])),
           'physical_runs': 0, 'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
           'scope': 'Hashing final regression before/after/snapshot, archived Round8 and current sources plus git HEAD. Child git CPU and final hash-seal writes excluded; no tests or physics.'}
(BASE / 'closure.json').write_text(json.dumps(closure, indent=2))
outputs = {str(p.relative_to(BASE)).replace('\\', '/'): digest(p) for p in BASE.rglob('*')
           if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts and p.suffix != '.pyc'}
(BASE / 'manifest.json').write_text(json.dumps({'schema': 'round9-independent-review-v1', 'outputs_sha256': outputs,
    'qualification': 'Local evidence seal, not a claim of completed original-map workload. Failed attempts retained; peripheral guards authored by this reviewer require root review.'}, indent=2))
print(json.dumps({k:v for k,v in closure.items() if k != 'final_files_sha256'}, indent=2))
