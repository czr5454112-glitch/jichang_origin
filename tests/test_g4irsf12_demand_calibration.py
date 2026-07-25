from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from scripts.eval import g4irsf12_demand_calibration as demand
from scripts.eval.g4irsf12_demand_calibration import (
    AIRPORT_REPORT_PATH,
    CALIBRATION_INPUTS_PATH,
    CONFIG_PATH,
    EXPECTED_BAGS,
    EXPECTED_DIRECT_BAGS,
    EXPECTED_EARLY_BAGS,
    EXPECTED_SEGMENTS,
    GENERATION_AUDIT_PATH,
    MANIFEST_DIR,
    ROOT,
    SCALE_ENVELOPE_PATH,
    _candidate_rows,
    build_protocol_config,
    check_bundle,
    collect_demand_evidence,
    render_bundle,
)


@pytest.fixture(scope="module")
def demand_evidence() -> dict[str, Any]:
    return collect_demand_evidence(ROOT)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_protected_identity_and_java_conversion_reproduce_exactly(
    demand_evidence: dict[str, Any],
) -> None:
    conversion = demand_evidence["conversion"]
    assert conversion["validation"] == "PASS_EXACT_JAVA_RULE_RECONSTRUCTION"
    assert conversion["raw_bag_count"] == EXPECTED_BAGS
    assert conversion["processed_segment_count"] == EXPECTED_SEGMENTS
    assert conversion["early_split_bag_count"] == EXPECTED_EARLY_BAGS
    assert conversion["direct_bag_count"] == EXPECTED_DIRECT_BAGS
    assert conversion["segments_per_bag"] == pytest.approx(43603 / 28506)

    hashes = demand_evidence["hashes"]
    assert hashes["map_raw_sha256"] == (
        "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
    )
    assert hashes["map_semantic_sha256"] == (
        "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
    )
    assert hashes["processed_input_raw_sha256"] == (
        "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
    )


def test_baseline_demand_covers_rates_mix_deadlines_dwell_and_route_lengths(
    demand_evidence: dict[str, Any],
) -> None:
    observed = demand_evidence["observed"]
    assert observed["average_bags_per_hour_over_24h"] == pytest.approx(1187.75)
    assert sum(row["bag_count"] for row in observed["hourly_profile"]) == EXPECTED_BAGS
    assert observed["rolling_peaks"]["5_minutes"]["bag_count"] == 321
    assert observed["rolling_peaks"]["15_minutes"]["bag_count"] == 847
    assert observed["rolling_peaks"]["60_minutes"]["bag_count"] == 3159

    assert observed["loader_station_counts"] == {
        "A1": 1176,
        "B1": 2872,
        "B2": 5544,
        "C1": 4533,
        "C2": 7542,
        "D1": 2585,
        "T": 4254,
    }
    assert sum(observed["physical_source_node_counts"].values()) == EXPECTED_BAGS
    assert sum(observed["loader_to_unloader_mix"].values()) == EXPECTED_BAGS
    assert sum(observed["physical_node_od_mix"].values()) == EXPECTED_BAGS

    deadline = observed["deadline_lead_seconds"]
    dwell = observed["planned_early_bag_ebs_dwell_seconds"]
    assert deadline["count"] == EXPECTED_BAGS
    assert dwell["count"] == EXPECTED_EARLY_BAGS
    assert deadline["p50"] <= deadline["p95"] <= deadline["p99"]
    assert dwell["min"] >= 2100.0

    route = observed["static_directed_shortest_path_lower_bounds"]
    assert route["unreachable_segment_count"] == 0
    assert route["bag_length_map_units"]["count"] == EXPECTED_BAGS
    assert route["bag_travel_time_seconds"]["mean"] > 0.0
    assert route["bag_hops"]["p99"] >= route["bag_hops"]["p50"]
    assert "not a realized route" in route["scope"]


def test_airport_scope_and_multiplier_fail_closed(
    demand_evidence: dict[str, Any],
) -> None:
    assert demand_evidence["scope"]["airport_identity"] == "UNKNOWN_NOT_ESTABLISHED"
    assert demand_evidence["scope"]["terminal_identity"] == "UNKNOWN_NOT_ESTABLISHED"
    calibration = demand_evidence["calibration"]
    assert calibration["calibrated_multiplier"] is None
    assert calibration["calibrated_multiplier_status"] == "UNKNOWN_NOT_COMPUTABLE"
    assert calibration["finite_uncertainty_interval"] is None
    assert (
        calibration["uncertainty_status"]
        == "UNBOUNDED_MISSING_SCOPE_AND_DESIGN_DAY_INPUTS"
    )
    assert all(
        value is None for value in calibration["required_unknown_inputs"].values()
    )
    assert "represented_system_design_day_checked_bags / 28506" == calibration[
        "final_multiplier_formula"
    ]

    capacity = demand_evidence["capacity_measurement_contract"]
    assert capacity["baseline_active_agent_density"] is None
    assert "AUXILIARY_ONLY" in capacity["mapf_agent_density_role"]
    assert all(value is None for value in capacity["current_runtime_values"].values())


def test_candidate_envelope_is_arithmetic_only_and_never_authorizes_execution(
    demand_evidence: dict[str, Any],
) -> None:
    rows = _candidate_rows(demand_evidence)
    assert [row["target_bag_count_arithmetic_only"] for row in rows] == [
        28506,
        31357,
        34207,
        37058,
        42759,
        57012,
    ]
    assert [
        row["estimated_segment_count_if_baseline_mix_preserved"] for row in rows
    ] == [43603, 47963, 52324, 56684, 65405, 87206]
    assert all(not row["calibrated_real_demand_claim"] for row in rows)
    assert all(not row["candidate_workload_materialized"] for row in rows)
    assert all(not row["runtime_executed"] for row in rows)
    assert all(not row["execution_authorized"] for row in rows)
    assert all(row["phase_l_status"] == "BLOCKED_NOT_RUN" for row in rows)
    assert rows[0]["references_existing_immutable_input"]
    assert not any(row["references_existing_immutable_input"] for row in rows[1:])


def test_protocol_and_manifests_preserve_generation_and_phase_l_boundaries(
    demand_evidence: dict[str, Any],
) -> None:
    protocol = build_protocol_config(demand_evidence)
    assert protocol["execution_policy"] == "DESCRIPTORS_ONLY_NO_SCALING_RUN"
    generation = protocol["future_generation_protocol"]
    assert generation["fixed_seed"] == 20260723
    assert not generation["time_compression"]
    assert generation["retain_each_baseline_bag_once"]
    assert (
        generation["allowed_label_if_materialized_and_audited"]
        == "original_rule_replay_scaled_input"
    )
    assert generation["forbidden_label"] == "original_project_generated"

    gates = protocol["phase_l_gates"]
    assert gates["original_task_generation_audit_pass"]
    assert gates["protected_map_identity_matches"]
    assert not gates["original_1x_full_formal_pass"]
    assert not gates["numeric_real_demand_calibration_complete"]
    assert not gates["traceable_1p1_workload_artifact_exists"]
    assert not gates["all_gates_pass"]
    assert gates["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    phase_j = protocol["phase_j_evidence"]
    assert phase_j["verification_status"] == "VERIFIED_COMPLETE_PERFORMANCE_FAIL"
    assert phase_j["bundle_reconstructed_from_ledger"]
    assert phase_j["full_repeat_completed"]
    assert not phase_j["original_entry_performance_pass"]
    assert not phase_j["original_1x_full_formal_pass"]
    assert phase_j["g4j_status"] == "CLOSED"
    assert not phase_j["g4j_enabled"]
    assert any("performance gates" in blocker for blocker in gates["blockers"])

    for scale_id, kind in (
        ("1p0", "baseline"),
        ("1p1", "candidate"),
        ("1p2", "candidate"),
        ("1p3", "candidate"),
        ("1p5", "candidate"),
        ("2p0", "candidate"),
    ):
        manifest = json.loads(
            (
                ROOT
                / MANIFEST_DIR
                / f"demand_{scale_id}_{kind}_manifest.json"
            ).read_text(encoding="utf-8")
        )
        artifact = manifest["artifact_state"]
        assert not artifact["candidate_workload_materialized"]
        assert not artifact["runtime_executed"]
        assert not artifact["execution_authorized"]
        assert artifact["task_output_path"] is None
        assert artifact["result_output_path"] is None
        assert manifest["forbidden_label"] == "original_project_generated"
        assert not manifest["calibrated_real_demand_claim"]
        assert all(value is None for value in manifest["runtime_metrics"].values())


def test_phase_j_binding_rejects_a_bundle_not_reconstructed_from_its_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provenance = {
        "binary_path": "C:/fixture/czr005_cpp.pyd",
        "binary_sha256": "a" * 64,
        "source_bundle_sha256": "b" * 64,
        "source_path_manifest_sha256": "c" * 64,
        "executor_id": "fixture:executor",
        "executor_source_sha256": "d" * 64,
    }
    bundle: dict[str, Any] = {
        "schema": demand.CANDIDATE_BUNDLE_SCHEMA,
        "g4j_enabled": False,
        "g4j_status": "CLOSED",
        "primary_denominator": "original_entry_time_tth",
        "current_provenance_status": "VERIFIED",
        "current_provenance": provenance,
        "finalists": [
            {
                "candidate_id": "J_F1",
                "executed_full_repeat_count": 5,
                "repeat_gate": "PASS",
                "v2_safe_original_entry_gate": "FAIL",
                "corrected_hca_original_entry_gate": "FAIL",
                "validated_full_gate": "FAIL",
                "promotion_status": "PENDING",
            }
        ],
    }
    bundle["bundle_sha256"] = demand._canonical_sha256(bundle)
    bundle_path = tmp_path / demand.PHASE_J_BUNDLE_PATH
    ledger_path = tmp_path / demand.PHASE_J_LEDGER_PATH
    bundle_path.parent.mkdir(parents=True)
    ledger_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    ledger_path.write_text("fixture-ledger\n", encoding="utf-8")
    monkeypatch.setattr(demand, "load_result_ledger", lambda *args, **kwargs: [{}])
    monkeypatch.setattr(
        demand,
        "rebuild_phase_j_candidate_bundle",
        lambda *args, **kwargs: dict(bundle),
    )

    verified = demand._phase_j_evidence(tmp_path)

    assert verified["verification_status"] == "VERIFIED_COMPLETE_PERFORMANCE_FAIL"
    assert verified["bundle_reconstructed_from_ledger"]
    assert verified["full_repeat_completed"]
    assert not verified["original_entry_performance_pass"]
    assert not verified["original_1x_full_formal_pass"]

    tampered = dict(bundle)
    tampered["finalists"] = [dict(bundle["finalists"][0], repeat_gate="PENDING")]
    tampered["bundle_sha256"] = demand._canonical_sha256(
        {key: value for key, value in tampered.items() if key != "bundle_sha256"}
    )
    bundle_path.write_text(json.dumps(tampered), encoding="utf-8")

    rejected = demand._phase_j_evidence(tmp_path)

    assert rejected["verification_status"] == "UNVERIFIED"
    assert not rejected["bundle_reconstructed_from_ledger"]
    assert not rejected["original_entry_performance_pass"]
    assert not rejected["original_1x_full_formal_pass"]
    assert any("does not exactly reconstruct" in blocker for blocker in rejected["blockers"])


def test_external_method_sources_are_primary_or_official(
    demand_evidence: dict[str, Any],
) -> None:
    allowed_hosts = {
        "www.caac.gov.cn",
        "nap.nationalacademies.org",
        "www.iata.org",
        "www.ifaamas.org",
        "ojs.aaai.org",
    }
    sources = demand_evidence["external_sources"]
    assert len(sources) >= 6
    assert {urlparse(source["url"]).hostname for source in sources} <= allowed_hosts
    assert all(source["url"].startswith("https://") for source in sources)


def test_committed_bundle_is_complete_deterministic_and_explicit(
    demand_evidence: dict[str, Any],
) -> None:
    outputs = render_bundle(demand_evidence)
    assert len(outputs) == 11
    check_bundle(ROOT, outputs)

    assert (ROOT / CONFIG_PATH).exists()
    calibration_rows = _read_csv(ROOT / CALIBRATION_INPUTS_PATH)
    multiplier = next(
        row for row in calibration_rows if row["field"] == "calibrated_multiplier"
    )
    assert multiplier["status"] == "UNKNOWN_NOT_COMPUTABLE"
    assert multiplier["value"] == ""

    scale_rows = _read_csv(ROOT / SCALE_ENVELOPE_PATH)
    assert len(scale_rows) == 6
    assert all(row["phase_l_status"] == "BLOCKED_NOT_RUN" for row in scale_rows)
    assert all(row["runtime_executed"] == "false" for row in scale_rows)

    airport_report = (ROOT / AIRPORT_REPORT_PATH).read_text(encoding="utf-8")
    generation_report = (ROOT / GENERATION_AUDIT_PATH).read_text(encoding="utf-8")
    assert "`UNKNOWN_NOT_COMPUTABLE`" in airport_report
    assert "No scale runtime was started." in airport_report
    assert "standard design-day" in airport_report
    assert "`PASS_WITH_NEGATIVE_GENERATOR_FINDING`" in generation_report
    assert "`original_project_generated`" in generation_report
    assert "does **not** contain an active larger-day demand generator" in (
        generation_report
    )
