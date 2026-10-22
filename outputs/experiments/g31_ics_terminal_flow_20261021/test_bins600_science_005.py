"""Synthetic input binding tests, no native or scientific replay."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

loader=importlib.util.spec_from_file_location('bins600_science',Path(__file__).with_name('bins600_science_005.py'))
d=importlib.util.module_from_spec(loader);loader.loader.exec_module(d)
a=d.audit_module()

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(d,'DIRECTORY',tmp_path)
    def save(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf8');return a.bind(path)
    source=dict(path='source.json',sha256='source');workflow=dict(path='workflow.json',sha256='workflow')
    base=[];tasks=[];receipts=[]
    for parent in a.PARENTS:
        for method in ('TF-B1-60','TF-B1-300','TF-B1-600'):
            directory=tmp_path/f'{parent}_{method}'
            plan=dict(method=method,task_id=f'{parent}_{method}',parent=dict(parent_seed=parent,split='dev'),
                source_bundle=source,horizon=59400.,activation=7200.,contract=dict(source='source',forecast_bin_edges_seconds=method))
            plan_ref=save(directory/'plan.json',plan)
            if method=='TF-B1-600':
                tasks.append(plan_ref);receipts.append(save(directory/'receipt.json',{}))
            else:
                report=save(directory/'report.json',dict(parent=parent,method=method,evidence={'plan.json':plan_ref}))
                base.append(dict(parent=parent,method=method,evidence=report))
    baseline=dict(status='complete',source_bundle=source,workflow=workflow,registered_runs=28,runs=base)
    final=save(tmp_path/'baseline.json',baseline)
    marker=save(tmp_path/'baseline_COMPLETE.json',dict(status='complete',final_report=final))
    intent=save(tmp_path/'intent.json',dict(workflow=workflow,baseline_science=marker))
    reg=dict(schema='g31.terminal_flow.bins600_extension.v1',source_bundle=source,parents=list(a.PARENTS),
        task_plans=tasks,intent=intent)
    reg_ref=save(tmp_path/'registration.json',reg)
    done=dict(registration=reg_ref,status='closed',receipts=receipts)
    h={'campaign':SimpleNamespace(method_contract_errors=lambda p:[],comparison_contract=lambda p:p['contract']),
       'flow':SimpleNamespace(closed_run=lambda p:None)}
    def invoke():
        save(tmp_path/'NATIVE_COMPLETE.json',done)
        return d.inspect(a,source,workflow,h)
    return dict(invoke=invoke,done=done,reg=reg,baseline=baseline,save=save,root=tmp_path,h=h)

def test_all_four_600_runs_and_eight_bound_baseline_reports_required(setup):
    rows,reports,refs=setup['invoke']()
    assert len(rows)==12 and len(reports)==8 and len(refs)==21

def test_incomplete_native_matrix_rejected(setup):
    setup['done']['receipts'].pop()
    with pytest.raises(ValueError,match='four_full_600'):setup['invoke']()

def test_receipt_order_cannot_bind_another_parent(setup):
    setup['done']['receipts'].reverse()
    with pytest.raises(ValueError,match='receipt_and_method'):setup['invoke']()

def test_changed_baseline_report_rejected(setup):
    p=Path(setup['baseline']['runs'][0]['evidence']['path']);p.write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='bound_file_changed'):setup['invoke']()

def test_source_mismatch_cannot_be_explained_as_bin_difference(setup):
    setup['h']['campaign'].comparison_contract=lambda p:dict(source=p['method'],forecast_bin_edges_seconds=p['method'])
    with pytest.raises(ValueError,match='unregistered_pair_axis'):setup['invoke']()

def test_method_contract_violation_rejected(setup):
    setup['h']['campaign'].method_contract_errors=lambda p:['projection_horizon_seconds']
    with pytest.raises(ValueError,match='receipt_and_method'):setup['invoke']()

def test_nonclosed_600_run_rejected(setup):
    setup['done']['status']='partial'
    with pytest.raises(ValueError,match='closed_registered'):setup['invoke']()
