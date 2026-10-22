"""Check the changed eight-run admission and unchanged process-ownership core."""
import ast
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]
path=ROOT/'outputs/terminal_flow_horizon_offline006.py'
spec=importlib.util.spec_from_file_location('horizon_supervisor006',path)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

def function_ast(path,name):
    tree=ast.parse(path.read_text(encoding='utf8'))
    return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)

@pytest.mark.parametrize('name',['execute','preflight','ledger_snapshot','evidence_bytes','closure_allows_close',
    'child_succeeded','reserve','snapshot','checked_preflight','gated_child'])
def test_resource_and_ledger_core_unchanged(name):
    assert function_ast(path,name)==function_ast(ROOT/'outputs/terminal_flow_bins600_offline005.py',name)

@pytest.fixture
def native(monkeypatch,tmp_path):
    data={}
    def ref(name,value):
        p=str(tmp_path/name);data[p]=value;return dict(path=p,sha256='fixture-'+name)
    source=ref('source.json',{})
    plans=[];receipts=[]
    for parent in (2201,2202,2203,2204):
        for method in ('TF-B1-60','TF-B1-60-H1800'):
            name=f'{parent}_{method}'
            plan=ref(name+'/plan.json',dict(method=method,parent=dict(parent_seed=parent,split='dev'),source_bundle=source))
            receipt=ref(name+'/receipt.json',dict(plan_sha256=plan['sha256'],process=dict(exitcode=0),
                worker=dict(scientific_status='closed',final_physical_time=59400.)))
            plans.append(plan);receipts.append(receipt)
    block=ref('block.json',dict(parents=[2201,2202,2203,2204],methods=['TF-B1-60','TF-B1-60-H1800'],
        source_bundle=source,task_plans=plans))
    reg=ref('registration.json',dict(schema='g31.terminal_flow.projection_horizon_workflow.v1',source_bundle=source,
        new_native_starts=8,block=block,dependencies={},driver=ref('driver.py',{})))
    done=ref('completion.json',dict(registration=reg,status='closed',all_registered_development_tasks_closed=True,receipts=receipts))
    s=dict(horizon_registration=reg,workflow=reg,horizon_completion=done,workflow_completion=done,
        source_manifest=source,registration_driver=ref('register.py',{}))
    monkeypatch.setattr(w,'checked',lambda r:Path(r['path']))
    monkeypatch.setattr(w,'read',lambda p:data[str(p)])
    return s,data,plans,receipts

def test_complete_fixed_native_matrix_admitted(native):
    w.validate_horizon_inputs(native[0])

@pytest.mark.parametrize('change',['duplicate_parent','test_parent','wrong_source','failed','wrong_method','missing_receipt','stale_plan_sha'])
def test_incomplete_or_unfair_native_matrix_rejected(native,change):
    s,data,plans,receipts=native
    plan=data[plans[-1]['path']];receipt=data[receipts[-1]['path']]
    if change=='duplicate_parent':plan['parent']['parent_seed']=2203
    elif change=='test_parent':plan['parent']['split']='test'
    elif change=='wrong_source':plan['source_bundle']={'path':'other','sha256':'other'}
    elif change=='failed':receipt['process']['exitcode']=1
    elif change=='wrong_method':plan['method']='TF-predictor'
    elif change=='missing_receipt':data[s['horizon_completion']['path']]['receipts'].pop()
    else:receipt['plan_sha256']='stale'
    with pytest.raises(ValueError):w.validate_horizon_inputs(s)
