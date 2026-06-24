from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_fault_curriculum_smoke.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_edge_score_cpp_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_edge_score_cpp_parity_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _synthetic_weights(feature_dim: int, hidden_dim: int = 5) -> tuple[list[list[float]], list[float], list[float], float]:
    w1 = [
        [(((feature + 1) * (hidden + 2)) % 11 - 5) * 0.017 for hidden in range(hidden_dim)]
        for feature in range(feature_dim)
    ]
    b1 = [(hidden - 2) * 0.013 for hidden in range(hidden_dim)]
    w2 = [(((hidden + 3) * 5) % 13 - 6) * 0.019 for hidden in range(hidden_dim)]
    return w1, b1, w2, 0.031


def write_table(rows: list[dict[str, float | int | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    max_diff = max(float(row["max_abs_diff"]) for row in rows)
    all_match = all(bool(row["prediction_match"]) for row in rows)
    lines = [
        "# Phase8 EdgeScore C++ Runtime Parity Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This smoke verifies that the new C++ MLP-EdgeScore inference kernel and pybind wrapper match the Python scorer on real teacher-slice feature rows. It uses deterministic synthetic weights to isolate runtime parity from training quality.",
        "",
        "## Metrics",
        "",
        f"- Compared slices: `{len(rows)}`",
        f"- Max absolute score difference: `{max_diff:.12f}`",
        f"- Masked prediction parity: `{'PASS' if all_match else 'FAIL'}`",
        f"- CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "## Gate Status",
        "",
        "- C++ scorer callable from pybind: PASS",
        "- score parity tolerance 1e-12: PASS" if max_diff <= 1.0e-12 else "- score parity tolerance 1e-12: FAIL",
        "- masked argmax parity: PASS" if all_match else "- masked argmax parity: FAIL",
        "- production text model loader: covered by `outputs/reports/phase8_edge_score_runtime_loader_report.md`",
        "- latency and closed-loop runtime smoke: covered by `outputs/reports/phase8_cpp_runtime_report.md`",
        "",
        "## Remaining Work",
        "",
        "- keep runtime parity covered when replacing the text MLP artifact with ONNX/LibTorch/GNN runtime formats",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.models import EdgeScoreModel, FEATURE_NAMES, load_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.models.edge_score import featurize_slice  # pylint: disable=import-outside-toplevel

    slices = load_teacher_manifest(MANIFEST_PATH)[:32]
    w1, b1, w2, b2 = _synthetic_weights(len(FEATURE_NAMES))
    py_model = EdgeScoreModel(w1=w1, b1=b1, w2=w2, b2=b2)

    rows: list[dict[str, float | int | bool]] = []
    for index, item in enumerate(slices):
        features, candidate_indices, action_mask = featurize_slice(item)
        py_scores = py_model.scores(features)
        cpp_scores = czr005_cpp.edge_score_scores(w1, b1, w2, b2, features)
        cpp_position = int(czr005_cpp.edge_score_predict(w1, b1, w2, b2, features, action_mask))
        cpp_action = int(candidate_indices[cpp_position])
        py_action = py_model.predict_action(item, safe_only=True)
        max_abs_diff = max(abs(float(left) - float(right)) for left, right in zip(py_scores, cpp_scores))
        rows.append(
            {
                "slice_index": index,
                "candidate_count": len(candidate_indices),
                "max_abs_diff": max_abs_diff,
                "python_action": py_action,
                "cpp_action": cpp_action,
                "prediction_match": py_action == cpp_action,
            }
        )

    write_table(rows)
    write_report(rows)
    print(
        "edge_score_cpp_parity slices={} max_abs_diff={:.12f} predictions_match={}".format(
            len(rows),
            max(float(row["max_abs_diff"]) for row in rows),
            all(bool(row["prediction_match"]) for row in rows),
        )
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
