"""Record the explicit post-user-interruption schedule before native launch."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

root = Path.cwd()
base = root / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
here = base / 'user_resume_20261015_001'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
tests = ET.parse(base / 'sealed_resume_pure_003.xml').getroot()
suite = tests.find('testsuite') if tests.tag != 'testsuite' else tests
assert int(suite.get('failures')) == int(suite.get('errors')) == int(suite.get('skipped')) == 0
plan = {'schema': 'g31.user_interruption_resumption_plan.v1',
    'registered_utc': datetime.now(timezone.utc).isoformat(),
    'authority': 'User requested comprehensive resume on 2026-10-15 after explicit pause.',
    'original_processes': 'Four original process identities observed absent. Their actual exit cause is unknown; old running receipts remain untouched.',
    'prior_attempts': 'Interrupted partial experiments, not successes and not measured 7200s budget failures. Complete prior source evidence and measured heartbeat costs retained; unpublished work cost remains unknown.',
    'input_contract': 'All original28506/57012 jobs,22 trays, unchanged directions/capacities/FIFO/mandatoryStorage, finalH86400; no removal or cap alteration.',
    'execution_contract': 'New attempts each capped at7200s including native reconstruction and continuation. Reconstruct every selected raw shard and match its contemporaneous native seal before state/session can escape. No JSON-only restoration.',
    'cost_contract': 'All measured prior source heartbeat costs, including excluded tail, remain charged conservatively; prior reconstruction separate/cumulative. No uninterrupted or complete100ms claim.',
    'native_binary': 'build_lt_session_024/python/czr005_circulation.cp311-win_amd64.pyd',
    'native_sha256': '030e4e116cd0ced9e4acc6a00ba5e111cbd5d2a48f14b62e9f2539f1e6a7710c',
    'public_static_cache': 'Accepted owner-isolated public graph/path pool, cold at each attempt. No observations/decisions/ACK cached.',
    'maximum_global_native_workers': 2,
    'schedule': '1x starts in free slot2 while026 acceptance owns slot1. Finite operation probe uses slot1 after026 exits;2x follows the short probe. Never more than2 native workers.',
    'pure_tests': {'xml': 'sealed_resume_pure_003.xml', 'sha256': sha(base / 'sealed_resume_pure_003.xml'), 'tests': int(suite.get('tests'))},
    'source_sha256': {str(p.relative_to(root)): sha(p) for p in [root / 'scripts/experiments/g31_ics_circulation/resume_sealed_stream.py', root / 'tests/test_g31_circulation_resume_sealed_stream.py']},
    'cases': {}}
assert sha(root / plan['native_binary']) == plan['native_sha256']
for scale in (1, 2):
    folder = base / f'full024_sealed_cut_{scale}x_20261015_001'
    cut = read(folder / 'cut_manifest.json')
    plan['cases'][f'full{scale}x'] = {'manifest': str((folder / 'cut_manifest.json').relative_to(root)),
        'manifest_sha256': sha(folder / 'cut_manifest.json'), 'stop_receipt': str((folder / 'source_stop_receipt.json').relative_to(root)),
        'stop_sha256': sha(folder / 'source_stop_receipt.json'), 'physical_time': cut['physical_time'],
        'known_native_seal': cut['known_native_seal'], 'offered_total': cut['offered_total'],
        'output': str((base / f'full024_resumed_{scale}x_20261015_001').relative_to(root))}
path = here / 'preregistered_resumption.json'
with path.open('x', encoding='utf-8') as out: json.dump(plan, out, indent=2, allow_nan=False)
state_path = root / 'docs/g31_ics_circulation/RESEARCH_STATE.json'
backup = here / 'RESEARCH_STATE_before_resume.json'
with backup.open('xb') as out: out.write(state_path.read_bytes())
state = read(state_path)
state['current_stage'] = 'User comprehensive resume2026-10-15. Old4process identities absent; immutable actual sealed cuts1xH54000/2xH28800 prepared.69pure resume checks pass; native026focused12+025/026legacy20pass, late known-seal gate running. Finite complete-operation probe pendingactual; joint192pure conditional only. Full-day business,complete100ms,joint effectiveness unmet.'
state['working_tree_identity'] = state['working_tree_identity'].replace('toward025', 'toward026')
pending = ['Execute new7200s-capped attempts from actual sealed cuts; preserve all28506/57012 jobs and original costs.',
    'Finish native026 actual known-seal late acceptance; build/focused tests alone are insufficient.',
    'Execute finite operation probe on accepted025 timing ABI, retaining unresolved roots; do not replace original business contract.',
    'Validate new3tray5job occupancy domain with actual legal messages, strong matched references and strict per-job protection.',
    'Freeze current sources, unified zero-skip regression and register all successes/failures; no commit/push.']
state['next_actions'] = pending
state['active_experiment']['pending'] = pending
state['active_experiment']['pause_status'] = 'User revoked pause; four old process identities absent, original exit cause unknown. See user_resume_20261015_001.'
state['active_experiment']['full024_status'] = 'Interrupted1x lastpublishedH55608.65206/135406updates; selectedactualsealH54000 shard268. Interrupted2x lastpublishedH29581.04327/68903updates; selectedactualsealH28800 shard136. Newattempts preregistered; no full-day success yet.'
state['active_experiment']['rolling_joint_status'] = 'Rolling00212actualbranches completed4jobs;20/24laterdecisions legally verified,4fallback;allmatchedgains0. New3tray192pure projections completed and audited; strong methods tie,actual/onlineunverified.'
state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
print(json.dumps({'plan_sha256': sha(path), 'cases': plan['cases'], 'pure_tests': plan['pure_tests']}, indent=2))
