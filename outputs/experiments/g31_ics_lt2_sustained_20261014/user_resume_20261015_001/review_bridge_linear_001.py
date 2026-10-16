"""Source-only root review; all inherited large artifact pins recheck in Job."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_linear as a
out=a.OUT/'bridge_saved_linear_prepare_001';here=Path(__file__).resolve().parent;base=a.base
expected='5048eb9e3365b5a29e69c82f685e821a36cc2417d4d9c9f8ea1876e56ad40032'
assert base.sha(out/'plan.json')==expected
plan=base.read(out/'plan.json');prior=base.read(a.PRIOR/'plan.json')
assert plan['linear_contract']==a.contract() and len(plan['source_before'])==87
allowed={'schema','source_before','linear_contract','pure','interpreter','preparation_scope','scope'}
assert set(plan)==set(prior)|{'linear_contract','preparation_scope'}
assert all(plan[k]==v for k,v in prior.items() if k not in allowed)
assert {str(p):base.sha(p) for p in a.closure()}==plan['source_before']
for name,digest in plan['source_before'].items():
    assert base.sha(name)==base.sha(out/'source'/Path(name).relative_to(a.ROOT))==digest
for name,digest in prior['source_before'].items():
    assert base.sha(name)==base.sha(a.PRIOR/'source'/Path(name).relative_to(a.ROOT))==digest
assert len(prior['source_before'])==84
loaded=a.prior.check_runtime(plan)
pure=plan['pure'];assert base.sha(pure['path'])==pure['sha256']
assert base.sha(pure['XML_path'])==pure['XML_sha256']=='39aeb1bd1344a03d8e23b2b47389ca6cf0c771b4a8a5dba0456e400d63cc8b00'
counts={k:sum(int(s.get(k,0)) for s in ET.parse(pure['XML_path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=53,failures=0,errors=0,skipped=0)
assert not (out/'execution_claim.json').exists()
assert base.sha(a.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
wrapper=here/'invoke_bridge_linear_001_measured.ps1'
text=(here/'invoke_bridge_saved_audit_002_measured.ps1').read_text(encoding='utf8')
for before,after in {
 'bridge_serialize_saved_audit_prepare_002':'bridge_saved_linear_prepare_001',
 'da470fb3e6f1366b32706e82a11f221bac567c5e9c3ac2ad9a878515e761bcf4':expected,
 'audit_bridge_serialize_once_saved':'audit_bridge_saved_linear',
 'g31.bridge.separate_saved_audit.external_application_wall.v1':'g31.bridge.linear_saved_audit.external_application_wall.v1',
 'native_calls=0;new_predictions=0;original_2400_timeout_unchanged=$true':'native_calls=0;new_predictions=0;original_2400_timeout_unchanged=$true;prior_saved600_timeout_unchanged=$true',
 'all new37270 and old27218 rows hashed and compared by original checker code.':'all new37270 and old27218 rows hashed and compared with exact private AST substitutions: shared readonly raw/input, actor-copy retention, observer-copy removal, strict ordered comparison and bounded progress. All original guards remain.',
}.items():
    assert before in text; text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
report={'schema':'g31.bridge.linear_saved_audit.root_source_review.v1',
 'status':'passed_separate_saved_audit_ready','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'plan_sha256':expected,'live_archive_source_count':87,'old84_unchanged':True,
 'loaded_sources':loaded,'pure_counts':counts,'original_source_proof':a.core.source_proof(),
 'rules':[
  'Original outer/inner verifier bodies restored exactly after enumerated AST expression substitutions; no physical, FIFO, Storage, cap, ACK, clock, source or denominator guard is removed.',
  'Only two exact final raw/input paths share one local decoded tree. Reviewed consumers read raw, use canonical fresh owner trees, and deepcopy input before adding transfers. No cached raw alias is handed to policy.',
  'Original actor result deepcopy remains. Observer captures private decoded row only after exact same ordinal, actual returned object identity and pending read binding. Actual args/kwargs are still reconstructed, preserving stronger prefix ordering checks.',
  'Ordered builtin JSON comparator preserves dictionary/list order, scalar type, finite float repr/signed zero and integer conversion domain; unsupported objects fall back to original encoder. Only original finite nonnegative native wall exclusion applies.',
  'All37270 new compressed hash prepass and27218 old compressed hash/decode comparisons remain. Full policy, original owner canonicalization, physical results, all28506 jobs/22trays and relay proofs remain.',
  '1024 bounded progress rows, stage boundaries and every256 hash/replay rows; no payload logging. Every read/hash/progress/copy/comparison/export charged to one600 attempt. Progress start never implies verification success.',
  'Original2400 and separateaudit002600 failures retained. Only existing exact all_job_states export/hash redirect permitted; old raw/output cannot be overwritten.',
  'Full large artifact/binary/input/reference checks deliberately deferred to the owned execution; prelaunch verifies source/pure and exact inherited plan identities, not a new raw decode.',
 ],
 'large_artifact_reads_in_root_review':0,'raw_decodes_in_root_review':0,
 'limits':['No native replay or independently reproduced seal.','No speedup guarantee, alloffered business success or100ms claim.','Source/pure may overlap; no isolated performance comparison.'],
 'native_calls':0,'new_predictions':0,'producer':{'path':str(Path(__file__).resolve()),'sha256':base.sha(__file__)},
 'wrapper_sha256':base.sha(wrapper)}
review=out/'root_source_review_001.json';ready=out/'root_ready_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_separate_saved_audit','plan_sha256':expected,
 'root_review':{'path':str(review),'sha256':base.sha(review)},'wrapper_sha256':base.sha(wrapper),
 'full_saved_audit_dispatched':False,'owned_seconds':600},f,indent=2)
print(json.dumps({'review_sha256':base.sha(review),'ready_sha256':base.sha(ready),'wrapper_sha256':base.sha(wrapper)}))
