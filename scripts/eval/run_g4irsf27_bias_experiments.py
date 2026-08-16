#!/usr/bin/env python3
"""Minimal G27 reconstruction scaffold for thesis Table 5.4.

The surviving legacy evidence does not support treating Table 5.4 as an
all-edge, all-day physical speed reduction.  This module therefore freezes a
small *observation-delay* reconstruction instead:

* physical travel and route-cost speed both remain at the registered standard
  speed;
* the deviation level selects one global ``U(0, k seconds)`` observation-delay
  rule, where ``k = deviation_percent / 10``;
* every cell uses the same seed and there is no per-cell tuning; and
* execution is impossible until the native runtime exposes the two append-only
  ABI arguments named below.  Tests use the narrow injected-backend seam only.

The result is deliberately labelled ``LEGACY_VARIANT_RECONSTRUCTION``.  G26's
whole-network physical derating remains available as a separate stress test,
but it is not evidence for this reconstructed Table 5.4 protocol.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import inspect
import io
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Protocol, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))


MANIFEST_SCHEMA = "czr005.g4irsf27.bias_manifest.v1"
CASE_RESULT_SCHEMA = "czr005.g4irsf27.bias_case_result.v1"
REPORT_SCHEMA = "czr005.g4irsf27.bias_report.v1"
REPORT_ROW_FIELDS = (
    "case_id",
    "standard_speed_mps",
    "deviation_percent",
    "archived_dynamic_minutes",
    "archived_static_minutes",
    "s4_minutes",
    "s4_beats_archived_dynamic_mean",
    "status",
)

PROTOCOL_LABEL = "LEGACY_VARIANT_RECONSTRUCTION"
DERATING_STRESS_LABEL = "SUSTAINED_PHYSICAL_DERATING_STRESS"
NATIVE_ABI_ARGUMENTS = (
    "legacy_observation_bias_max_seconds",
    "legacy_observation_bias_seed",
)

PAPER_DAY_SEGMENTS = 43_603
PAPER_DAY_RAW_BAGS = 28_506
FIXED_OBSERVATION_BIAS_SEED = 20_260_816
ACTIVE_QUEUE_DISCIPLINE = "fifo"
STANDARD_SPEEDS_MPS = (1.5, 2.0, 2.5, 3.0)
DEVIATION_LEVELS_PERCENT = (10, 20, 30)

SPEED_RELEASE_CSV: Mapping[float, Path] = {
    1.5: ROOT / "artifacts/datasets/g4irsf26_release_speed_1p5.csv",
    2.0: ROOT / "artifacts/datasets/g4irsf26_release_speed_2p0.csv",
    2.5: ROOT / "artifacts/datasets/g4irsf24_release_compact.csv",
    3.0: ROOT / "artifacts/datasets/g4irsf26_release_speed_3p0.csv",
}

# Values transcribed from thesis Table 5.4.  Times are minutes per original
# bag, where multi-segment bag times are summed before taking the mean.
ARCHIVED_TABLE_5_4: Mapping[tuple[float, int], Mapping[str, float]] = {
    (1.5, 10): {"dynamic": 6.45, "static": 6.59, "improvement": 2.12},
    (1.5, 20): {"dynamic": 6.67, "static": 6.86, "improvement": 2.77},
    (1.5, 30): {"dynamic": 6.91, "static": 7.11, "improvement": 2.81},
    (2.0, 10): {"dynamic": 4.92, "static": 5.07, "improvement": 2.96},
    (2.0, 20): {"dynamic": 5.16, "static": 5.36, "improvement": 3.73},
    (2.0, 30): {"dynamic": 5.42, "static": 5.62, "improvement": 3.56},
    (2.5, 10): {"dynamic": 3.99, "static": 4.19, "improvement": 4.77},
    (2.5, 20): {"dynamic": 4.25, "static": 4.46, "improvement": 4.71},
    (2.5, 30): {"dynamic": 4.49, "static": 4.72, "improvement": 4.87},
    (3.0, 10): {"dynamic": 3.39, "static": 3.56, "improvement": 4.78},
    (3.0, 20): {"dynamic": 3.51, "static": 3.72, "improvement": 5.65},
    (3.0, 30): {"dynamic": 3.64, "static": 3.87, "improvement": 5.94},
}

# Means recovered from the retained four-column legacy completion traces.
# Suffix 0 is the archived dynamic arm and suffix 1 is the static arm.  The
# formula is mean_bag(sum_segment(end_time - start_time)) / 60.
_RECOVERED_RAW_MEAN_MINUTES: Mapping[tuple[float, int, str], float] = {
    (1.5, 10, "dynamic"): 6.444986435604201,
    (1.5, 10, "static"): 6.5907598400336775,
    (1.5, 20, "dynamic"): 6.669873009191048,
    (1.5, 20, "static"): 6.857323019715148,
    (1.5, 30, "dynamic"): 6.917944760167449,
    (1.5, 30, "static"): 7.111498748801422,
    (2.0, 10, "dynamic"): 4.922692883369582,
    (2.0, 10, "static"): 5.072849575527958,
    (2.0, 20, "dynamic"): 5.1653447227484275,
    (2.0, 20, "static"): 5.3595582216609365,
    (2.0, 30, "dynamic"): 5.419780046306041,
    (2.0, 30, "static"): 5.62078042049627,
    (2.5, 10, "dynamic"): 3.9960131200449025,
    (2.5, 20, "dynamic"): 4.251424846231203,
    (2.5, 20, "static"): 4.459347154984915,
    (2.5, 30, "dynamic"): 4.495626651699057,
    (2.5, 30, "static"): 4.715569236885802,
}


class ObservationBiasAbiUnavailable(RuntimeError):
    """Raised before simulation when the G27 ABI arguments are unavailable."""


@dataclass(frozen=True)
class ObservationBiasPlan:
    """Immutable parameters for the native deterministic S4 delay stream."""

    seed: int
    maximum_seconds: float


class ObservationBiasBackend(Protocol):
    """Narrow seam implemented by the future ABI adapter and fake tests."""

    def run_case(
        self,
        *,
        case: Mapping[str, Any],
        release_csv: Path,
        bias_plan: ObservationBiasPlan,
    ) -> Mapping[str, Any]:
        """Run one complete S4 case and return its compact summary."""


def _speed_label(speed_mps: float) -> str:
    return f"{speed_mps:g}".replace(".", "p")


def _relative_release(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def observation_bias_max_seconds(deviation_percent: int) -> float:
    """Apply the one global inferred mapping; this is not a fitted cell value."""

    if deviation_percent not in DEVIATION_LEVELS_PERCENT:
        raise ValueError(
            f"unsupported deviation level {deviation_percent}; expected "
            f"one of {DEVIATION_LEVELS_PERCENT}"
        )
    return deviation_percent / 10.0


def recovered_raw_evidence(
    standard_speed_mps: float, deviation_percent: int
) -> dict[str, dict[str, Any]]:
    """Return retained trace evidence, including explicit evidence gaps."""

    evidence: dict[str, dict[str, Any]] = {}
    for arm, suffix in (("dynamic", 0), ("static", 1)):
        filename = f"{standard_speed_mps:.1f} {deviation_percent} {suffix}.txt"
        recovered = _RECOVERED_RAW_MEAN_MINUTES.get(
            (standard_speed_mps, deviation_percent, arm)
        )
        if recovered is not None:
            evidence[arm] = {
                "status": "RECOVERED_COMPLETION_TRACE",
                "source_collection": "legacy_仿真数据2",
                "filename": filename,
                "row_count": PAPER_DAY_SEGMENTS,
                "raw_bag_count": PAPER_DAY_RAW_BAGS,
                "mean_total_segment_time_minutes": recovered,
            }
        elif standard_speed_mps == 2.5 and deviation_percent == 10 and arm == "static":
            evidence[arm] = {
                "status": "PRESENT_BUT_NOT_COMPLETION_TRACE",
                "source_collection": "legacy_仿真数据2",
                "filename": filename,
                "row_count": PAPER_DAY_SEGMENTS,
                "observed_column_count": 3,
                "reason": "file contains a start/input trace, not end-time results",
            }
        else:
            evidence[arm] = {
                "status": "SOURCE_FILE_NOT_RETAINED",
                "source_collection": "legacy_仿真数据2",
                "filename": filename,
                "reason": "no retained 3.0 m/s completion trace was found",
            }
    return evidence


def bias_cases() -> list[dict[str, Any]]:
    """Return the frozen 4-speed x 3-level reconstruction matrix."""

    cases: list[dict[str, Any]] = []
    for standard_speed_mps in STANDARD_SPEEDS_MPS:
        release_csv = SPEED_RELEASE_CSV[standard_speed_mps]
        for deviation_percent in DEVIATION_LEVELS_PERCENT:
            g26_case_id = (
                f"t5_4_std_{_speed_label(standard_speed_mps)}_dev_"
                f"{deviation_percent}"
            )
            cases.append(
                {
                    "case_id": (
                        f"t5_4_bias_std_{_speed_label(standard_speed_mps)}_"
                        f"dev_{deviation_percent}"
                    ),
                    "paper_table": "5.4",
                    "protocol_fidelity": PROTOCOL_LABEL,
                    "standard_speed_mps": standard_speed_mps,
                    "physical_edge_speed_mps": standard_speed_mps,
                    "route_cost_speed_mps": standard_speed_mps,
                    "queue_discipline": ACTIVE_QUEUE_DISCIPLINE,
                    "deviation_percent": deviation_percent,
                    "release_csv": _relative_release(release_csv),
                    "release_registration": "G26_SPEED_SPECIFIC_EXACT_RELEASE",
                    "selected_segment_count": PAPER_DAY_SEGMENTS,
                    "selected_raw_bag_count": PAPER_DAY_RAW_BAGS,
                    "observation_bias": {
                        "seed": FIXED_OBSERVATION_BIAS_SEED,
                        "distribution": "uniform_0_to_k_seconds",
                        "maximum_seconds": observation_bias_max_seconds(
                            deviation_percent
                        ),
                        "level_mapping": "k_seconds=deviation_percent/10",
                        "level_mapping_evidence": (
                            "INFERRED_FROM_SURVIVING_LEGACY_BIAS_TIME_CODE"
                        ),
                        "target": (
                            "position_observation_and_conflict_prediction_time"
                        ),
                        "changes_physical_travel_time": False,
                        "changes_route_cost_speed": False,
                        "runtime_stream": "FIXED_REPRODUCIBLE_S4_STREAM",
                        "archived_comparison_pairing": (
                            "UNPAIRED_ARCHIVED_VALUES_NO_SHARED_SEED"
                        ),
                    },
                    "archived_paper_reported": dict(
                        ARCHIVED_TABLE_5_4[
                            (standard_speed_mps, deviation_percent)
                        ]
                    ),
                    "recovered_raw_evidence": recovered_raw_evidence(
                        standard_speed_mps, deviation_percent
                    ),
                    "separate_g26_stress_reference": {
                        "label": DERATING_STRESS_LABEL,
                        "g26_case_id": g26_case_id,
                        "changes_physical_travel_time": True,
                        "counts_as_table_5_4_reconstruction": False,
                    },
                }
            )
    return cases


def case_by_id(case_id: str) -> dict[str, Any]:
    for case in bias_cases():
        if case["case_id"] == case_id:
            return case
    raise KeyError(f"unknown G27 bias case: {case_id}")


def manifest_payload() -> dict[str, Any]:
    cases = bias_cases()
    return {
        "schema": MANIFEST_SCHEMA,
        "protocol_fidelity": PROTOCOL_LABEL,
        "case_count": len(cases),
        "fixed_seed": FIXED_OBSERVATION_BIAS_SEED,
        "per_cell_tuning": False,
        "native_abi_arguments_required": list(NATIVE_ABI_ARGUMENTS),
        "native_runtime_entrypoint": "g4irsf11_event_runtime_from_records",
        "execution_status": "RUN_ONLY_WITH_COMPILED_OBSERVATION_BIAS_ABI",
        "claim_boundary": (
            "results are a legacy-variant reconstruction, not exact recovery "
            "of the missing 2021 simulator variant"
        ),
        "raw_recovery_formula": (
            "mean_bag(sum_segment(end_time-start_time))/60"
        ),
        "cases": cases,
        "separate_stress_family": {
            "label": DERATING_STRESS_LABEL,
            "source": "G26 speed-deviation cases",
            "counts_as_table_5_4_reconstruction": False,
        },
    }


def _load_native_module(binary: Path) -> Any:
    from scripts.eval import g4irsf15_causal_campaign as g15

    return g15._load_exact_module(binary.resolve(strict=True))


class _NativeObservationBiasBackend:
    def __init__(
        self,
        binary: Path,
        *,
        service_aware_potential: bool = False,
    ) -> None:
        self._binary = binary
        self._service_aware_potential = service_aware_potential

    def run_case(
        self,
        *,
        case: Mapping[str, Any],
        release_csv: Path,
        bias_plan: ObservationBiasPlan,
    ) -> Mapping[str, Any]:
        # Reuse the exact G26/G24 request path.  The observation-delay pair is
        # the only runtime delta; the explicit G28 option changes only the
        # precomputed heuristic matrix.  Both graph speeds stay nominal.
        from czr005 import cpp_backend
        from scripts.eval import g4irsf12_reproducible_harness as harness
        from scripts.eval import run_g4irsf24_native_race as g24
        from scripts.eval import run_g4irsf26_paper_experiments as g26

        canonical = harness.load_input_prefix(harness.FULL_SIZE_SEGMENTS, root=ROOT)
        g26._full_workload_gate(canonical)
        prefix, alignment = g24.apply_exact_hca_releases(canonical, release_csv)
        if int(alignment.get("aligned_segment_count", -1)) != PAPER_DAY_SEGMENTS:
            raise ValueError("exact release alignment did not cover 43,603 segments")

        speed = float(case["standard_speed_mps"])
        nominal_case = g26.case_by_id(f"t5_2_speed_{_speed_label(speed)}")
        request, reconstruction = g26.build_s4_request(
            nominal_case,
            prefix,
            binary=self._binary,
        )
        potential_contract: Mapping[str, Any] | None = None
        if self._service_aware_potential:
            from scripts.eval import run_g4irsf28_service_potential as g28

            request, potential_contract = g28.apply_service_aware_potential(request)
        request.update(
            scenario=(
                f"g4irsf28_{case['case_id']}"
                if potential_contract is not None
                else f"g4irsf27_{case['case_id']}"
            ),
            queue_discipline=ACTIVE_QUEUE_DISCIPLINE,
            legacy_observation_bias_max_seconds=bias_plan.maximum_seconds,
            legacy_observation_bias_seed=bias_plan.seed,
        )
        wall_started = time.perf_counter()
        payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
        wall_seconds = time.perf_counter() - wall_started
        if not isinstance(payload, Mapping):
            raise ValueError("native S4 result is not an object")
        summary = payload.get("summary")
        bags = payload.get("bags")
        if not isinstance(summary, Mapping) or not isinstance(bags, list):
            raise ValueError("native S4 result lacks summary or bag rows")
        if any(not isinstance(row, Mapping) for row in bags):
            raise ValueError("native S4 bag payload contains a non-object")

        outcome = g26.summarize_paper_outcome(prefix.rows, bags)
        strict_safety = g24._strict_s4_safety(summary, PAPER_DAY_SEGMENTS)
        runtime_echo_gates = g26._runtime_echo_gates(summary)

        maximum_echo = summary.get("legacy_observation_bias_max_seconds")
        seed_echo = summary.get("legacy_observation_bias_seed")
        sample_count = summary.get("legacy_observation_bias_sample_count")
        total_seconds = summary.get("legacy_observation_bias_total_seconds")
        bias_echo_gates = {
            "maximum_seconds_echo": (
                isinstance(maximum_echo, (int, float))
                and not isinstance(maximum_echo, bool)
                and math.isclose(
                    float(maximum_echo),
                    bias_plan.maximum_seconds,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ),
            "seed_echo": seed_echo == bias_plan.seed,
            "sample_count_positive": (
                isinstance(sample_count, int)
                and not isinstance(sample_count, bool)
                and sample_count > 0
            ),
            "total_seconds_nonnegative": (
                isinstance(total_seconds, (int, float))
                and not isinstance(total_seconds, bool)
                and math.isfinite(float(total_seconds))
                and float(total_seconds) >= 0.0
            ),
            "claim_boundary_echo": summary.get(
                "legacy_observation_bias_claim_boundary"
            )
            == "deterministic_local_observation_delay_only",
        }
        admitted = (
            bool(strict_safety.get("pass"))
            and all(runtime_echo_gates.values())
            and all(bias_echo_gates.values())
        )
        minutes = outcome["paper_raw_bag_tth"]["distribution"]["minutes"]
        result = {
            "status": "COMPLETE" if admitted else "FAILED_STRICT_S4_GATE",
            "tth_mean_minutes": minutes["mean"],
            "tth_distribution_minutes": dict(minutes),
            "selected_segment_count": PAPER_DAY_SEGMENTS,
            "selected_raw_bag_count": PAPER_DAY_RAW_BAGS,
            "completed_raw_bag_count": outcome["completed_raw_bag_count"],
            "queue_discipline": ACTIVE_QUEUE_DISCIPLINE,
            "strict_safety": strict_safety,
            "runtime_echo_gates": runtime_echo_gates,
            "observation_bias_echo_gates": bias_echo_gates,
            "observation_bias_runtime": {
                "maximum_seconds": maximum_echo,
                "seed": seed_echo,
                "sample_count": sample_count,
                "total_seconds": total_seconds,
                "claim_boundary": summary.get(
                    "legacy_observation_bias_claim_boundary"
                ),
            },
            "exact_release_alignment": alignment,
            "nominal_speed_reconstruction": reconstruction,
            "native_wall_seconds": wall_seconds,
        }
        if potential_contract is not None:
            result["service_aware_potential"] = {
                "enabled": True,
                "change_scope": "heuristic_time_only",
                "contract": dict(potential_contract),
            }
        return result


def native_backend_or_raise(
    binary: Path,
    *,
    service_aware_potential: bool = False,
) -> ObservationBiasBackend:
    """Verify the append-only ABI pair, failing before simulation starts."""

    from czr005 import cpp_backend

    resolved_binary = binary.resolve(strict=True)
    wrapper_parameters = inspect.signature(
        cpp_backend.g4irsf11_event_runtime_from_records
    ).parameters
    missing_wrapper = [
        name for name in NATIVE_ABI_ARGUMENTS if name not in wrapper_parameters
    ]
    if missing_wrapper:
        raise ObservationBiasAbiUnavailable(
            "G27 requires append-only event-runtime arguments "
            f"{', '.join(missing_wrapper)}; the Python wrapper lacks them. "
            "No full run was started."
        )

    try:
        native_module = _load_native_module(resolved_binary)
    except Exception as exc:
        raise ObservationBiasAbiUnavailable(
            "G27 requires the observation-bias event-runtime ABI, but the "
            "native backend could not be loaded. No full run was started."
        ) from exc
    native_entrypoint = getattr(
        native_module, "g4irsf11_event_runtime_from_records", None
    )
    documentation = str(getattr(native_entrypoint, "__doc__", ""))
    missing_native = [
        name for name in NATIVE_ABI_ARGUMENTS if name not in documentation
    ]
    if not callable(native_entrypoint) or missing_native:
        raise ObservationBiasAbiUnavailable(
            "G27 requires compiled event-runtime arguments "
            f"{', '.join(missing_native or NATIVE_ABI_ARGUMENTS)}; this build "
            "does not expose them. No full run was started."
        )
    return _NativeObservationBiasBackend(
        resolved_binary,
        service_aware_potential=service_aware_potential,
    )


def _validate_backend_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    if normalized.get("status") not in {"COMPLETE", "FAILED_STRICT_S4_GATE"}:
        raise ValueError(
            "observation-bias backend status must be COMPLETE or "
            "FAILED_STRICT_S4_GATE"
        )
    mean_minutes = normalized.get("tth_mean_minutes")
    if isinstance(mean_minutes, bool) or not isinstance(mean_minutes, (int, float)):
        raise ValueError("observation-bias backend must return numeric tth_mean_minutes")
    if float(mean_minutes) < 0.0:
        raise ValueError("tth_mean_minutes must be non-negative")
    normalized["tth_mean_minutes"] = float(mean_minutes)
    return normalized


def execute_case(
    case_id: str,
    backend: ObservationBiasBackend | None = None,
    *,
    binary: Path | None = None,
    service_aware_potential: bool = False,
) -> dict[str, Any]:
    """Run one case, optionally replacing only its static local potential."""

    case = case_by_id(case_id)
    release_csv = ROOT / case["release_csv"]
    if not release_csv.is_file():
        raise FileNotFoundError(
            f"registered speed-specific release is missing: {release_csv}"
        )
    if backend is None and binary is None:
        raise ValueError("binary is required for native G27 execution")
    selected_backend = (
        backend
        if backend is not None
        else native_backend_or_raise(
            binary,
            service_aware_potential=service_aware_potential,
        )
    )
    run_case = getattr(selected_backend, "run_case", None)
    if not callable(run_case):
        raise TypeError("observation-bias backend must provide run_case(...)")
    bias = case["observation_bias"]
    plan = ObservationBiasPlan(
        seed=int(bias["seed"]),
        maximum_seconds=float(bias["maximum_seconds"]),
    )
    summary = _validate_backend_summary(
        run_case(case=case, release_csv=release_csv, bias_plan=plan)
    )
    potential_evidence = summary.get("service_aware_potential")
    if service_aware_potential and not isinstance(potential_evidence, Mapping):
        raise ValueError(
            "service-aware bias execution must return its potential contract"
        )
    archived = case["archived_paper_reported"]
    current_mean = summary["tth_mean_minutes"]
    admitted = summary["status"] == "COMPLETE"
    runtime_protocol: dict[str, Any] = {
        "queue_discipline": case["queue_discipline"],
    }
    if isinstance(potential_evidence, Mapping):
        runtime_protocol["service_aware_potential"] = dict(potential_evidence)
    return {
        "schema": CASE_RESULT_SCHEMA,
        "case_id": case_id,
        "status": summary["status"],
        "protocol_fidelity": PROTOCOL_LABEL,
        "standard_speed_mps": case["standard_speed_mps"],
        "physical_edge_speed_mps": case["physical_edge_speed_mps"],
        "deviation_percent": case["deviation_percent"],
        "release_csv": case["release_csv"],
        "runtime_protocol": runtime_protocol,
        "observation_bias": dict(bias),
        "archived_paper_reported": dict(archived),
        "recovered_raw_evidence": case["recovered_raw_evidence"],
        "runtime_summary": summary,
        "comparison": {
            "s4_beats_archived_dynamic_mean": (
                current_mean < archived["dynamic"] if admitted else None
            ),
            "s4_beats_archived_static_mean": (
                current_mean < archived["static"] if admitted else None
            ),
            "comparison_is_exact_protocol_reproduction": False,
        },
        "separate_g26_stress_reference": case["separate_g26_stress_reference"],
    }


def build_report(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a compact 12-row report without merging G26 stress evidence."""

    by_case: dict[str, Mapping[str, Any]] = {}
    for result in results:
        case_id = result.get("case_id")
        if not isinstance(case_id, str):
            raise ValueError("each result must have a string case_id")
        if case_id in by_case:
            raise ValueError(f"duplicate result for {case_id}")
        case_by_id(case_id)
        by_case[case_id] = result

    rows: list[dict[str, Any]] = []
    for case in bias_cases():
        result = by_case.get(case["case_id"])
        runtime_summary = result.get("runtime_summary") if result else None
        comparison = result.get("comparison") if result else None
        result_status = result.get("status") if result else "NOT_RUN"
        rows.append(
            {
                "case_id": case["case_id"],
                "standard_speed_mps": case["standard_speed_mps"],
                "deviation_percent": case["deviation_percent"],
                "archived_dynamic_minutes": case["archived_paper_reported"][
                    "dynamic"
                ],
                "archived_static_minutes": case["archived_paper_reported"][
                    "static"
                ],
                "s4_minutes": (
                    runtime_summary.get("tth_mean_minutes")
                    if isinstance(runtime_summary, Mapping)
                    else None
                ),
                "s4_beats_archived_dynamic_mean": (
                    comparison.get("s4_beats_archived_dynamic_mean")
                    if isinstance(comparison, Mapping)
                    else None
                ),
                "status": result_status,
            }
        )

    completed = [row for row in rows if row["status"] == "COMPLETE"]
    failed = [row for row in rows if row["status"] == "FAILED_STRICT_S4_GATE"]
    if not by_case:
        verdict = "NOT_RUN_COMPILED_OBSERVATION_BIAS_ABI_REQUIRED"
    elif failed:
        verdict = "PARTIAL_OR_FAILED_LEGACY_VARIANT_RECONSTRUCTION"
    elif len(completed) < len(rows):
        verdict = "PARTIAL_LEGACY_VARIANT_RECONSTRUCTION"
    elif all(row["s4_beats_archived_dynamic_mean"] for row in completed):
        verdict = "ALL_12_BEAT_ARCHIVED_DYNAMIC_UNDER_RECONSTRUCTION"
    else:
        verdict = "RECONSTRUCTION_COMPLETE_NOT_ALL_12_BEAT_ARCHIVED_DYNAMIC"
    return {
        "schema": REPORT_SCHEMA,
        "protocol_fidelity": PROTOCOL_LABEL,
        "verdict": verdict,
        "completed_case_count": len(completed),
        "failed_case_count": len(failed),
        "expected_case_count": len(rows),
        "exact_legacy_variant_recovered": False,
        "rows": rows,
        "separate_stress_family": {
            "label": DERATING_STRESS_LABEL,
            "counts_as_table_5_4_reconstruction": False,
        },
    }


def render_markdown_report(report: Mapping[str, Any]) -> str:
    """Render the compact report with the evidence boundary up front."""

    lines = [
        "# G27 Table 5.4 observation-bias reconstruction",
        "",
        f"- Protocol: `{report['protocol_fidelity']}`",
        f"- Verdict: `{report['verdict']}`",
        "- Exact missing legacy simulator recovered: `false`",
        (
            "- Archived comparator: unpaired retained historical values; "
            "it does not share the G27 S4 seed."
        ),
        (
            f"- Strict safety: {report['completed_case_count']}/"
            f"{report['expected_case_count']} admitted case results passed "
            "all strict safety gates."
        ),
        (
            "- G26 all-edge physical derating remains a separate "
            f"`{DERATING_STRESS_LABEL}` experiment."
        ),
        "",
        "| speed | level | archived dynamic | archived static | S4 | beats dynamic | status |",
        "|---:|---:|---:|---:|---:|:---:|:---|",
    ]
    for row in report["rows"]:
        s4_value = row["s4_minutes"]
        s4_text = "—" if s4_value is None else f"{float(s4_value):.4f}"
        beats = row["s4_beats_archived_dynamic_mean"]
        beats_text = "—" if beats is None else ("yes" if beats else "no")
        lines.append(
            "| {speed:g} | {level} | {dynamic:.2f} | {static:.2f} | "
            "{s4} | {beats} | {status} |".format(
                speed=row["standard_speed_mps"],
                level=row["deviation_percent"],
                dynamic=row["archived_dynamic_minutes"],
                static=row["archived_static_minutes"],
                s4=s4_text,
                beats=beats_text,
                status=row["status"],
            )
        )
    return "\n".join(lines) + "\n"


def render_csv_report(report: Mapping[str, Any]) -> str:
    """Render the same compact report rows as CSV."""

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=REPORT_ROW_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(report["rows"])
    return stream.getvalue()


def _write_or_print(payload: str, output: Path | None) -> None:
    if output is None:
        print(payload, end="" if payload.endswith("\n") else "\n")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    manifest_parser = commands.add_parser("manifest", help="print the frozen plan")
    manifest_parser.add_argument("--output", type=Path)

    run_parser = commands.add_parser(
        "run-case", help="run one case only when the compiled bias ABI exists"
    )
    run_parser.add_argument("--case-id", required=True)
    run_parser.add_argument("--binary", required=True, type=Path)
    run_parser.add_argument("--output", type=Path)
    run_parser.add_argument(
        "--service-aware-potential",
        action="store_true",
        help=(
            "replace only heuristic_time with the G28 service-aware static "
            "local potential"
        ),
    )

    report_parser = commands.add_parser("report", help="render saved case results")
    report_parser.add_argument("--result", action="append", type=Path, default=[])
    report_parser.add_argument("--output-json", type=Path)
    report_parser.add_argument("--output-csv", type=Path)
    report_parser.add_argument("--output-markdown", type=Path)

    args = parser.parse_args(argv)
    if args.command == "manifest":
        _write_or_print(_json_text(manifest_payload()), args.output)
        return 0
    if args.command == "run-case":
        try:
            result = execute_case(
                args.case_id,
                binary=args.binary,
                service_aware_potential=args.service_aware_potential,
            )
        except ObservationBiasAbiUnavailable as exc:
            print(str(exc), file=sys.stderr)
            return 2
        _write_or_print(_json_text(result), args.output)
        return 0

    results: list[Mapping[str, Any]] = []
    for path in args.result:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            parser.error(f"result is not one JSON object: {path}")
        results.append(payload)
    report = build_report(results)
    json_text = _json_text(report)
    csv_text = render_csv_report(report)
    markdown = render_markdown_report(report)
    if (
        args.output_json is None
        and args.output_csv is None
        and args.output_markdown is None
    ):
        print(markdown, end="")
    else:
        if args.output_json is not None:
            _write_or_print(json_text, args.output_json)
        if args.output_csv is not None:
            _write_or_print(csv_text, args.output_csv)
        if args.output_markdown is not None:
            _write_or_print(markdown, args.output_markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
