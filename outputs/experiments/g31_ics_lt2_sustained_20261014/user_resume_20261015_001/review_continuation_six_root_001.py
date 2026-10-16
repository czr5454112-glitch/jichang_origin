from pathlib import Path
import json
from scripts.experiments.g31_ics_circulation import validate_live_conditional_continuation as a
from scripts.experiments.g31_ics_circulation import live_obligation_conditional_continuation as model

HERE=Path(__file__).resolve().parent
DEST=a.OUT/'conditional_continuation_six_prepare_001'
expected='dd91512a60cc6ef336842ab93a5341a47ebd90276470116b24e8cb4e90917c56'
assert a.sha(DEST/'plan.json')==expected
plan=a.read(DEST/'plan.json')
assert a.sha(a.__file__)=='dae6a437127b4191ee6b23ae58db4ae2715829f3ba14fcbc697c3c1d0c8c2ecf'
a.check_domain(plan['rows'])
assert len(plan['source_sha256'])==109 and plan['hard_application_seconds']==120
assert [plan[k] for k in ('maximum_initial_engines','expected_cutpoints','expected_independent_suffixes',
 'expected_main_resumes','expected_suffix_resumes','expected_total_resumes','expected_whole_graph_forks')]==[6,14,14,14,25,39,28]
assert plan['source_proof']==model.source_proof()
for path,digest in plan['source_sha256'].items():assert a.sha(path)==a.sha(DEST/plan['source_archive'][path])==digest
pure=a.pure_gate()
assert not (DEST/'execution_claim.json').exists()
body=(HERE/'invoke_phase_b_six_root_001_measured.ps1').read_text(encoding='utf8')
changes={
 'live_phase_b_pause_prepare_001':'conditional_continuation_six_prepare_001',
 'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb':expected,
 'validate_live_phase_b_pause --execute':'validate_live_conditional_continuation --execute',
 'g31.passive_phase_b_six.external_wall.v1':'g31.same_action_continuation_six.external_wall.v1',
 'shared_owned_seconds=120;fixed_rows=6;maximum_model_evaluations=6;expected_hook_points=14;native_calls=0':
  'shared_owned_seconds=120;fixed_rows=6;maximum_initial_engines=6;expected_cutpoints=14;expected_suffixes=14;expected_resume_calls=39;expected_graph_forks=28;native_calls=0',
 'Fixed6 passive model runs,14 snapshot points, full prediction bytes against frozen lazy comparands, complete alias graph and isolation checks. Independent actual supplied inventories do not establish model-point relations. Whole launch/import/pins/model/copy/check/export/cleanup/exit included. No resumability, native authority, hidden-state coverage, online efficacy or100ms certificate.':
  'Fixed6 initial model engines and14 independently forked same-action suffixes from four explicit call frames;39 resumes and28 forks, no prefix reinitialization. All20 terminal output bytes match frozen lazy; each reached cut graph and terminal graph exact to mainline, original retained cuts mutation-isolated. All imports/pins/model/forks/outputchecks/exports/exit within120. Factory-made model states only, no native authority, actualopaqueID relation, hiddenstatecoverage, onlineefficacy or100ms.',
 "if ($taskWall -gt 120) {throw 'Whole Python six-input budget exceeded'}":
  "if ($taskWall -gt 120) {throw 'Whole Python continuation six-input budget exceeded'}"
}
for old,new in changes.items():
    assert body.count(old)==1,old
    body=body.replace(old,new)
wrapper=HERE/'invoke_continuation_six_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.same_action_six.root_source_review.v1','plan_sha256':expected,'source_count':109,
 'pure':[{ 'path':str(p),'sha256':a.sha(p)} for p in pure],'model_calls_during_review':0,
 'review':[
  'Read full4frame module,19corefake tests, newdriver16pure and originaldecide/activate/tick source. Exact AST/inverse/code-shape checks and fullglobals retained.',
  'Each cut continues originaldecide tail then activate tail then remainingtick owners then after_event; only thereafter next heap pop. No run initialization or dedup prelude repeated.',
  'count20001 budget earlyreturn bypassesfinish; overhorizon event popped/timeassigned before count/hooks and final returned. Changedaction/consumedinstance reject within factory-only scope.',
  'Exactly6 initial starts/6advances/14mainresumes/25suffixresumes/28forks. Every main and14suffix output saved before comparison target reads. Extra/missing/failure paths remainunknown.',
  'All20 fullpredictions compared to frozenlazy bytes, each latercut graph/metadata and complete terminalgraph compared to samecase mainline. Explicitmutation only aftersuffixfinished; retainedcut staysexact.',
  'Copiedgraphs exist in memory during producer; saved graphdigests alone not independent future alias proof. No actualendpoint/target/expectedchronology enters model, except preregisteredmaximumcuts workcap.',
  'Require exact_six_main_and_fourteen_same_action_suffixes receipt with6exact0unknown counts, unchangedsource/loadentryexit and outer<=120; process0 alone insufficient.'
 ],'wrapper_sha256':a.sha(wrapper),'source_sha256':a.sha(__file__)}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_bounded_conformance_attempt','plan_sha256':expected,
 'root_review':{'path':str(path),'sha256':a.sha(path)},'wrapper_sha256':a.sha(wrapper)}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review_sha256':a.sha(path),'ready_sha256':a.sha(DEST/'root_ready_001.json'),'wrapper_sha256':a.sha(wrapper)}))
