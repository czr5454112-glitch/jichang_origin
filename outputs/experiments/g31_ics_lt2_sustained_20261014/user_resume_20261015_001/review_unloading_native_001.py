"""Root review: one already-budgeted actual pair for observed unload crossing."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import launch_live_obligation_unloading as launcher
c=launcher.campaign;here=Path(__file__).resolve().parent
out=c.OUT/'live_obligation_unloading_native_prepare_001'
expected='6c82cc7ad10aae82f2f9d9059899dca20753e4bf0f5a78885d2e53e505199ecd'
assert c.sha(out/'preregistered_protocol.json')==expected
plan=c.read(out/'preregistered_protocol.json');c.verify(out,plan)
assert len(plan['source_sha256'])==93 and len(plan['rows'])==96
assert c.sha(c.OLD_PLAN)==c.OLD_PLAN_SHA and c.sha(c.HISTORY_PREP)==c.HISTORY_PREP_SHA
old=c.read(c.OLD_PLAN);assert len(old['source_sha256'])==91
for path,digest in old['source_sha256'].items():assert c.sha(path)==c.sha(c.OLD_PLAN.parent/old['source_archive'][path])==digest
counts={k:sum(int(s.get(k,0)) for s in ET.parse(c.TEST_XML).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=79,failures=0,errors=0,skipped=0)
assert c.sha(c.TEST_XML)=='ed48274534c4aca941781d3919a6fa5cee730ccc31e83a3f3c6cf78f6ddce4c3'
for name in ('verify_attempts','verify_saved','verify_replies','verify_partial'):
    assert getattr(c.saved,name).__code__ is getattr(c.saved.old,name).__code__
assert c._native_branch.__code__ is c.prior._run_branch.__code__
assert c.run_branch.__code__ is c.base.run_branch.__code__
assert c.sha(out/'source_handoff.json')=='297c2b80ba11a1c7f9af5e410c670ae8e0f1a056133e83ad063c67011950198c'
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'launch_claim.json').exists()
wrapper=here/'invoke_unloading_native_001_measured.ps1'
text=(here/'invoke_historical_native_001_measured.ps1').read_text(encoding='utf8')
changes={
 'live_obligation_historical_native_prepare_001':'live_obligation_unloading_native_prepare_001',
 'bc3bc04e8c81e496120cfd7760e83c6274bd7e92f287fe68ba8d1e206737fcd5':expected,
 'launch_live_obligation_historical':'launch_live_obligation_unloading',
 '7ca023146806bf0beba4aa15e049ed75717b5bffa480ce1a04c1e6f3eb9fa955':c.sha(launcher.__file__),
 'g31.historical_native.external_application_wall.v1':'g31.unloading_native.external_application_wall.v1',
 'actual owner-local historical ACK/immutable publication binding, collection attempts and bounded replies':'actual owner-local historical ACK/immutable publication binding, the one existing fresh pair for an actual observed unloading crossing, collection attempts and bounded replies',
}
for before,after in changes.items():assert before in text,before;text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
review=out/'root_prelaunch_review_001.json'
report={'schema':'g31.unloading_native.root_prelaunch_review.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'passed_fixed96_attempt_ready','plan_sha256':expected,'live_archive_sources_verified':93,
 'old91_unchanged':True,'pure_tests':counts,'source_handoff':c.reference(out/'source_handoff.json'),
 'rules':[
  'All old retry eligibility results are returned unchanged except the exact unsupported stable_observed_unloading first-read case. Saved224 regression changes only vector16/17 qualification; this is not an actual new pair result.',
  'B first_reuse_route only, recollection_index exact0, same collected current native view, delivered digest-bound A/B sources with age/validity/union guards and exact unloading E/receiver identity. Captured unload end may trigger recollection but cannot infer completion.',
  'Exact original L source/current identity and owned physical action set, delivered terminal own ACKs and unchanged five sequential .01 additions strictly before known L service bound. No epsilon, third pair, new wire delay or relaxed endpoint permission.',
  'Only the actual existing collector may acquire the fresh pair, retaining exact LocalTransport/session/admission/capability seal. All unchanged history/occupancy/current/terminal-receipt guards must then pass; absent terminal facts remain unknown.',
  'Old91/historical94of96 remain immutable. New3x32 inputs, H40/fivejobs, one600s tree with all native027 entry/exit acceptance, exports and full saved verifier retained. No label or old outcome used to select an action.',
  'Original full branch and saved verifier bytecodes privately rebound, no global patch or new native binary. First pure verifier namespace failure is retained; corrected79 pure tests passed before freezing.',
 ],
 'limits':['Finite functional96, no isolated latency/100ms or online strong-method claim.',
           'Every family member must be independently assessed; physical completion alone does not resolve information unknowns.'],
 'wrapper':c.reference(wrapper),'producer':c.reference(__file__),'native_executions':0,'model_evaluations':0}
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_one_bounded_actual_attempt','plan_sha256':expected,
 'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),'native_branches':96,'owned_seconds':600,'native_dispatched':False},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),
 'wrapper_sha256':c.sha(wrapper),'launcher_sha256':c.sha(launcher.__file__)}))
