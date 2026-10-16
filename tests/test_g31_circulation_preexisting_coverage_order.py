"""Native coverage follows captured row order; no duplicate or set-only pass."""
import copy
import pytest

from scripts.experiments.g31_ics_circulation import native_preexisting_initial_adapter as adapter
from scripts.experiments.g31_ics_circulation import verify_preexisting_delivery as verifier
from scripts.experiments.g31_ics_circulation import research_native_preexisting_occupancy as runner
from test_g31_circulation_preexisting_online_model import initial_pair
from test_g31_circulation_preexisting_delivery_evidence import raw_fixture


def test_native_input_job_order_is_supported_without_sorting():
    view, ack, peer = initial_pair("B")
    body = peer[0]["capture"]
    assert [j["business_bag_id"] for j in body["jobs"]] == ["loaded", "receiver", "blocker"]
    assert body["coverage"]["business_bag_ids"] == ["loaded", "receiver", "blocker"]
    result = adapter.validate_pair(view, ack, peer)
    assert result["status"] == "conditional_validated_data"
    assert result["native_delivery_verified"] is False


@pytest.mark.parametrize("field,rows,key", [
    ("business_bag_ids", "jobs", "business_bag_id"), ("tray_ids", "trays", "tray_id")])
@pytest.mark.parametrize("defect", ["coverage_reordered", "coverage_duplicate", "coverage_missing", "coverage_extra", "rows_duplicate", "rows_missing", "identity_bool"])
def test_adapter_requires_exact_unique_native_row_membership(field, rows, key, defect):
    view, ack, peer = initial_pair("B"); body = peer[0]["capture"]
    values = body["coverage"][field]
    if defect == "coverage_reordered": values.reverse()
    elif defect == "coverage_duplicate": values.append(values[0])
    elif defect == "coverage_missing": values.pop()
    elif defect == "coverage_extra": values.append("undeclared")
    elif defect == "rows_duplicate":
        body[rows].append(copy.deepcopy(body[rows][0])); values.append(values[0])
    elif defect == "rows_missing": body[rows].pop()
    else:
        # Test the membership guard directly: the typed native digest encoder
        # rejects non-string identity before a fabricated envelope can be made.
        values[0] = True
        assert not adapter.coverage_matches_rows(values, body[rows], key)
        return
    peer[0]["payload_sha256"] = adapter.capture_digest(body)
    result = adapter.validate_pair(view, ack, peer)
    assert result["status"] == "unknown"
    assert result["reasons"] == ["missing_or_unrepresented_coverage"]


@pytest.mark.parametrize("defect", ["coverage_sorted", "coverage_duplicate", "rows_duplicate"])
def test_independent_verifier_also_checks_native_order_and_uniqueness(defect):
    specification = runner.protocol()["rows"]["block1_load1/delivery"]
    raw = raw_fixture(specification)
    message = raw["initial_owners"]["B"]["raw_endpoints"]["received"][0]
    body = message["capture"]
    if defect == "coverage_sorted": body["coverage"]["business_bag_ids"].sort()
    elif defect == "coverage_duplicate": body["coverage"]["business_bag_ids"].append("loaded")
    else:
        body["jobs"].append(copy.deepcopy(body["jobs"][0]))
        body["coverage"]["business_bag_ids"].append("loaded")
    message["payload_sha256"] = adapter.capture_digest(body)
    result = verifier.verify_branch(raw, specification, raw["input"])
    assert result["status"] == "unknown_or_failed" and result["reason"] == "wrong_capture_scope"
