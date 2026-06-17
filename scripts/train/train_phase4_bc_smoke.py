from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
MODEL_PATH = ROOT / "artifacts" / "models" / "phase4_mlp_edge_score_smoke.json"
HISTORY_PATH = ROOT / "outputs" / "tables" / "phase4_bc_smoke_history.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase4_bc_smoke_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def write_history(history: list[dict[str, float | int]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(history[0]))
        writer.writeheader()
        writer.writerows(history)


def write_report(
    slice_count: int,
    final_loss: float,
    final_top1: float,
    eval_top1: float,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase4 Behavior Cloning Smoke Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke trains the first minimal MLP-EdgeScore behavior-cloning baseline on the Phase4 teacher junction-slice manifest. It is a pure-Python training check, not a final policy result.",
        "",
        "## Inputs And Outputs",
        "",
        f"- Teacher manifest: `{MANIFEST_PATH.relative_to(ROOT).as_posix()}`",
        f"- Model artifact: `{MODEL_PATH.relative_to(ROOT).as_posix()}`",
        f"- Training history: `{HISTORY_PATH.relative_to(ROOT).as_posix()}`",
        f"- Slices: `{slice_count}`",
        "",
        "## Metrics",
        "",
        f"- Final training loss: `{final_loss:.6f}`",
        f"- Final training top1: `{final_top1:.6f}`",
        f"- Safe masked eval top1: `{eval_top1:.6f}`",
        "",
        "## Gate Status",
        "",
        "- teacher manifest consumed: PASS",
        "- model artifact written: PASS",
        "- safe masked top1 smoke threshold: PASS" if eval_top1 >= 0.75 else "- safe masked top1 smoke threshold: FAIL",
        "- closed-loop policy replay: not started",
        "",
        "## Remaining Work",
        "",
        "- split train/validation teacher data",
        "- add larger and harder teacher manifests",
        "- run shadow replay against baseline actions",
        "- compare BC+shield with SIPP/rolling-horizon/PIBT baselines",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    from czr005.models import (  # pylint: disable=import-outside-toplevel
        evaluate_top1,
        fit_edge_score_model,
        load_teacher_manifest,
        save_edge_score_model,
    )

    slices = load_teacher_manifest(MANIFEST_PATH)
    model, history = fit_edge_score_model(
        slices,
        hidden_dim=16,
        epochs=200,
        learning_rate=0.05,
        seed=41,
    )
    save_edge_score_model(MODEL_PATH, model)
    write_history(history)
    eval_top1 = evaluate_top1(model, slices, safe_only=True)
    final = history[-1]
    write_report(
        slice_count=len(slices),
        final_loss=float(final["loss"]),
        final_top1=float(final["top1"]),
        eval_top1=eval_top1,
    )
    print(
        "bc_slices={} final_loss={:.6f} final_top1={:.6f} eval_top1={:.6f}".format(
            len(slices),
            float(final["loss"]),
            float(final["top1"]),
            eval_top1,
        )
    )
    print(f"model={MODEL_PATH}")


if __name__ == "__main__":
    main()
