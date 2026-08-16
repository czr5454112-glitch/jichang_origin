from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import run_g4irsf27_bias_experiments as g27


def test_matrix_is_four_speeds_by_three_levels_with_registered_releases() -> None:
    cases = g27.bias_cases()
    assert len(cases) == 12
    assert len({case["case_id"] for case in cases}) == 12
    assert {
        (case["standard_speed_mps"], case["deviation_percent"])
        for case in cases
    } == {
        (speed, level)
        for speed in g27.STANDARD_SPEEDS_MPS
        for level in g27.DEVIATION_LEVELS_PERCENT
    }
    assert all((g27.ROOT / case["release_csv"]).is_file() for case in cases)
    assert {
        case["release_csv"] for case in cases
    } == {path.relative_to(g27.ROOT).as_posix() for path in g27.SPEED_RELEASE_CSV.values()}


def test_one_seed_one_level_rule_and_nominal_physical_speed_are_frozen() -> None:
    cases = g27.bias_cases()
    assert {case["observation_bias"]["seed"] for case in cases} == {
        g27.FIXED_OBSERVATION_BIAS_SEED
    }
    assert all(
        case["observation_bias"]["maximum_seconds"]
        == case["deviation_percent"] / 10.0
        for case in cases
    )
    assert all(
        case["physical_edge_speed_mps"] == case["standard_speed_mps"]
        and case["route_cost_speed_mps"] == case["standard_speed_mps"]
        for case in cases
    )
    assert {case["queue_discipline"] for case in cases} == {"fifo"}
    assert all(
        not case["observation_bias"]["changes_physical_travel_time"]
        and not case["observation_bias"]["changes_route_cost_speed"]
        for case in cases
    )
    assert g27.manifest_payload()["per_cell_tuning"] is False


def test_bias_plan_carries_only_fixed_seed_and_global_level_mapping() -> None:
    plans = {
        level: g27.ObservationBiasPlan(
            seed=g27.FIXED_OBSERVATION_BIAS_SEED,
            maximum_seconds=g27.observation_bias_max_seconds(level),
        )
        for level in g27.DEVIATION_LEVELS_PERCENT
    }
    assert {plan.seed for plan in plans.values()} == {
        g27.FIXED_OBSERVATION_BIAS_SEED
    }
    assert [plans[level].maximum_seconds for level in (10, 20, 30)] == [
        1.0,
        2.0,
        3.0,
    ]
    assert set(g27.ObservationBiasPlan.__dataclass_fields__) == {
        "seed",
        "maximum_seconds",
    }
    assert all(
        case["observation_bias"]["archived_comparison_pairing"]
        == "UNPAIRED_ARCHIVED_VALUES_NO_SHARED_SEED"
        for case in g27.bias_cases()
    )


def test_archived_values_and_seventeen_raw_completion_traces_are_registered() -> None:
    cases = g27.bias_cases()
    recovered = [
        (case, arm, evidence)
        for case in cases
        for arm, evidence in case["recovered_raw_evidence"].items()
        if evidence["status"] == "RECOVERED_COMPLETION_TRACE"
    ]
    assert len(recovered) == 17
    for case, arm, evidence in recovered:
        assert evidence["row_count"] == 43_603
        assert evidence["raw_bag_count"] == 28_506
        assert abs(
            evidence["mean_total_segment_time_minutes"]
            - case["archived_paper_reported"][arm]
        ) < 0.011

    malformed = g27.case_by_id("t5_4_bias_std_2p5_dev_10")
    assert malformed["recovered_raw_evidence"]["static"]["status"] == (
        "PRESENT_BUT_NOT_COMPLETION_TRACE"
    )
    assert malformed["recovered_raw_evidence"]["static"][
        "observed_column_count"
    ] == 3
    speed_three = [
        case for case in cases if case["standard_speed_mps"] == 3.0
    ]
    assert all(
        evidence["status"] == "SOURCE_FILE_NOT_RETAINED"
        for case in speed_three
        for evidence in case["recovered_raw_evidence"].values()
    )


def test_g26_derating_is_a_separate_stress_not_table_5_4_evidence() -> None:
    manifest = g27.manifest_payload()
    assert manifest["protocol_fidelity"] == "LEGACY_VARIANT_RECONSTRUCTION"
    assert manifest["separate_stress_family"] == {
        "label": "SUSTAINED_PHYSICAL_DERATING_STRESS",
        "source": "G26 speed-deviation cases",
        "counts_as_table_5_4_reconstruction": False,
    }
    assert all(
        case["separate_g26_stress_reference"][
            "counts_as_table_5_4_reconstruction"
        ]
        is False
        for case in manifest["cases"]
    )


class _FakeBiasBackend:
    def __init__(self, mean_minutes: float = 4.0) -> None:
        self.mean_minutes = mean_minutes
        self.calls: list[dict] = []

    def run_case(self, *, case, release_csv: Path, bias_plan):
        self.calls.append(
            {
                "case": case,
                "release_csv": release_csv,
                "seed": bias_plan.seed,
                "maximum_seconds": bias_plan.maximum_seconds,
            }
        )
        return {
            "status": "COMPLETE",
            "tth_mean_minutes": self.mean_minutes,
            "selected_segment_count": 43_603,
            "selected_raw_bag_count": 28_506,
        }


def test_fake_backend_seam_runs_without_native_abi_and_builds_report() -> None:
    backend = _FakeBiasBackend(mean_minutes=4.0)
    case_id = "t5_4_bias_std_2p5_dev_20"
    result = g27.execute_case(case_id, backend=backend)
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call["case"]["physical_edge_speed_mps"] == 2.5
    assert call["release_csv"] == g27.SPEED_RELEASE_CSV[2.5]
    assert call["seed"] == g27.FIXED_OBSERVATION_BIAS_SEED
    assert call["maximum_seconds"] == 2.0
    assert result["protocol_fidelity"] == "LEGACY_VARIANT_RECONSTRUCTION"
    assert result["runtime_protocol"] == {"queue_discipline": "fifo"}
    assert result["comparison"] == {
        "s4_beats_archived_dynamic_mean": True,
        "s4_beats_archived_static_mean": True,
        "comparison_is_exact_protocol_reproduction": False,
    }

    report = g27.build_report([result])
    assert report["verdict"] == "PARTIAL_LEGACY_VARIANT_RECONSTRUCTION"
    assert report["completed_case_count"] == 1
    markdown = g27.render_markdown_report(report)
    assert "LEGACY_VARIANT_RECONSTRUCTION" in markdown
    assert "SUSTAINED_PHYSICAL_DERATING_STRESS" in markdown
    assert "unpaired retained historical values" in markdown
    assert "1/12 admitted case results passed all strict safety gates" in markdown


def test_native_adapter_reuses_nominal_g26_request_and_aggregates_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from czr005 import cpp_backend
    from scripts.eval import g4irsf12_reproducible_harness as harness
    from scripts.eval import run_g4irsf24_native_race as g24
    from scripts.eval import run_g4irsf26_paper_experiments as g26

    prefix = SimpleNamespace(rows=[{"task_id": 1}], raw_bag_count=28_506)
    captured: dict = {}
    monkeypatch.setattr(harness, "load_input_prefix", lambda *args, **kwargs: prefix)
    monkeypatch.setattr(g26, "_full_workload_gate", lambda value: {"pass": True})
    monkeypatch.setattr(
        g24,
        "apply_exact_hca_releases",
        lambda value, release: (
            value,
            {"aligned_segment_count": 43_603, "source": release.name},
        ),
    )
    monkeypatch.setattr(
        g26,
        "case_by_id",
        lambda case_id: {
            "case_id": case_id,
            "standard_speed_mps": 2.5,
            "actual_speed_mps": 2.5,
            "seed_edges": [],
        },
    )

    def fake_request(case, value, *, binary):
        captured["nominal_case"] = dict(case)
        captured["binary"] = binary
        return {"ordinary_request": True}, {"speed": {"actual": 2.5}}

    monkeypatch.setattr(g26, "build_s4_request", fake_request)

    def fake_runtime(**request):
        captured["request"] = dict(request)
        return {
            "summary": {
                "legacy_observation_bias_max_seconds": 2.0,
                "legacy_observation_bias_seed": g27.FIXED_OBSERVATION_BIAS_SEED,
                "legacy_observation_bias_sample_count": 123,
                "legacy_observation_bias_total_seconds": 117.0,
                "legacy_observation_bias_claim_boundary": (
                    "deterministic_local_observation_delay_only"
                ),
            },
            "bags": [{"segment_id": "fixture"}],
        }

    monkeypatch.setattr(
        cpp_backend, "g4irsf11_event_runtime_from_records", fake_runtime
    )
    monkeypatch.setattr(
        g26,
        "summarize_paper_outcome",
        lambda rows, bags: {
            "completed_raw_bag_count": 28_506,
            "paper_raw_bag_tth": {
                "distribution": {
                    "minutes": {
                        "min": 3.0,
                        "p50": 3.7,
                        "mean": 4.0,
                        "p95": 4.8,
                        "p99": 5.0,
                        "max": 5.4,
                    }
                }
            },
        },
    )
    monkeypatch.setattr(
        g24, "_strict_s4_safety", lambda summary, count: {"pass": True}
    )
    monkeypatch.setattr(
        g26,
        "_runtime_echo_gates",
        lambda summary: {"s4": True, "j2": True, "e2": True},
    )

    case = g27.case_by_id("t5_4_bias_std_2p5_dev_20")
    backend = g27._NativeObservationBiasBackend(Path(g27.__file__))
    summary = backend.run_case(
        case=case,
        release_csv=g27.SPEED_RELEASE_CSV[2.5],
        bias_plan=g27.ObservationBiasPlan(
            seed=g27.FIXED_OBSERVATION_BIAS_SEED,
            maximum_seconds=2.0,
        ),
    )
    assert captured["nominal_case"]["standard_speed_mps"] == 2.5
    assert captured["nominal_case"]["actual_speed_mps"] == 2.5
    assert captured["request"]["legacy_observation_bias_max_seconds"] == 2.0
    assert captured["request"]["legacy_observation_bias_seed"] == (
        g27.FIXED_OBSERVATION_BIAS_SEED
    )
    assert captured["request"]["queue_discipline"] == "fifo"
    assert summary["status"] == "COMPLETE"
    assert summary["tth_mean_minutes"] == 4.0
    assert summary["queue_discipline"] == "fifo"
    assert summary["strict_safety"]["pass"] is True
    assert all(summary["observation_bias_echo_gates"].values())


def test_native_execution_fails_clearly_before_run_when_hook_is_absent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loaded_paths: list[Path] = []

    def fake_load(binary: Path) -> SimpleNamespace:
        loaded_paths.append(binary)
        return SimpleNamespace(g4irsf11_event_runtime_from_records=lambda: None)

    monkeypatch.setattr(
        g27,
        "_load_native_module",
        fake_load,
    )
    binary = Path(g27.__file__)
    with pytest.raises(g27.ObservationBiasAbiUnavailable) as raised:
        g27.execute_case(
            "t5_4_bias_std_1p5_dev_10",
            binary=binary,
        )
    message = str(raised.value)
    assert "legacy_observation_bias_max_seconds" in message
    assert "legacy_observation_bias_seed" in message
    assert "No full run was started" in message
    assert loaded_paths == [binary.resolve()]

    exit_code = g27.main(
        [
            "run-case",
            "--case-id",
            "t5_4_bias_std_1p5_dev_10",
            "--binary",
            str(binary),
        ]
    )
    assert exit_code == 2
    assert "No full run was started" in capsys.readouterr().err
    assert loaded_paths == [binary.resolve(), binary.resolve()]


def test_empty_report_remains_not_run_and_does_not_claim_g26_stress() -> None:
    report = g27.build_report([])
    assert report["verdict"] == (
        "NOT_RUN_COMPILED_OBSERVATION_BIAS_ABI_REQUIRED"
    )
    assert report["completed_case_count"] == 0
    assert report["exact_legacy_variant_recovered"] is False
    assert report["separate_stress_family"][
        "counts_as_table_5_4_reconstruction"
    ] is False


def test_report_csv_option_writes_the_same_twelve_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = Path("g27.csv")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        g27,
        "_write_or_print",
        lambda payload, destination: captured.update(
            payload=payload, destination=destination
        ),
    )
    assert g27.main(["report", "--output-csv", str(output)]) == 0
    rows = list(csv.DictReader(str(captured["payload"]).splitlines()))
    assert captured["destination"] == output
    assert len(rows) == 12
    assert tuple(rows[0]) == g27.REPORT_ROW_FIELDS
    assert [row["case_id"] for row in rows] == [
        row["case_id"] for row in g27.build_report([])["rows"]
    ]
