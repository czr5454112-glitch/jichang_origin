"""Root review: restricted native-view representation repair, fixed96 unchanged."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import launch_live_obligation_recollection_v2 as launcher
c=launcher.campaign; here=Path(__file__).parent
out=c.OUT/'live_obligation_recollection_native_v2_prepare_001'
expected='f0db13dfee5ba0329664137cbcb1ef1452dc18be785950423cc8a7b6e020f6f8'
assert c.sha(out/'preregistered_protocol.json')==expected
plan=c.read(out/'preregistered_protocol.json'); c.verify(out,plan)
assert len(plan['source_sha256'])==85 and len(plan['rows'])==96
assert c.sha(c.FAILED_PLAN)==c.FAILED_PLAN_SHA and c.sha(c.DIAGNOSIS)==c.DIAGNOSIS_SHA
old=c.read(c.FAILED_PLAN); assert len(old['source_sha256'])==82
for path,digest in old['source_sha256'].items():
    assert c.sha(path)==c.sha(c.FAILED_PLAN.parent/old['source_archive'][path])==digest
counts={k:sum(int(s.get(k,0)) for s in ET.parse(c.TEST_XML).getroot().iter('testsuite'))
        for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=64,failures=0,errors=0,skipped=0)
assert c.sha(c.TEST_XML)=='82909777d748c76d56daba2fc56f1e14098674f0107afa8f5c3246706da2ec3a'
assert c.policy.OwnerPolicy.decide_pending.__code__ is c.policy.old.OwnerPolicy.decide_pending.__code__
assert c.policy.adapter is c.policy.old.adapter
for name in ('verify_attempts','verify_saved','replay_information','verify_replies','verify_partial'):
    assert getattr(c.saved,name).__code__ is getattr(c.saved.old,name).__code__
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'launch_claim.json').exists()
wrapper=here/'invoke_recollection_native_v2_001_measured.ps1'
assert not wrapper.exists()
text=(here/'invoke_recollection_native_001_measured.ps1').read_text(encoding='utf8')
changes={
 'live_obligation_recollection_native_prepare_001':'live_obligation_recollection_native_v2_prepare_001',
 '9b5d2cc047a0c75cdde4d916542728b491dccc71c09cf026720aad9c135dea98':expected,
 'launch_live_obligation_recollection':'launch_live_obligation_recollection_v2',
 '701b2653386be550aaad9a95779a8fba7378e7d8b4e9ae4bcaca53a045e6c3fa':c.sha(launcher.__file__),
 'g31.recollection_native.external_application_wall.v1':'g31.recollection_native.external_application_wall.v2',
 'Functional96 validation; concurrent source and pure checks permitted. No latency benchmark or isolated performance claim.':'Functional96 validation; concurrent original026 logging-only full-day bridge and source/pure checks permitted, total at most two native workers. No latency benchmark or isolated performance claim.',
}
for before,after in changes.items():
    assert before in text; text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f: f.write(text)
review=out/'root_prelaunch_review_001.json'
report={'schema':'g31.recollection_native.root_prelaunch_review.v2',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_fixed96_attempt_ready',
 'plan_sha256':expected,'live_archive_sources_verified':85,'old82_unchanged':True,'pure_tests':counts,
 'source_bound_failure_diagnosis':c.reference(c.DIAGNOSIS),
 'reviewed_rules':[
  'Normalizer permits tuple-to-list only in accepted027 node_records/edge_records row locations and exact row lengths; other tuples/custom objects/nonstring keys/nonfinite/cycles rejected.',
  'Every field,scalar exact type,float.hex and array order compared. Dictionary key order ignored consistently with existing sealed adapter sorting; no data field or timestamp discarded.',
  'Original decide_pending bytecode and actual failed-read session/time/content seal unchanged; pure normalized view cannot grant capability.',
  'Original initial branch,all physical inputs,96 fixed vectors,all current target/action/ACK-union/time/service and max-one-fresh-pair limits retained.',
  'Same full saved verifier bytecode privately bound to same new screen. 44 actual source-shaped tuple failures individually covered; JSON-only expected records alone do not stand for live shapes.',
  'Old52assessed44unknown and zero actual fresh pairs remain immutable. New96 native outcomes required; no old normal-message model or online optimizer result reused.',
  'All96 denominator,fullH40/five-job receipts,entry/exit acceptance and exports/audit share600s owned process tree.',
 ],
 'limits':['Functional finite validation only; concurrent bridge means no isolated performance comparison.',
           'Complete16/32 references require all members assessed; no generic model/joint/100ms/day certificate.'],
 'wrapper':c.reference(wrapper),'producer':c.reference(__file__),'native_executions':0,'model_evaluations':0}
with review.open('x',encoding='utf8') as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:
    json.dump({'status':'ready_for_one_bounded_actual_attempt','plan_sha256':expected,
       'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
       'native_branches':96,'owned_seconds':600,'native_dispatched':False},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper)}))
