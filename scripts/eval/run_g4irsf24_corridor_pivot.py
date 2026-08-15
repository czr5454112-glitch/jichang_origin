#!/usr/bin/env python3
"""Run the one justified G24 reconvergent-corridor pivot at 1x and 2x.

The learner projects a few offline corridor measurements into the existing
G24 edge-residual table.  This runner does not add a planner or a new runtime
path; it only pairs that frozen table against unchanged S4.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_g4irsf19_bounded_capacity as capacity
from scripts.eval import run_g4irsf24_dlp_campaign as campaign


SCHEMA = "czr005.g4irsf24.reconvergent_corridor_campaign.v1"
DEFAULT_OUTPUT = ROOT / "outputs/tables/g4irsf24_reconvergent_corridor.json"


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _optional_metric(run: Mapping[str, Any], name: str) -> float | None:
    timing = run.get("timing")
    processed = timing.get("processed_attempt") if isinstance(timing, Mapping) else None
    return _finite(processed.get(name)) if isinstance(processed, Mapping) else None


def run_campaign(
    *,
    binary: Path,
    release_csv: Path,
    artifact_path: Path,
    output: Path,
    s4_already_beats_fresh_hca: bool = False,
) -> dict[str, Any]:
    artifact = campaign._read_json(artifact_path)
    if artifact.get("schema") != "czr005.g4irsf24.dlp.v1" or artifact.get("mode") != "ewma":
        raise campaign.DLPCampaignError("corridor pivot needs one G24 EWMA artifact")

    runs: list[dict[str, Any]] = []
    orders = {1: ("S4", "CORRIDOR"), 2: ("CORRIDOR", "S4")}
    for scale in (1, 2):
        rows, _descriptor = capacity.load_g18_scale_input(scale, ROOT)
        if scale == 1:
            rows = campaign._exact_release_rows(rows, release_csv)
        for arm in orders[scale]:
            row = campaign._run_complete(
                binary=binary,
                case_id=f"corridor_{scale}x_{arm}",
                rows=rows,
                artifact=artifact if arm == "CORRIDOR" else None,
                scale=scale,
            )
            row.update(arm=arm, scale=scale)
            runs.append(row)

    indexed = {(int(row["scale"]), str(row["arm"])): row for row in runs}
    comparisons: list[dict[str, Any]] = []
    for scale in (1, 2):
        baseline = indexed[(scale, "S4")]
        candidate = indexed[(scale, "CORRIDOR")]
        complete_safe = all(
            row.get("status") == "PASS"
            and isinstance(row.get("safety"), Mapping)
            and row["safety"].get("pass") is True
            for row in (baseline, candidate)
        )
        baseline_mean = _optional_metric(baseline, "mean_seconds")
        candidate_mean = _optional_metric(candidate, "mean_seconds")
        baseline_p95 = _optional_metric(baseline, "p95_seconds")
        candidate_p95 = _optional_metric(candidate, "p95_seconds")
        baseline_p99 = _optional_metric(baseline, "p99_seconds")
        candidate_p99 = _optional_metric(candidate, "p99_seconds")
        baseline_events = _finite(baseline.get("events_per_completed"))
        candidate_events = _finite(candidate.get("events_per_completed"))
        baseline_deadline = _finite(baseline.get("deadline_miss_count"))
        candidate_deadline = _finite(candidate.get("deadline_miss_count"))
        metrics_available = complete_safe and all(
            value is not None
            for value in (
                baseline_mean,
                candidate_mean,
                baseline_p95,
                candidate_p95,
                baseline_p99,
                candidate_p99,
                baseline_events,
                candidate_events,
                baseline_deadline,
                candidate_deadline,
            )
        )
        metrics_available = bool(
            metrics_available
            and baseline_mean > 0.0
            and baseline_p95 > 0.0
            and baseline_p99 > 0.0
            and baseline_events > 0.0
        )
        mean_delta = candidate_mean - baseline_mean if metrics_available else None
        p95_delta = candidate_p95 - baseline_p95 if metrics_available else None
        p99_delta = candidate_p99 - baseline_p99 if metrics_available else None
        candidate_dlp = candidate.get("dlp")
        mutations = int(
            candidate_dlp.get("g4irsf24_dlp_committed_mutation_count", 0)
            if isinstance(candidate_dlp, Mapping)
            else 0
        )
        event_increase = candidate_events / baseline_events - 1.0 if metrics_available else None
        comparisons.append(
            {
                "scale": scale,
                "complete_and_safe": complete_safe,
                "metrics_available": metrics_available,
                "mean_delta_seconds": mean_delta,
                "mean_improvement_fraction": (
                    -mean_delta / baseline_mean if metrics_available else None
                ),
                "p95_delta_seconds": p95_delta,
                "p99_delta_seconds": p99_delta,
                "committed_mutations": mutations,
                "events_per_completed_relative_increase": event_increase,
                "deadline_miss_delta": (
                    int(candidate_deadline) - int(baseline_deadline)
                    if metrics_available
                    else None
                ),
            }
        )

    one, two = comparisons
    one_business_win = (
        one["mean_improvement_fraction"] is not None
        and (
            one["mean_improvement_fraction"] >= 0.01
            or -one["mean_delta_seconds"] >= 2.0
        )
    )
    one_baseline_p95 = _optional_metric(indexed[(1, "S4")], "p95_seconds")
    one_baseline_p99 = _optional_metric(indexed[(1, "S4")], "p99_seconds")
    one_hold_for_scale = (
        one["mean_improvement_fraction"] is not None
        and one_baseline_p95 is not None
        and one_baseline_p99 is not None
        and one["mean_improvement_fraction"] >= -0.001
        and one["p95_delta_seconds"] <= 0.001 * one_baseline_p95
        and one["p99_delta_seconds"] <= 0.001 * one_baseline_p99
    )
    two_business_win = (
        two["mean_improvement_fraction"] is not None
        and (
            two["mean_improvement_fraction"] >= 0.02
            or -two["mean_delta_seconds"] >= 5.0
        )
    )
    gates = {
        "all_runs_complete_and_safe": all(row["complete_and_safe"] for row in comparisons),
        "all_comparison_metrics_available": all(row["metrics_available"] for row in comparisons),
        "real_mutations_at_both_scales": all(int(row["committed_mutations"]) >= 20 for row in comparisons),
        "one_x_business_win_or_hold_with_two_x_win": one_business_win or (
            s4_already_beats_fresh_hca and one_hold_for_scale and two_business_win
        ),
        "one_x_p95_p99_nonregression": (
            one["p95_delta_seconds"] is not None
            and one["p99_delta_seconds"] is not None
            and one_baseline_p95 is not None
            and one_baseline_p99 is not None
            and one["p95_delta_seconds"] <= 0.001 * one_baseline_p95
            and one["p99_delta_seconds"] <= 0.001 * one_baseline_p99
        ),
        "two_x_business_win": two_business_win,
        "two_x_p95_p99_nonregression": (
            two["p95_delta_seconds"] is not None
            and two["p99_delta_seconds"] is not None
            and two["p95_delta_seconds"] <= 0.0
            and two["p99_delta_seconds"] <= 0.0
        ),
        "event_budget": (
            one["events_per_completed_relative_increase"] is not None
            and two["events_per_completed_relative_increase"] is not None
            and one["events_per_completed_relative_increase"] <= 0.03
            and two["events_per_completed_relative_increase"] <= 0.05
        ),
        "deadline_nonregression": (
            one["deadline_miss_delta"] is not None
            and two["deadline_miss_delta"] is not None
            and one["deadline_miss_delta"] <= 0
            and two["deadline_miss_delta"] <= 0
        ),
    }
    go = all(gates.values())
    payload = {
        "schema": SCHEMA,
        "stage": "CORRIDOR_1X_2X",
        "status": "CORRIDOR_GO" if go else "CORRIDOR_NO_GO_KEEP_S4",
        "active_policy": "CORRIDOR" if go else "S4",
        "binary": _portable_path(binary),
        "release_csv": _portable_path(release_csv),
        "artifact_path": _portable_path(artifact_path),
        "s4_already_beats_fresh_hca": bool(s4_already_beats_fresh_hca),
        "artifact_contract": {
            key: artifact[key]
            for key in ("schema", "mode", "beta", "min_support", "margin_seconds", "detour_allowance_seconds")
        },
        "runs": runs,
        "comparisons": comparisons,
        "gates": gates,
    }
    campaign._write_json(output, payload)
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--release-csv", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--s4-already-beats-fresh-hca",
        action="store_true",
        help="Allow the 1x hold plus 2x win route only after independent fresh-HCA evidence",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_campaign(
        binary=args.binary.resolve(strict=True),
        release_csv=args.release_csv.resolve(strict=True),
        artifact_path=args.artifact.resolve(strict=True),
        output=args.output if args.output.is_absolute() else ROOT / args.output,
        s4_already_beats_fresh_hca=args.s4_already_beats_fresh_hca,
    )
    print(json.dumps({"status": payload["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
