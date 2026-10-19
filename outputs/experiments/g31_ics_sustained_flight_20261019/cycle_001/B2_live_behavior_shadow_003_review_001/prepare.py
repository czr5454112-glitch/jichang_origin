"""Prepare read-only audit budget/inputs; no artifact audit or native calls."""
import hashlib
import json
import gzip
from pathlib import Path
HERE=Path(__file__).resolve().parent;CYCLE=HERE.parent;ROOT=HERE.parents[4]
RUN=CYCLE/'B2_live_behavior_shadow_003';BASE=CYCLE/'C00_receiver_recorded_budget_002'
def read(path):
    data=Path(path).read_bytes();return json.loads(gzip.decompress(data) if str(path).endswith('.gz') else data)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def refs(value):
    if isinstance(value,dict):
        if {'path','sha256'}<=set(value):yield value
        for item in value.values():yield from refs(item)
    elif isinstance(value,list):
        for item in value:yield from refs(item)
def write(path,data):
    with Path(path).open('x',encoding='utf8') as f:json.dump(data,f,indent=2)
plan=read(RUN/'plan.json');resources=plan['behavior_shadow'];audit=HERE/'audit.py'
entry=ROOT/'scripts/experiments/g31_ics_circulation/foundation_airport_shadow_review.py'
sources=set(plan['source_sha256'])|{str(HERE/'prepare.py'),str(audit),str(entry)}
for source,archive in plan['source_archive'].items():sources.add(str(RUN/archive))
for folder in (RUN,BASE):
    for path in [folder/'plan.json',folder/'receipt.json',folder/'C00/raw.json.gz',folder/'C00/client_calls.json.gz',
                 folder/'C00/delivered_ack_views.json.gz',folder/'C00/worker_report.json',folder/'C00/acceptance.json']:
        sources.add(str(path))
    data=read(folder/'C00/raw.json.gz')
    sources.update(segment['raw']['path'] for segment in data['segments'])
    sources.add(read(folder/'plan.json')['input']['path'])
for name in ('behavior_shadow_receipt.json','behavior_shadow_events.jsonl','policy_observation_receipt.json','policy_observations.jsonl.gz','policy_observations.blobs.jsonl.gz'):
    sources.add(str(RUN/'C00'/name))
for reference in refs(resources):sources.add(reference['path'])
for reference in refs(read(resources['model_manifest']['path'])):sources.add(reference['path'])
sources.add(str(ROOT/'scripts/experiments/g31_ics_circulation/foundation_airport_observations_v2.py'))
assert all(Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT) for path in sources)
spec={'task_id':HERE.name,'module':'scripts.experiments.g31_ics_circulation.foundation_airport_shadow_review',
    'args':['--audit',str(audit),'--audit-sha256',sha(audit)],'native_branches':0,'hard_seconds':120,
    'inner_admission':'g31_shadow_readonly_audit_v1','sources':sorted(sources),
    'requires':['B2_live_behavior_shadow_003'],
    'assessment':{'path':str(HERE/'report.json'),'allowed_statuses':['passed_closed_two_callback_shadow_mechanism']},
    'next_action':'Report independent native/command/ACK parity and two real public callback/model/actual first request/ACK/edge joins; retain score and entire callback timing without100ms, policy gain or heldout claims. No retry.'}
write(CYCLE/(HERE.name+'_task.json'),spec)
write(HERE/'audit_registration_basis.json',{'schema':'g31.shadow_readonly_audit_registration.v1',
    'soft_seconds':100,'hard_seconds':120,'native_branches':0,'fit_calls':0,'automatic_retries':0,
    'audit':{'path':str(audit),'sha256':sha(audit)},'entry':{'path':str(entry),'sha256':sha(entry)},
    'input_count':len(sources),'entry_in_prior49_file_full_regression':False,
    'entry_validation':'The registered actual audit execution validates this new minimal entry; no claim that previous full regression covered it.'})
print(json.dumps({'spec':str(CYCLE/(HERE.name+'_task.json')),'sources':len(sources),'entry_sha256':sha(entry)}))
