from __future__ import annotations

import csv
import json

from czr005.g4irsf16 import contract_regression as regression
from czr005.policies.g4irsf16_supervisor import (
    ActionKind,
    ActionSource,
    FULL_ASTAR_FALLBACK_ALLOWED,
    G4IRSF16Supervisor,
    SupervisorState,
)


def _by_key(rows: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
    return {(str(row["tier"]), str(row["case_id"])): row for row in rows}


def test_tail_pibt_matrix_covers_t0_t3_and_uses_strict_attribution() -> None:
    rows = regression.build_tail_pibt_rows()
    assert len(rows) == 4 * len(regression.TAIL_CASES) == 32
    assert {str(row["tier"]) for row in rows} == {"T0", "T1", "T2", "T3"}
    assert all(row["contract_pass"] is True for row in rows)
    assert sum(int(row["unsafe_entry_count"]) for row in rows) == 0

    keyed = _by_key(rows)
    t0_rule = keyed[("T0", "local_rule_authorization_veto")]
    assert t0_rule["source"] == ActionSource.I3_MODEL.value
    assert t0_rule["local_rule_veto_applied"] is False

    for tier in ("T1", "T2", "T3"):
        veto = keyed[(tier, "local_rule_authorization_veto")]
        assert veto["supervisor_state"] == SupervisorState.F2_NORMAL.value
        assert veto["source"] == ActionSource.FROZEN_F2.value
        assert veto["local_rule_veto_applied"] is True

    for tier in ("T0", "T1"):
        no_f2 = keyed[(tier, "no_safe_f2")]
        assert no_f2["action"] == ActionKind.SAFE_HOLD.value
        assert no_f2["capability_credited_to_tier"] is False
    assert keyed[("T2", "no_safe_f2")]["capability_credited_to_tier"] is True

    for tier in ("T0", "T1", "T2"):
        blocker = keyed[(tier, "strict_local_blocker")]
        assert blocker["action"] == ActionKind.SAFE_HOLD.value
        assert int(blocker["committed_batch_size"]) == 0
    strict = keyed[("T3", "strict_local_blocker")]
    assert strict["action"] == ActionKind.ATOMIC_ONE_STEP_BATCH.value
    assert strict["source"] == ActionSource.STRICT_LOCAL_PIBT.value
    assert int(strict["prepared_batch_size"]) == 2
    assert int(strict["committed_batch_size"]) == 2
    assert strict["atomic_all_or_none"] is True
    assert strict["second_atomic_consume_rejected"] is True

    guarded = keyed[("T3", "model_abstention_cannot_trigger_pibt")]
    assert guarded["action"] == ActionKind.SAFE_HOLD.value
    assert guarded["source"] == ActionSource.LOCAL_SAFETY.value
    assert int(guarded["committed_batch_size"]) == 0


def test_fault_matrix_covers_required_fault_and_transaction_cases() -> None:
    rows = regression.build_fault_rows()
    assert [str(row["case_id"]) for row in rows] == list(
        regression.REQUIRED_FAULT_CASES
    )
    assert all(row["contract_pass"] is True for row in rows)
    assert sum(int(row["unsafe_entry_count"]) for row in rows) == 0
    assert sum(int(row["used_full_astar_count"]) for row in rows) == 0

    keyed = {str(row["case_id"]): row for row in rows}
    delayed = keyed["delayed_message"]
    assert int(delayed["stale_generation_rejection_count"]) == 2
    assert delayed["old_token_rejected"] is True

    dropped = keyed["dropped_message"]
    assert int(dropped["message_generation_gap"]) == 2
    assert dropped["old_token_rejected"] is True
    assert int(dropped["repair_reentry_count"]) == 1

    for case_id in (
        "dropped_message",
        "repair_reopen",
        "i4_hold_fault",
        "i3_prepare_fault",
        "pibt_transaction_fault",
    ):
        row = keyed[case_id]
        assert row["repair_expected"] is True
        assert row["repair_once"] is True
        assert int(row["repair_reentry_count"]) == 1

    i4 = keyed["i4_hold_fault"]
    assert i4["old_token_rejected"] is True
    assert "opportunity_consumed" in str(i4["event_trace"])

    i3 = keyed["i3_prepare_fault"]
    assert i3["old_token_rejected"] is True
    assert "override_consumed" in str(i3["event_trace"])

    pibt = keyed["pibt_transaction_fault"]
    assert int(pibt["pibt_prepared_batch_size"]) == 2
    assert int(pibt["pibt_aborted_commit_size"]) == 0
    assert int(pibt["pibt_successful_commit_size"]) == 2
    assert pibt["atomic_all_or_none"] is True
    assert pibt["second_atomic_consume_rejected"] is True


def test_summary_enforces_unsafe_stale_repair_atomic_and_no_astar() -> None:
    tail = regression.build_tail_pibt_rows()
    fault = regression.build_fault_rows()
    summary = regression.build_summary(tail, fault)
    assert summary["evaluation_scope"] == (
        "SUPERVISOR_CONTRACT_REGRESSION_NOT_FULL_CLOSED_LOOP_TTH"
    )
    assert summary["overall_pass"] is True
    assert summary["invariants"] == {
        "unsafe_zero": True,
        "stale_action_rejected": True,
        "repair_reentry_once_per_fault_episode": True,
        "pibt_atomic_all_or_none": True,
        "full_astar_forbidden": True,
    }
    assert FULL_ASTAR_FALLBACK_ALLOWED is False
    assert "not a full closed-loop run" in str(summary["disclaimer"])
    assert "not TTH evidence" in str(summary["disclaimer"])


def test_regression_directly_drives_existing_supervisor(
    monkeypatch,
) -> None:
    call_count = 0
    original = G4IRSF16Supervisor.evaluate

    def counted(self, context):
        nonlocal call_count
        call_count += 1
        return original(self, context)

    monkeypatch.setattr(G4IRSF16Supervisor, "evaluate", counted)
    tail = regression.build_tail_pibt_rows()
    fault = regression.build_fault_rows()
    assert call_count >= len(tail) + len(fault)


def test_writer_publishes_deterministic_contract_artifacts(tmp_path) -> None:
    first = regression.write_contract_regression(tmp_path)
    paths = [
        regression.TAIL_TABLE_OUTPUT,
        regression.FAULT_TABLE_OUTPUT,
        regression.TAIL_REPORT_OUTPUT,
        regression.FAULT_REPORT_OUTPUT,
        regression.SUMMARY_OUTPUT,
    ]
    before = {
        path: (tmp_path / path).read_bytes()
        for path in paths
    }
    second = regression.write_contract_regression(tmp_path)
    after = {
        path: (tmp_path / path).read_bytes()
        for path in paths
    }
    assert first == second
    assert before == after

    with (tmp_path / regression.TAIL_TABLE_OUTPUT).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        tail_rows = list(csv.DictReader(handle))
    with (tmp_path / regression.FAULT_TABLE_OUTPUT).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        fault_rows = list(csv.DictReader(handle))
    assert len(tail_rows) == 32
    assert len(fault_rows) == 9
    assert set(tail_rows[0]) == set(regression.TAIL_COLUMNS)
    assert set(fault_rows[0]) == set(regression.FAULT_COLUMNS)

    summary = json.loads(
        (tmp_path / regression.SUMMARY_OUTPUT).read_text(encoding="utf-8")
    )
    assert summary["overall_pass"] is True
    tail_report = (tmp_path / regression.TAIL_REPORT_OUTPUT).read_text(
        encoding="utf-8"
    )
    fault_report = (tmp_path / regression.FAULT_REPORT_OUTPUT).read_text(
        encoding="utf-8"
    )
    assert "**not** a full closed-loop run" in tail_report
    assert "not a native runtime fault campaign" in fault_report
    assert "No tail-performance conclusion" in tail_report
