"""Assessor rejects altered reference actions, inputs and missing completions."""
import copy
import gzip
import json
from pathlib import Path
from scripts.experiments.g31_ics_circulation import verify_native_feedback_outage as verifier

PATH = Path(__file__).resolve().parents[1] / "outputs/experiments/g31_ics_lt2_sustained_20261014/native_feedback_outage_001"


def fixture():
    key = "outage/gate6/offline_time00"
    plan = json.loads((PATH / "preregistered_protocol.json").read_text())
    return json.load(gzip.open(PATH / (key + ".json.gz"), "rt")), plan["rows"][key]


def test_reference_identity_cannot_be_relabelled_under_valid_physics():
    raw, row = fixture()
    assert verifier.check_raw(raw, row) == []
    changed = copy.deepcopy(row)
    changed["departure"] += .001
    assert "offline_reference_action_identity_mismatch" in verifier.check_raw(raw, changed)


def test_business_or_exogenous_schedule_change_is_rejected():
    raw, row = fixture()
    raw["input"]["owner_protocol"]["owner_outages"][0]["end"] += .01
    assert "input_or_exogenous_contract_changed" in verifier.check_raw(raw, row)


def test_unfinished_completion_is_not_strict_protected_success():
    raw, row = fixture()
    raw["result"]["jobs"][-1]["completed_at"] = -1.
    assert "physical_full_population_reassessment" in verifier.check_raw(raw, row)
