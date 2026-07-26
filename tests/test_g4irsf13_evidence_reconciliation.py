from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval import g4irsf13_evidence_reconciliation as evidence


ROOT = Path(__file__).resolve().parents[1]


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_frozen_inputs_and_f2_repeats_are_admissible() -> None:
    assert evidence.validate_inputs(ROOT) == []
    rows = evidence._f2_rows(ROOT)
    assert [int(row["repeat_index"]) for row in rows] == [1, 2, 3, 4, 5]
    assert {row["deterministic_result_sha256"] for row in rows} == {
        evidence.EXPECTED_F2_RESULT_SHA256
    }
    assert {row["resource_semantics_echo"] for row in rows} == {
        "R3_java_node_window_compatible"
    }
    assert {row["pibt_mode_echo"] for row in rows} == {"P2"}
    assert {row["case_config_sha256"] for row in rows} == {
        evidence.EXPECTED_F2_CONFIG_SHA256
    }
    assert {row["binary_sha256"] for row in rows} == {
        evidence.EXPECTED_F2_BINARY_SHA256
    }
    assert len({row["evidence_row_binding_sha256"] for row in rows}) == 5


def test_build_is_append_only_and_uses_corrected_denominator() -> None:
    payloads = evidence.build_payloads(ROOT)
    assert set(payloads) == {
        evidence.RECONCILIATION_REPORT,
        evidence.FRESHNESS_TABLE,
        evidence.BASELINE_MANIFEST,
        evidence.F2_POLICY,
        evidence.ANCESTRY_REPORT,
    }
    policy = json.loads(payloads[evidence.F2_POLICY])
    assert policy["metrics"]["original_entry_mean_minutes"] == (
        evidence.EXPECTED_F2_MEAN_MINUTES
    )
    assert policy["metrics"]["delta_vs_v2_safe_seconds"] > 1.13
    assert policy["hard_gates"]["complete_raw_bags"] == 28506
    assert policy["hard_gates"]["runtime_full_astar_calls"] == 0
    manifest = json.loads(payloads[evidence.BASELINE_MANIFEST])
    assert manifest["sealed_artifacts_rewritten"] is False
    assert manifest["g4j_status"] == "CLOSED"


def test_freshness_audit_scopes_supersession() -> None:
    rows = evidence._artifact_rows(ROOT)
    by_domain = {row["evidence_domain"]: row for row in rows}
    assert by_domain["resource_semantics"]["freshness"].startswith("SUPERSEDED")
    assert by_domain["bounded_local_pibt"]["freshness"].startswith("SUPERSEDED")
    assert by_domain["v3_status"]["freshness"] == "PARTIALLY_SUPERSEDED"
    assert by_domain["denominator_reconciliation"]["freshness"] == "CURRENT"
    assert all(row["file_sha256"] for row in rows)


def test_committed_reconciliation_outputs_are_current() -> None:
    assert evidence.validate_committed_outputs(ROOT) == []
    manifest = _object(ROOT / evidence.BASELINE_MANIFEST)
    policy = _object(ROOT / evidence.F2_POLICY)
    assert manifest["frozen_control_policy_sha256"] == policy["policy_sha256"]
    with (ROOT / evidence.FRESHNESS_TABLE).open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
