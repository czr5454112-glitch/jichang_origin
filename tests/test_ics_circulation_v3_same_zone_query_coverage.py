from copy import deepcopy
from dataclasses import asdict

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator, _TOPOLOGY_CACHE
from scripts.experiments.ics_circulation_v3.same_zone_query_probe import QueryProbeGenerator
from scripts.experiments.ics_circulation_v3.same_zone_query_coverage import (
    VARIANTS, cold_fullgraph_cache, probe_query, query_summary, select_requests)


def captured_query():
    state=Snapshot(0,Network({n:Node(n,'z','p',2)for n in ('a','b','c')},
        {'ab':Edge('ab','a','b',1),'bc':Edge('bc','b','c',1),'ca':Edge('ca','c','a',1)}),
        {'t':Tray('t','a','loaded','b')},{'b':Bag('b','a','c',0,30)})
    generator=RegionalCandidateGenerator(horizon=12,expansion_limit=3000,static_path_limit=8,
        deadline_ms=None,dynamic_local=True,local_label_limit=3,cache_contract='isolated_replay_v1')
    sink=[];QueryProbeGenerator(generator,sink,'fast_generator').generate(state,'b','t',4)
    return sink[0]


def test_fixed_four_way_shadow_keeps_k_horizon_and_does_not_mutate_capture():
    query=captured_query();before=deepcopy(query)
    result=probe_query(query)
    assert result['status']=='completed_shadow_probe'
    assert [x['variant']for x in result['variants']]==[x[0]for x in VARIANTS]
    assert result['variants'][0]['original_query_reproduced']
    assert all(r['settings']['requested_k']==4 and r['settings']['horizon']==12 for r in result['variants'])
    assert all(r['query_input_unchanged']for r in result['variants'])
    assert query==before


def test_original_pool_mismatch_does_not_run_stronger_searches():
    query=captured_query();query['options']=()
    result=probe_query(query)
    assert result['status']=='baseline_query_mismatch'
    assert len(result['variants'])==1


def test_altered_input_binding_and_unfinished_observation_rejected():
    query=captured_query();query['snapshot'].version+=1
    with pytest.raises(ValueError,match='binding'):probe_query(query)
    query=captured_query();query['phase']='error'
    with pytest.raises(ValueError,match='completed'):probe_query(query)


def row(identity,*,status='expansion_budget_exhausted',case='case0',tick=1,source='a'):
    return {'query_id':identity,'case_id':case,'time':tick,'query_ordinal':tick,
        'scene':'scene','callsite':'engine_loaded','source':source,'destination':'c','requested_k':4,
        'protected':False,'last_search_status':status,'raw_candidate_count':4 if status=='candidate_limit_reached'else 0}


def test_selection_keeps_all_truncations_and_earliest_control_without_values():
    rows=[row('failed2',tick=2),row('failed1'),row('later',status='candidate_limit_reached',case='case1'),
          row('first',status='candidate_limit_reached',tick=7)]
    selected=select_requests(rows)
    assert {r['query_id']for r in selected['formal']}=={'failed1','failed2','first'}
    assert {r['query_id']for r in selected['pilot']}=={'failed1','first'}
    modified=[{**r,'total_cost':9999-i}for i,r in enumerate(reversed(rows))]
    again=select_requests(modified)
    assert [r['query_id']for r in again['formal']]==[r['query_id']for r in selected['formal']]


def test_no_success_control_is_preserved_as_missing_cell():
    selected=select_requests([row('only'),row('unmatched',status='candidate_limit_reached',source='b')])
    assert selected['missing_control_cells']==1 and len(selected['formal'])==1
    assert selected['controls'][0]['control_query_id']is None


def test_reference_cache_is_restored_on_exception():
    original=deepcopy(_TOPOLOGY_CACHE)
    try:
        _TOPOLOGY_CACHE.clear();_TOPOLOGY_CACHE['sentinel']={'x':1}
        with pytest.raises(RuntimeError):
            with cold_fullgraph_cache():
                assert not _TOPOLOGY_CACHE
                _TOPOLOGY_CACHE['new']={'x':2}
                raise RuntimeError('stop')
        assert list(_TOPOLOGY_CACHE)==['sentinel'] and _TOPOLOGY_CACHE['sentinel']=={'x':1}
    finally:
        _TOPOLOGY_CACHE.clear();_TOPOLOGY_CACHE.update(original)


def test_summary_distinguishes_raw_count_from_execution_authorization():
    query=captured_query();summary=query_summary(query)
    assert summary['raw_candidate_count']==len(query['options'])
    assert summary['source']=='a' and summary['destination']=='c' and summary['role']=='origin'
    assert 'snapshot'not in summary and 'future'not in summary


def test_collection_query_write_failure_keeps_other_queries_and_outcome(tmp_path,monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_same_zone_query_coverage as runner
    first=captured_query();second=deepcopy(first);second['query_ordinal']=1
    real_dump=runner.pickle.dump
    def fail_first(query,*args,**kwargs):
        if query['query_ordinal']==0:raise OSError('injected query output failure')
        return real_dump(query,*args,**kwargs)
    monkeypatch.setattr(runner.pickle,'dump',fail_first)
    folder=tmp_path/'case';folder.mkdir()
    indices,failures=runner.persist_collection(folder,tmp_path,{'case_id':'case','scene':'s','tape_id':'t'},
        [first,second],{'status':'controller_quiescent','retained':True})
    assert [q['query_ordinal']for q in indices]==[1]
    assert failures[0]['scope']=='query'and failures[0]['query_ordinal']==0
    assert runner.read(folder/'outcome.json.gz')['retained']
    assert runner.read(folder/'queries.json')==indices


def test_collection_outcome_write_failure_recovers_full_result(tmp_path,monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_same_zone_query_coverage as runner
    def fail(*args,**kwargs):raise OSError('injected outcome compression failure')
    monkeypatch.setattr(runner,'write_gzip',fail)
    outcome={'status':'controller_quiescent','searches':[{'work':7}],'cpu_seconds':1.5}
    indices,failures=runner.persist_collection(tmp_path,tmp_path,{'case_id':'case','scene':'s','tape_id':'t'},[],outcome)
    assert indices==[]and failures[0]['scope']=='outcome'
    assert runner.read(tmp_path/'outcome.recovery.json')==outcome


def test_authorization_exception_keeps_generated_pool_and_work(monkeypatch):
    from scripts.experiments.ics_circulation_v3 import same_zone_query_coverage as helper
    query=captured_query()
    class BrokenValidator:
        def validate(self,*args,**kwargs):raise RuntimeError('injected authorization observer failure')
    # Generator uses runtime validator independently; fail only shadow's second
    # authorization entrance, after the original search has returned its pool.
    monkeypatch.setattr(helper,'ExecutionValidator',BrokenValidator)
    result=helper.probe_query(query)
    assert result['status']=='shadow_variant_failure'
    assert len(result['variants'])==1
    partial=result['variants'][0]
    assert partial['raw_candidate_count']>0 and partial['work']>0
    assert partial['failure']['scope']=='authorization'


def test_later_variant_exception_retains_first_completed_variant(monkeypatch):
    from scripts.experiments.ics_circulation_v3 import same_zone_query_coverage as helper
    original=helper.shadow_variant
    def fail_second(query,variant):
        if variant[0]=='regional12000':raise RuntimeError('injected second-variant observer failure')
        return original(query,variant)
    monkeypatch.setattr(helper,'shadow_variant',fail_second)
    result=helper.probe_query(captured_query())
    assert result['status']=='shadow_variant_failure'and result['failed_variant']=='regional12000'
    assert len(result['variants'])==1 and result['variants'][0]['original_query_reproduced']


def test_shadow_write_failure_recovers_all_finished_variants(tmp_path,monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_same_zone_query_coverage as runner
    import gzip,pickle
    query=captured_query();path=tmp_path/'captured.pkl.gz'
    with gzip.open(path,'wb')as f:pickle.dump(query,f)
    (tmp_path/'pilot').mkdir()
    monkeypatch.setattr(runner,'verify',lambda *a:None)
    monkeypatch.setattr(runner,'verify_manifest',lambda *a:None)
    monkeypatch.setattr(runner,'collection_root',lambda *a:tmp_path)
    def fail(*args,**kwargs):raise OSError('injected primary output failure')
    monkeypatch.setattr(runner,'write',fail)
    request={'file':'captured.pkl.gz','sha256':runner.file_sha(path),
        'case_id':'case','query_id':'case:q00000','query_ordinal':0}
    row=runner.probe_worker(tmp_path,'pilot',request)
    assert row['status']=='probe_persistence_failure'and row['file'].endswith('.recovery.json')
    recovered=runner.read(tmp_path/row['file'])
    assert len(recovered['result']['variants'])==4
    assert recovered['invocation_cpu_seconds']>=0 and recovered['result']['status']=='completed_shadow_probe'


def test_old_raw_must_match_preexisting_manifest(tmp_path,monkeypatch):
    from scripts.experiments.ics_circulation_v3 import run_same_zone_query_coverage as runner
    folder=tmp_path/'full';folder.mkdir();(folder/'raw.json.gz').write_bytes(b'changed')
    runner.write(folder/'summary.json',{'rows':[]})
    runner.write(folder/'manifest.json',{'raw.json.gz':'not-the-current-sha'})
    monkeypatch.setattr(runner,'OLD',tmp_path)
    with pytest.raises(ValueError,match='round6 manifest drift'):runner.validate_old_artifacts()
