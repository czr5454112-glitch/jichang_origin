"""Plot the complete fixed-seed DH/G31 comparison without selective timing."""
from __future__ import annotations

import csv
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "outputs/tables/feng_cie_dh_repaired_cells_20260905.csv"
OUT = ROOT / "outputs/figures/feng_cie_dh_repaired_comparison_20260905"
METHODS = {"FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION": ("Java CIE-DH reconstruction", "#4169a1"),
           "G31_S4_NATIVE_SYSTEM": ("G31", "#cb6716")}
LOADS = (1.0, 1.75, 2.0)


def main() -> None:
    with TABLE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 180:
        raise ValueError("the publication plot requires the complete 180-cell validated export")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none", "axes.titleweight": "bold"})
    fig, axes = plt.subplots(3, 2, figsize=(10.8, 10.0), sharex="col")
    for col, map_name in enumerate(("map2", "nanning")):
        for method, (label, color) in METHODS.items():
            by_load = {load: [row for row in rows if row["map"] == map_name
                              and row["method"] == method and float(row["load_factor"]) == load]
                       for load in LOADS}
            if any(len(group) != 10 for group in by_load.values()):
                raise ValueError("a plotted group lacks a fixed seed")
            for panel, metric in enumerate(("completion_rate", "on_time_rate")):
                values = [[100 * float(row[metric]) for row in by_load[load]] for load in LOADS]
                axes[panel, col].plot(LOADS, [statistics.fmean(v) for v in values], marker="o",
                                      lw=2, color=color, label=label)
                axes[panel, col].fill_between(LOADS, [min(v) for v in values], [max(v) for v in values],
                                              color=color, alpha=.14, linewidth=0)
            for metric, style in (("population_latency_mean_seconds", "-"),
                                  ("scheduled_release_latency_mean_seconds", "--")):
                eligible_loads, values = [], []
                for load in LOADS[:2]:
                    both = [row for row in rows if row["map"] == map_name
                            and row["method"] in METHODS and float(row["load_factor"]) == load]
                    if any(row["full_population_complete"].lower() != "true" for row in both):
                        continue
                    group = [float(row[metric]) for row in by_load[load]]
                    eligible_loads.append(load)
                    values.append(statistics.fmean(group))
                axes[2, col].plot(eligible_loads, values, marker="o", color=color, ls=style, lw=2)
        axes[0, col].set_title("map2" if map_name == "map2" else "Nanning")
        for panel, label in enumerate(("Completed bags (%)", "On-time bags (%)", "Mean latency per bag (s)")):
            ax = axes[panel, col]
            ax.set_ylabel(label)
            ax.grid(axis="y", color="#e6e6e6", lw=.7)
            ax.set_xticks(LOADS, ("1x", "1.75x", "2x"))
            ax.set_xlim(.94, 2.06)
            if panel < 2:
                ax.set_ylim(0, 104)
            else:
                ax.set_ylim(bottom=0)
                ax.text(2.0, .08, "N/A", ha="center", transform=ax.get_xaxis_transform(), color="#666666")
                ax.set_xlabel("Frozen workload scale")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .985), ncol=2, frameon=False)
    fig.text(.5, .025,
             "10 fixed seeds: lines show means; shading shows seed ranges.\n"
             "Latency: solid = sum(completion - admission); dashed = sum(completion - scheduled release).\n"
             "No formal 2x latency. Full populations only. DH remains a partial reconstruction of Feng's method.",
             ha="center", va="bottom", fontsize=9, color="#444444")
    fig.tight_layout(rect=(0, .105, 1, .95), h_pad=1.6)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT.with_suffix(".png"), dpi=220)
    fig.savefig(OUT.with_suffix(".svg"))
    svg = OUT.with_suffix(".svg")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
                   encoding="utf-8", newline="\n")
    plt.close(fig)
    print(OUT.with_suffix(".png"))


if __name__ == "__main__":
    main()
