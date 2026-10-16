import copy
from fractions import Fraction
import math
import pytest
from scripts.experiments.g31_ics_circulation import public_live_obligation_interval as m


@pytest.fixture(scope="module")
def package():
    return m.fixed_contracts()


def arguments():
    return dict(t0=10.25, x=9.05, hq=1.1, hx=1.1, advance=1.5,
        fixed_advance=.5, detour=1.3, resource_id=3, x_resource_id=3, capacity=1)


def test_fixed_construction_not_search(package):
    assert tuple(row["case_id"] for row in package["cases"]) == m.CASE_IDS
    assert [row["interval_screen"]["status"] for row in package["cases"]] == [
        "conditional_isolated_interval_witness", "rejected_isolated_interval_hypothesis",
        "rejected_isolated_interval_hypothesis"]
    assert package["new_projection_or_native_execution_count"] == 0
    assert package["initial_candidate_count_per_method"] == 32
    assert package["later_candidate_count_per_method"] == 4


def test_public_derived_values(package):
    v=package["construction"]["values"]
    assert {k:Fraction(v[k]) for k in ("slow_release","fast_release","advance","detour","x","P_release")} == {
        "slow_release":Fraction("7.3"),"fast_release":Fraction("6.3"),"advance":Fraction("1.5"),
        "detour":Fraction("1.3"),"x":Fraction("9.05"),"P_release":Fraction("8.95")}
    assert Fraction(v["route_service_window"]) > Fraction(v["later_collect_and_route_wire"])


def test_real_reservation_order_not_arrival_order():
    a=arguments(); first=m.interval_screen(**a)
    assert first["status"] == "conditional_isolated_interval_witness"
    a["x"] += 1.0  # mistakenly substitute physical arrival for reservation
    second=m.interval_screen(**a)
    assert second["status"] == "rejected_isolated_interval_hypothesis"
    assert "baseline_X_clears_before_Q" in second["failed_predicates"]


@pytest.mark.parametrize("field,value", [("advance",True),("detour",math.nan),("hq",0),
    ("hx",-1),("x_resource_id",4),("capacity",2),("resource_id",True)])
def test_invalid_domain_fails_closed(field,value):
    a=arguments();a[field]=value
    assert m.interval_screen(**a)["status"] == "unknown_invalid_interval_contract"


@pytest.mark.parametrize("field,value,failed", [
    ("detour",1.5,"early_supply_can_pay_detour"),
    ("advance",2.3,"even_earliest_default_Q_cannot_clear_before_X"),
    ("detour",1.4,"bypass_beats_best_safe_timing_only_bound"),
    ("fixed_advance",1.3,"detour_exceeds_order_gap_and_fixed_initial_advance")])
def test_equality_is_not_strict_gain_or_barrier(field,value,failed):
    a=arguments();a[field]=value; result=m.interval_screen(**a)
    assert result["status"] == "rejected_isolated_interval_hypothesis"
    assert failed in result["failed_predicates"]


def test_all_five_jobs_stock_and_complete_new_graph(package):
    for row in package["cases"]:
        data=row["input"]
        assert {j["business_bag_id"] for j in data["jobs"]} == m.JOBS
        assert [t["tray_id"] for t in data["trays"]] == ["L","E","P"]
        assert len(data["node_records"]) == len(data["heuristic_time"]) == 11
        assert all(len(r)==11 for r in data["heuristic_time"])
        assert len(data["edge_records"]) == 14
        assert {(n[0],v) for n in data["node_records"] for v in n[5]} == {(e[0],e[1]) for e in data["edge_records"]}
        assert row["static_permissions"]["status"] == "static_contract_permissions_present"
        assert row["whole_population_protection"] == "unknown"
        assert not row["interval_screen"]["native_protection_certified"]


def test_negative_contract_changes_are_only_preregistered(package):
    pos, no, insufficient = [copy.deepcopy(r["input"]) for r in package["cases"]]
    for data in (pos,no,insufficient):
        data.pop("heuristic_time");data.pop("potential_contract",None)
    assert pos["node_contracts"]==no["node_contracts"]==insufficient["node_contracts"]
    assert pos["edge_contracts"]==no["edge_contracts"]==insufficient["edge_contracts"]
    next(j for j in no["jobs"] if j["business_bag_id"]=="blocker")["storage_release_at"]=8.95
    next(e for e in insufficient["edge_records"] if e[:2]==[0,2])[2]=2.0
    assert m.encoded(pos)==m.encoded(no)==m.encoded(insufficient)


def test_no_hidden_owner_or_tray_permission(package):
    data=copy.deepcopy(package["cases"][0]["input"])
    next(n for n in data["node_contracts"] if n["node"]==6)["allow_export"]=False
    assert m.static_permissions(data)["status"]=="unsupported_static_permissions"
    data=copy.deepcopy(package["cases"][0]["input"])
    next(e for e in data["edge_contracts"] if (e["from"],e["to"])==(7,8))["capacity"]=0
    assert m.static_permissions(data)["status"]=="unsupported_static_permissions"


def test_changed_source_is_not_silently_new_parameter():
    data=m.source_contract();data["jobs"][0]["load_seconds"]+=1
    with pytest.raises(ValueError,match="unsupported_source_contract"):
        m.derive(data)


def test_outputs_do_not_alias_or_promote_unknown(package):
    a=m.fixed_contracts(); a["cases"][0]["input"]["jobs"][0]["deadline"]=0
    assert package["cases"][0]["input"]["jobs"][0]["deadline"]==40
    assert a["cases"][1]["input"]["jobs"][0]["deadline"]==40
    assert all(row["native_embedding_status"].startswith("unknown") for row in package["cases"])
    assert "unprotected proposals" in package["policy_contract"]["strong_baselines"][-1]
