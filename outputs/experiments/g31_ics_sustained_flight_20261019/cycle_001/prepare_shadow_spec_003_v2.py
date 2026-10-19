"""Administrative source classification only; no native or training launch.

Keep v1 spec/plan untouched. External interpreter is a pinned runtime, never
a project source. Run --verify-only with the exact launch interpreter before
ledger registration/execution; the unchanged campaign also hashes its pinned
runtime references before launching the bounded worker.
"""
import hashlib
import json
from pathlib import Path
import sys

CYCLE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
RUN=CYCLE/'B2_live_behavior_shadow_003'
COMPANION=RUN/'external_runtime_preregistration.json'
ORIGINAL=CYCLE/'B2_live_behavior_shadow_003_task.json'
REPAIRED=CYCLE/'B2_live_behavior_shadow_003_task_v2.json'

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,allow_nan=False)

def verify(companion):
    actual=Path(sys.executable).resolve();expected=companion['external_runtime']
    assert actual==Path(expected['path']).resolve(), 'actual_launcher_interpreter_path_changed'
    assert sha(actual)==expected['sha256'], 'actual_launcher_interpreter_bytes_changed'
    assert ref(RUN/'plan.json')==companion['unchanged_plan'], 'plan_changed'
    assert ref(__file__)==companion['verification_program'], 'admin_verifier_changed'
    plan=read(RUN/'plan.json')
    assert expected in plan['runtime_references'], 'runtime_not_pinned_in_campaign'
    assert len(plan['source_sha256'])==116
    return {'status':'verified_actual_interpreter_before_ledger_launch',
        'actual_sys_executable':str(actual),'sha256':sha(actual),
        'plan_sha256':sha(RUN/'plan.json'),'native_sessions':0,'fit_calls':0}

if '--verify-only' in sys.argv:
    print(json.dumps(verify(read(COMPANION))))
else:
    original=read(ORIGINAL);plan=read(RUN/'plan.json')
    outside=[path for path in original['sources'] if not Path(path).resolve().is_relative_to(ROOT)]
    assert len(outside)==1 and Path(outside[0]).resolve()==Path(sys.executable).resolve()
    runtime=ref(outside[0]);assert runtime in plan['runtime_references']
    companion={'schema':'g31.airport_shadow_external_runtime_preregistration.v1',
        'classification':'external executable runtime, not research-tree source',
        'external_runtime':runtime,'actual_prepare_interpreter':str(Path(sys.executable).resolve()),
        'unchanged_plan':ref(RUN/'plan.json'),'original_spec':ref(ORIGINAL),
        'verification_program':ref(__file__),
        'prelaunch_requirement':'Invoke this frozen program --verify-only with the exact interpreter used for run_sustained_learning; require successful exit before register/run.',
        'campaign_check':'Unchanged plan runtime_references and delegate check_pins retain exact interpreter SHA check before child launch.',
        'runtime_source_closure_count_unchanged':116,'native_budget_unchanged':1,
        'prior_registration':'rejected_before_registration_reservation_or_native',
        'prior_rejection_reason':'source_outside_research_tree',
        'prior_native_calls':0,'prior_native_reserved':0,'ledger_rules_changed':False}
    verification=verify(companion)
    write(COMPANION,companion)
    task=dict(original)
    task['sources']=sorted([p for p in original['sources'] if p not in outside]+[str(COMPANION)])
    task['requires']=['B2_behavior_training_001','C00_receiver_recorded_budget_002','B2_behavior_training_001_review_001']
    assert len(task['sources'])==147 and all(Path(p).resolve().is_relative_to(ROOT) for p in task['sources'])
    write(REPAIRED,task)
    write(RUN/'registration_rejection_and_spec_repair.json',{
        'schema':'g31.airport_shadow_registration_admin_repair.v1',
        'status':'original_registration_rejected_before_reservation_or_execution',
        'reported_by':'root actual run_sustained_learning registration result',
        'reason':'source_outside_research_tree: '+outside[0],
        'original_spec':ref(ORIGINAL),'repaired_spec':ref(REPAIRED),'runtime_companion':ref(COMPANION),
        'actual_interpreter_verification':verification,'project_sources_and_refs':146,
        'in_tree_runtime_companion':1,'total_registration_pins':147,
        'unchanged_runtime_source_count':116,'unchanged_plan':ref(RUN/'plan.json'),
        'task_was_registered':False,'native_branches_reserved':0,'native_sessions_started':0,
        'ledger_native_reserved_reported_unchanged':51,'automatic_retry_of_native':False})
    print(json.dumps({'status':'prepared_admin_spec_v2','spec':str(REPAIRED),
        'spec_sha256':sha(REPAIRED),'plan_sha256':sha(RUN/'plan.json'),'verification':verification}))
