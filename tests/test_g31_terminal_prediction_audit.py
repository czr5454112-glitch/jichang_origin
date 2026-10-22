"""Audit exports must be complete, causal, and compared by physical orders."""
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_prediction_audit as audit


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("chunk", [1, 7, 29])
def test_streaming_audit_reads_exactly_across_json_and_unicode_boundaries(tmp_path, compressed, chunk):
    path = tmp_path/("rows.json.gz" if compressed else "rows.json")
    values = [{"name": "观察🚀", "state": {"owner": "a", "pending": [1, 2]}}, 12000, None,
              {"escaped": "new\nline\"test", "value": -1.25e10}]
    opener = gzip.open if compressed else open
    with opener(path, "wt", encoding="utf-8") as stream:
        stream.write(" \n"+json.dumps(values, ensure_ascii=False)+" \n")
    assert list(audit.iter_json_array(path, chunk_bytes=chunk)) == values


@pytest.mark.parametrize("text", ["[", '[{"x":1}', '[1 2]', '[1,]', '[1] false', '[]{}'])
def test_incomplete_or_malformed_export_cannot_be_audited_as_complete(tmp_path, text):
    path = tmp_path/"rows.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        list(audit.iter_json_array(path, chunk_bytes=1))


def test_TEST_rejected_before_opening_worker_or_observations(tmp_path, monkeypatch):
    (tmp_path/"plan.json").write_text(json.dumps({"parent": {"split": "test"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="TEST_not_opened"):
        audit.closed_plan(tmp_path)


def test_open_or_failed_process_cannot_supply_public_state_comparison(tmp_path):
    plan = {"parent": {"split": "dev"}}
    worker = {"scientific_status": "open", "process_status": "running"}
    (tmp_path/"plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tmp_path/"worker_report.json").write_text(json.dumps(worker), encoding="utf-8")
    receipt = {"plan_sha256": audit.study.sha(tmp_path/"plan.json"), "worker": worker, "process": {"exitcode": 0}}
    (tmp_path/"receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="closed_successful"):
        audit.closed_plan(tmp_path)


def test_physical_allocation_summary_does_not_confuse_plan_hash_with_order_change():
    catalog = {"candidates": [{"action_id": "send", "action_type": "empty_transfer", "tray_id": "tray",
        "source": "source", "destination": "destination"}]}
    choice = {"action_id": "send", "flow_plan": {"plan_id": "unimportant_forecast_digest",
        "chosen": [{"source": "source", "destination": "destination"}]*2},
        "empty_transport_order": {"target_by": 100.}, "reason": "positive_gain", "flow_verification": {"exact_net_gain": 3.}}
    physical = audit.physical_choice(choice, catalog)
    assert physical["allocation"] == [{"source": "source", "destination": "destination", "quantity": 2}]
    assert physical["planned_quantity"] == 2
    assert "plan_id" not in physical

