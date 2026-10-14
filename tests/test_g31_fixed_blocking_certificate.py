"""The restricted state certificate must fail closed when a premise changes."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation.certify_original_blocking import certify


def fixture():
    data={"node_contracts":[{"node":n,"capacity":2 if n==1 else 1} for n in range(4)],
        "edge_contracts":[{"from":0,"to":1,"capacity":1},{"from":1,"to":2,"capacity":1},
                          {"from":2,"to":3,"capacity":0}],
        "jobs":[{"business_bag_id":f"B{i}","storage_node":1,"destination":goal}
                for i,goal in enumerate([3,2,2])],"faults":[],"transfers":[]}
    snapshot={"trays":[{"node":n,"active_leg":i,"mode":"loaded","edge_to":-1,"reception_node":-1}
                        for i,n in enumerate([1,1,0])],
        "legs":[{"runtime_id":i,"job_index":i,"kind":"storage_out" if i<2 else "storage_in"} for i in range(3)],
        "junctions":[{"node":1,"queue":[0,1]},{"node":0,"queue":[2]}],
        "resource_waits":[{"runtime_id":0,"node":1,"static_blocked":True,"receiving_nodes":[]},
                          {"runtime_id":2,"node":0,"static_blocked":False,"receiving_nodes":[1]}]}
    return data,snapshot


def test_certificate_proves_only_the_declared_dead_end():
    data,snapshot=fixture()
    result=certify(data,snapshot)
    assert result["status"]=="proved_under_listed_fixed_contract"
    assert result["global_optimality"]=="unknown"
    assert result["airport_physical_infeasibility_claim"] is False


@pytest.mark.parametrize("variant",["reachable_head","empty_tray","missing_fifo_occupant","fault_tape","wrong_stage"])
def test_broken_premise_returns_unknown(variant):
    data,snapshot=copy.deepcopy(fixture())
    if variant=="reachable_head":data["jobs"][0]["destination"]=2
    if variant=="empty_tray":snapshot["trays"][2]["mode"]="empty"
    if variant=="missing_fifo_occupant":snapshot["junctions"][0]["queue"]= [0]
    if variant=="fault_tape":data["faults"].append({"reason":"future change unknown"})
    if variant=="wrong_stage":snapshot["legs"][2]["kind"]="direct"
    assert certify(data,snapshot)["status"]=="unknown"
