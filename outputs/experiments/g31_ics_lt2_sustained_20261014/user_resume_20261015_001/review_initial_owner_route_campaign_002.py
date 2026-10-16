"""Root prelaunch source/pin review. No native/predictor execution."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_campaign as c
OUT=c.OUT/'initial_owner_route_campaign_prepare_002'
EXPECTED='937d8505d33feeead2bfbbeb3479bb0038a82fbdd013ba2273700123e519d3e5'
plan=c.verify_plan(OUT,EXPECTED)
assert len(plan['source_sha256'])==124 and len(plan['compiled_source_archive_sha256'])==67 and len(plan['rows'])==18
loaded=c.check_loaded_sources(plan)
suite=ET.parse(plan['pure_XML']['path']).getroot()
counts={k:sum(int(s.attrib.get(k,0)) for s in suite.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=53,failures=0,errors=0,skipped=0)
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
wrapper=Path(__file__).resolve().parent/'invoke_initial_owner_route_campaign_002_measured.ps1'
assert not (OUT/'execution_claim.json').exists()
report={'schema':'g31.initial_owner_route.root_prelaunch_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_finite_native_attempt_ready',
 'campaign_sha256':EXPECTED,'source_preparation':c.reference(OUT/'source_preparation.json'),
 'live_archive_sources_verified':124,'compiled_archive_sources_verified':67,'loaded_project_sources_verified':len(loaded),
 'pure_tests':counts,'predictor_functional_startup':plan['startup_reference'],
 'reviewed_rules':[
 'Six original cases with fixed-default and finite2 solver; three genuine native fault variants each both arms; total18 preserved.',
 'Actual accepted027 NativeSession, fixed B action at.11 before advance and both fixed continuation owners; no session proxy.',
 'Root admitted at.05 before publication/collection; source and receiver rechecked from actual owned endpoints; real ACK and actual firsthop plus complete drain required.',
 'Successful final collection and initial A/B raw endpoints saved with original collection bytecode in private namespace.',
 'Complete root wall includes all query/native/background/codec/RPC/return/ledger work; cold startup/acceptance/cleanup and full campaign separately unamortized.',
 'Failure/partial diagnostic uses no result_at or drain; preserves exact physical cut and offline diagnostics.',
 'Verifier reconstructs final-check choice in event order, including later overrun downgrade, rather than substituting final choice retrospectively.',
 'Immutable request/retry payloads, RPC counts/identity, endpoint replay and all-five-job full-H40 physical audit retained. No full internal query tape claim.',
 'Owner outage gates execution/publication, not ACK delivery; globaldrop3 may prevent initial readiness. Route-only ACK fault is explicitly unavailable.',
 '600s owned process tree and no restart; performance window has no concurrent experimental native/pure workloads.',
 ],
 'limits':['Finite2 initial-stage integration only, not full32 search.','No generic or cold100ms, two-machine, original-day or joint-novelty certificate.','Normal point model is not certified on future fault cases.','Unrelated user/system load not controlled.'],
 'reviewed_wrapper':c.reference(wrapper),'review_producer':c.reference(__file__),
 'native_executions_in_review':0,'model_evaluations_in_review':0}
review=OUT/'root_prelaunch_review_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready={'status':'ready_for_one_bounded_actual_attempt','campaign_sha256':EXPECTED,
 'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
 'native_dispatched':False,'fixed_native_branches':18,'owned_seconds':600,
 'three_overall_goals_still_unmet':True}
dest=OUT/'root_ready_001.json'
with dest.open('x',encoding='utf8') as f:json.dump(ready,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(dest),'wrapper_sha256':c.sha(wrapper),'sources':124,'pure':53,'native_dispatched':False}))
