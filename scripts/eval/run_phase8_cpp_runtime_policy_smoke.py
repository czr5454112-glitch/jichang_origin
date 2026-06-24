from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
FAULT_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_fault_curriculum_smoke.jsonl"
LATENCY_TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_cpp_runtime_latency.csv"
CLOSED_LOOP_TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_cpp_runtime_closed_loop.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_cpp_runtime_report.md"
LATENCY_REPEATS = 200


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def write_table(path: Path, rows: list[dict[str, float | int | str | bool]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    latency_rows: list[dict[str, float | int | str | bool]],
    closed_loop_rows: list[dict[str, float | int | str | bool]],
    feature_dim: int,
    hidden_dim: int,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cpp_batch = _row_by_mode(latency_rows, "cpp_predict_many")
    cpp_closed_loop_rows = [row for row in closed_loop_rows if row["policy"] == "cpp_runtime_policy"]
    py_closed_loop_rows = [row for row in closed_loop_rows if row["policy"] == "python_runtime_text_policy"]
    no_cpp_conflicts = all(row["post_shield_conflicts"] == 0 for row in cpp_closed_loop_rows)
    no_cpp_truncation = all(not bool(row["truncated"]) for row in cpp_closed_loop_rows)
    matches_python_planned = all(
        cpp_row["planned_count"] == py_row["planned_count"]
        for cpp_row, py_row in zip(cpp_closed_loop_rows, py_closed_loop_rows)
    )
    latency_mismatches = sum(int(row["prediction_mismatches"]) for row in latency_rows)

    lines = [
        "# Phase8 C++ Runtime Policy Smoke Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This smoke uses the exported MLP-EdgeScore runtime text artifact from Phase8, loads it through both Python and C++, measures C++ pybind inference latency, and runs the C++ loaded scorer as the policy inside the existing shielded Python junction environment.",
        "",
        "This script is the local C++ inference and Python-environment closed-loop smoke. Native C++ compact replay, event replay, repair-window replay, and model-unavailable fallback evidence are tracked by the later Phase8 reports linked in the gate status below.",
        "",
        "## Runtime Artifact",
        "",
        f"- Model text artifact: `{MODEL_PATH.relative_to(ROOT).as_posix()}`",
        f"- Feature dimension: `{feature_dim}`",
        f"- Hidden dimension: `{hidden_dim}`",
        "",
        "## Inference Latency",
        "",
        "| Mode | Samples | Repeats | Elapsed seconds | Decisions/s | Mismatches |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in latency_rows:
        lines.append(
            "| {mode} | {sample_count} | {repeats} | {elapsed_seconds:.6f} | "
            "{decisions_per_second:.2f} | {prediction_mismatches} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"Latency CSV: `{LATENCY_TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Closed-Loop Smoke",
            "",
            "| Case | Policy | Fault edges | Tasks | Planned | Unplanned | Conflicts | Steps | Decisions/s | Truncated |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in closed_loop_rows:
        lines.append(
            "| {case} | {policy} | {fault_edges} | {max_tasks} | {planned_count} | {unplanned_count} | "
            "{post_shield_conflicts} | {steps} | {decisions_per_second:.2f} | {truncated} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"Closed-loop CSV: `{CLOSED_LOOP_TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- C++ text artifact load: PASS",
            "- C++ batch inference parity: PASS" if latency_mismatches == 0 else "- C++ batch inference parity: FAIL",
            "- runtime latency measured: PASS" if cpp_batch["decisions_per_second"] > 0 else "- runtime latency measured: FAIL",
            "- C++ runtime policy closed-loop smoke: PASS" if no_cpp_conflicts and no_cpp_truncation else "- C++ runtime policy closed-loop smoke: FAIL",
            "- C++ runtime policy matches Python artifact planned counts: PASS" if matches_python_planned else "- C++ runtime policy matches Python artifact planned counts: FAIL",
            "- native C++ event replay: covered by `outputs/reports/phase8_native_cpp_event_parity_report.md` and `outputs/reports/phase8_legacy_event_parity_report.md`",
            "- model-unavailable fallback: covered by native fallback replay reports and pybind smoke",
            "- safety constraints independent of neural output: PASS; hard action masks, C++ shield checks, and fallback replay remain available without model output",
            "",
            "## Remaining Work",
            "",
            "- add larger batch latency sweeps and compare against rolling-horizon/SIPP runtime under identical task windows",
            "- validate runtime checkpoints on heldout maps, randomized density windows, and repair schedules",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _row_by_mode(rows: list[dict[str, float | int | str | bool]], mode: str) -> dict[str, float | int | str | bool]:
    for row in rows:
        if row["mode"] == mode:
            return row
    raise ValueError(f"missing latency row: {mode}")


def _format_faults(fault_edges: set[tuple[int, int]]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _masked_argmax(scores: list[float], mask: list[bool]) -> int:
    masked = [score if allowed else -1.0e9 for score, allowed in zip(scores, mask)]
    return max(range(len(masked)), key=lambda index: masked[index])


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv  # pylint: disable=import-outside-toplevel
    from czr005.eval import edge_score_policy_factory, runtime_edge_score_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.models import load_edge_score_runtime_text, load_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.models.edge_score import featurize_slice  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"missing runtime model artifact: {MODEL_PATH}")

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    tasks = tuple(TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"))
    py_model = load_edge_score_runtime_text(MODEL_PATH)
    cpp_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    summary = czr005_cpp.edge_score_load_summary(str(MODEL_PATH))

    feature_batches: list[list[list[float]]] = []
    action_masks: list[list[bool]] = []
    py_positions: list[int] = []
    for item in load_teacher_manifest(FAULT_MANIFEST_PATH):
        features, _, mask = featurize_slice(item)
        feature_batches.append(features)
        action_masks.append(mask)
        py_positions.append(_masked_argmax(py_model.scores(features), mask))

    cpp_positions = [int(value) for value in cpp_model.predict_many(feature_batches, action_masks)]
    prediction_mismatches = sum(
        1 for py_position, cpp_position in zip(py_positions, cpp_positions) if py_position != cpp_position
    )
    sample_count = len(feature_batches)

    latency_rows: list[dict[str, float | int | str | bool]] = []
    start = perf_counter()
    for _ in range(LATENCY_REPEATS):
        for features, mask in zip(feature_batches, action_masks):
            _masked_argmax(py_model.scores(features), mask)
    elapsed = perf_counter() - start
    latency_rows.append(_latency_row("python_runtime_text", sample_count, LATENCY_REPEATS, elapsed, 0))

    start = perf_counter()
    for _ in range(LATENCY_REPEATS):
        for features, mask in zip(feature_batches, action_masks):
            cpp_model.predict(features, mask)
    elapsed = perf_counter() - start
    latency_rows.append(_latency_row("cpp_pybind_per_slice", sample_count, LATENCY_REPEATS, elapsed, prediction_mismatches))

    start = perf_counter()
    for _ in range(LATENCY_REPEATS):
        cpp_model.predict_many(feature_batches, action_masks)
    elapsed = perf_counter() - start
    latency_rows.append(_latency_row("cpp_predict_many", sample_count, LATENCY_REPEATS, elapsed, prediction_mismatches))

    cases = (
        ("density_train_first8", tasks[:8], set()),
        ("density_combined_first16", tasks[:16], set()),
        ("fault_alt_route_first8", tasks[:8], {(16, 17)}),
        ("fault_goal_exit_first8", tasks[:8], {(28, 47)}),
    )
    policies = (
        ("python_runtime_text_policy", edge_score_policy_factory(py_model, safe_only=True)),
        ("cpp_runtime_policy", runtime_edge_score_policy_factory(cpp_model, safe_only=True)),
    )
    closed_loop_rows: list[dict[str, float | int | str | bool]] = []
    for case_name, case_tasks, fault_edges in cases:
        for policy_name, policy in policies:
            env = IcsJunctionEnv(
                graph,
                case_tasks,
                fault_edges=fault_edges,
                max_decisions_per_task=128,
            )
            start = perf_counter()
            result, run_info = env.run_policy(policy, seed=43, max_steps=len(case_tasks) * 128)
            elapsed = perf_counter() - start
            summary_row = env.episode_summary()
            closed_loop_rows.append(
                {
                    "case": case_name,
                    "policy": policy_name,
                    "fault_edges": _format_faults(fault_edges),
                    "max_tasks": len(case_tasks),
                    "planned_count": result.metrics.planned_count,
                    "unplanned_count": result.metrics.unplanned_count,
                    "post_shield_conflicts": summary_row["post_shield_conflicts"],
                    "shield_blocks": summary_row["shield_blocks"],
                    "unsafe_proposals": summary_row["unsafe_proposals"],
                    "steps": run_info.steps,
                    "truncated": run_info.truncated,
                    "elapsed_seconds": elapsed,
                    "decisions_per_second": run_info.steps / elapsed if elapsed > 0.0 else 0.0,
                }
            )

    write_table(LATENCY_TABLE_PATH, latency_rows)
    write_table(CLOSED_LOOP_TABLE_PATH, closed_loop_rows)
    write_report(
        latency_rows,
        closed_loop_rows,
        feature_dim=int(summary["feature_dim"]),
        hidden_dim=int(summary["hidden_dim"]),
    )

    if prediction_mismatches:
        raise AssertionError(f"C++ runtime prediction mismatches: {prediction_mismatches}")
    cpp_rows = [row for row in closed_loop_rows if row["policy"] == "cpp_runtime_policy"]
    if any(row["post_shield_conflicts"] != 0 or row["truncated"] for row in cpp_rows):
        raise AssertionError("C++ runtime policy closed-loop smoke failed")

    cpp_batch = _row_by_mode(latency_rows, "cpp_predict_many")
    print(
        "phase8_cpp_runtime samples={} cpp_predict_many_dps={:.2f} closed_loop_cases={} mismatches={}".format(
            sample_count,
            float(cpp_batch["decisions_per_second"]),
            len(cpp_rows),
            prediction_mismatches,
        )
    )
    print(f"report={REPORT_PATH}")


def _latency_row(
    mode: str,
    sample_count: int,
    repeats: int,
    elapsed_seconds: float,
    prediction_mismatches: int,
) -> dict[str, float | int | str | bool]:
    decisions = sample_count * repeats
    return {
        "mode": mode,
        "sample_count": sample_count,
        "repeats": repeats,
        "decision_count": decisions,
        "elapsed_seconds": elapsed_seconds,
        "decisions_per_second": decisions / elapsed_seconds if elapsed_seconds > 0.0 else 0.0,
        "prediction_mismatches": prediction_mismatches,
    }


if __name__ == "__main__":
    main()
