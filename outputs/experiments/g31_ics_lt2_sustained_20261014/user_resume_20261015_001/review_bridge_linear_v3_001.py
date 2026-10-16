"""Root source-only review of logging correction, no large artifact reads."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_linear_v3 as a
out=a.OUT/'bridge_saved_linear_v3_prepare_001';here=Path(__file__).resolve().parent;base=a.base
expected='4bbf6f364ac097db7fbf2bd1ff35f9ea74500566f367933e552bf6da6f0bd87e'
assert base.sha(out/'plan.json')==expected
assert base.sha(out/'preparation.json')=='37241cb2d4bac1409ccdbdd8961aa931e2a445feada7ac7fcb70083d92336524'
plan=base.read(out/'plan.json');prior=base.read(a.old.PRIOR/'plan.json')
assert plan['linear_contract']==a.contract() and len(plan['source_before'])==92
allowed={'schema','source_before','linear_contract','pure','interpreter','preparation_scope','scope'}
assert set(plan)==set(prior)|{'linear_contract','preparation_scope'}
assert all(plan[k]==v for k,v in prior.items() if k not in allowed)
assert {str(p):base.sha(p) for p in a.closure()}==plan['source_before']
for name,digest in plan['source_before'].items():
    assert base.sha(name)==base.sha(out/'source'/Path(name).relative_to(a.ROOT))==digest
for prior_dir,count in ((a.old.PRIOR,84),(a.FAILED,87),(a.FROZEN_PREP,90)):
    old_plan=base.read(prior_dir/'plan.json');assert len(old_plan['source_before'])==count
    for name,digest in old_plan['source_before'].items():
        assert plan['source_before'][name]==base.sha(name)==base.sha(prior_dir/'source'/Path(name).relative_to(a.ROOT))==digest
loaded=a.prior.check_runtime(plan)
pure=plan['pure'];assert base.sha(pure['path'])==pure['sha256']=='6a5dae697c363af7bfbfd44d991f2f1167824868695c29ad32f17c2d81bd592d'
assert base.sha(pure['XML_path'])==pure['XML_sha256']=='2f2de0dc39f78888b1a13ab9af9f90c33357a64ca3bfab61c0c6ff50db026797'
counts={k:sum(int(s.get(k,0)) for s in ET.parse(pure['XML_path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=69,failures=0,errors=0,skipped=0)
assert not (out/'execution_claim.json').exists()
assert base.sha(a.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
wrapper=here/'invoke_bridge_linear_v3_001_measured.ps1'
text=(here/'invoke_bridge_linear_001_measured.ps1').read_text(encoding='utf8')
for before,after in {
 'bridge_saved_linear_prepare_001':'bridge_saved_linear_v3_prepare_001',
 '5048eb9e3365b5a29e69c82f685e821a36cc2417d4d9c9f8ea1876e56ad40032':expected,
 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_linear --execute':'scripts.experiments.g31_ics_circulation.audit_bridge_saved_linear_v3 --execute',
 'g31.bridge.linear_saved_audit.external_application_wall.v1':'g31.bridge.linear_saved_audit.external_application_wall.v3',
 'All original guards remain.':'All original guards remain. Progress-only correction aggregates ordinary bootstrap reads every256 under the same1024 limit, and preserves the first fatal even if a policy catches it. The earlier linear001 failure and unexecutedv2 prepare remain immutable.',
}.items():
    assert before in text;text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
report={'schema':'g31.bridge.linear_saved_audit.root_source_review.v3',
 'status':'passed_separate_saved_audit_ready','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'plan_sha256':expected,'live_archive_source_count':92,'old84_87_90_unchanged':True,
 'loaded_sources':loaded,'pure_counts':counts,'original_source_proof':a.core.source_proof(),
 'progress_contract':a.core.progress_contract(),
 'rules':[
  'Exact old linear001 bind and complete verifier bodies retained. No physical, FIFO, Storage, cap, ACK, clock, source or denominator guard removed.',
  'Only two exact final raw/input paths share local decoded trees. Original actor deepcopy, private observer identity, exact ordered argument/result checks and all37270new/27218old compressed hashes remain.',
  'Only ordinary bootstrap read logging changes: every read still occurs, without caching; every256 completed reads emits one counter. Two large whole-document decode stages remain individually visible.',
  'Full10305bootstrap plus37270 hash/replay count and128fixed-stage reserve used465of1024 records in pure tests. No dynamic log expansion or budget extension.',
  'First progress error object stays sticky. A policy swallowing it cannot produce a certificate; secondary replay-order error cannot replace it. An earlier genuine checker error remains primary if later reporting/cleanup fails; sidecar uses exact exception identities.',
  'One600 owned tree, all import/hash/read/decode/replay/export/exit charged; original2400, audit002600, linear00192s failure and pure00160 timeout preserved. Priorv2 preparation remains unexecuted.',
  'Only existing all_job_states export/hash redirects to new output. Large artifact/source binary/reference hashes are rechecked inside the owned execution, not represented as a prelaunch raw decode.',
 ],
 'large_artifact_reads_in_root_review':0,'raw_decodes_in_root_review':0,
 'native_calls':0,'new_predictions':0,
 'limits':['No native replay or independently reproduced seal.','No speedup, alloffered success or100ms claim.','Source/pure work may overlap; no isolated timing comparison.'],
 'producer':{'path':str(Path(__file__).resolve()),'sha256':base.sha(__file__)},'wrapper_sha256':base.sha(wrapper)}
review=out/'root_source_review_001.json';ready=out/'root_ready_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_separate_saved_audit','plan_sha256':expected,
 'root_review':{'path':str(review),'sha256':base.sha(review)},'wrapper_sha256':base.sha(wrapper),
 'full_saved_audit_dispatched':False,'owned_seconds':600},f,indent=2)
print(json.dumps({'review_sha256':base.sha(review),'ready_sha256':base.sha(ready),'wrapper_sha256':base.sha(wrapper)}))
