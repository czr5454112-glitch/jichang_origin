"""Real native verification for the explicitly synthetic mechanism domains."""
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.research_synthetic_contention import (
    scene, run_factorial, run_higher_order, classify_joint_subset,
)


def test_domains_preserve_stock_per_group_and_label_synthetic():
    small, triple = scene(), scene(higher_order=True)
    assert "SYNTHETIC" in small["model_scope"] and "SYNTHETIC" in triple["model_scope"]
    assert len(small["trays"]) == 2 and len(triple["trays"]) == 3
    assert {n["resource_owner"] for n in small["node_contracts"]} == {"A", "B"}
    assert next(n for n in triple["node_contracts"] if n["node"] == 3)["capacity"] == 2


@pytest.mark.parametrize("problem", ["horizon", "pending", "missing", "expired", "other_rejection"])
def test_nonreceipt_alone_cannot_certify_joint_overcapacity(problem):
    row = {"common_horizon_complete": True, "selected_count": 3, "physical_received_count": 2,
           "acks": [{"status": "received"}, {"status": "received"},
                    {"status": "rejected", "reason": "receiving_full"}]}
    assert classify_joint_subset(row) == "unexecutable_joint_set"
    if problem == "horizon":
        row["common_horizon_complete"] = False
    elif problem == "missing":
        row["acks"][-1] = None
    elif problem == "other_rejection":
        row["acks"][-1]["reason"] = "source_permission_denied"
    else:
        row["acks"][-1]["status"] = problem
    assert classify_joint_subset(row).startswith("unknown")


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native identity required")
def test_native_factorial_is_nonseparable_but_normal_regression_is_retained():
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    report, raw = run_factorial(native, scene())
    assert report["status"] == "assessed"
    assert abs(report["kappa_completion_sum_seconds"]) > .1
    assert len(report["cells"]) == 4
    assert all(row["business_complete"] and row["audit"]["status"] == "passed" for row in report["cells"].values())
    assert all(row["transfer_ack"]["status"] == "received" for row in report["cells"].values())
    assert report["cells"]["route0_early0"]["zero_regression_passed"]
    assert not report["cells"]["route1_early1"]["zero_regression_passed"]
    for key in report["cells"]:
        assert raw[key]["calls"][0]["request"] == raw[key]["fixed_timer_retries"][0]["request"]


@pytest.mark.skipif(not os.environ.get("G31_CIRCULATION_BINARY"), reason="explicit native identity required")
def test_native_all_pairs_feasible_does_not_imply_triple_receiving_feasibility():
    native = load_native(os.environ["G31_CIRCULATION_BINARY"])
    report, _ = run_higher_order(native, scene(higher_order=True))
    assert report["higher_order_overcapacity_witness"]
    assert len(report["subsets"]) == 8
    assert report["all_pairs_execute"] and not report["triple_all_execute"]
    triple = report["subsets"]["7"]
    assert triple["physical_received_count"] == 2
    assert sorted(a["status"] for a in triple["acks"]) == ["received", "received", "rejected"]
    assert [a["reason"] for a in triple["acks"] if a["status"] == "rejected"] == ["receiving_full"]
    assert all(s["audit"]["status"] == "passed" for s in report["subsets"].values())
