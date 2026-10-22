"""Offline labels require native arrival receipts and a closed bound process."""
import copy
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast_evaluation as study


def sources():
    worker = {"process_status": "completed", "scientific_status": "closed", "final_physical_time": 18000.}
    plan = {"parent": {"split": "train"}, "input": {"path": "input.json", "sha256": "hash"}}
    receipt = {"plan_sha256": "hash", "worker": copy.deepcopy(worker), "process": {"exitcode": 0}}
    terminal = {"physical_clock": 18000., "advance": {"horizon_complete": True, "status": "reached"},
        "receipts": [{"event": "BAG_ARRIVAL", "business_bag_id": "actual", "time": 100., "node": 0}]}
    native_input = {"jobs": [{"business_bag_id": "actual", "arrival": 100., "origin": 0},
                             {"business_bag_id": "future", "arrival": 20000., "origin": 24}]}
    return {"plan.json": plan, "worker_report.json": worker, "receipt.json": receipt,
            "terminal_evidence.json.gz": terminal, "input.json": native_input}


def fixture_reader(monkeypatch, data):
    monkeypatch.setattr(study, "read", lambda path: data[Path(path).name])
    monkeypatch.setattr(study, "sha", lambda path: "hash")
    monkeypatch.setattr(study, "bound", lambda path: {"path": str(path), "sha256": "hash"})


def test_actual_prefix_labels_do_not_count_unarrived_offered_population(monkeypatch):
    fixture_reader(monkeypatch, sources())
    _, arrivals, evidence = study.load_closed_run("run", split="train")
    assert arrivals == {"airport_node_0": [100.]}
    assert evidence["native_arrival_count"] == 1
    assert evidence["future_jobs_used_as_arrival_labels"] is False
    assert study.count(arrivals, "airport_node_0", 0., 100.) == 1
    assert study.count(arrivals, "airport_node_0", 100., 200.) == 0
    assert study.count(arrivals, "airport_node_24", 0., 18000.) == 0


@pytest.mark.parametrize("mutation", ["DEV", "failed_process", "missing_receipt", "future_receipt", "wrong_station", "unclosed"])
def test_offline_producer_rejects_unbound_or_unobserved_counts(monkeypatch, mutation):
    data = sources()
    if mutation == "DEV": data["plan.json"]["parent"]["split"] = "dev"
    elif mutation == "failed_process": data["receipt.json"]["process"]["exitcode"] = 1
    elif mutation == "missing_receipt": data["terminal_evidence.json.gz"]["receipts"] = []
    elif mutation == "future_receipt":
        data["terminal_evidence.json.gz"]["receipts"].append(
            {"event": "BAG_ARRIVAL", "business_bag_id": "future", "time": 20000., "node": 24})
    elif mutation == "wrong_station": data["terminal_evidence.json.gz"]["receipts"][0]["node"] = 24
    elif mutation == "unclosed": data["terminal_evidence.json.gz"]["advance"]["horizon_complete"] = False
    fixture_reader(monkeypatch, data)
    with pytest.raises(ValueError): study.load_closed_run("run", split="train")
