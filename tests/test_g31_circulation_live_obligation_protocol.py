import copy
import json
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_projection_protocol as p
from scripts.experiments.g31_ics_circulation import research_public_live_obligation as runner


def fake_prediction(action):
    commands=[];events=[]
    for job,source,flag,target,default in (("loaded",0,"initial_action",2,1),("reuse1",7,"later_action",8,3)):
        preferred=action[flag]!="native_default"
        events.append({"event":"EDGE_ENTER","job":job,"source":source,"target":target if preferred else default})
        if preferred:commands.append({"job":job,"from":source,"next":target,"status":"updated","executed_at":2.,"ack_delivered_at":2.02})
    return {"status":"conditional_prediction","completion":{j:20. for j in p.model.JOBS},"completion_sum":100.,
        "projected_commands":commands,"physical_projection":events,
        "projected_transfers":[{"tray":t,"physical_status":"received","terminal":True,"ack":"received","ack_at":10.} for t in ("E","L","L")],
        "native_protection_certified":False,"online_information_delivered":False}


def fake_rows():
    rows=p.plan_rows()
    for row in rows.values():row["assessment"]=p.assessment(fake_prediction(row["action"]),row["action"])
    return rows


def test_full_fixed_denominator_and_strong_incumbent():
    assert len(p.plan_rows())==96 and p.incumbent_action()["return_delay"]==0.
    result=p.compare(fake_rows())
    assert all(c["assessed"]==32 and c["unknown"]==0 for c in result["cases"].values())
    assert all(r["member_count"]==16 and r["status"]=="complete_conditional_reference" for c in result["cases"].values() for r in c["references"].values())
    assert not result["native_protection_certified"]


@pytest.mark.parametrize("problem",["missing_row","wrong_action","wrong_case"])
def test_denominator_or_action_binding_fail_closed(problem):
    rows=fake_rows();key=next(iter(rows))
    if problem=="missing_row":rows.pop(key)
    elif problem=="wrong_action":rows[key]["action"]["return_delay"]=.25
    else:rows[key]["case"]="unregistered_case"
    with pytest.raises(ValueError,match="fixed96"):p.compare(rows)


@pytest.mark.parametrize("problem",["missing_job","unfinished","wrong_actual_edge","rejected","missing_ack","bool_completion","claim_authority"])
def test_physical_and_terminal_denominator_not_promoted(problem):
    action=next(a for a in p.model.actions() if a["initial_action"]=="prefer_2" and a["later_action"]=="prefer_8")
    value=fake_prediction(action)
    if problem=="missing_job":value["completion"].pop("blocker")
    elif problem=="unfinished":value["completion"]["blocker"]=-1.
    elif problem=="wrong_actual_edge":value["physical_projection"][0]["target"]=1
    elif problem=="rejected":value["projected_commands"][0]["status"]="rejected"
    elif problem=="missing_ack":value["projected_transfers"][0]["terminal"]=False
    elif problem=="bool_completion":value["completion"]["loaded"]=True
    else:value["native_protection_certified"]=True
    assert p.assessment(value,action)["status"]=="unknown_model_or_selected_action"


def test_one_unknown_invalidates_reference_but_remains_in_all96():
    rows=fake_rows();key=next(k for k,r in rows.items() if r["action"]["initial_action"]=="native_default")
    rows[key]["assessment"]["status"]="unknown_model_or_selected_action"
    result=p.compare(rows);case=rows[key]["case"]
    assert result["row_count"]==96 and result["cases"][case]["unknown"]==1
    assert result["cases"][case]["references"]["fixed_initial_native_default"]["status"]=="unknown_incomplete_reference"


def test_no_tolerance_for_completed_job_regression():
    rows=fake_rows();group={k:r for k,r in rows.items() if r["case"]=="mechanism"}
    baseline=next(r for r in group.values() if r["action"]==p.incumbent_action())
    row=copy.deepcopy(baseline);row["assessment"]["completion"]["receiver"]+=1e-14
    assert p.protected(row,baseline) is False


def test_execution_order_is_explicit_despite_sorted_json_maps():
    plan=json.loads(json.dumps({"case_order":list(p.model.construction.CASE_IDS),"rows":p.plan_rows()},sort_keys=True))
    keys=runner.execution_keys(plan)
    assert next(iter(plan["rows"])).startswith("insufficient_advance/")
    assert keys[0]=="mechanism/vector_00" and keys[32]=="no_overlap/vector_00" and keys[64]=="insufficient_advance/vector_00"
    rows=copy.deepcopy(plan["rows"])
    for index,key in enumerate(keys):rows[key]["execution_index"]=index
    runner.verify_execution_order(plan,{"rows":rows,"executed":96,"execution_order":keys})


def test_wrong_actual_execution_order_cannot_be_relabelled():
    plan={"case_order":list(p.model.construction.CASE_IDS),"rows":p.plan_rows()}
    actual=sorted(plan["rows"]);rows=copy.deepcopy(plan["rows"])
    for index,key in enumerate(actual):rows[key]["execution_index"]=index
    with pytest.raises(ValueError,match="actual_execution_order"):
        runner.verify_execution_order(plan,{"rows":rows,"executed":96,"execution_order":actual})
