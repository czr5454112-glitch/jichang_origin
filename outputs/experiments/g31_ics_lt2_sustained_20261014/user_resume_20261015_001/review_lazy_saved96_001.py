"""Pin source-reviewed saved96 audit and its whole Python outer clock."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
out=OUT/'live_comm_lazy_saved_review_001'
expected='1d7e685bf1e676d2da5a910f2ecf64e20563684c6b185d7a65ffd0a2d1722c89'
assert sha(out/'plan.json')==expected
plan=read(out/'plan.json');assert len(plan['source_sha256'])==93 and plan['fixed_seconds']==180.
assert not (out/'execution_claim.json').exists()
for path,digest in plan['source_sha256'].items():assert sha(path)==sha(out/plan['source_archive'][path])==digest
source=ROOT/'scripts/experiments/g31_ics_circulation/review_live_communication_lazy_saved.py'
assert sha(source)=='953cfe13c45f9e95e410862ffebe846494829212360f59ebdaa5983db8cbd6ec'
original=HERE/'invoke_communication_lazy_001_measured.ps1'
assert sha(original)=='626ccf84c252e54172af1d22dca1ae4fd1ecaf75accb06fe1dda5fd0f5d5b410'
body=original.read_text(encoding='utf8')
changes={
 'live_communication_lazy_prepare_001':'live_comm_lazy_saved_review_001',
 'afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497':expected,
 'validate_live_communication_lazy':'review_live_communication_lazy_saved',
 'ready_for_one_bounded_conformance_attempt':'ready_for_one_saved96_audit',
 'g31.communication_lazy.external_wall.v1':'g31.communication_lazy.saved96.external_wall.v1',
 'whole_python_within_360_seconds=($taskWall -le 360)':'whole_python_within_180_seconds=($taskWall -le 180)',
 'shared_owned_seconds=360;fixed_rows=96;maximum_model_evaluations=96;native_calls=0':'shared_owned_seconds=180;fixed_rows=96;maximum_model_evaluations=0;native_calls=0',
 'Fresh fixed3x32 lazy-view communication conformance. All96 recomputed with original guard/chronology/endpoint checks; saved73 full prediction bytes must remain equal. Only unused full-view construction changes. Whole launch/import/pins/model/targets/equality/export/cleanup/exit included. Offline360s based on measured cost does not change the100ms product target; no online efficacy claim.':
 'Separate fixed96 saved audit: original192 initial and226 later guards, all five endpoints/ordered chronology,73 full-output bytes, original93 and producer100 source/archive and complete recorded entry/exit pins. No prediction or native. Full launch/import/checks/read/decode/export/cleanup/exit included. Retrospective conformance is not online rolling efficacy or100ms.'
}
for before,after in changes.items():assert body.count(before)==1,before;body=body.replace(before,after)
wrapper=HERE/'invoke_lazy_saved96_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
report={'schema':'g31.lazy96.saved_audit.root_binding.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'ready_for_one_saved96_audit','plan':ref(out/'plan.json'),'source':ref(source),
 'audit_sources':93,'producer_sources':100,'original_sources':93,'fixed_saved_rows':96,'full_output_comparisons':73,
 'owned_seconds':180,'model_or_native_calls':0,'root_role':'Author of separate audit, independent of model and producer; requested R1 source review before dispatch.',
 'requirements':['Full saved96 evidence and original validation methods; new prediction/native invocation absent.',
  'All actual inputs and complete saved predictions hash-bound; all unknowns remain in producer evidence.',
  'Outer clock and bounded completed required in addition to report success. No causal speedup or online efficacy inferred.'],
 'wrapper':ref(wrapper)}
review=out/'root_source_review_001.json'
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,allow_nan=False)
with (out/'root_ready_001.json').open('x',encoding='utf8') as stream:json.dump({'status':report['status'],
 'plan_sha256':expected,'root_review':ref(review),'wrapper_sha256':sha(wrapper),'owned_seconds':180},stream,indent=2)
print(json.dumps({'review_sha256':sha(review),'wrapper_sha256':sha(wrapper),'ready_sha256':sha(out/'root_ready_001.json')}))
