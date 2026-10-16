"""Root source/domain/pin review; no native or model evaluations."""
from datetime import datetime, timezone
from pathlib import Path
import json
from scripts.experiments.g31_ics_circulation import research_live_obligation_native_domain as m

here=Path(__file__).resolve().parent;out=here.parent
folder=out/'live_obligation_native_domain_prepare_001';plan=m.read(folder/'preregistered_protocol.json')
assert m.sha(folder/'preregistered_protocol.json')=='dc9cc27b6a04eae5eb8ce5d97b9ef844e00657b2cec34004bafb41f952586c04'
m.verify(folder,plan)
old=out/'live_obligation_native_probe_prepare_004';oldplan=m.read(old/'preregistered_protocol.json')
for p,d in oldplan['source_sha256'].items():assert m.sha(p)==m.sha(old/oldplan['source_archive'][p])==d
assert len(plan['rows'])==96 and plan['case_order']==['mechanism','no_overlap','insufficient_advance']
assert plan['first_return_action_semantics']['first_return_not_before']==7.84
before=here/'invoke_live_obligation_native_probe_004_measured.ps1'
wrapper=here/'invoke_live_obligation_native_domain_001_measured.ps1';assert not wrapper.exists()
text=before.read_text(encoding='utf8').replace('live_obligation_native_probe_prepare_004','live_obligation_native_domain_prepare_001').replace('research_live_obligation_native_probe','research_live_obligation_native_domain').replace('7f5b1937a44efb2c7fe9b376765a1b9ddb44a9ad93575cadf48f6e0dc06acabc','dc9cc27b6a04eae5eb8ce5d97b9ef844e00657b2cec34004bafb41f952586c04').replace('2d87ee2eed5890008a30bf3fba2b5a634b25a9b914854ee77798bda77d2fdad9','d065cb78e6a37f1ae31d6a7a1a08f42c5f5e31ff746e7d765f5a15159d2a577c').replace('g31.live_obligation_native_probe.external_application_wall.v1','g31.live_obligation_native_fixed96.external_application_wall.v1').replace('child_job_budget_seconds=120;native_branch_budget=3','child_job_budget_seconds=600;native_branch_budget=96').replace('shared120s owned worker','shared600s owned worker').replace('three fixed vector12/24/25 native sessions','all96 fixed native sessions across three frozen cases').replace('full five-job physical audit and saved endpoint replay','full five-job physical audit and saved endpoint replay for each branch; complete16 reference families only when every member is assessed; frozen same32-budget public-model selections mapped afterward')
assert 'shared120s' not in text and 'native_branch_budget=3' not in text
wrapper.write_text(text,encoding='utf8')
r={'status':'passed_root_fixed96_source_and_domain_review','recorded_utc':datetime.now(timezone.utc).isoformat(),'plan':m.reference(folder/'preregistered_protocol.json'),'wrapper':m.reference(wrapper),'source_count':75,'old004_source_count_unchanged':73,'pure_test_count':38,'native_binary':'accepted027','branch_count':96,'case_count':3,'actions_per_case':32,'reference_family_size':16,'shared_child_seconds':600,'reviewed':'Full guard and adapter diffs against accepted004; runner extension and new comparison contract; actual frozen input/action semantics and tests. Three public graph plus full job contracts identify case. Existing lifecycle restrictions still fail unknown. No native result chooses online actions.','absolute_return_rule':'First0.5 means max(actual now, frozen public7.84); second return is immediate.004 all0 unaffected.','all_candidate_outcomes_required':True,'no_epsilon':True,'old_sources_changed':False,'actual_native_dispatched':0,'online_solver_executed':False,'complete100ms_certified':False}
dest=folder/'root_prelaunch_review_001.json';assert not dest.exists();m.write(dest,r)
print(json.dumps({'review':m.reference(dest),'wrapper':m.reference(wrapper)}))
