"""Information partitions, all-regime protection and fail-closed table guards."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import audit_reuse_information as audit


def table():
    rows = {}
    for gate in audit.REGIMES:
        inputs = {}
        for owner in ("A", "B"):
            view = {"schema": "g31.owner_protocol_observation.v1", "owner_id": owner, "now": .11,
                "node_records": [], "edge_records": [], "edge_contracts": [], "node_contracts": [],
                "jobs": [{"arrival": 0., "storage_release_at": float(gate)}] if owner == "A" else [],
                "trays": [], "delivered_messages": []}
            inputs[owner] = {"view": view, "own_predecision_calls": [], "public_contract": audit.contract()}
        cells = {}
        for key in audit.CELL_KEYS:
            times = {j: 10. for j in sorted(audit.JOBS)}
            if key.endswith("window0"):
                times["receiver"] = 11.
            if gate == "6.0" and key == "route2_window0":
                times["receiver"] = 9.
            cells[key] = {"status": "assessed", "audit": {"status": "passed"},
                "completion": times, "completion_sum": sum(times.values())}
        rows[gate] = {"inputs": inputs, "cells": cells}
    return rows


def test_indistinguishable_receiver_must_choose_one_window_and_inputs_are_unchanged():
    rows = table()
    before = copy.deepcopy(rows)
    report = audit.assess(rows)
    assert report["status"] == "assessed"
    assert report["observation_partition"]["A"]["class_count"] == 3
    assert report["observation_partition"]["B"]["class_count"] == 1
    assert report["enumerated_policy_count"] == 32
    assert report["team_minus_full_information_seconds"] == 1.
    assert all(len(p["B_windows_by_class"]) == 1 for p in report["policies"])
    assert rows == before
    assert report["general_decentralized_impossibility"] is False


def test_delivered_information_splits_classes_and_can_close_table_gap():
    rows = table()
    for gate, row in rows.items():
        row["inputs"]["B"]["view"]["delivered_messages"] = [{"message_id": "captured",
            "source_owner": "A", "target_owner": "B", "delivered_at": .1,
            "observed_at": .09, "storage_release_at": float(gate)}]
    report = audit.assess(rows)
    assert report["status"] == "assessed"
    assert report["observation_partition"]["B"]["class_count"] == 3
    assert report["enumerated_policy_count"] == 512
    assert report["team_minus_full_information_seconds"] == 0.
    # Abstract information-partition test; it does not implement a native message kind.


def test_own_request_history_is_part_of_the_information_class():
    rows = table()
    for gate, row in rows.items():
        row["inputs"]["B"]["own_predecision_calls"] = [{"at": .05,
            "request": {"owner_id": "B", "request_id": gate}}]
    report = audit.assess(rows)
    assert report["observation_partition"]["B"]["class_count"] == 3
    assert report["team_minus_full_information_seconds"] == 0.


def test_protection_is_per_job_not_net_gain_and_has_no_positive_epsilon():
    rows = table()
    for row in rows.values():
        cell = row["cells"]["route2_window2"]
        cell["completion"]["loaded"] += 1e-12
        cell["completion"]["receiver"] -= 5
        cell["completion_sum"] = sum(cell["completion"].values())
    report = audit.assess(rows)
    assert report["status"] == "assessed"
    assert all(not p["protected_in_every_regime"] for p in report["policies"]
               if "route2_window2" in p["actions"].values())


@pytest.mark.parametrize("defect", ["future_capture", "future_local_job", "future_published_job",
    "future_physical_fact", "future_ack", "bool_time", "infinite_time"])
def test_future_information_cannot_split_observation_classes(defect):
    rows = table()
    view = rows["6.0"]["inputs"]["B"]["view"]
    message = {"message_id": "m", "source_owner": "A", "target_owner": "B",
               "observed_at": .06, "delivered_at": .07, "jobs": [{"arrival": .05}]}
    view["delivered_messages"] = [message]
    if defect == "future_capture":
        message["observed_at"] = 100.
    elif defect == "future_local_job":
        view["jobs"] = [{"arrival": 100.}]
    elif defect == "future_published_job":
        message["jobs"][0]["arrival"] = .065
    elif defect == "future_physical_fact":
        view["jobs"] = [{"arrival": .01, "loaded_at": .12}]
    elif defect == "future_ack":
        view["delivered_command_acks"] = [{"observed_at": .1, "delivered_at": .09}]
    elif defect == "bool_time":
        message["observed_at"] = False
    else:
        message["observed_at"] = float("inf")
    assert audit.assess(rows)["status"] == "unknown"


@pytest.mark.parametrize("defect", ["missing_regime", "missing_cell", "unknown_cell", "bad_audit",
    "missing_job", "nonfinite", "wrong_sum", "future_message", "wrong_owner_message", "private_contract_label"])
def test_missing_or_invalid_information_does_not_become_zero_gap(defect):
    rows = table()
    row = rows["6.0"]
    cell = row["cells"]["route2_window0"]
    view = row["inputs"]["B"]["view"]
    if defect == "missing_regime":
        rows.pop("0.0")
    elif defect == "missing_cell":
        row["cells"].pop("route2_window0")
    elif defect == "unknown_cell":
        cell["status"] = "unknown"
    elif defect == "bad_audit":
        cell["audit"]["status"] = "failed"
    elif defect == "missing_job":
        cell["completion"].pop("loaded")
    elif defect == "nonfinite":
        cell["completion"]["loaded"] = float("nan")
    elif defect == "wrong_sum":
        cell["completion_sum"] += 1
    elif defect in ("future_message", "wrong_owner_message"):
        view["delivered_messages"] = [{"target_owner": "A" if defect == "wrong_owner_message" else "B",
                                      "delivered_at": .12 if defect == "future_message" else .1}]
    else:
        row["inputs"]["B"]["public_contract"]["gate"] = 6
    report = audit.assess(rows)
    assert report["status"] == "unknown"
    assert report["best_team_policy"] is None
    assert report["full_information_reference"] is None
    assert report["team_minus_full_information_seconds"] is None
