"""Regression of the compiled mature G31 circulation host, never a Python simulator."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result, load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.validate_native_cycle import check_campaign, scenarios


@pytest.fixture(scope="module")
def native():
    configured = os.environ.get("G31_CIRCULATION_BINARY")
    if configured:
        binary = Path(configured)
    else:
        folder = Path(__file__).resolve().parents[1] / "build_g31_circulation" / "python"
        matches = list(folder.glob("czr005_circulation*.pyd")) + list(folder.glob("czr005_circulation*.so"))
        assert len(matches) == 1, "Build target czr005_circulation or set G31_CIRCULATION_BINARY"
        binary = matches[0]
    return load_native(binary)


def test_full_physical_acceptance_matrix(native):
    rows = {}
    for name, data in scenarios():
        rows[name] = native.run(data)
        audit_result(data, rows[name])
    assert check_campaign(rows)["scenario_count"] == 13


@pytest.mark.parametrize("mutation,reason", [
    (lambda s: s["trays"].clear(), "empty_fleet"),
    (lambda s: s["trays"].append(dict(s["trays"][0])), "invalid_tray"),
    (lambda s: s["jobs"].append(dict(s["jobs"][0])), "invalid_job"),
    (lambda s: s["node_contracts"].pop(), "node_contract_coverage"),
    (lambda s: s["edge_contracts"].pop(), "edge_contract_coverage"),
    (lambda s: s["node_contracts"][0].update(capacity=0), "invalid_node_contract"),
    (lambda s: s["edge_contracts"][0].update(capacity=-1), "invalid_edge_contract"),
    (lambda s: s["edge_contracts"][0].update(entry_headway=-1), "invalid_edge_contract"),
    (lambda s: s["jobs"][0].update(storage_node=0), "zero_hop_contract_unsupported"),
    (lambda s: s["jobs"][0].update(arrival=float("nan")), "invalid_job"),
    (lambda s: s["jobs"][0].update(unload_seconds=-1), "invalid_job"),
    (lambda s: s["transfers"][0].update(tray_id="ghost"), "invalid_transfer"),
    (lambda s: s["transfers"][0].update(message_delay=float("inf")), "invalid_transfer"),
])
def test_invalid_physical_contracts_are_rejected(native, mutation, reason):
    data = tiny_cycle()
    mutation(data)
    with pytest.raises(ValueError, match="circulation:" + reason):
        native.run(data)


def test_cross_region_port_cannot_take_over_same_zone_module(native):
    data = tiny_cycle()
    data["node_contracts"][4]["zone"] = "A"
    result = native.run(data)
    assert result["transfers"][0]["reason"] == "same_zone_transfer_not_authorized"
    assert result["jobs"][1]["loaded_at"] < 0
    audit_result(data, result)


def test_binding_default_horizon_handles_late_absolute_time(native):
    data = tiny_cycle()
    data["options"].pop("max_simulation_time")
    for job in data["jobs"]:
        for field in ("arrival", "deadline", "storage_release_at"):
            job[field] += 90000
    for request in data["transfers"]:
        for field in ("issued_at", "earliest_departure", "expiry"):
            request[field] += 90000
    result = native.run(data)
    assert all(j["status"] == "completed" for j in result["jobs"])
    audit_result(data, result)


def test_waiting_bags_use_arrival_fifo_independent_of_input_order(native):
    data = tiny_cycle()
    data["trays"][0]["node"] = 4
    data["jobs"][0]["arrival"] = 0.2
    data["jobs"][1]["arrival"] = 0.1
    data["transfers"][0]["issued_at"] = 0.0
    result = native.run(data)
    assert result["jobs"][1]["loaded_at"] >= 0
    assert result["jobs"][0]["loaded_at"] < 0
    audit_result(data, result)


@pytest.mark.parametrize("tamper", ["reuse_traversal", "erase_empty_trip", "shorten_hold", "invent_second_tray"])
def test_receipt_auditor_rejects_manufactured_cycle(native, tamper):
    data = tiny_cycle()
    result = deepcopy(native.run(data))
    entries = [e for e in result["receipts"] if e["event"] == "EDGE_ENTER"]
    if tamper == "reuse_traversal":
        entries[1]["traversal_id"] = entries[0]["traversal_id"]
    elif tamper == "erase_empty_trip":
        empty_ids = {r["transport_leg_id"] for r in result["leg_identities"] if r["kind"] == "empty_return"}
        result["receipts"] = [r for r in result["receipts"] if not (
            r["transport_leg_id"] in empty_ids and r["event"] in ("EDGE_ENTER", "EDGE_EXIT"))]
    elif tamper == "shorten_hold":
        data["jobs"][0]["hold_seconds"] += 2
    else:
        result["trays"].append({"tray_id": "invented"})
    with pytest.raises(AssertionError):
        audit_result(data, result)
