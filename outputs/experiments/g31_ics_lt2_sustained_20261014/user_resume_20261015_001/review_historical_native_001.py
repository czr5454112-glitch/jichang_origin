"""Root review of actual owner-local history support, fixed fresh96 domain."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import launch_live_obligation_historical as launcher
c=launcher.campaign;here=Path(__file__).parent
out=c.OUT/'live_obligation_historical_native_prepare_001'
expected='bc3bc04e8c81e496120cfd7760e83c6274bd7e92f287fe68ba8d1e206737fcd5'
assert c.sha(out/'preregistered_protocol.json')==expected
plan=c.read(out/'preregistered_protocol.json');c.verify(out,plan)
assert len(plan['source_sha256'])==91 and len(plan['rows'])==96
assert c.sha(c.OLD_PLAN)==c.OLD_PLAN_SHA and c.sha(c.HISTORY_PREP)==c.HISTORY_PREP_SHA
old=c.read(c.OLD_PLAN);assert len(old['source_sha256'])==85
for path,digest in old['source_sha256'].items():assert c.sha(path)==c.sha(c.OLD_PLAN.parent/old['source_archive'][path])==digest
history=c.read(c.HISTORY_PREP)
for path,item in history['source_archive'].items():assert c.sha(path)==c.sha(item['archive']['path'])==item['sha256']
counts={k:sum(int(s.get(k,0)) for s in ET.parse(c.TEST_XML).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=82,failures=0,errors=0,skipped=0)
assert c.sha(c.TEST_XML)=='b59f1ae22778fae9d80a736f2642c6c2bedf666b40aa3ce9176a67943c335017'
for name in ('verify_attempts','verify_saved','verify_replies','verify_partial'):
 assert getattr(c.saved,name).__code__ is getattr(c.saved.base,name).__code__
assert c._native_branch.__code__ is c.prior._run_branch.__code__
assert c.run_branch.__code__ is c.base.run_branch.__code__
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'launch_claim.json').exists()
wrapper=here/'invoke_historical_native_001_measured.ps1';assert not wrapper.exists()
text=(here/'invoke_recollection_native_v2_001_measured.ps1').read_text(encoding='utf8')
changes={
 'live_obligation_recollection_native_v2_prepare_001':'live_obligation_historical_native_prepare_001',
 'f0db13dfee5ba0329664137cbcb1ef1452dc18be785950423cc8a7b6e020f6f8':expected,
 'launch_live_obligation_recollection_v2':'launch_live_obligation_historical',
 '35cbe11497846e10fc0cf765a5be9fb58465d9263902e3a5e01fba4e638bd574':c.sha(launcher.__file__),
 'g31.recollection_native.external_application_wall.v2':'g31.historical_native.external_application_wall.v1',
 'Functional96 validation; concurrent original026 logging-only full-day bridge and source/pure checks permitted, total at most two native workers. No latency benchmark or isolated performance claim.':'Functional96 validation; source/pure development may overlap. At most two native workers; this invocation has one. No latency benchmark or isolated performance claim.',
 'actual collection attempts and bounded replies':'actual owner-local historical ACK/immutable publication binding, collection attempts and bounded replies',
}
for before,after in changes.items():assert before in text;text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
review=out/'root_prelaunch_review_001.json'
report={'schema':'g31.historical_native.root_prelaunch_review.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'passed_fixed96_attempt_ready','plan_sha256':expected,'live_archive_sources_verified':91,
 'old85_and_historical_pure_sources_unchanged':True,'pure_tests':counts,
 'rules':[
  'Only B/first_reuse_route exact goal-loaded E/P is added. Current B own endpoint must contain a delivered valid selfACK with digest, immutable own request and actual observed final-edge identity matching the current pair.',
  'Derived arrival plus public service deadline is a separate field with complete provenance. Raw clamped ready remains unchanged; no terminal receipt or private remote state invented. Two unloading-crossing cases remain unsupported.',
  'Actual adapter requires exact fixture.LocalTransport, same accepted NativeSession, current admission identity and actual owned-row aliases. Full immutable first/retry call prefix, scalar types and order checked before and after original three endpoint reads.',
  'Original accepted handle/session/time/content seal is retained with the extra audit ledger included. Unknown or partial reads cannot gain origin capability; same original maximum one fresh pair and reply/choice budgets retained.',
  'Full current owner/action/ACK union/occupancy/L .01wire and strict zero-tolerance protection guards rerun. Saved verifier reconstructs lawful publication ledger from raw call prefix and unique actual owner admission, then compares complete information.',
  'Actual96 is mandatory because first collection may now succeed and change later timing. No saved94/2 or old80/16 promoted. Same three cases by32, H40/five jobs, actual physical inputs/actions and600 owned tree including entry/exit acceptance, all exports and saved audits.',
  'Old full branch and saved verifier bytecodes privately rebound; no global monkeypatch or new native binary. Full source closure, interpreter, binary, references and input hashes verified.',
 ],
 'limits':['Finite functional validation; no complete full32 optimizer100ms, original-day protection or joint novelty claim.',
  'Complete reference families require every member assessed. Missing/failed/timedout branches remain in96 denominator.',
  'Normal-exchange pure projection output is not reused as a fresh native label.'],
 'wrapper':c.reference(wrapper),'producer':c.reference(__file__),'native_executions':0,'model_evaluations':0}
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_one_bounded_actual_attempt','plan_sha256':expected,
 'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),'native_branches':96,'owned_seconds':600,'native_dispatched':False},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper),'launcher_sha256':c.sha(launcher.__file__)}))
