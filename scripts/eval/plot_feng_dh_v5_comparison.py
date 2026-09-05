"""Publish seed-level THT/TH figures from the audited V5 campaign cell table.

No simulator is executed. By default all 180 method cells are required. Every
plotted method/map/load group requires all ten frozen seeds. THT additionally
requires every raw population to finish and is always N/A at 2x. Seed ranges
are descriptive ranges, not bag-level intervals or confidence intervals.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
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
from scripts.eval import run_cie_external_baseline_robustness as external

METHODS = ("G31_S4_NATIVE_SYSTEM", "FENG_DH_BOUNDARY_CLEARANCE_V5", "FENG_NATIVE_HCA")
LABELS = {METHODS[0]: "G31 (archived)", METHODS[1]: "V5 DH reconstruction", METHODS[2]: "HCA (archived obs.)"}
COLORS = {METHODS[0]: "#0072B2", METHODS[1]: "#D55E00", METHODS[2]: "#7F3C8D"}
MARKERS = {METHODS[0]: "s", METHODS[1]: "o", METHODS[2]: "^"}
SOURCE_SHA = "7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7"
CLASS_SHA = "a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869"
STATS = ("min", "mean", "max")
CELLS = ROOT / "outputs/tables/feng_dh_v5_cells_20260905.csv"
OUTPUT = ROOT / "outputs/figures/feng_dh_v5_20260905"
CONTROL_NOTES = ROOT / "outputs/runtime/cie_external_baseline_boundary_clearance_v5/control_completion_notes.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: object) -> float | None:
    if value is None or str(value).strip() in {"", "N/A"}:
        return None
    result = float(value)
    require(math.isfinite(result) and result >= 0, "non-finite or negative plotted metric")
    return result


def boolean(value: object) -> bool:
    require(value in (True, False, "True", "False", "true", "false"), "invalid population-completion flag")
    return str(value).lower() == "true"


def load_control_audit(path: Path) -> dict:
    """Attach interpretation to unchanged observations, without adding a run gate."""
    if not path.exists():
        return {"status": "NOT_PROVIDED", "path": str(path.resolve()), "sha256": None}
    value = json.loads(path.read_text(encoding="utf-8"))
    require(value["schema"] == "czr005.feng_v5_hca_control_completion_notes.v1", "unknown control audit")
    require(value["audited_cell_count"] == len(value["cells"]) == 60
            and value["affected_cell_count"] == sum(int(c["residual"]) > 0 for c in value["cells"]), "control audit count differs")
    return {"status": "ARCHIVED_OBSERVATIONS_WITH_ACCOUNTING_LIMIT", "path": str(path.resolve()), "sha256": sha(path),
            "audited_cell_count": value["audited_cell_count"], "affected_cell_count": value["affected_cell_count"],
            "interpretation": "Affected HCA observations are not evidence of a loss-free physical baseline or capacity superiority."}


def load_cells(path: Path, *, allow_partial: bool = False) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    indexed = {}
    paired = {}
    for row in rows:
        map_name, load, seed, method = row["map"], float(row["load_factor"]), int(row["seed"]), row["method"]
        require(map_name in external.MAPS and load in external.LOAD_FACTORS
                and seed in external.SEEDS and method in METHODS, "unfrozen cell coordinate")
        key = (map_name, load, seed, method)
        require(key not in indexed, "duplicate cell; seed duplication cannot replace a missing seed")
        require(float(row["fixed_horizon_seconds"]) == external.FIXED_HORIZON_SECONDS, "fixed horizon differs")
        require(row["primary_timing_definition"] == "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE",
                "plot requires common scheduled-release timing, not admission timing")
        require(row["TH_definition"] == "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259", "TH definition differs")
        require(not boolean(row["historical_shared_D"]), "randomized campaign is not historical Table 5.3")
        raw_count = int(row["raw_bag_count"])
        complete = boolean(row["full_population_complete"])
        completed = number(row["TH_completed_raw_bags"])
        require(completed is not None and completed.is_integer() and 0 <= completed <= raw_count, "TH population mismatch")
        require(completed == number(row["completed_raw_bag_count"]), "two TH count columns disagree")
        require(complete == (completed == raw_count), "full-completion flag disagrees with raw population")
        require(raw_count - completed == number(row["unfinished_raw_bag_count"]), "unfinished denominator mismatch")
        require(raw_count == external.EXPECTED_POPULATIONS[load][0], "unfrozen offered raw population")
        if method == METHODS[1]:
            require(row["source_sha256"] == SOURCE_SHA and row["class_sha256"] == CLASS_SHA,
                    "table does not identify the selected V5 implementation")
        timing = {stat: number(row[f"tht_scheduled_release_{stat}_seconds"]) for stat in STATS}
        if load == 2.0 or not complete:
            require(all(v is None for v in timing.values()), "forbidden 2x/incomplete timing leaked into source table")
        elif all(v is not None for v in timing.values()):
            require(row["formal_timing_status"] == "FULL_POPULATION_RAW_BAG_TIMING", "timing is not formally eligible")
            require(timing["min"] <= timing["mean"] <= timing["max"], "THT statistics out of order")
        row_key = (map_name, load, seed)
        identity = row["workload_identity_sha256"]
        require(bool(identity), "missing paired workload identity")
        require(row_key not in paired or paired[row_key] == identity, "methods do not share the same seed workload")
        paired[row_key] = identity
        indexed[key] = {"raw_bag_count": raw_count, "complete": complete, "TH": completed, "THT": timing}
    require(allow_partial or len(indexed) == 180, "final figures require all 180 cells; --allow-partial is preview only")
    require(bool(indexed), "empty comparison table")
    return indexed


def summarize(indexed: dict) -> list[dict]:
    groups = []
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for method in METHODS:
                records = [(seed, indexed[(map_name, load, seed, method)]) for seed in external.SEEDS
                           if (map_name, load, seed, method) in indexed]
                full = len(records) == len(external.SEEDS)
                populations_complete = full and all(row["complete"] for _, row in records)
                if load == 2.0:
                    timing_status = "NA_2X_PROTOCOL"
                elif not full:
                    timing_status = "NA_MISSING_FROZEN_SEEDS"
                elif not populations_complete:
                    timing_status = "NA_INCOMPLETE_RAW_POPULATION"
                elif any(row["THT"][stat] is None for _, row in records for stat in STATS):
                    timing_status = "NA_MISSING_TIMING"
                else:
                    timing_status = "ELIGIBLE_TEN_SEEDS"
                group = {"map": map_name, "load_factor": load, "method": method,
                    "observed_seed_count": len(records), "complete_population_seed_count": sum(row["complete"] for _, row in records),
                    "missing_seeds": [s for s in external.SEEDS if all(s != found for found, _ in records)],
                    "THT_status": timing_status, "TH_status": "ELIGIBLE_TEN_SEEDS" if full else "NA_MISSING_FROZEN_SEEDS",
                    "offered_raw_bags": external.EXPECTED_POPULATIONS[load][0], "statistics": {}}
                for metric in ("THT_min", "THT_mean", "THT_max", "TH"):
                    eligible = full if metric == "TH" else timing_status == "ELIGIBLE_TEN_SEEDS"
                    values = [row["TH"] if metric == "TH" else row["THT"][metric.split("_")[1]]
                              for _, row in records] if eligible else []
                    group["statistics"][metric] = {"seed_values": values,
                        "mean_across_seeds": statistics.fmean(values) if values else None,
                        "seed_range_low": min(values) if values else None,
                        "seed_range_high": max(values) if values else None}
                groups.append(group)
    return groups


def draw_group(ax, x: float, method: str, statistic: dict) -> None:
    values = statistic["seed_values"]
    color, marker = COLORS[method], MARKERS[method]
    center = statistic["mean_across_seeds"]
    low, high = statistic["seed_range_low"], statistic["seed_range_high"]
    ax.errorbar([x], [center], yerr=[[center - low], [high - center]], fmt="none",
                ecolor=color, elinewidth=1.2, capsize=3.5, zorder=3)
    jitter = [x + (i - 4.5) * .012 for i in range(10)]
    ax.scatter(jitter, values, color=color, marker=marker, s=12, alpha=.38, linewidths=0, zorder=4)
    ax.scatter([x], [center], color=color, marker=marker, s=48, edgecolors="white", linewidths=.8, zorder=5)


def axes_style(ax, *, count: bool) -> None:
    ax.set_xticks(range(3), ["1×", "1.75×", "2×"])
    ax.set_xlim(-.48, 2.48)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Workload load factor")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}" if count else "{x:,.0f}"))
    ax.grid(axis="y", color="#dddddd", linewidth=.65, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)


def render(groups: list[dict], output: Path, *, preview: bool = False, synthetic_qa: bool = False,
           control_audit: dict | None = None) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 11, "axes.labelsize": 10, "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.facecolor": "white"})
    indexed = {(g["map"], g["load_factor"], g["method"]): g for g in groups}
    legend = [Line2D([], [], color=COLORS[m], marker=MARKERS[m], linestyle="none", markersize=7, label=LABELS[m])
              for m in METHODS]
    prefix = "SYNTHETIC QA — NOT EXPERIMENT RESULTS\n" if synthetic_qa else "PARTIAL PREVIEW — missing groups suppressed\n" if preview else ""
    footnote = "Large points: mean of 10 seed statistics. Faint points: individual seeds. Whiskers: observed seed min–max (not confidence intervals)."
    provenance = "V5 is a disclosed-assumption DH reconstruction. G31/HCA use archived controls; the historical HCA build hash is unavailable."
    accounting_note = (f"HCA: {control_audit['affected_cell_count']}/{control_audit['audited_cell_count']} archived cells have segment-accounting anomalies; see control audit. Purple points are observed records, not clean capacity evidence."
                       if control_audit and control_audit["status"] != "NOT_PROVIDED" else
                       "HCA accounting qualification is not attached. Purple points are archived observations, not verified loss-free capacity evidence.")
    fig, axes = plt.subplots(2, 3, figsize=(14.4, 8.9))
    for row, map_name in enumerate(external.MAPS):
        for column, stat in enumerate(STATS):
            ax = axes[row, column]
            ax.set_title(f"{'Map2' if map_name == 'map2' else 'Nanning'} | THT {stat}")
            for x, load in enumerate(external.LOAD_FACTORS):
                if load == 2.0:
                    ax.axvspan(x - .36, x + .36, color="#f0f0f0", zorder=-1)
                    ax.text(x, .43, "N/A\n2× protocol", ha="center", va="center", color="#555555",
                            transform=ax.get_xaxis_transform(), fontsize=10)
                    continue
                for position, method in enumerate(METHODS):
                    group = indexed[(map_name, load, method)]
                    x_method = x + (position - 1) * .22
                    if group["THT_status"] == "ELIGIBLE_TEN_SEEDS":
                        draw_group(ax, x_method, method, group["statistics"]["THT_" + stat])
                    else:
                        reason = "unfinished" if group["THT_status"] == "NA_INCOMPLETE_RAW_POPULATION" else "missing data"
                        ax.text(x_method, .05, f"N/A\n{reason}", color=COLORS[method], fontsize=7.2,
                                ha="center", va="bottom", rotation=90, transform=ax.get_xaxis_transform())
            axes_style(ax, count=False)
            ax.set_ylabel("Seconds")
    fig.suptitle(prefix + "Scheduled-release THT: V5 reconstructed DH and archived G31/HCA observations", fontsize=14, y=.98)
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5, .092), ncol=3, frameon=False)
    fig.text(.5, .071, "Each bag: sum of segment (completion − common canonical scheduled release). Min/mean/max are bag-population statistics within each seed.", ha="center", fontsize=8.4)
    fig.text(.5, .048, footnote, ha="center", fontsize=8.4)
    fig.text(.5, .026, provenance, ha="center", fontsize=8.2, color="#555555")
    fig.text(.5, .008, accounting_note, ha="center", fontsize=8.0, color="#604266")
    fig.subplots_adjust(left=.065, right=.985, top=.90 if not prefix else .87, bottom=.20, hspace=.38, wspace=.30)
    paths = []
    for extension in ("png", "pdf"):
        path = output / ("feng_dh_v5_tht_min_mean_max_20260905." + extension)
        fig.savefig(path, dpi=220, metadata={"Creator": "plot_feng_dh_v5_comparison.py"})
        paths.append(path)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.7))
    for ax, map_name in zip(axes, external.MAPS):
        ax.set_title("Map2" if map_name == "map2" else "Nanning")
        offered = [external.EXPECTED_POPULATIONS[load][0] for load in external.LOAD_FACTORS]
        ax.plot(range(3), offered, color="#777777", linestyle=":", marker="D", markersize=4,
                markerfacecolor="white", linewidth=1.1, label="Offered raw bags", zorder=2)
        for x, load in enumerate(external.LOAD_FACTORS):
            for position, method in enumerate(METHODS):
                group = indexed[(map_name, load, method)]
                x_method = x + (position - 1) * .22
                if group["TH_status"] == "ELIGIBLE_TEN_SEEDS":
                    draw_group(ax, x_method, method, group["statistics"]["TH"])
                else:
                    ax.text(x_method, .05, "N/A\nmissing seeds", color=COLORS[method], fontsize=8,
                            rotation=90, ha="center", va="bottom", transform=ax.get_xaxis_transform())
        axes_style(ax, count=True)
        ax.set_ylabel("Completed raw bags (TH)")
    fig.suptitle(prefix + "Fixed-horizon TH: V5 reconstructed DH and archived G31/HCA observations", fontsize=14, y=.98)
    all_handles = legend + [Line2D([], [], color="#777777", linestyle=":", marker="D", markerfacecolor="white", markersize=4, label="Offered raw bags")]
    fig.legend(handles=all_handles, loc="lower center", bbox_to_anchor=(.5, .125), ncol=4, frameon=False)
    fig.text(.5, .104, "TH = completed raw-bag count by absolute model epoch 98,259 s. Includes every load; unfinished bags remain in the fixed denominator.", ha="center", fontsize=8.4)
    fig.text(.5, .073, footnote, ha="center", fontsize=8.4)
    fig.text(.5, .040, provenance, ha="center", fontsize=8.2, color="#555555")
    fig.text(.5, .012, accounting_note, ha="center", fontsize=8.0, color="#604266")
    fig.subplots_adjust(left=.075, right=.985, top=.84 if not prefix else .80, bottom=.28, wspace=.24)
    for extension in ("png", "pdf"):
        path = output / ("feng_dh_v5_fixed_horizon_th_20260905." + extension)
        fig.savefig(path, dpi=220, metadata={"Creator": "plot_feng_dh_v5_comparison.py"})
        paths.append(path)
    plt.close(fig)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=Path, default=CELLS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--allow-partial", action="store_true", help="Preview only; never estimate groups from fewer than ten seeds")
    parser.add_argument("--control-notes", type=Path, default=CONTROL_NOTES, help="Optional control-accounting interpretation sidecar")
    args = parser.parse_args()
    input_sha = sha(args.cells)
    indexed = load_cells(args.cells, allow_partial=args.allow_partial)
    require(sha(args.cells) == input_sha, "input table changed while being read")
    groups = summarize(indexed)
    control_audit = load_control_audit(args.control_notes)
    outputs = render(groups, args.output_dir, preview=len(indexed) < 180, control_audit=control_audit)
    statistics_path = args.output_dir / "feng_dh_v5_plot_statistics_20260905.json"
    statistics_path.write_text(json.dumps(groups, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema": "czr005.feng_v5_scientific_figures.v1",
        "status": "FINAL_MATRIX" if len(indexed) == 180 else "PARTIAL_PREVIEW",
        "input_table": str(args.cells.resolve()), "input_table_sha256": input_sha, "observed_cells": len(indexed),
        "script_sha256": sha(Path(__file__)), "matplotlib_version": matplotlib.__version__,
        "source_sha256": SOURCE_SHA, "class_sha256": CLASS_SHA, "seeds": list(external.SEEDS),
        "interval_definition": "DESCRIPTIVE_MIN_MAX_OF_TEN_SEED_STATISTICS_NOT_CONFIDENCE_INTERVAL",
        "THT_definition": "SUM_OF_SEGMENT_COMPLETION_MINUS_SHARED_CANONICAL_SCHEDULED_RELEASE_PER_RAW_BAG",
        "THT_gate": "ALL_TEN_SEEDS_ALL_RAW_BAGS_COMPLETE_AND_LOAD_NOT_2X; OTHERWISE_NA_NO_SUBSET",
        "TH_definition": "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259",
        "provenance": "V5 reconstruction; archived G31/HCA; historical HCA runtime build hash unavailable",
        "control_accounting_audit": control_audit,
        "statistics": {"path": str(statistics_path.resolve()), "sha256": sha(statistics_path)},
        "figures": [{"path": str(path.resolve()), "sha256": sha(path)} for path in outputs]}
    require(sha(args.cells) == input_sha, "input table changed while figures were rendered; rerun against final export")
    if control_audit["sha256"] is not None:
        require(sha(args.control_notes) == control_audit["sha256"], "control audit changed while figures were rendered")
    (args.output_dir / "figure_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "figures": len(outputs), "cells": len(indexed)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
