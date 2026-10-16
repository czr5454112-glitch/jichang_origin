"""Root source/image/input checks only; no worker or prediction dispatch."""
import json
from pathlib import Path
from scripts.experiments.g31_ics_circulation import measure_json_prediction_service as m

D = m.OUT / 'json_prediction_RPC_prepare_002'
H = m.OUT / 'user_resume_20261015_001'
assert m.sha(D / 'ready.json') == '84ded34a92809a98819e60ce55eda60ec69999690ae49d08bcb2a727a449e1ab'
assert m.sha(D / 'preregistered_protocol.json') == 'c30af2fa76ec3cb57d5fa627f7daf6b419bbdbb863c3ff8e384626880dd35d06'
plan = m.read(D / 'preregistered_protocol.json')
m.verify_pins(D, plan)
assert len(plan['source_sha256']) == 85
assert plan['image']['version'] == 'e3de2dd352b6a6b114cf31fee832c595418b1bcc6e2e4c7409df5c2159086c65'
pure = m.OUT / 'json_prediction_worker_pure_005'
m.check_pure_gate(pure, m.read(pure / 'receipt.json'))
assert m.sha(pure / 'tests.xml') == '6248a5fc1d299898850965bec761d25c844cb015efa2cd194e4194038d7e7d62'
assert not any((D / n).exists() for n in ('execution_claim.json', 'ledger.json', 'report.json', 'external_application_wall.json'))
wrapper = H / 'invoke_json_prediction_RPC_002_measured.ps1'
assert 'c30af2fa76ec3cb57d5fa627f7daf6b419bbdbb863c3ff8e384626880dd35d06' in wrapper.read_text()
report = {'status':'passed_root_prelaunch_source_and_artifact_check', 'plan_sha256':m.sha(D / 'preregistered_protocol.json'),
          'source_count':85, 'pure_tests':80, 'wrapper_sha256':m.sha(wrapper), 'native_calls':0, 'new_predictions':0,
          'checks':['Root read strict JSON codec, source-image loader, private context construction, process client and full campaign verifier.',
                    'Only implementation guards move to startup; per-request data guards, isolation, fingerprint, potential, complete baseline and32 predictions remain.',
                    'Fixed exact loaded-source maps and full startup proofs are bound to actual pure-gate startup/close records, with omission/tamper rejection.',
                    'Caller outside-call clocks include input decode, IPC, worker result and caller bookkeeping/return; shutdown includes reclamation.',
                    'Per-wire2MiB and saved-artifact64MiB bounds differ; deadline watchdog plus owned120s tree preserve failures regardless Windows exitcode.',
                    'Both arms use the same source image and six JSON-decoded inputs; all768 outputs and24 baselines required, no discarded warmup.',
                    'Cold and close costs remain explicit and whole external application wall includes all setup/checks/export; no full100ms certification.']}
path = D / 'root_prelaunch_review_001.json'
with path.open('x', encoding='utf8') as f: json.dump(report, f, indent=2)
print(json.dumps({'status':report['status'], 'sha256':m.sha(path)}))
