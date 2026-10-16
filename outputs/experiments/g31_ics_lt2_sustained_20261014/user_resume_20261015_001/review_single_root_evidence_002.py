"""Root source/pin review of the full saved18 evidence construction mock."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_single_root_evidence as m
c=m.c
out=c.OUT/'single_root_evidence_pair_prepare_002'
expected='086dd891c9b60a2700045c5c75da0cd9d67776f541e1c8c9eb215f82d8ba36cf'
plan=m.verify_pins(out,expected)
assert len(plan['source_sha256'])==128
assert len(plan['row_order'])==72 and len(plan['input_raw'])==18
loaded=c.check_loaded_sources(plan)
counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure_XML']['path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=51,failures=0,errors=0,skipped=0)
assert plan['pure_XML']['sha256']=='95ad0265ebc5c3ae326971b1ab0975636d054e0fc00d4e0a568343188a3b1f08'
old=c.verify_plan(m.m.SOURCE,m.m.CAMPAIGN_SHA)
assert len(old['source_sha256'])==130
narrow=out/'independent_source_review_legal_001.json'
assert c.sha(narrow)=='ffbecc26e9bddc04fa8b25b2759db583be2cfd1bc2957c77d2a9f7aa089014c4'
assert c.read(narrow)['status']=='no_concrete_source_blocker_identified'
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
wrapper=Path(__file__).parent/'invoke_single_root_evidence_002_measured.ps1'
report={'schema':'g31.single_root_evidence.root_source_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_fixed_saved18_mock_gate_ready',
 'plan_sha256':expected,'preparation':c.reference(out/'preparation.json'),
 'live_archive_source_count':128,'loaded_sources_verified':len(loaded),'old_native130_sources_unchanged':True,
 'pure_counts':counts,'independent_narrow_review':c.reference(narrow),
 'rules':[
  'Exactly original18 saved roots, ABBA4 for each, 36 full constructions per arm. No prediction, native session, scheduler change or historical result promotion.',
  'Candidate builds the complete evidence tree in original field order, performs existing fresh normalization, encodes it once, strictly decodes and compares ordered types and float bits. All original events and both endpoint records remain.',
  'Only newly owned value and ledger are returned without a second deepcopy. Original publish bytecode, holder return identity, append and outside-return clock retained.',
  'Encode/decode/ledger failures propagate before success. Pure actual18 equality uses frozen clocks; independent source review finds no concrete blocker.',
  'Saved readback retains all72 rows with hashes, exact topology and formulas, full original evidence/ledger/returncodec. Historic root/event/deadline clocks are data, never new native request timing.',
  'Every sample begins before mock construction and ends after publication returns. Setup/hash/source check/export/deallocation/readback/cleanup remain in fixed240 owned campaign or the complete external Python application clock.',
  'Shared240 is fixed and retains failures or partials; external startup and parent tails are neither subtracted nor amortized.',
 ],
 'limitations':['Mock evidence/return cost only; no live full32 or finite2 complete request100ms claim.',
  'Actual native18 remains16closed/2unknown and0under100ms.',
  'Dispatch requires bridge completion and no concurrent agent heavy work; unrelated system load uncontrolled.'],
 'native_calls':0,'new_predictions':0,'benchmark_calls_in_review':0,
 'producer':c.reference(__file__),'wrapper':c.reference(wrapper)}
dest=out/'root_source_review_001.json'
with dest.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:
 json.dump({'status':'ready_for_one_bounded_mock_attempt','plan_sha256':expected,
  'root_review':c.reference(dest),'wrapper_sha256':c.sha(wrapper),'benchmark_dispatched':False,
  'fixed_calls':72,'owned_seconds':240},f,indent=2)
print(json.dumps({'review_sha256':c.sha(dest),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper)}))
