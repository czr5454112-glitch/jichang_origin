"""Render the common selected candidate from a verified comparison snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CELLS = ("map2_1x", "nanning_1x", "map2_2x", "nanning_2x")
COLORS = {"hca": "#384653", "g31": "#187D9A"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("choose a new output directory")
    data = json.loads(args.comparison.read_text(encoding="utf-8"))
    selected = {}
    for cell in CELLS:
        for algorithm in ("hca", "g31"):
            records = [r for r in data["runs"] if r["cell"] == cell and r["algorithm"] == algorithm]
            if len(records) != 1 or not records[0]["comparable"]:
                raise ValueError(f"need one fully audited {algorithm} run for {cell}")
            run = records[0]
            if run["metrics"]["user_tht"]["mean"] is None:
                raise ValueError("full-population THT is required; no completed-subset substitution")
            if not run["system"]["window_fully_observed"]:
                raise ValueError("original observation window must be fully observed")
            selected[cell, algorithm] = run

    args.output.mkdir(parents=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 120})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for ax, cell in zip(axes.flat, CELLS):
        denominator = selected[cell, "hca"]["business_denominator"]
        for algorithm in ("hca", "g31"):
            run = selected[cell, algorithm]
            if run["business_denominator"] != denominator:
                raise ValueError("business population differs")
            curve = run["system"]["hourly_cumulative_business_completion"]
            done = run["system"]["business_completions_in_window"]
            ax.plot([p["hours_since_window_start"] for p in curve],
                    [p["cumulative_completed_businesses"] for p in curve],
                    color=COLORS[algorithm], linewidth=2,
                    label=f"{algorithm.upper()}: {done:,} completed")
        ax.axhline(denominator, color="#CCD3D8", linewidth=1, linestyle="--")
        ax.set(title=f"{cell} | {denominator:,} original business bags",
               xlabel="Hours since original observation start", ylabel="Cumulative final-goal completions")
        ax.grid(alpha=.18)
        ax.legend(fontsize=9, loc="upper left")
    fig.suptitle("Fixed-window throughput: continuous motion, 2-second headway\n"
                 "Same demand and source order; later drain completions excluded", fontsize=13)
    for suffix in ("png", "pdf"):
        fig.savefig(args.output / f"completion_curves.{suffix}", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(4, 2, figsize=(12, 11), layout="constrained")
    for row, cell in enumerate(CELLS):
        for col, (metric, title) in enumerate((("user_tht", "Primary THT"),
                                               ("canonical_to_first_attempt", "Preplanning elapsed"))):
            ax = axes[row, col]
            values = [selected[cell, alg]["metrics"][metric]["mean"] / 60 for alg in ("hca", "g31")]
            ax.barh([0, 1], values, height=.55, color=[COLORS[alg] for alg in ("hca", "g31")])
            pad = max(values) * .025
            for y, value in enumerate(values):
                ax.text(value + pad, y, f"{value:.2f}", va="center", fontsize=10)
            ax.set(title=f"{cell}: {title}", yticks=[0, 1], yticklabels=["HCA", "G31"],
                   xlabel="Mean minutes per original business bag; transport legs summed")
            ax.invert_yaxis()
            ax.set_xlim(0, max(values) * 1.2)
            ax.grid(axis="x", alpha=.15)
    fig.suptitle("Full-cohort transfer THT and time before its clock starts\n"
                 "THT includes failed planning retries; EBS storage excluded. Axes differ by panel.", fontsize=13)
    for suffix in ("png", "pdf"):
        fig.savefig(args.output / f"duration_components.{suffix}", dpi=180)
    plt.close(fig)

    shutil.copyfile(__file__, args.output / Path(__file__).name)
    receipt = dict(input=str(args.comparison.resolve()),
                   input_sha256=hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
                   runs={f"{cell}:{algorithm}": run["id"] for (cell, algorithm), run in selected.items()},
                   boundary="One frozen trace per map/scale. These figures do not establish general statistical superiority.")
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
