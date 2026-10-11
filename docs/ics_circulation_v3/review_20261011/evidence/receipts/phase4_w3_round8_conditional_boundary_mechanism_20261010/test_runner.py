"""Output-local failure/gate checks; no original-graph physical calls."""
from pathlib import Path
import importlib.util
import json
import pytest

PATH=Path(__file__).with_name('runner.py')
SPEC=importlib.util.spec_from_file_location('conditional_boundary_runner',PATH)
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf8')


def test_frozen_evaluator_is_used_without_replacement():
    from scripts.experiments.ics_circulation_v3.run_same_zone_stability import evaluate
    assert runner.evaluate is evaluate
    assert runner.WORKERS == 3


@pytest.mark.parametrize('bad',('status','replication','source','accounting','duplicate','empty_replication'))
def test_bridge_gate_rejects_incomplete_or_mismatch(tmp_path,bad):
    keys=('evaluation_ledger','cache_before','cache_after','searches','search_calls','search_work',
        'stopped_at','event_trace_suffix','selector_history_suffix','actual_slow_trigger_times',
        'slow_history_suffix','physical_tick_trace','forced_intervention')
    replication={**{k:True for k in keys},'result':{'total_cost':True}}
    rows=[];manifest={}
    for i in range(2):
        path=tmp_path/f'bridge/b{i}.json';write(path,{'example':i})
        manifest[f'bridge/b{i}.json']=runner.file_sha(path)
        rows.append({'request_key':f'b{i}','physical_key':f'b{i}','status':'controller_quiescent',
            'replication':dict(replication),'actual_physical_call':True,
            'file':f'bridge/b{i}.json','sha256':runner.file_sha(path)})
    write(tmp_path/'bridge_rows.json',[{'request_key':r['request_key'],'physical_key':r['physical_key']} for r in rows])
    summary={'planned_physical_calls':2,'rows':rows,
             'source_input_test_unchanged':True,'complete_resource_accounting':True}
    if bad=='status':summary['rows'][0]['status']='budget_censored'
    if bad=='replication':summary['rows'][0]['replication']['searches']=False
    if bad=='source':summary['source_input_test_unchanged']=False
    if bad=='accounting':summary['complete_resource_accounting']=False
    if bad=='duplicate':summary['rows'][1]=summary['rows'][0]
    if bad=='empty_replication':summary['rows'][0]['replication']={}
    path=tmp_path/'bridge/summary.json';write(path,summary)
    write(tmp_path/'bridge/manifest.json',{**manifest,'bridge/summary.json':runner.file_sha(path)})
    with pytest.raises(ValueError,match='exact original bridges'):runner.require_bridge(tmp_path)


def test_bridge_gate_detects_mutated_original_artifact(tmp_path):
    path=tmp_path/'bridge/summary.json';write(path,{'anything':'original'})
    write(tmp_path/'bridge/manifest.json',{'bridge/summary.json':runner.file_sha(path)})
    write(path,{'anything':'changed'})
    with pytest.raises(ValueError,match='immutable file'):runner.require_bridge(tmp_path)


def test_worker_crash_never_imputes_unknown_work_zero():
    result=runner.worker_failure({'physical_key':'x'},RuntimeError('failure'))
    assert result['actual_physical_call'] is None
    assert result['invocation_cpu_seconds'] is None
    assert result['failure']['message']=='failure'


def test_submission_failure_retains_grid_and_prior_future(tmp_path):
    class Pool:
        def __init__(self):self.calls=[]
        def submit(self,fn,output,stage,row):
            self.calls.append(row['physical_key'])
            if row['physical_key']=='x1':raise RuntimeError('broken submission')
            return row['physical_key']+'_future'
    rows=[{'physical_key':f'x{i}'} for i in range(3)]
    results=[];pool=Pool()
    jobs=runner.submit_requests(pool,tmp_path,'full',rows,tmp_path,results)
    assert pool.calls==['x0','x1','x2']
    assert set(jobs)=={'x0_future','x2_future'}
    assert results[0]['status']=='submission_failure'
    assert results[0]['actual_physical_call'] is None
    assert results[0]['invocation_cpu_seconds'] is None
    assert (tmp_path/'x1.submission_failure.json').exists()
