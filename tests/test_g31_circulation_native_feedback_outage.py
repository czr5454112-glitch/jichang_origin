"""Unchanged business, complete finite reference and strict paired protection."""
import copy
from scripts.experiments.g31_ics_circulation import research_native_feedback_outage as study


def test_full31_native_reference_and_reused_healthy_denominator_prespecified():
    p = study.protocol()
    assert p["row_denominator"] == len(p["rows"]) == 117
    assert sum(not r["reuse_prior"] for r in p["rows"].values()) == p["maximum_new_native_branches"] == 108
    assert sum(r["scope"] == "offline_finite_reference_only" for r in p["rows"].values()) == 93
    times = study.reference_times()
    assert len(times) == len(set(times)) == 31 and min(times) == .11 and max(times) == 6.11
    outage = study.outage_contract()
    assert .11 < outage["start"] < .12 and outage["end"] == 6.1


def test_all31_reference_needed_and_positive_perjob_delta_is_not_tolerated():
    rows = copy.deepcopy(study.protocol()["rows"])
    for r in rows.values():
        r.update(status="assessed", summary={"completion": {j: 10. for j in ("loaded", "receiver", "reuse1", "reuse2")}})
    rows["outage/gate6/offline_time30"]["status"] = "unknown_failed"
    rows["outage/gate6/joint_model"]["summary"]["completion"]["reuse2"] += 1e-12
    result = study.comparison(rows)["outage/gate6/"]
    assert result["offline_reference_status"] == "unknown" and "joint_gain_vs_offline_fixed31" not in result
    assert not result["joint_protected_vs_incumbent"] and not result["joint_protected_vs_fixed_model"]
    assert not result["feedback_protected_vs_paired_native_keep"]


def test_healthy_and_outage_initial_policy_actions_receive_no_regime_argument():
    import inspect
    source = inspect.getsource(study.run_cell)
    assert 'online.owner_first_action(native, session, client, o, planning[o], policy)' in source
    assert 'data["owner_protocol"]["owner_outages"] = [outage_contract()]' in source
    p = study.protocol()
    for gate in (0, 6, 12):
        for policy in ("incumbent", "fixed_route_model", "joint_model"):
            assert p["rows"][f"healthy/gate{gate}/{policy}"]["reuse_prior"] is True
