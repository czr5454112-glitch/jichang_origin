"""One fixed public bundle / all32 candidates; pure profiling, no native."""
from pathlib import Path
import cProfile
import gzip
import hashlib
import json
import pstats
import time
from datetime import datetime, timezone
from scripts.experiments.g31_ics_circulation import public_native_preference_projection as model

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write_new(p, value):
    with p.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)

validation_path = OUT/'public_native_preference_projection_validation_008.json'
assert sha(validation_path) == 'f24bb52bbaad00c75c73e2db3f2c9d757945c3bdbdabf74411c535c2b9623ebd'
validation = json.loads(validation_path.read_bytes())
pins = validation['loaded_project_source_pins_before_and_after']
assert all(sha(path) == digest for path, digest in pins.items())
audit_path = OUT/'native_preference_matrix_native_001_independent_audit.json'
audit = json.loads(audit_path.read_bytes())
key = sorted(k for k,r in validation['rows'].items() if r['authority_valid_counterfactual_comparison'])[0]
saved = audit['rows'][key]
assert sha(saved['raw_artifact']) == saved['raw_sha256']
raw = json.loads(gzip.decompress(Path(saved['raw_artifact']).read_bytes()))
bundle = raw['initial_owners']['A']['information']['bundle']
case = model.contract.infer_case(bundle['jobs'])
windows = model.contract.domain.domain(case)['public_derivation']['supply_windows']
actions = model.vocabulary.domain(windows)['actions']
assert len(actions) == 32
directory = OUT/'public_projection_008_profile_001'
directory.mkdir(exist_ok=False)
plan = {'recorded_utc': datetime.now(timezone.utc).isoformat(), 'validation_sha256': sha(validation_path),
        'source_pins': pins, 'raw_sha256': saved['raw_sha256'], 'bundle_source': key,
        'actions': actions, 'calls': 32, 'scope': 'One fixed initial public bundle, all32 unchanged actions, one profiled sweep; retrospective CPU attribution only. No native/complete-request/performance generalization.'}
write_new(directory/'plan.json', plan)
profiler = cProfile.Profile()
started = time.perf_counter()
profiler.enable()
results = [model.predict(bundle, action) for action in actions]
profiler.disable()
elapsed = time.perf_counter()-started
assert all(sha(path) == digest for path, digest in pins.items())
stats = pstats.Stats(profiler)
rows = []
for (file, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
    rows.append({'file': file, 'line': line, 'function': name, 'primitive_calls': primitive,
                 'calls': calls, 'own_seconds': own, 'cumulative_seconds': cumulative})
rows.sort(key=lambda r: r['cumulative_seconds'], reverse=True)
report = {'status': 'completed_single_pure_profile', 'plan_sha256': sha(directory/'plan.json'),
          'calls': len(results), 'conditional_results': sum(r['status']=='conditional_prediction' for r in results),
          'profiled_wall_seconds': elapsed, 'top_cumulative': rows[:30],
          'top_own': sorted(rows, key=lambda r: r['own_seconds'], reverse=True)[:20],
          'source_changed': [], 'native_executions': 0, 'complete_100ms_certified': False,
          'scope': 'Profiler overhead included; concurrent native experiments. Not an unprofiled performance benchmark or complete request measurement.'}
write_new(directory/'report.json', report)
print(json.dumps({'profile_sha256': sha(directory/'report.json'), 'profiled_wall_seconds': elapsed,
                  'top': [{'function':r['function'], 'calls':r['calls'], 'own_seconds':r['own_seconds'],
                           'cumulative_seconds':r['cumulative_seconds']} for r in rows[:12]]}))
