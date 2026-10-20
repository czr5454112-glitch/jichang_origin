"""Recompute saved native030 micro-gates without spending another constructor.

The native-producing CLI is native030_inventory_spi_gates.py. Its explicit
--ledger and fresh --output are mandatory; a normal pytest collection never
implicitly launches a simulator or consumes the campaign budget.
"""
from collections import Counter
import json
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.native_host import audit_result

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "outputs/experiments/g31_ics_inventory_spi_20261020/cycle_001/native_gates"


@pytest.fixture(scope="module")
def gates():
    path = Path(os.environ.get("G31_NATIVE030_EVIDENCE", str(DEFAULT)))
    if not (path / "13_after_other_failure/receipt.json").exists():
        pytest.skip("native030 evidence is not present; no implicit native execution")
    return path


def read(gates, name, file):
    return json.loads((gates / name / file).read_text(encoding="utf-8"))


def test_saved_all_successful_gates_conserve_actual_trays_edges_and_capacity(gates):
    passed = 0
    for directory in sorted(gates.iterdir()):
        receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
        if receipt["status"] != "passed":
            continue
        data = json.loads((directory / "input.json").read_text(encoding="utf-8"))
        transfer = json.loads((directory / "transfer.json").read_text(encoding="utf-8"))
        data["transfers"] = [dict(transfer, issued_at=0.)]
        if (directory / "fresh_transfer.json").exists():
            fresh = json.loads((directory / "fresh_transfer.json").read_text(encoding="utf-8"))
            data["transfers"].append(dict(fresh, issued_at=9.6))
        result = json.loads((directory / "final_result.json").read_text(encoding="utf-8"))
        assert audit_result(data, result)["status"] == "passed"
        passed += 1
    assert passed == 12


def test_saved_wakeup_causal_counterexample_keeps_failed_tray_quarantined(gates):
    before = read(gates, "01_before_expiry", "final_result.json")
    after = read(gates, "03_after_expiry", "final_result.json")
    assert before["jobs"][0]["status"] != "completed"
    assert after["jobs"][0]["status"] == "completed"
    assert before["trays"][0]["mode"] == after["trays"][0]["mode"] == "quarantined"
    assert not read(gates, "01_before_expiry", "at_6_diagnostics.json")["resource_waits"]
    assert read(gates, "03_after_expiry", "at_6_diagnostics.json")["resource_waits"]
    assert not any(row["event"] == "EMPTY_RECOVERY_GRANTED" for row in after["receipts"])


def test_saved_no_expiry_control_has_exact_same_physical_trace(gates):
    before = read(gates, "02_before_no_expiry", "final_result.json")
    after = read(gates, "04_after_no_expiry", "final_result.json")
    for field in ("jobs", "trays", "transfers", "receipts", "leg_identities"):
        assert before[field] == after[field]


def test_saved_fifo_and_unique_arbitration_per_node_timestamp(gates):
    for name in ("03_after_expiry", "05_after_checkpoint_retry", "09_after_fifo_retry"):
        result = read(gates, name, "final_result.json")
        counts = Counter((r["node"], r["time"]) for r in result["native_events"]
                         if r["event"] == "JUNCTION_ARBITRATION")
        assert counts and max(counts.values()) == 1
    result = read(gates, "09_after_fifo_retry", "final_result.json")
    entries = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER" and r["from"] == 0]
    assert [r["tray_id"] for r in entries] == ["Y", "Z"]
    assert entries[1]["time"] - entries[0]["time"] >= .1


def test_saved_checkpoint_retry_generation_and_stale_delayed_ack(gates):
    receipt = read(gates, "05_after_checkpoint_retry", "receipt.json")
    assert receipt["same_expiry_replayed_identically_after_restore"]
    assert receipt["restore_additional_constructors"] == 0
    for name in ("06_after_recovery_valid", "11_after_recovery_valid_reuse"):
        proof = read(gates, name, "recovery_proof.json")
        assert proof["final"]["generation"] == proof["binding"]["expected_generation"] + 1
        assert proof["stale_ack"]["last_delivered_ack"]["reason"] == "stale_recovery_generation"
        result = read(gates, name, "final_result.json")
        assert sum(r["event"] == "EMPTY_RECOVERY_GRANTED" for r in result["receipts"]) == 1
        assert result["transfers"][0]["status"] == "failed"
    result = read(gates, "11_after_recovery_valid_reuse", "final_result.json")
    assert result["transfers"][1]["status"] == "received"


def test_saved_rejections_preserve_quarantine_and_do_not_clear_uncertain_obligation(gates):
    rows = read(gates, "07_after_recovery_reject", "rejected_command_acks.json")
    assert len(rows) == 8 and all(r["last_delivered_ack"]["status"] == "rejected" for r in rows)
    entered = read(gates, "10_after_entered_empty_rejected", "already_entered_recovery_rejection.json")
    assert entered["current"]["edge_to"] >= 0
    assert entered["ack"]["last_delivered_ack"]["reason"] == "inflight_or_receiving_obligation"
    uncertain = read(gates, "13_after_other_failure", "unlisted_failure_recovery_rejection.json")
    assert uncertain["current"]["mode"] == "quarantined"
    assert uncertain["current"]["reception_node"] >= 0
    assert "failed_empty_recovery" not in uncertain["current"]
    assert uncertain["ack"]["last_delivered_ack"]["reason"] == "inflight_or_receiving_obligation"
    assert read(gates, "08_after_recovery_outage", "outage_ack.json")["last_delivered_ack"]["reason"] == "recovery_expired"


def test_failed_fixture_attempt_is_retained_and_counted(gates):
    failed = read(gates, "12_after_unlisted_failure", "receipt.json")
    assert failed["status"] == "failed" and failed["constructors"] == 1
    assert len(list(gates.glob("*/receipt.json"))) == 13
