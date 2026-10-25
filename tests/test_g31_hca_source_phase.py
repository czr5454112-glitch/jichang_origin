from scripts.experiments.g31_no_wait.hca_source_phase import analyze


def fixture():
    specs=[('0:direct',0,'direct',2,4,0,10,10,15),
           ('1:storage_in',1,'storage_in',1,2,0,1,1,30),
           ('1:storage_out',1,'storage_out',2,4,10,30,30,40),
           ('2:storage_in',2,'storage_in',3,2,0,1,1,5),
           ('2:storage_out',2,'storage_out',2,4,10,31,31,41)]
    rows=[];bags=[]
    for sid,task,leg,start,goal,nominal,first,success,finish in specs:
        rows.append(dict(segment_id=sid,task_id=task,leg=leg,start=start,goal=goal,pass_time=nominal))
        bags.append(dict(segment_id=sid,release_time=first,admission=success,observed_finish=finish))
    return rows,bags


def test_same_epoch_gate_and_unready_nominal_head_blocking():
    result=analyze(*fixture())
    assert result['same_epoch_inbound_report_and_outbound_first_attempt']==1
    assert result['source_generation_order_violations']==[]
    assert result['causal_violations']==[]
    block=result['largest_eligibility_blocks'][0]
    assert block['head']=='1:storage_out'
    assert block['later_ready_bag']=='2:storage_out'
    # Previous source success at 10 permits the next source head only at 11.
    assert block['demonstrated_eligibility_block_seconds']==19


def test_missing_head_attempt_does_not_claim_observed_block():
    rows,bags=fixture()
    bags[2]['release_time']=None;bags[2]['admission']=None
    bags[4]['release_time']=None;bags[4]['admission']=None
    result=analyze(rows,bags)
    assert result['causally_unready_ebs_heads_blocking_a_later_ready_task']==0


def test_original_nominal_tie_does_not_become_readiness_sort():
    rows,bags=fixture()
    bags[2]['release_time']=31;bags[4]['release_time']=30
    result=analyze(rows,bags)
    assert result['source_generation_order_violations']==[['1:storage_out','2:storage_out']]


def test_later_nominal_release_does_not_count_as_ready_during_block():
    rows,bags=fixture();rows[4]['pass_time']=35;bags[4]['release_time']=35;bags[4]['admission']=35
    result=analyze(rows,bags)
    assert result['causally_unready_ebs_heads_blocking_a_later_ready_task']==0
