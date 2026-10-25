import copy
import csv
import json
import pytest
from scripts.experiments.g31_no_wait.hca_prefix import prefix_bags,clip_csv_rows,clip_report_lines,project
from scripts.experiments.g31_no_wait.tht_metrics import audit_tht


def fixture():
    rows=[];bags=[]
    for task,(first,admission,finish) in enumerate([(0,0,8),(6,7,17),(9,12,22),(11,14,24),(10,10,20)]):
        sid=f'{task}:direct'
        rows.append(dict(segment_id=sid,task_id=task,leg='direct',start=0,goal=1,pass_time=0.,std=100.,original_entry_time=0.))
        bags.append(dict(segment_id=sid,task_id=task,start=0,goal=1,release_time=first,
            first_planning_attempt_time=first,admitted_time=admission,admission=admission,
            finish=finish,finish_time=finish,observed_finish=finish,completed=True,
            route=[[0,admission,admission+2],[1,finish,finish+2]],commit_ordinal=task+1,
            edge_travel_time_seconds=finish-admission-2,node_service_time_seconds=2,
            junction_queue_wait_seconds=0,attempt_count=99))
    return rows,bags


def test_prefix_preserves_denominator_and_censors_future_events():
    rows,bags=fixture();result=prefix_bags(rows,bags,10)
    assert len(result)==5
    assert sum(b['completed'] for b in result)==1
    assert result[0]['actual_finish']==8
    assert result[1]['admission']==7 and result[1]['finish']==17
    assert result[1]['route'] and result[1]['completed'] is False
    assert result[1]['observed_finish'] is None and result[1]['actual_finish'] is None
    assert result[2]['first_planning_attempt_time']==9
    assert result[2]['admission'] is None and result[2]['route']==[] and result[2]['finish'] is None
    assert result[3]['first_planning_attempt_time'] is None and result[3]['release_time'] is None
    assert result[3]['admission'] is None and result[3]['finish'] is None and result[3]['route']==[]
    assert result[4]['first_planning_attempt_time']==10 and result[4]['admission']==10


def test_no_future_cumulative_counters_or_plan_details_leak():
    rows,bags=fixture();result=prefix_bags(rows,bags,10)
    assert all('attempt_count' not in bag for bag in result)
    assert 'edge_travel_time_seconds' not in result[2]
    assert result[2]['source_queue_delay'] is None
    assert result[2]['commit_ordinal'] is None


def test_no_mutation_and_projection_idempotent():
    rows,bags=fixture();before=copy.deepcopy(bags)
    result=prefix_bags(rows,bags,10)
    assert bags==before
    assert prefix_bags(rows,result,10)==result
    result[0]['route'][0][1]=999
    assert bags==before


def test_full_population_tht_remains_null_instead_of_completed_only():
    rows,bags=fixture();metrics=audit_tht(rows,prefix_bags(rows,bags,10),horizon=10)
    assert metrics['passed']
    assert metrics['business_denominator']==5
    assert metrics['completed_businesses']==1
    assert metrics['user_tht_full_population_available'] is False
    assert metrics['user_tht']['full_population']['mean'] is None


def test_delayed_actual_report_is_not_completed_by_prediction_alone():
    rows,bags=fixture();bags[0].update(finish=10,observed_finish=11,finish_time=11,route=[[0,0,2],[1,10,12]])
    result=prefix_bags(rows,bags,10)
    assert result[0]['finish']==10
    assert result[0]['completed'] is False
    assert result[0]['actual_finish'] is None


@pytest.mark.parametrize('failure',['missing_first','identity','early_admission','early_report','missing_route'])
def test_unproved_or_inconsistent_history_rejected(failure):
    rows,bags=fixture()
    if failure=='missing_first':bags[0].pop('first_planning_attempt_time')
    elif failure=='identity':bags[0]['goal']=2
    elif failure=='early_admission':bags[0]['admission']=-1
    elif failure=='early_report':bags[0]['observed_finish']=7
    elif failure=='missing_route':bags[0]['route']=[]
    with pytest.raises(ValueError):prefix_bags(rows,bags,10)


def test_event_filters_keep_order_exact_boundary_and_original_fields():
    records=[{'ordinal':'1','epoch':'9','goal_prediction':'20'},
             {'ordinal':'2','epoch':'10','goal_prediction':'30'},
             {'ordinal':'3','epoch':'10.000001','goal_prediction':'40'}]
    assert clip_csv_rows(records,'epoch',10)==records[:2]
    assert clip_report_lines('1  9\n2  10\n3  11\n',10)=='1  9\n2  10\n'


def test_end_to_end_projection_writes_audited_censored_prefix(tmp_path):
    parent=tmp_path/'source';run=parent/'micro';raw=run/'run_01';raw.mkdir(parents=True)
    def write(path,value):path.write_text(json.dumps(value),encoding='utf-8')
    def write_rows(path,rows):path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    rows=[];bags=[]
    for task,(first,admission) in enumerate([(0,0),(9,12),(13,16)]):
        finish=admission+8;sid=f'{task}:direct'
        rows.append(dict(segment_id=sid,task_id=task,leg='direct',start=0,goal=1,pass_time=0.,std=100.,original_entry_time=0.))
        bags.append(dict(segment_id=sid,task_id=task,start=0,goal=1,release_time=first,first_planning_attempt_time=first,
            admission=admission,finish=finish,observed_finish=finish,completed=True,
            route=[[0,admission,admission+2],[1,finish,finish+2]],commit_ordinal=task+1))
    canonical=parent/'canonical.jsonl';write_rows(canonical,rows)
    profile=parent/'profile.json';write(profile,{'nodes':[{'location':0,'service_time':2,'node_type':'source','outgoing':[1]},
        {'location':1,'service_time':2,'node_type':'goal','outgoing':[]}],'edges':[{'start':0,'end':1,'length':12}]})
    write(parent/'manifest.json',{'speed_mps':2,'physical_adapter':{'contract':{'fixture':True}},
        'cells':{'micro':{'canonical':str(canonical),'map':{'draft_profile':str(profile)}}}})
    write(parent/'SOURCE_FREEZE.json',{'files':[]})
    write(raw/'run_status.json',{'status':'complete','start_epoch':0})
    write(run/'continuous_analysis.json',{'horizon':40})
    write_rows(run/'annotated_physical_bags.jsonl',bags)
    for name,clock,values in [('release.csv','release_epoch',[0,9,13]),('routes.csv','epoch',[0,12,16])]:
        with (raw/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=['ordinal',clock]);writer.writeheader()
            writer.writerows([{'ordinal':i+1,clock:value} for i,value in enumerate(values)])
    (raw/'output.txt').write_text('0 8\n1 20\n2 24\n',encoding='utf-8')
    (raw/'outputstarttime.txt').write_text('0 0 0 0\n1 0 0 12\n2 0 0 16\n',encoding='utf-8')
    output=tmp_path/'prefix'/'micro';result=project(run,output,10)
    assert result['passed'] and result['segments']==3
    assert result['attempted']==2 and result['admitted']==1 and result['completed']==1
    assert not result['user_tht_full_population_available']
    receipt=json.loads((output/'manifest.json').read_text())
    assert receipt['independent_java_run'] is False and receipt['status']=='complete'
    status=json.loads((output/'run_01/run_status.json').read_text())
    assert status['wall_seconds'] is None and status['status']=='derived_prefix'
    assert (output/'run_01/output.txt').read_text()=='0 8\n'
    checked=project(run,tmp_path/'prefix_checked'/'micro',10,reference=output)
    assert checked['reference_parity']['passed']
    assert all(checked['reference_parity']['checks'].values())
