"""Plot the repaired HCA campaign from the same verified inputs as its report.

No simulation is run. Large points are means of ten seed statistics; faint
points retain each seed and whiskers show descriptive seed ranges, not CIs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import StrMethodFormatter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import report_hca_segment_identity_campaign as report

METHODS, STATS, external = report.METHODS, report.STATS, report.external
LABELS = dict(zip(METHODS, ("G31 (reused)", "V5 DH reconstruction (reused)", "HCA identity repair (new)")))
COLORS = dict(zip(METHODS, ("#0072B2", "#D55E00", "#7F3C8D")))
MARKERS = dict(zip(METHODS, ("s", "o", "^")))
OUTPUT = ROOT / "outputs/figures/hca_segment_identity_20260906"
require, number, boolean, sha = report.require, report.number, report.boolean, report.sha


def summarize(indexed: dict) -> list[dict]:
    groups = []
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                records = [(seed, indexed[map_name, load, seed, method]) for seed in external.SEEDS
                           if (map_name, load, seed, method) in indexed]
                full = len(records) == 10
                complete = sum(boolean(r["full_population_complete"]) for _, r in records)
                if load == 2:
                    status = "NA_2X_PROTOCOL"
                elif not full:
                    status = "NA_MISSING_FROZEN_SEEDS"
                elif complete != 10:
                    status = "NA_INCOMPLETE_RAW_POPULATION"
                elif any(number(r[f"tht_scheduled_release_{s}_seconds"]) is None for _, r in records for s in STATS):
                    status = "NA_MISSING_TIMING"
                else:
                    status = "ELIGIBLE_TEN_SEEDS"
                statistics_by_metric = {}
                for metric in ("THT_min", "THT_mean", "THT_max", "TH"):
                    eligible = full if metric == "TH" else status == "ELIGIBLE_TEN_SEEDS"
                    field = "TH_completed_raw_bags" if metric == "TH" else f"tht_scheduled_release_{metric.split('_')[1]}_seconds"
                    values = [number(r[field]) for _, r in records] if eligible else []
                    statistics_by_metric[metric] = {"seed_values": values,
                        "mean_across_seeds": statistics.fmean(values) if values else None,
                        "seed_range_low": min(values) if values else None,
                        "seed_range_high": max(values) if values else None}
                groups.append({"map": map_name, "load_factor": load, "method": method,
                    "observed_seed_count": len(records), "complete_population_seed_count": complete,
                    "missing_seeds": [s for s in external.SEEDS if s not in {seed for seed, _ in records}],
                    "THT_status": status, "TH_status": "ELIGIBLE_TEN_SEEDS" if full else "NA_MISSING_FROZEN_SEEDS",
                    "statistics": statistics_by_metric})
    return groups


def draw_group(ax, x: float, method: str, stat: dict) -> None:
    center = stat["mean_across_seeds"]
    low, high = stat["seed_range_low"], stat["seed_range_high"]
    ax.errorbar([x], [center], yerr=[[center-low], [high-center]], fmt="none", ecolor=COLORS[method],
                elinewidth=1.2, capsize=3.5, zorder=3)
    ax.scatter([x+(i-4.5)*.012 for i in range(10)], stat["seed_values"], color=COLORS[method],
               marker=MARKERS[method], s=12, alpha=.38, linewidths=0, zorder=4)
    ax.scatter([x], [center], color=COLORS[method], marker=MARKERS[method], s=48,
               edgecolors="white", linewidths=.8, zorder=5)


def axes_style(ax) -> None:
    ax.set_xticks(range(3), ["1×", "1.75×", "2×"])
    ax.set_xlim(-.48, 2.48)
    upper = ax.get_ylim()[1]
    ax.set_ylim(0, upper*1.04 if upper > 0 else 1)
    ax.set_xlabel("Workload load factor")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="y", color="#dddddd", linewidth=.65, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)


def render(groups: list[dict], output: Path, *, synthetic_qa: bool = False) -> list[Path]:
    """Synthetic layout checks must carry an unmistakable visible watermark."""
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 11, "axes.labelsize": 10, "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.facecolor": "white"})
    indexed = {(g["map"], g["load_factor"], g["method"]): g for g in groups}
    legend = [Line2D([], [], color=COLORS[m], marker=MARKERS[m], linestyle="none", markersize=7, label=LABELS[m]) for m in METHODS]
    prefix = "SYNTHETIC QA — NOT EXPERIMENT RESULTS\n" if synthetic_qa else ""
    footnote = "Large points: mean of 10 seed statistics. Faint points: individual seeds. Whiskers: seed min–max (not confidence intervals)."
    provenance = "60 new HCA identity-repair runs; 120 frozen G31/V5 cells reused. Independent scheduled EBS segments are retained for all methods."
    limitation = "Historical HCA (43/60 accounting anomalies) is excluded from these plots. New accounting validation is not an exhaustive physical proof."
    outputs = []

    def save(fig, stem):
        for extension in ("png", "pdf"):
            path = output / (stem + "." + extension)
            metadata = {"Creator": "plot_hca_segment_identity_campaign.py"}
            if extension == "pdf":
                metadata.update(CreationDate=None, ModDate=None)
            fig.savefig(path, dpi=220, metadata=metadata)
            outputs.append(path)
        plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(14.4, 8.9))
    for row, map_name in enumerate(external.MAPS):
        for column, stat in enumerate(STATS):
            ax = axes[row, column]
            ax.set_title(f"{'Map2' if map_name == 'map2' else 'Nanning'} | THT(D) {stat}")
            for x, load in enumerate(external.LOAD_FACTORS):
                if load == 2:
                    ax.axvspan(x-.36, x+.36, color="#f0f0f0", zorder=-1)
                    ax.text(x, .43, "N/A\n2× protocol", ha="center", va="center", color="#555555",
                            transform=ax.get_xaxis_transform())
                    continue
                for position, method in enumerate(METHODS):
                    g = indexed[map_name, load, method]
                    at = x+(position-1)*.22
                    if g["THT_status"] == "ELIGIBLE_TEN_SEEDS":
                        draw_group(ax, at, method, g["statistics"]["THT_"+stat])
                    else:
                        reason = "unfinished" if g["THT_status"] == "NA_INCOMPLETE_RAW_POPULATION" else "missing data"
                        ax.text(at, .05, "N/A\n"+reason, color=COLORS[method], fontsize=7.2,
                                rotation=90, ha="center", va="bottom", transform=ax.get_xaxis_transform())
            axes_style(ax)
            ax.set_ylabel("Seconds")
    fig.suptitle(prefix+"Scheduled-release THT(D) after the HCA execution-identity repair", fontsize=14, y=.98)
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5, .112), ncol=3, frameon=False)
    fig.text(.5, .090, "Each bag: sum of segment (completion − common canonical D). Min/mean/max are population statistics within each seed.", ha="center", fontsize=8.4)
    fig.text(.5, .070, "Clock scope: native-start rankings can differ (see report). Common D is not verified as Feng's exact timing implementation.", ha="center", fontsize=8.4)
    fig.text(.5, .050, footnote, ha="center", fontsize=8.4)
    fig.text(.5, .030, provenance, ha="center", fontsize=8.1, color="#555555")
    fig.text(.5, .010, limitation, ha="center", fontsize=8.0, color="#555555")
    fig.subplots_adjust(left=.065, right=.985, top=.87 if synthetic_qa else .90, bottom=.22, hspace=.38, wspace=.30)
    save(fig, "hca_segment_identity_tht_min_mean_max_20260906")

    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.7))
    for ax, map_name in zip(axes, external.MAPS):
        ax.set_title("Map2" if map_name == "map2" else "Nanning")
        offered = [external.EXPECTED_POPULATIONS[l][0] for l in external.LOAD_FACTORS]
        ax.plot(range(3), offered, color="#777777", linestyle=":", marker="D", markersize=4,
                markerfacecolor="white", linewidth=1.1, zorder=2)
        for x, load in enumerate(external.LOAD_FACTORS):
            for position, method in enumerate(METHODS):
                g = indexed[map_name, load, method]
                if g["TH_status"] == "ELIGIBLE_TEN_SEEDS":
                    draw_group(ax, x+(position-1)*.22, method, g["statistics"]["TH"])
                else:
                    ax.text(x+(position-1)*.22, .05, "N/A\nmissing seeds", color=COLORS[method], fontsize=8,
                            rotation=90, ha="center", va="bottom", transform=ax.get_xaxis_transform())
        axes_style(ax)
        ax.set_ylabel("Completed raw bags (TH)")
    fig.suptitle(prefix+"Fixed-horizon TH after the HCA execution-identity repair", fontsize=14, y=.98)
    offered_handle = Line2D([], [], color="#777777", linestyle=":", marker="D", markerfacecolor="white", markersize=4, label="Offered raw bags")
    fig.legend(handles=legend+[offered_handle], loc="lower center", bbox_to_anchor=(.5, .125), ncol=4, frameon=False)
    fig.text(.5, .104, "TH = completed raw-bag count by absolute model epoch 98,259 s. Every offered raw bag remains in the denominator.", ha="center", fontsize=8.4)
    fig.text(.5, .073, footnote, ha="center", fontsize=8.4)
    fig.text(.5, .040, provenance, ha="center", fontsize=8.1, color="#555555")
    fig.text(.5, .012, limitation, ha="center", fontsize=8.0, color="#555555")
    fig.subplots_adjust(left=.075, right=.985, top=.80 if synthetic_qa else .84, bottom=.28, wspace=.24)
    save(fig, "hca_segment_identity_fixed_horizon_th_20260906")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-root", type=Path, default=report.TABLE_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=report.EVIDENCE)
    parser.add_argument("--old-cells", type=Path, default=report.OLD_CELLS)
    parser.add_argument("--control-notes", type=Path, default=report.CONTROL_NOTES)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows, _, manifest, _, _, _, paths, hashes = report.load_final(args)
    groups = summarize(report.validate_cells(rows))
    outputs = render(groups, args.output_dir)
    statistics_path = args.output_dir / "hca_segment_identity_plot_statistics_20260906.json"
    statistics_path.write_text(json.dumps(groups, indent=2)+"\n", encoding="utf-8")
    value = {"schema": "czr005.hca_segment_identity_scientific_figures.v1", "status": "FINAL_MATRIX",
        "observed_cells": 180, "new_hca_cells": 60, "reused_g31_v5_cells": 120,
        "script_sha256": sha(Path(__file__)), "validation_script_sha256": sha(Path(report.__file__)),
        "matplotlib_version": matplotlib.__version__, "seeds": list(external.SEEDS),
        "inputs": {n: {"path": str(p.resolve()), "sha256": hashes[n]} for n, p in paths.items()},
        "interval_definition": "DESCRIPTIVE_MIN_MAX_OF_TEN_SEED_STATISTICS_NOT_CONFIDENCE_INTERVAL",
        "THT_gate": "ALL_TEN_SEEDS_ALL_RAW_BAGS_COMPLETE_AND_LOAD_NOT_2X; OTHERWISE_NA_NO_SUBSET",
        "TH_definition": "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259",
        "historical_hca_anomalies_not_applied_to_new_hca": True,
        "statistics": {"path": str(statistics_path.resolve()), "sha256": sha(statistics_path)},
        "figures": [{"path": str(p.resolve()), "sha256": sha(p)} for p in outputs]}
    require(all(sha(p) == hashes[n] for n, p in paths.items()), "input changed while rendering figures")
    (args.output_dir / "figure_manifest.json").write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "FINAL_MATRIX", "figures": len(outputs), "cells": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
