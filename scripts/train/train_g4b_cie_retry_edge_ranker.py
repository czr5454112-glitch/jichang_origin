from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
G4A_GATE_PATH = ROOT / "outputs" / "tables" / "g4a_dataset_gate.csv"
G4A_INTERFACE_PATH = ROOT / "outputs" / "tables" / "g4a_interface_decision_slices.csv"
MODEL_PATH = ROOT / "artifacts" / "models" / "g4b_cie_retry_edge_ranker_smoke.json"
HISTORY_PATH = ROOT / "outputs" / "tables" / "g4b_training_history.csv"
OFFLINE_PATH = ROOT / "outputs" / "tables" / "g4b_offline_accuracy.csv"
ABLATION_PATH = ROOT / "outputs" / "tables" / "g4b_feature_ablation.csv"
TRAIN_REPORT_PATH = ROOT / "outputs" / "reports" / "g4b_cie_retry_training_notes.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _assert_g4a_gate() -> None:
    rows = _read_csv(G4A_GATE_PATH)
    failed = [row for row in rows if row["pass"] != "True"]
    if failed:
        raise AssertionError(f"G4A gate failed; refusing to train G4B: {failed}")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _split_rows(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["split"] == split]


def _write_training_report(history: list[dict[str, Any]], offline_rows: list[dict[str, Any]], ablation_rows: list[dict[str, Any]]) -> None:
    final = history[-1]
    all_row = next(row for row in offline_rows if row["split"] == "all")
    TRAIN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4B CIE Retry Training Notes",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This trains a minimal pure-Python MLP candidate scorer on the G4A verified CIE retry interface slices. It is a pilot model, not a paper-grade learning result. No GNN, Transformer, PPO, MAPPO, or RL is used.",
        "",
        "## Training Result",
        "",
        f"- Final training loss: `{float(final['loss']):.6f}`",
        f"- Final training top1: `{float(final['top1']):.6f}`",
        f"- All-split model top1: `{float(all_row['model_top1']):.6f}`",
        f"- All-split shortest-time heuristic top1: `{float(all_row['shortest_time_heuristic_top1']):.6f}`",
        "",
        "## Feature Ablation",
        "",
        _markdown_table(["Ablation", "All top1"], [[row["ablation"], f"{float(row['all_top1']):.6f}"] for row in ablation_rows]),
        "",
        "## Artifacts",
        "",
        f"- Model: `{_relative(MODEL_PATH)}`",
        f"- Training history: `{_relative(HISTORY_PATH)}`",
        f"- Offline accuracy: `{_relative(OFFLINE_PATH)}`",
        f"- Feature ablation: `{_relative(ABLATION_PATH)}`",
    ]
    TRAIN_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
        ]
    )


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    _prepare_imports()
    _assert_g4a_gate()

    from czr005.models import (  # pylint: disable=import-outside-toplevel
        evaluate_g4b_top1,
        fit_g4b_model,
        heuristic_shortest_time_top1,
        load_g4a_interface_slices,
        random_safe_expected_top1,
        save_g4b_model,
    )

    rows = load_g4a_interface_slices(G4A_INTERFACE_PATH)
    train_rows = _split_rows(rows, "train")
    val_rows = _split_rows(rows, "val")
    test_rows = _split_rows(rows, "test")
    if not train_rows or not val_rows or not test_rows:
        raise AssertionError("G4A split must contain train, val, and test rows")

    model, history = fit_g4b_model(train_rows, hidden_dim=18, epochs=220, learning_rate=0.04, seed=73)
    save_g4b_model(MODEL_PATH, model)
    history_rows = [
        {"epoch": row["epoch"], "loss": f"{float(row['loss']):.8f}", "top1": f"{float(row['top1']):.8f}"}
        for row in history
    ]
    _write_csv(HISTORY_PATH, history_rows, ["epoch", "loss", "top1"])

    splits = {
        "train": train_rows,
        "val": val_rows,
        "test": test_rows,
        "all": rows,
    }
    offline_rows: list[dict[str, Any]] = []
    for split, items in splits.items():
        model_top1 = evaluate_g4b_top1(model, items)
        shortest_top1 = heuristic_shortest_time_top1(items)
        random_top1 = random_safe_expected_top1(items)
        offline_rows.append(
            {
                "split": split,
                "sample_count": len(items),
                "model_top1": f"{model_top1:.8f}",
                "shortest_time_heuristic_top1": f"{shortest_top1:.8f}",
                "random_safe_expected_top1": f"{random_top1:.8f}",
                "model_beats_shortest_time": model_top1 > shortest_top1,
            }
        )
    _write_csv(
        OFFLINE_PATH,
        offline_rows,
        [
            "split",
            "sample_count",
            "model_top1",
            "shortest_time_heuristic_top1",
            "random_safe_expected_top1",
            "model_beats_shortest_time",
        ],
    )

    ablation_specs = {
        "none": set(),
        "no_slack": {"time_slack_scaled"},
        "no_node_pressure": {"local_node_pressure_scaled", "candidate_node_pressure_scaled"},
        "no_fault_flag": {"candidate_faulted"},
        "no_branch_flag": {"is_branch_node", "out_degree_scaled"},
        "no_candidate_distance": {"candidate_shortest_time_to_goal_scaled", "candidate_travel_time_scaled"},
    }
    ablation_rows = [
        {
            "ablation": name,
            "all_top1": f"{evaluate_g4b_top1(model, rows, ablation=disabled):.8f}",
            "val_top1": f"{evaluate_g4b_top1(model, val_rows, ablation=disabled):.8f}",
            "test_top1": f"{evaluate_g4b_top1(model, test_rows, ablation=disabled):.8f}",
        }
        for name, disabled in ablation_specs.items()
    ]
    _write_csv(ABLATION_PATH, ablation_rows, ["ablation", "all_top1", "val_top1", "test_top1"])
    _write_training_report(history_rows, offline_rows, ablation_rows)

    all_row = next(row for row in offline_rows if row["split"] == "all")
    print(
        "g4b train complete: "
        f"slices={len(rows)} train={len(train_rows)} val={len(val_rows)} test={len(test_rows)} "
        f"model_top1={all_row['model_top1']} shortest_top1={all_row['shortest_time_heuristic_top1']}"
    )


if __name__ == "__main__":
    main()
