from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
BASE_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
DAGGER_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_dagger_smoke.jsonl"
FAULT_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_fault_curriculum_smoke.jsonl"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_edge_score_runtime_loader_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_edge_score_runtime_loader_report.md"
SCORE_TOLERANCE = 1.0e-10
COMPARE_SLICE_COUNT = 64


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def write_table(rows: list[dict[str, float | int | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    rows: list[dict[str, float | int | bool]],
    final_loss: float,
    compare_top1: float,
    feature_dim: int,
    hidden_dim: int,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    max_diff = max(float(row["max_abs_diff"]) for row in rows)
    mismatch_count = sum(1 for row in rows if not bool(row["prediction_match"]))
    lines = [
        "# Phase8 EdgeScore Runtime Loader Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke trains the fault-curriculum MLP-EdgeScore model in Python, exports it to the text runtime artifact format, loads that artifact through the C++ pybind runtime model, and compares scores plus safe-masked predictions on real teacher slices.",
        "",
        "## Artifact",
        "",
        f"- Model text artifact: `{MODEL_PATH.relative_to(ROOT).as_posix()}`",
        f"- Feature dimension: `{feature_dim}`",
        f"- Hidden dimension: `{hidden_dim}`",
        f"- Training final loss: `{final_loss:.6f}`",
        f"- Compare-slice Python top1: `{compare_top1:.6f}`",
        "",
        "## Metrics",
        "",
        f"- Compared slices: `{len(rows)}`",
        f"- Max absolute score difference: `{max_diff:.12f}`",
        f"- Prediction mismatches: `{mismatch_count}`",
        f"- CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "## Gate Status",
        "",
        "- Python text export: PASS",
        "- C++ text artifact load: PASS",
        "- score parity tolerance 1e-10: PASS" if max_diff <= SCORE_TOLERANCE else "- score parity tolerance 1e-10: FAIL",
        "- masked argmax parity: PASS" if mismatch_count == 0 else "- masked argmax parity: FAIL",
        "- C++ closed-loop replay: not covered",
        "",
        "## Remaining Work",
        "",
        "- bind the runtime scorer into a C++ shielded replay loop",
        "- measure C++ policy inference latency on larger replay batches",
        "- validate exported checkpoints across heldout maps and fault schedules",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.models import (  # pylint: disable=import-outside-toplevel
        evaluate_top1,
        fit_edge_score_model,
        load_teacher_manifest,
        save_edge_score_runtime_text,
    )
    from czr005.models.edge_score import featurize_slice  # pylint: disable=import-outside-toplevel

    base_slices = load_teacher_manifest(BASE_MANIFEST_PATH)
    dagger_slices = load_teacher_manifest(DAGGER_MANIFEST_PATH)
    fault_slices = load_teacher_manifest(FAULT_MANIFEST_PATH)
    model, history = fit_edge_score_model(
        base_slices + dagger_slices + fault_slices,
        hidden_dim=16,
        epochs=160,
        learning_rate=0.05,
        seed=61,
    )
    save_edge_score_runtime_text(MODEL_PATH, model)

    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    summary = czr005_cpp.edge_score_load_summary(str(MODEL_PATH))
    compare_slices = fault_slices[:COMPARE_SLICE_COUNT]

    rows: list[dict[str, float | int | bool]] = []
    for index, item in enumerate(compare_slices):
        features, candidate_indices, action_mask = featurize_slice(item)
        py_scores = model.scores(features)
        cpp_scores = runtime_model.scores(features)
        py_action = model.predict_action(item, safe_only=True)
        cpp_position = int(runtime_model.predict(features, action_mask))
        cpp_action = int(candidate_indices[cpp_position])
        max_abs_diff = max(abs(float(left) - float(right)) for left, right in zip(py_scores, cpp_scores))
        rows.append(
            {
                "slice_index": index,
                "candidate_count": len(candidate_indices),
                "max_abs_diff": max_abs_diff,
                "python_action": int(py_action),
                "cpp_action": cpp_action,
                "prediction_match": py_action == cpp_action,
            }
        )

    write_table(rows)
    write_report(
        rows,
        final_loss=float(history[-1]["loss"]),
        compare_top1=evaluate_top1(model, compare_slices),
        feature_dim=int(summary["feature_dim"]),
        hidden_dim=int(summary["hidden_dim"]),
    )

    max_diff = max(float(row["max_abs_diff"]) for row in rows)
    mismatches = sum(1 for row in rows if not bool(row["prediction_match"]))
    if max_diff > SCORE_TOLERANCE or mismatches:
        raise AssertionError(f"runtime loader parity failed: max_diff={max_diff:.12f} mismatches={mismatches}")

    print(
        "edge_score_runtime_loader slices={} max_abs_diff={:.12f} prediction_mismatches={}".format(
            len(rows),
            max_diff,
            mismatches,
        )
    )
    print(f"model={MODEL_PATH}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
