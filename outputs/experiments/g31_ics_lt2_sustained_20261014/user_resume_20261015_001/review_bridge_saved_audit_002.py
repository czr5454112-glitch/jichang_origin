"""Root review of the separately budgeted immutable bridge saved audit."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import audit_bridge_serialize_once_saved as a
out=a.OUT/'bridge_serialize_saved_audit_prepare_002';base=a.base
expected='da470fb3e6f1366b32706e82a11f221bac567c5e9c3ac2ad9a878515e761bcf4'
plan=a.verify_plan(out,expected);loaded=a.check_runtime(plan)
assert len(plan['source_before'])==84
counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure']['XML_path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=16,failures=0,errors=0,skipped=0)
assert plan['pure']['XML_sha256']=='7ae564a438d046485fe12671b4adfa2ba04bc4b1878f4c9a84e92ce090bc3f93'
assert base.sha(a.ROOT/'scripts/experiments/g31_ics_circulation/audit_bridge_serialize_once_saved.py')=='8b65ca86ab17c90ac69de4fe0af8b89c5c2c59c814c6cc49139c3fa3bcf4af91'
assert not (out/'execution_claim.json').exists()
assert base.sha(a.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
wrapper=Path(__file__).parent/'invoke_bridge_saved_audit_002_measured.ps1'
report={'schema':'g31.bridge.separate_saved_audit.root_source_review.v1',
 'status':'passed_separate_saved_audit_ready','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'plan_sha256':expected,'live_archive_source_count':84,'loaded_sources':loaded,'pure_counts':counts,
 'original_campaign_sha256':a.CAMPAIGN_SHA,'original_timeout_external_sha256':a.EXTERNAL_SHA,
 'rules':[
  'Both original complete verifier code objects are retained. Every policy/physical/FIFO/Storage/cap/ACK/clock check and all37270 new/27218 complete old row hash/order checks remain.',
  'Private runner namespace preserves every old82 live/archive/input/compiled026/reference pin, then validates exact loaded domain against old82 plus two frozen audit/test files. No module hiding or runtime pin bypass.',
  'Only exactly one derived all_job_states gzwrite and sha are redirected into the new audit directory. Duplicate/foreign/existing writes fail. Result evidence maps the real new output path explicitly.',
  'Original timeout directory receives no writes. New600 includes reads,hashes,replay,exports; wholePython includes startup/parent cleanup/tail. Original2400 remains failed even if independent saved audit passes.',
  'Inherited shared2400 cost text is retained as historical metadata; current report labels separate600 accurately. Pure receipt and explicit XML identities checked at execution entry and exit.',
 ],
 'limitations':['No independent native-state replay; recorded native seal is format/hash-bound evidence only.',
  'Saved audit does not establish alloffered normal protection,100ms or method novelty.',
  'Originalraw compressed74.38MB; gzip tail ISIZE1337978093 modulo2^32, not a completed decode proof.'],
 'native_calls':0,'new_predictions':0,'full_saved_replays_in_review':0,
 'producer':{'path':str(Path(__file__).resolve()),'sha256':base.sha(__file__)},
 'wrapper_sha256':base.sha(wrapper)}
review=out/'root_source_review_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_separate_saved_audit','plan_sha256':expected,
 'root_review':{'path':str(review),'sha256':base.sha(review)},'wrapper_sha256':base.sha(wrapper),
 'full_saved_audit_dispatched':False,'owned_seconds':600},f,indent=2)
print(json.dumps({'review_sha256':base.sha(review),'ready_sha256':base.sha(ready),'wrapper_sha256':base.sha(wrapper)}))
