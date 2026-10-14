"""A mechanism subset is selected from source rules, never observed winners."""
from collections import Counter
import pytest

from scripts.experiments.g31_ics_circulation.original_mechanism import select_input
from scripts.experiments.g31_ics_circulation.original_workload import ProxyContract, build_input


@pytest.mark.parametrize("count",[2,24])
def test_prespecified_subset_keeps_full_graph_and_original_business(count):
    data, selection, lineage = select_input(count)
    parent, _, _ = build_input(scale=1,contract=ProxyContract(
        "nanning-on-carrier-proxy-v1-n4-s4-t2",4,4,2,1.,1.,0.,"finite_berth_waiting_research_proxy"))
    originals = {j["business_bag_id"]:j for j in parent["jobs"]}
    assert all(j == originals[j["business_bag_id"]] for j in data["jobs"])
    assert len(data["jobs"]) == count
    assert data["node_records"] == parent["node_records"]
    assert data["edge_records"] == parent["edge_records"]
    assert data["node_contracts"] == parent["node_contracts"]
    assert data["edge_contracts"] == parent["edge_contracts"]
    assert len(data["trays"]) == 1 and data["trays"][0] in parent["trays"]
    assert data["transfers"] == []
    assert selection["selected_without_simulation_results"]
    assert selection["mother_offered"] == len(lineage) == 28506
    assert sum(r["selected_for_witness"] for r in lineage) == count
    assert all(r["eligibility"] == "eligible_static_round_trip" for r in lineage if r["selected_for_witness"])
    assert Counter(r["eligibility"] for r in lineage) == selection["eligibility_counts"]
