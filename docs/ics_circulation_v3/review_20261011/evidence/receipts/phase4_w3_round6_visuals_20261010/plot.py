"""Standalone full-domain figures from the completed author analysis only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from time import process_time, perf_counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(source, output):
    cpu, wall = process_time(), perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / "plot.py")
    before = digest(source)
    data = json.loads(source.read_text(encoding="utf-8"))
    if data["errors"] or "full" not in data["stages"]:
        raise ValueError("completed, zero-error full analysis required")
    rows = [r for r in data["rows"] if r["stage"] == "full"]
    if len(rows) != 81 or any(r["status"] != "controller_quiescent" for r in rows):
        raise ValueError("all 81 complete cases required; do not plot a selected successful subset")
    scenes = ("cross_cycle", "counterflow", "near_full")
    policies = ("old32", "old64", "same_zone32plus32")
    names = ("Original / 32", "Original / 64", "Same-zone / 32+32")
    colors = ("#98a5b3", "#546b81", "#176b55")
    tapes = ("nominal", *(f"error{i:02d}" for i in range(8)))
    by = {(r["scene"], r["tape_id"], r["policy"]): r for r in rows}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.facecolor": "white"})
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.8))
    x = np.arange(3)
    for j, policy in enumerate(policies):
        totals = [sum(by[s, t, policy]["total_cost"] for t in tapes) for s in scenes]
        axes[0].bar(x + (j - 1) * .24, totals, .23, color=colors[j], label=names[j])
        completed = [sum(by[s, t, policy]["on_time"] for t in tapes) for s in scenes]
        axes[1].bar(x + (j - 1) * .24, completed, .23, color=colors[j])
        cpus = [sum(by[s, t, policy]["invocation_cpu_seconds"] for t in tapes) for s in scenes]
        axes[2].bar(x + (j - 1) * .24, cpus, .23, color=colors[j])
    titles = ("Complete-cycle objective J", "Tasks completed on time", "Complete invocation CPU (seconds)")
    for ax, title in zip(axes, titles):
        ax.set_xticks(x, ("Cross cycle", "Counterflow", "Near full"))
        ax.set_title(title, loc="left", fontsize=12)
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=10, ncol=3,
               loc="upper left", bbox_to_anchor=(.055, .91))
    fig.suptitle("Same-zone direct supply: all 81 predeclared deployments", x=.06, ha="left", fontsize=16, fontweight="bold")
    fig.text(.06, .02, "Three reused development flows × nine tapes × three policies. Correlated task instances; no independent operating-day claim.\nCPU includes setup, simulation, tracing and serialization; it is not decision latency. All policies retain the original objective and forecasts.", fontsize=9, color="#4b5563")
    fig.subplots_adjust(left=.06, right=.98, top=.80, bottom=.20, wspace=.28)
    for suffix in ("png", "svg"):
        fig.savefig(output / ("all_deployments." + suffix), dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 5.2), sharey=True)
    y = np.arange(9)
    for ax, scene in zip(axes, scenes):
        for policy, color, marker, label in (
            ("old64", colors[1], "x", "Original 64 − Original 32"),
            ("same_zone32plus32", colors[2], "o", "Same-zone − Original 32")):
            delta = [by[scene, t, policy]["total_cost"] - by[scene, t, "old32"]["total_cost"] for t in tapes]
            ax.plot(delta, y, linestyle="", marker=marker, color=color, label=label)
        ax.axvline(0, color="#9ca3af", linewidth=1)
        ax.set_title(scene.replace("_", " ").title(), loc="left")
        ax.grid(axis="x", alpha=.2)
        ax.set_xlabel("Paired change in J (negative = lower)")
        ax.set_yticks(y, ("Nominal", *(f"Error tape {i:02d}" for i in range(8))))
        ax.set_ylim(8.7, -.7)
        # Keep a visible scale even if every paired difference is exactly zero.
        if ax.get_xlim()[1] - ax.get_xlim()[0] < 1:
            ax.set_xlim(-1, 1)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=10, ncol=2,
               loc="upper left", bbox_to_anchor=(.085, .91))
    fig.suptitle("Every paired tape: improvements, ties and regressions retained", x=.09, ha="left", fontsize=16, fontweight="bold")
    fig.text(.09, .025, "Fixed synthetic cancellation/jitter stress, original forecast publications unchanged. This is sensitivity evidence, not a calibrated demand distribution.", fontsize=9, color="#4b5563")
    fig.subplots_adjust(left=.09, right=.98, top=.77, bottom=.17, wspace=.30)
    for suffix in ("png", "svg"):
        fig.savefig(output / ("all_paired_tapes." + suffix), dpi=180)
    plt.close(fig)
    if digest(source) != before:
        raise ValueError("analysis input changed")
    metadata = {"source": str(source.resolve()), "source_sha256": before, "cases": 81,
                "cpu_seconds_measured_after_plot_imports": process_time() - cpu,
                "wall_seconds_measured_after_plot_imports": perf_counter() - wall}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({p.name: digest(p) for p in output.iterdir() if p.is_file()}, indent=2), encoding="utf-8")
    print(json.dumps(metadata))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.source, args.output)
