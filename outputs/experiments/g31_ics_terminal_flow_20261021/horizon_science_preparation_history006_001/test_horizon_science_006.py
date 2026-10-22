"""Audit admission fixtures: complete same-source pairs and compact ACK bounds."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
DATA=Path(__file__).resolve().parent
d=load('horizon_science_test006',DATA/'horizon_science_006.py')
a=load('horizon_science_original_test',DATA/'final_science_audit_004.py')
u=load('horizon_unified_original_test',DATA/'unified_order_audit_005.py')
flow=load('scripts.experiments.g31_ics_circulation.horizon_science_staged_flow',
    DATA/'horizon_repair_preparation_006/foundation_airport_transport_campaign.py')

@pytest.fixture
def fixture(tmp_path):
    def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding='utf8');return a.bind(p)
    source=save(tmp_path/'terminal_flow_runtime_006/source_manifest.json',dict(root=str(tmp_path/'terminal_flow_runtime_006'),worker_evidence_contract=u.CONTRACT))
    base=a.read(d.CYCLE/'runs/TF_bridge_all_005_TF-B1-60_P2201/plan.json')
    plans=[];receipts=[];directories=[]
    for parent in a.PARENTS:
        for method in d.METHODS:
            path=tmp_path/f'{parent}_{method}';p=copy.deepcopy(base)
            p.update(method=method,source_bundle=source,batch='initial',projection_horizon_seconds=600. if method==d.METHODS[0] else 1800.)
            p['parent']['parent_seed']=parent
            ref=save(path/'plan.json',p);plans.append(ref);directories.append(path)
            receipts.append(save(path/'receipt.json',{}))
            (path/'delivered_ack_evidence.json.gz').write_bytes(b'fake-ack')
            save(path/'worker_report.json',dict(delivered_ack_evidence_scope='complete transfer ACK history and transfer ledger; owner protocol subset',
                delivered_ack_evidence=dict(gzip_bytes=8)))
    block=save(tmp_path/'block.json',dict(methods=list(d.METHODS),parents=list(a.PARENTS),task_plans=plans,source_bundle=source))
    workflow=save(tmp_path/'workflow_006/registration.json',dict(schema='g31.terminal_flow.projection_horizon_workflow.v1',
        source_bundle=source,block=block,dependencies={}))
    save(tmp_path/'workflow_006/completion.json',dict(registration=workflow,all_registered_development_tasks_closed=True,TEST_unlocked=False,receipts=receipts))
    seen=[];h=dict(campaign=flow,flow=SimpleNamespace(closed_run=lambda p:seen.append(p)))
    return source,workflow,h,seen,directories,save

def test_eight_fresh_same_source_inputs_are_required(fixture):
    source,workflow,h,seen,_,_=fixture
    rows,refs=d.inspect(a,u,source,workflow,h)
    assert len(rows)==len(seen)==8

@pytest.mark.parametrize('bad',['wrong_source','wrong_axis','test','unclosed','ack_size','ack_scope','matrix'])
def test_bad_horizon_evidence_is_not_admitted(fixture,bad):
    source,workflow,h,seen,dirs,save=fixture
    if bad=='unclosed':
        def fail(p):raise ValueError('unclosed native')
        h['flow'].closed_run=fail
    elif bad in ('ack_size','ack_scope'):
        p=dirs[-1]/'worker_report.json';v=a.read(p)
        if bad=='ack_size':v['delivered_ack_evidence']['gzip_bytes']=9
        else:v['delivered_ack_evidence_scope']='full owner protocol'
        save(p,v)
    else:
        reg=a.bound_read(workflow);block=a.bound_read(reg['block'])
        if bad=='matrix':block['task_plans'].pop()
        else:
            ref=block['task_plans'][-1];v=a.bound_read(ref)
            if bad=='wrong_source':v['source_bundle']={'path':'other','sha256':'other'}
            elif bad=='wrong_axis':v['projection_horizon_seconds']=900.
            else:v['parent']['split']='test'
            block['task_plans'][-1]=save(Path(ref['path']),v)
        reg['block']=save(Path(reg['block']['path']),block)
        workflow=save(Path(workflow['path']),reg)
        done_path=Path(workflow['path']).with_name('completion.json');done=a.read(done_path);done['registration']=workflow;save(done_path,done)
    with pytest.raises(ValueError):d.inspect(a,u,source,workflow,h)
