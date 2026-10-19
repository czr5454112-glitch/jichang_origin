"""Freeze the prepared diagnostic task; does not execute native or models."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
CYCLE=Path(__file__).resolve().parent
RUN=CYCLE/'B2_live_behavior_shadow_003'

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
def refs(value):
    if isinstance(value,dict):
        if {'path','sha256'}<=set(value):yield value
        for item in value.values():yield from refs(item)
    elif isinstance(value,list):
        for item in value:yield from refs(item)

plan=read(RUN/'plan.json');resources=plan['behavior_shadow']
allrefs=list(refs(plan))+list(refs(read(resources['model_manifest']['path'])))
sources=set(plan['source_sha256'])|{str(RUN/'plan.json')}|{r['path']for r in allrefs}
for path,expected in plan['source_sha256'].items():assert sha(path)==expected
for source,archive in plan['source_archive'].items():assert sha(RUN/archive)==plan['source_sha256'][source]
for item in allrefs:assert sha(item['path'])==item['sha256']
old=read(resources['baseline_plan']['path'])
assert len(old['source_sha256'])==107
assert all(plan['source_sha256'][k]==v for k,v in old['source_sha256'].items())
assert Path(plan['input']['path']).read_bytes()==Path(old['input']['path']).read_bytes()
targets=read(resources['runtime_targets']['path'])
assert len(targets)==2 and all(set(r)=={'callback'} and set(r['callback'])=={'owner_id','now','sequence','residual_index','request_prefix'} for r in targets)
task={'task_id':RUN.name,'module':'scripts.experiments.g31_ics_circulation.foundation_airport_shadow_campaign',
    'args':['--launch','--output',str(RUN)],'native_branches':1,'hard_seconds':720,
    'sources':sorted(sources),'requires':[],
    'assessment':{'path':str(RUN/'receipt.json'),'allowed_statuses':['requested_calibration_end_reached','censored_before_requested_window_end','native_event_budget_censored']},
    'next_action':'Retain every failure/partial. After native closes independently verify source archives and all new gzip/reference hashes, full native jobs/trays/transfers/receipts and command parity versus baseline, exact2 actual callback/public/model/submit/positiveACK/unique firstedge joins; both ACK and edge within300. Scores must not select actions. Diagnostic mechanism only, no gain/heldout/100ms certification; no automatic retry.'}
write(CYCLE/(RUN.name+'_task.json'),task)
freeze={'schema':'g31.airport_live_shadow_preparation_audit.v1','status':'prepared_not_executed',
    'plan':{'path':str(RUN/'plan.json'),'sha256':sha(RUN/'plan.json')},
    'runtime_source_count':len(plan['source_sha256']),'registered_sources_and_references':len(sources),
    'original107_source_bytes_preserved':True,'same_native_input_bytes':True,'input_sha256':plan['input']['sha256'],
    'runtime_targets':targets,'real_model_manifest':resources['model_manifest'],
    'resource_budget':resources['contract'],'actual_native_calls':0,'actual_fit_calls':0,
    'pure_test_report':{'path':str(ROOT/'outputs/airport_shadow_tests_005.xml'),'sha256':sha(ROOT/'outputs/airport_shadow_tests_005.xml')},
    'pure_tests_passed':16,'scorer_and_entire_recorded_callback_timed_separately':True,
    'full_native_request_ACK_edge_join_pending':True,'runtime_scoring_outcomes_not_yet_known':True}
write(RUN/'preparation_audit.json',freeze)
for name,reason in [('B2_live_behavior_shadow_001','Runtime target retained offline outcome and reference-command fields; replaced by identity-only target contract.'),
                    ('B2_live_behavior_shadow_002','Identity-only planner corrected, but execute_continuous still loaded the full offline selection; replaced by separate pinned runtime identity artifact and no live selection load.')]:
    write(CYCLE/name/'superseded.json',{'status':'superseded_preparation_never_registered_or_executed','reason':reason,
        'original_plan_sha256':sha(CYCLE/name/'plan.json'),'replacement':freeze['plan'],'native_calls':0})
write(CYCLE/'C00_receiver_recorded_budget_002_review_001/shadow_callback_selection_superseded.json',{
    'superseded_file':'shadow_callback_selection.json','reason':'Exploratory edge-only window; request1943 positive delivered ACK at+302.2 violates frozen double300 rule.',
    'applicable_selection':resources['selection'],'all3978_materialization_audit_complete':True})
print(json.dumps({'plan_sha256':freeze['plan']['sha256'],'sources':len(plan['source_sha256']),
    'registered_refs':len(sources),'task':str(CYCLE/(RUN.name+'_task.json'))}))
