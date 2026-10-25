"""Plot a saved comparison snapshot; never run or alter a simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("choose a fresh figure directory")
    data = json.loads(args.comparison.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 120})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    selected = []
    for row, cell in enumerate(("map2_1x", "nanning_1x")):
        runs = [r for r in data["runs"] if r["cell"] == cell and r["comparable"]]
        baseline = next(r for r in runs if r["algorithm"] == "hca")
        candidates = sorted((r for r in runs if r["algorithm"] == "g31"), key=lambda r: r["id"])
        runs = [baseline, *candidates]
        labels = []
        for i, run in enumerate(runs):
            if run["algorithm"] == "hca":
                label, color = "HCA", "#202020"
            elif "cap120" in run["id"]:
                label, color = "G31 cap120", "#2468B4"
            elif "cap30" in run["id"]:
                label, color = "G31 cap30", "#D88124"
            else:
                label, color = "G31 unbounded", "#888888"
            labels.append(label)
            curve = run["system"]["hourly_cumulative_business_completion"]
            axes[row, 0].plot([p["hours_since_window_start"] for p in curve],
                              [p["cumulative_completed_businesses"] for p in curve],
                              label=label, color=color, linewidth=1.9)
            wait = run["metrics"]["canonical_to_first_attempt"]["mean"] / 60
            tht = run["metrics"]["user_tht"]["mean"] / 60
            axes[row, 1].barh(i, wait, color="#D8DFE8", height=.6)
            axes[row, 1].barh(i, tht, left=wait, color=color, height=.6)
            axes[row, 1].text(wait + tht + .3, i, f"{wait+tht:.1f}", va="center", fontsize=9)
            selected.append(run["id"])
        axes[row, 0].set(title=f"{cell}: cumulative business completions",
                         xlabel="Hours since observation start", ylabel="Completed business bags")
        axes[row, 0].grid(alpha=.2)
        axes[row, 0].legend(fontsize=8, loc="upper left")
        axes[row, 1].set(title=f"{cell}: mean elapsed time per business",
                         xlabel="Minutes; EBS legs summed, storage excluded",
                         yticks=range(len(labels)), yticklabels=labels)
        axes[row, 1].invert_yaxis()
        axes[row, 1].margins(x=.15)
    axes[0, 1].legend(handles=[Patch(color="#D8DFE8", label="Canonical release to first attempt"),
                              Patch(color="#2468B4", label="User THT (includes retries)")],
                      fontsize=8, loc="upper right")
    fig.suptitle("G31 005 diagnostic screen: system delay versus transfer THT\n"
                 "Matched 2-second headway and canonical FIFO; 28,506 businesses per map", fontsize=13)
    fig.savefig(args.output / "system_comparison.png", dpi=180)
    fig.savefig(args.output / "system_comparison.pdf")
    plt.close(fig)
    shutil.copyfile(__file__, args.output / Path(__file__).name)
    receipt = {"input": str(args.comparison.resolve()),
               "input_sha256": hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
               "runs": selected, "winner_selected": False,
               "boundary": "All displayed 1x cohorts completed. This diagnostic does not establish high-load superiority."}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
