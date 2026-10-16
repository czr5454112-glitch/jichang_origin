from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import live_obligation_owned_same_information_search as search
from scripts.experiments.g31_ics_circulation import prepare_live_owned_initial_runtime as prepare
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=prepare.ROOT
DEST=OUT/'live_owned_initial_runtime_source_prepare_001';sha=prepare.sha
expected='7333bc27f2905e0d5077c6f300639885478753ae91e97532bdde8f31c9be1ecd'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==336
for name,digest in plan['source_sha256'].items():assert sha(ROOT/name)==digest==sha(DEST/plan['source_archive'][name])
assert plan['source_proof']==search.source_proof()
for name in ('test_g31_circulation_future_later_paired_driver','test_g31_circulation_live_initial_decision_seam','test_g31_circulation_future_later_fork'):
    assert 'tests/'+name+'.py' in plan['source_sha256']
pure=OUT/'live_owned_initial_runtime_pure_001'
assert sha(pure/'receipt.json')=='adcb2f7739df8204d9f3d21c9c8a14f335076962fcd3f03148075b7949314816'
assert sha(pure/'tests.xml')=='a55a424bdc8f05eb11082c23da1818796e658a0cad0a665a73207b194fb0deca'
xml=ET.parse(pure/'tests.xml');assert len(xml.findall('.//testcase'))==47
assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
legal=OUT/'owned_initial_runtime_source_review_legal_001.json'
assert sha(legal)=='466010fb949e5da1f8322e4ce497ea3ed0ea8a0b8973be530e6f9439a11c66b5'
result={'schema':'g31.owned_initial_runtime.root_source_review.v1','plan_sha256':expected,
 'review_script_sha256':sha(__file__),'sources_current_and_archive_verified':336,'focused_pure_tests':47,
 'independent_legal_review':{'path':str(legal),'sha256':sha(legal)},'actual_model_calls':0,'native_calls':0,
 'notes':[
 'Root read all3 newmodules,47tests,prepare/pure harness and original paired/group/provider/future fork source. Full private namespaces retained and only explicit inverse AST replacements remove diagnostics. Separate construction ownership contract never invents graph hashes or graph-proof flags.',
 'Exact source factories produce closed serial private object graphs from guarded JSON-backed context. Both wholegraph children exist before either resume; private saver sees returned prediction only. Scope excludes arbitrary private mutation, concurrent mutation or arbitrary externally supplied graph.',
 'Point alias,popped-event,no-recorder and terminal consumed guards remain. Future source inventory and every dynamic cut/owner/ACK/wire/deadline guard are original. Pure tiny synthetic realguard/fork case counts80cuts65sourceproofs32wholeclones, and provider fake counts16context; not real model performance.',
 'After-save terminal failure keeps saved prediction but unknown status. All32 outcomes and costs remain; source/origin failure invalidates selectable completions. All strongmethods get same32; strict one-ULP regression rejected.',
 'Final proposal explicitly binds originv2 revalidate; oldsearch function code/defaults/kwdefaults/closure unchanged. Old provider and earlier3unknown native result stay immutable.',
 '336pins include qualified bare helper test dependencies. Future full96 must save alloutputs beforetargets and compare complete bytes/types/order/floathex/semantic chronology. Old fullgraph audit is historical independent reference, not a new graph measurement.',
 'Only source accepted here; no actual model/native/100ms/online superiority or full-day certificate.']}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'review_sha256':sha(path),'status':'source_reviewed_actual_conformance_pending'}))
