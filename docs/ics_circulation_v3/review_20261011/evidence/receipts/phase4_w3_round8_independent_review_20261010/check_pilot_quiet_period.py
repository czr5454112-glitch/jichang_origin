"""Supplement initial auditor's positive-duration check with actual slow period."""
from pathlib import Path
import hashlib
import json
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'phase4_w3_same_zone_stability_20261010'
started, cpu = time.perf_counter(), time.process_time()
bound, rows, failures = {}, [], []


def read(path):
    data = path.read_bytes()
    bound[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


protocol = read(BASE / 'protocol.json')
prior = Path(protocol['source'])
for stage in ('bridge', 'pilot'):
    for row in read(BASE / stage / 'summary.json')['rows']:
        metadata = read(prior / row['metadata_file'])
        duration = row['milestones']['controller_quiescent']['time'] - row['milestones']['controller_quiescent']['quiet_since']
        period = metadata['active_continuation']['slow_period']
        rows.append({'stage': stage, 'physical_key': row['physical_key'], 'quiet_duration': duration, 'actual_slow_period': period})
        if duration < period:
            failures.append(rows[-1])
result = {'schema': 'ics_round8_pilot_quiet_period_supplement_v1', 'checks': len(rows), 'failures': failures,
    'rows': rows, 'files_sha256': bound, 'cpu_seconds': time.process_time() - cpu,
    'wall_seconds': time.perf_counter() - started,
    'scope': 'Pure summary/metadata supplement: initial raw auditor checked positive integer duration and an actual crossed slow trigger; this explicitly binds the minimum duration to active_continuation.slow_period. No raw replay or simulation.'}
(HERE / 'quiet_period_supplement.json').write_text(json.dumps(result, indent=2), encoding='utf8')
print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'files_sha256')}))
