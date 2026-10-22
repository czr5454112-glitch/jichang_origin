"""Final export drops only unrelated histories and releases each raw owner view."""
import gc
from pathlib import Path
import weakref

import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_joint_campaign import (
    collect_transfer_ack_evidence, terminal_evidence_subset, transfer_ack_evidence_subset,
)


def view(owner="A"):
    return dict(schema="g31.owner_protocol_observation.v1", now=100., owner_id=owner, scope="native owner scope",
        delivered_transfer_acks=[dict(request_id="x", status="dispatching", observed_at=10., delivered_at=12.),
                                 dict(request_id="x", status="failed", observed_at=90., delivered_at=92.)],
        client_transfer_ledger=[dict(request_id="x", status="failed", received_at=-1.)],
        client_commands=[dict(planning_snapshot={"very_large": []})],
        delivered_command_acks=[dict(command_id="command")])


def test_complete_transfer_history_including_failure_and_ledger_remains_identical():
    raw = view()
    subset = transfer_ack_evidence_subset(raw)
    assert subset["delivered_transfer_acks"] is raw["delivered_transfer_acks"]
    assert subset["client_transfer_ledger"] is raw["client_transfer_ledger"]
    assert [row["status"] for row in subset["delivered_transfer_acks"]] == ["dispatching", "failed"]
    assert "client_commands" not in subset and "delivered_command_acks" not in subset
    assert "client_commands" in raw  # The offline source is not mutated.
    assert not subset["evidence_scope"]["complete_owner_protocol_view"]
    assert subset["scope"] == raw["scope"] and subset["now"] == 100.


def test_original_owner_command_histories_released_before_next_observation():
    class History:
        pass
    class Session:
        previous = None
        observed = []
        def observe_protocol(self, owner):
            gc.collect()
            assert self.previous is None or self.previous() is None
            raw = view(owner)
            raw["client_commands"] = History()
            self.previous = weakref.ref(raw["client_commands"])
            self.observed.append(owner)
            return raw
    session = Session()
    retained = collect_transfer_ack_evidence(session, ["A", "B", "C"])
    gc.collect()
    assert session.previous() is None
    assert list(retained) == session.observed == ["A", "B", "C"]
    assert sum(len(row["delivered_transfer_acks"]) for row in retained.values()) == 6


def test_physical_subset_retains_complete_arrays_without_duplicate_copy():
    raw = dict(schema="native", physical_clock=100., advance={}, population={}, jobs=[{}], trays=[{}],
               transfers=[{}], leg_identities=[{}], receipts=[{}], events_processed=5, status="closed",
               owner_protocol_histories={"A": view()})
    subset = terminal_evidence_subset(raw)
    assert "owner_protocol_histories" not in subset
    for key in ("jobs", "trays", "transfers", "leg_identities", "receipts"):
        assert subset[key] is raw[key]
    assert subset["physical_clock"] == raw["physical_clock"]


def test_missing_ack_history_does_not_silently_become_empty():
    raw = view()
    del raw["delivered_transfer_acks"]
    with pytest.raises(ValueError, match="complete_owner_transfer_ack"):
        transfer_ack_evidence_subset(raw)


def test_owner_binding_is_checked():
    class Session:
        def observe_protocol(self, owner):
            return view("wrong-owner")
    with pytest.raises(ValueError, match="transfer_ack_owner_binding"):
        collect_transfer_ack_evidence(Session(), ["A"])


def test_existing_closed_dev_full_export_and_all_request_joins_are_equal():
    """Read-only integration check; never creates a NativeSession or reads TEST."""
    from scripts.experiments.g31_ics_circulation.foundation_airport_transport_evidence import read
    from scripts.experiments.g31_ics_circulation.foundation_airport_pair_dataset import window_cost
    from scripts.experiments.g31_ics_circulation.foundation_airport_service_metrics import physical_progress_intervals
    from scripts.experiments.g31_ics_circulation.foundation_airport_prospective_campaign import indexed_execution
    path = Path(__file__).resolve().parents[1]/"outputs/experiments/g31_ics_action_value_20261020/cycle_001/E_N18_C10_P801_001"
    if not (path/"final_result.json.gz").exists():
        pytest.skip("Historical closed DEV export not present in this checkout")
    assert read(path/"plan.json")["parent"]["split"] == "dev"
    assert read(path/"worker_report.json")["status"] == "complete"
    raw, acks = read(path/"final_result.json.gz"), read(path/"ack_views.json.gz")
    assert raw["physical_clock"] == 59400. and raw["advance"]["horizon_complete"]
    data, calls = read(path/"input.json"), read(path/"client_calls.json.gz")
    compact, ack_subset = terminal_evidence_subset(raw), {owner: transfer_ack_evidence_subset(v) for owner, v in acks.items()}
    assert window_cost(data, raw, start=7200., end=59400.) == window_cost(data, compact, start=7200., end=59400.)
    assert physical_progress_intervals(raw, start=7200., end=59400.) == physical_progress_intervals(compact, start=7200., end=59400.)
    index = [dict(owner_id=c["request"]["owner_id"], observed_at=c["at"], tray_id=c["request"]["tray_id"],
                  chosen_intent=c["request"], decision_differs=False) for c in calls if c["kind"] == "transfer" and not c["retry"]]
    assert index
    assert indexed_execution(index, raw, calls, acks) == indexed_execution(index, compact, calls, ack_subset)
