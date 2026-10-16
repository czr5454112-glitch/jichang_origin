"""Root prelaunch review of full18 one-build evidence/actual-observation gate."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_gate_campaign_v2 as c
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_gate_campaign_v2 as launcher
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_gate_campaign_v2 as verifier
out=c.OUT/'initial_owner_route_gate_campaign_prepare_002';here=Path(__file__).resolve().parent
expected='659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4'
plan=c.verify_plan(out,expected)
assert len(plan['source_sha256'])==141 and len(plan['compiled_source_archive_sha256'])==67 and len(plan['rows'])==18
loaded=c.check_loaded_sources(plan)
counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure_XML']['path']).getroot().iter('testsuite'))
        for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=130,failures=0,errors=0,skipped=0)
assert plan['pure_XML']['sha256']=='1f682f58d7a612aea72d12fbbe351c3254164ac70cbf199898750cd0011ba708'
older=c.OUT/'initial_owner_route_campaign_v3_prepare_001';previous=c.read(older/'campaign.json')
assert len(previous['source_sha256'])==130
for name,digest in previous['source_sha256'].items():
    assert c.sha(name)==c.sha(older/previous['source_archive'][name])==digest
assert plan['rows']==previous['rows']
withheld=c.OUT/'initial_owner_route_gate_campaign_prepare_001'
assert c.sha(withheld/'root_dispatch_withheld_001.json')=='9b0a188713e33412b13990e3393377e147825e6fd3528a60bc333c55d699f759'
old_gate=c.read(withheld/'campaign.json');assert len(old_gate['source_sha256'])==139
for name,digest in old_gate['source_sha256'].items():
    assert c.sha(name)==c.sha(withheld/old_gate['source_archive'][name])==digest
assert not (withheld/'execution_claim.json').exists()

assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_initial_owner_gate_002_measured.ps1'
assert not wrapper.exists()
text=(here/'invoke_initial_owner_route_v3_001_measured.ps1').read_text(encoding='utf8')
changes={
 'initial_owner_route_campaign_v3_prepare_001':'initial_owner_route_gate_campaign_prepare_002',
 'e5459ab579d76e65c76ee41b0a4bc5f06224f3be0796ace6636ec4d0a2f7b46d':expected,
 'launch_initial_owner_route_campaign_v3':'launch_initial_owner_route_gate_campaign_v2',
 'c4f845cc5137622586b7cfb89b95e4293686b25ff2247cace57f652f6773e338':c.sha(launcher.__file__),
 'g31.initial_owner_route.external_application_wall.v3':'g31.initial_owner_route_gate.external_application_wall.v1',
 'Fresh96 functional campaign and bridge prelaunch review ended. Other agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this performance window closes.':'Fresh historical96 native and saved review completed. Before dispatch all agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this performance window closes.',
 'all policy/codec/endpoint and physical export, saved endpoint/RPC/physical verification':'all policy/codec/complete required outbox proof/endpoint and physical export, saved full refresh/outbox/endpoint/RPC/physical verification',
}
for before,after in changes.items():assert before in text; text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
report={'schema':'g31.initial_owner_gate.root_prelaunch_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_finite_native_attempt_ready',
 'campaign_sha256':expected,'source_preparation':c.reference(out/'source_preparation.json'),
 'live_archive_sources_verified':141,'compiled027_archive_sources_verified':67,
 'loaded_project_sources_verified':len(loaded),'old130_source_package_unchanged':True,
 'pure_tests':counts,'startup_reference':plan['startup_reference'],
 'reviewed_rules':[
  'All18 original declarations, input/arm/fault denominator, NativeSession027, LocalTransport identity, background .05 cadence and client.activate ID sequence retained; original firsthop unchanged.',
  'Private scheduler and refresh transforms restore complete original AST; no global monkeypatch or native proxy. ActualAdvanceChain computes continuity internally from actual native advance calls and validates closed exact function identities.',
  'Root skips duplicate observation/drain only after complete chained A/B notification cursors, no A delta, no new protocol calls and no due A retry; uncertainty falls back. Initial collection precedes chain and cannot manufacture continuity.',
  'Original ACK-change expression evaluated once and unconditional row assignment retained. Separate strict body_is_new checks dictionary order, builtin type, finite float.hex and signed zero. Equal Python ACKs with a different representation get a new full body even when ack_changed stays false. Actual queries, empty resets and retry terminal resets remain unchanged.',
  'Incremental saved refresh replay processes complete owner query order, immutable first/retry calls, ACK change/handling lineage and exact outbox at every gate checkpoint and final; actual arguments cannot be replaced with saved surrogate inputs.',
  'All root-required trace/calls/creations/outbox and advance prefix are inserted before the single complete normalize/encode, charged to original outside-return root wall. Full-H later trace raw export remains charged to branch/campaign.',
  'Original endpoint/RPC/image/physical full verifier functions retained in private namespaces, plus source-bound notification gate and query/outbox proof. Does not claim every internal native query is replayed.',
  'Compiled scheduler differential and all original gates retained. New intermediate equal-but-reordered and int/float/signed-zero changes followed by final restoration are checked per query. Tests reproduce the withheld001 gap without changing its139-source package. Actual v3 ACK shapes are shape data, not future policy information.',
  'One600s owned process tree,18 native branches,1 pure RPC predictor. Complete root/cold/failure costs retained, no subtraction/amortization. Failed artifact/firsthop/trace rows remain unknown.',
 ],
 'limits':['Finite2 initial request only; full32 and general100ms remain unproved.',
           'Additional full trace evidence may consume the observed gate savings; no speed promised.',
           'Exclusive agents must be confirmed immediately before dispatch; unrelated user/system load uncontrolled.',
           'No original-day or online strong-method certificate.'],
 'producer':c.reference(__file__),'wrapper':c.reference(wrapper),'native_executions':0,'model_evaluations':0}
review=out/'root_prelaunch_review_001.json';ready=out/'root_ready_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_one_bounded_actual_attempt',
 'campaign_sha256':expected,'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
 'native_dispatched':False,'fixed_native_branches':18,'owned_seconds':600},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),
 'wrapper_sha256':c.sha(wrapper),'launcher_sha256':c.sha(launcher.__file__)}))
