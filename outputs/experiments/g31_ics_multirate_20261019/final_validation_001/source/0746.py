from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation.audit_original_carrier_bound import analyze


def data():
    return {"node_contracts":[{"node":n,"capacity":4} for n in range(4)],
        "edge_records":[[0,1,1,1],[1,2,1,1],[2,0,1,1],[2,3,1,1]],
        "edge_contracts":[{"from":u,"to":v,"capacity":cap} for u,v,cap in [(0,1,1),(1,2,1),(2,0,1),(2,3,0)]],
        "trays":[{"tray_id":"a"},{"tray_id":"b"}],
        "jobs":[{"business_bag_id":str(i),"origin":0,"arrival":i,"storage_node":1,"destination":d}
                for i,d in enumerate([2,3,2,2,3,2])]}


def test_permanent_bad_budget_respects_one_remaining_carrier():
    result=analyze(data());assert result["topologically_reachable"]==4
    assert result["zero_unreachable_load_prefix_bound"]==1
    assert result["completion_upper_bound"]==3
    assert result["independent_prefix_dp_agrees"]


def test_stage_unreachable_uses_complete_graph_not_selected_path():
    x=data();x["edge_records"].append([0,3,1,1]);x["edge_contracts"].append({"from":0,"to":3,"capacity":1})
    assert analyze(x)["completion_upper_bound"]==6


def test_tied_release_order_is_unknown_instead_of_assumed_fifo():
    x=data();x["jobs"][1]["arrival"]=0
    with pytest.raises(ValueError,match="ties_require"):analyze(x)


def test_one_carrier_cannot_pass_first_permanent_load():
    x=data();x["trays"]=x["trays"][:1]
    assert analyze(x)["completion_upper_bound"]==1


def test_mandatory_storage_reachability_not_just_direct_destination():
    x=data();x["jobs"][0]["storage_node"]=3
    assert analyze(x)["zero_unreachable_load_prefix_bound"]==0


def test_input_not_modified_and_duplicate_identity_rejected():
    x=data();old=deepcopy(x);analyze(x);assert x==old
    x["jobs"][1]["business_bag_id"]="0"
    with pytest.raises(ValueError,match="duplicate_job"):analyze(x)
