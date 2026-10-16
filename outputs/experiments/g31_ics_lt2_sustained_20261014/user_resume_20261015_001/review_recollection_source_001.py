"""Root source review, pin readback and prior pure evidence; no native/predictor."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=HERE.parent
PACKAGE=OUT/'live_obligation_recollection_source_prepare_001'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
plan=PACKAGE/'source_preparation.json'
assert sha(plan)=='31b9884de31f4c55eddc18525adc0761f98fa70cedf40bb0a98add80cb7b47f7'
p=read(plan)
assert len(p['sources'])==81
for name,digest in p['sources'].items():
    assert sha(name)==digest, name
    assert sha(PACKAGE/p['source_archive'][name])==digest, name
for key in ('old_campaign','stage_a','protocol','saved_window_evidence'):
    assert sha(p[key]['path'])==p[key]['sha256'], key
xml=p['tests']['xml']
assert sha(xml['path'])==xml['sha256']
suite=ET.parse(xml['path']).getroot()
counts={k:sum(int(s.attrib.get(k,0)) for s in suite.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts=={'tests':51,'failures':0,'errors':0,'skipped':0},counts
old=read(p['old_campaign']['path'])
assert all(p['sources'].get(name)==digest for name,digest in old['source_sha256'].items())
report={
 'schema':'g31.recollection.root_source_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'source_pure_review_passed_new_native_package_preparation_permitted',
 'source_preparation':{'path':str(plan),'sha256':sha(plan)},
 'live_archive_source_count':81,
 'saved_pure_tests':counts,
 'reviewed_rules':[
  'New private collector keeps original three real owner endpoints, session bound native027 handle and ledger; failed read seal binds contents and physical time. JSON is not authority.',
  'Existing native v3 digest/source/current/action coverage checks remain in cloned validator; only reviewed lifecycle Stage A supplied-data support differs.',
  'Retry requires sealed specific failure and unchanged original uncommitted L identity, exact current physical action set, terminal ACKs before old union, and finite strict available service/wire window.',
  'At most one fresh pair per deciding phase. Peer admits at most two distinct strictly monotone actual invitations; actual reply captures do not qualify as invitations.',
  'Physics continues; immutable retries and owned refresh continue. Original quiet start is retained across recollection. A absolute not-before7.84 semantics remains unchanged.',
  'Fresh collection still must pass source/current/union checks, then final current target/window and local receiving guards before a fixed counterfactual action.',
  'All collection attempts must be exported by the separate runner on success and exception, without deepcopy of live native capabilities.',
 ],
 'limitations':[
  '51 pure tests and 44 saved windows are conditional policy/source evidence, not new native success.',
  'New communication schedule can change physical trajectories. Existing normal-exchange predictor is not a certified protection model for recollection.',
  'Original 96 run remains34assessed62unknown and must not be reclassified.',
  'No optimizer,100ms benchmark,joint effectiveness or full airport claim is made.',
 ],
 'required_new_package':[
  'Separate immutable source closure and exactly96 fixed branches with common communication policy and all denominators.',
  'Bind new policy/adapter and success/exception evidence in private namespace; no mutations of original frozen sources.',
  'Same original physical inputs, runtime notification overlay, source-native acceptance, full H40 physical audit, all5job completion records.',
  'External whole application and owned600 budget includes native entry/exit acceptance, every branch and saved audits; fail closed and preserve partial evidence.',
  'Root review before native dispatch. No prediction count or success may be fabricated from old saved outcomes.',
 ],
 'native_executions':0,'model_evaluations':0,'native_dispatch_authorized_by_this_review':False,
 'review_producer':{'path':str(Path(__file__).resolve()),'sha256':sha(__file__)}
}
dest=PACKAGE/'root_source_review_001.json'
with dest.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'status':report['status'],'sha256':sha(dest),'source_count':81,'pure':counts}))
