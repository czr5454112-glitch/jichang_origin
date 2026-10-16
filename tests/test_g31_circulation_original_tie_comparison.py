"""Full denominator, undefined unfinished differences, actual gate admission."""
import copy
from scripts.experiments.g31_ics_circulation import research_original_tie_comparison as comparison


def fixture():
    data = {"jobs": [{"business_bag_id": j, "arrival": arrival, "deadline": 22200.} for j, arrival in
                     ((comparison.chain.TARGET, 0.), (comparison.BENEFICIARY, 0.), ("future", 30000.))]}
    rows = [{"business_bag_id": j["business_bag_id"], "completed_at": 100. if j["business_bag_id"] == comparison.BENEFICIARY else -1.} for j in data["jobs"]]
    arm = {"status": "reached", "physical_audit": {"status": "passed"},
        "result": {"jobs": rows, "receipts": [], "advance": {"horizon_complete": True, "physical_time": 22200.}},
        "intent": {"status": "waiting", "decisions": [], "path": [0, 1]}}
    return data, {"control": copy.deepcopy(arm), "candidate": copy.deepcopy(arm)}


def test_unfinished_bad0_is_not_zero_regression_and_future_denominator_stays():
    data, arms = fixture()
    arms["candidate"]["result"]["jobs"][1]["completed_at"] = 99.
    report = comparison.assess(data, arms)
    assert report["offered_full_input_denominator"] == 3 and report["arrived_by_common_horizon"] == 2
    assert report["completion_delta_defined_count"] == 1
    assert comparison.chain.TARGET not in report["completion_deltas_defined_subset"]
    assert report["strict_full_population_protection"].startswith("unknown")
    assert report["strict_horizon_offered_protection"].startswith("unknown") and report["gain_all_jobs"] is None


def test_observed_regression_fails_even_when_other_jobs_unfinished():
    data, arms = fixture(); arms["candidate"]["result"]["jobs"][1]["completed_at"] = 100.000000001
    report = comparison.assess(data, arms)
    assert report["strict_horizon_offered_protection"] == report["strict_full_population_protection"] == "failed"


def test_censoring_and_missing_offered_rows_cannot_certify_mechanism():
    data, arms = fixture(); arms["candidate"]["result"]["advance"]["horizon_complete"] = False
    assert comparison.assess(data, arms)["storage_order_mechanism"] == "unknown"
    arms["candidate"]["result"]["advance"]["horizon_complete"] = True
    arms["candidate"]["result"]["jobs"].pop(0)
    assert comparison.assess(data, arms)["status"] == "unknown_missing_arrived_population"


def test_nominal_gate_status_without_actual_ack_edge_evidence_not_admitted():
    protocol = {"input_sha256": "input", "hypothesis": {"commands": [{"from": 1, "next": 2}], "path": [0, 1, 2]}}
    gate = {"status": "all_four_intents_and_edges_observed", "source_changed": [], "input_sha256": "input", "binary_sha256": "binary",
        "intent": {**protocol["hypothesis"], "decisions": [], "observed_edges": []}}
    assert not comparison.validate_gate(gate, protocol, "binary")
