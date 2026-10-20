"""Render only a supplied offline-review JSON; never open native/test run files.

Real results (explicit opt-in):
  python render_results.py --input path/to/prospective_offline_review.json --output figures
Hand-written, unmistakably labelled layout verification:
  python render_results.py --demo --output dummy_validation

The three primary model seeds remain separate within each of the two fixed
synthetic parents. Resource C11 is the preregistered mixed-domain seed 29.
No test-based selection, fitting, imputation, uncertainty interval or pooling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, ScalarFormatter

SCHEMA = "g31.airport.prospective_offline_review.v1"
PARENTS = (901, 902)
PRIMARY_SEEDS = (17, 29, 43)
FLEETS = (18, 22, 26)
COLORS = {"C00": "#64748B", "C10": "#0072B2", "C11": "#D55E00"}
SEED_COLORS = {17: "#0072B2", 29: "#D55E00", 43: "#009E73"}
SOURCE_SCOPE = (
    "Two conditional synthetic parents share one historical workload template. "
    "Training seeds are repeated fits, not independent airport days."
)


def require(condition, message):
    if not condition:
        raise ValueError("render_results:" + message)


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def source_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def indexes(review):
    require(review.get("schema") == SCHEMA, "unsupported_review_schema")
    require(review.get("all_parents_conditional_synthetic") is True
        and review.get("independent_parent_count") == 2
        and review.get("independent_real_airport_days") == 0, "explicit_two_synthetic_parent_scope")
    rows, names, comparisons = {}, {}, {}
    for row in review["rows"]:
        key = (row["batch"], row["fleet"], row["parent_seed"], row["variant"], row["model_seed"])
        require(key not in rows and row["name"] not in names, "duplicate_registered_cell")
        rows[key], names[row["name"]] = row, row
    for comparison in review["comparisons"]:
        key = (comparison["reference"], comparison["candidate"])
        require(key not in comparisons, "duplicate_comparison")
        comparisons[key] = comparison
    return rows, comparisons


def cost_status(row):
    if row is None:
        return None, "missing row"
    if row.get("status") != "complete":
        return None, row.get("status", "missing status")
    cost = row.get("full_window_cost")
    if cost is None:
        return None, "missing full cost"
    require(cost["physical_population"] == 28506 and cost["label_start"] == 7200.
        and cost["label_end"] == 59400., "wrong_population_or_cost_window")
    require(finite_number(cost["backlog_integral_bag_seconds"])
        and cost["backlog_integral_bag_seconds"] >= 0., "invalid_integral")
    for key in ("completed_by_end", "on_time_by_end"):
        require(type(cost[key]) is int and 0 <= cost[key] <= 28506, "invalid_service_count")
    require(cost["on_time_by_end"] <= cost["completed_by_end"], "on_time_exceeds_complete")
    return cost, "complete"


def extract_points(review):
    """Return plotting data without silently filling any unavailable outcome."""
    rows, comparisons = indexes(review)
    primary, reactive, resource = [], [], []
    for parent in PARENTS:
        reference = rows.get(("D", 22, parent, "C10", None))
        old, old_status = cost_status(reference)
        for seed in PRIMARY_SEEDS:
            candidate = rows.get(("D", 22, parent, "C11", seed))
            new, new_status = cost_status(candidate)
            item = {"parent_seed": parent, "model_seed": seed, "fleet": 22,
                "training_domain": "primary_22", "gain_bag_seconds": None,
                "reference": reference["name"] if reference else None,
                "candidate": candidate["name"] if candidate else None,
                "status": "unavailable"}
            if candidate:
                require(candidate["training_domain"] == "primary_22", "primary_domain_mismatch")
            comparison = comparisons.get((item["reference"], item["candidate"]))
            if old is None or new is None:
                item["reason"] = f"C10: {old_status}; C11: {new_status}"
                item["display_reason"] = ("C10: "+old_status) if old is None else ("C11: "+new_status)
            elif not comparison or comparison.get("status") != "complete_same_resource_comparison" \
                    or comparison.get("common_sources_and_full_warmup_verified") is not True:
                item["reason"] = "missing verified same-resource comparison"
                item["display_reason"] = "comparison unverified"
            else:
                gain = comparison.get("advantage_bag_seconds")
                require(finite_number(gain), "nonfinite_verified_gain")
                require(abs(gain-(old["backlog_integral_bag_seconds"]
                    - new["backlog_integral_bag_seconds"])) <= 1e-6, "gain_disagrees_with_review_costs")
                item.update(status="complete_verified", gain_bag_seconds=gain,
                    per_job_comparison=comparison.get("per_job_comparison"),
                    maximum_known_delay_seconds=comparison.get("maximum_known_delay_seconds"))
            primary.append(item)
        current_only = rows.get(("D", 22, parent, "C00", None))
        current_cost, current_status = cost_status(current_only)
        for seed in PRIMARY_SEEDS:
            candidate = rows.get(("D", 22, parent, "C11", seed))
            new, new_status = cost_status(candidate)
            item = {"parent_seed": parent, "model_seed": seed, "fleet": 22,
                "training_domain": "primary_22", "gain_bag_seconds": None,
                "reference": current_only["name"] if current_only else None,
                "candidate": candidate["name"] if candidate else None, "status": "unavailable",
                "comparison_scope": "Full-row cost arithmetic versus C00; primary learning attribution remains C11 versus C10.",
                "per_job_comparison_recomputed_by_renderer": False}
            if current_cost is None or new is None:
                item["reason"] = f"C00: {current_status}; C11: {new_status}"
                item["display_reason"] = ("C00: "+current_status) if current_cost is None else ("C11: "+new_status)
            else:
                for field in ("input_semantic_sha256", "jobs_digest", "initial_trays_digest", "binary_sha256"):
                    require(isinstance(current_only.get(field), str) and bool(current_only[field])
                        and current_only[field] == candidate.get(field), "reactive_comparison_identity:"+field)
                gain = current_cost["backlog_integral_bag_seconds"] - new["backlog_integral_bag_seconds"]
                item.update(status="complete_row_arithmetic", gain_bag_seconds=gain,
                    common_physical_input_identity_verified=True)
            reactive.append(item)
        parent_digests = set()
        for variant in ("C00", "C10", "C11"):
            for fleet in FLEETS:
                batch = "G" if variant == "C11" or fleet != 22 else "D"
                row = rows.get((batch, fleet, parent, variant, 29 if variant == "C11" else None))
                cost, status = cost_status(row)
                if row and variant == "C11":
                    require(row["training_domain"] == "mixed_18_22_26", "resource_domain_mismatch")
                if cost is not None:
                    require(isinstance(row.get("jobs_digest"), str) and bool(row["jobs_digest"]),
                        "resource_workload_identity_missing")
                    parent_digests.add(row["jobs_digest"])
                resource.append({"parent_seed": parent, "fleet": fleet, "variant": variant,
                    "model_seed": 29 if variant == "C11" else None,
                    "training_domain": "mixed_18_22_26" if variant == "C11" else None,
                    "run": row["name"] if row else None, "status": status,
                    "completed": cost["completed_by_end"] if cost else None,
                    "on_time": cost["on_time_by_end"] if cost else None})
        require(len(parent_digests) <= 1, "resource_curves_do_not_share_workload")
    return {"primary_gain": primary, "primary_reactive_gain": reactive, "resource_service": resource}


def style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 12, "axes.labelsize": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.axisbelow": True, "grid.color": "#DDE2E7", "grid.linewidth": .6,
        "savefig.dpi": 220, "pdf.fonttype": 42, "ps.fonttype": 42,
    })


def watermark(fig, demo):
    if demo:
        fig.text(.5, .5, "DUMMY — NOT EXPERIMENT RESULTS", ha="center", va="center",
            fontsize=26, color="#B91C1C", alpha=.16, rotation=22)


def gain_figure(points, *, demo=False, baseline="C10"):
    require(baseline in ("C00", "C10"), "supported_gain_baseline")
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 5.8), sharey=True)
    all_gains = [row["gain_bag_seconds"] for row in points if row["gain_bag_seconds"] is not None]
    span = max([abs(value) for value in all_gains] + [1.])
    lower, upper = min(all_gains+[0.]), max(all_gains+[0.])
    pad = .20*max(upper-lower, span)
    for ax, parent in zip(axes, PARENTS):
        ax.set_title(f"Conditional synthetic parent {parent}")
        ax.axhline(0, color="#475569", lw=1.0, zorder=1)
        ax.grid(axis="y")
        ax.set_ylim(lower-pad, upper+pad)
        ax.set_xlim(-.45, 2.45)
        ax.set_xticks(range(3), [str(seed) for seed in PRIMARY_SEEDS])
        ax.set_xlabel("Primary training seed (all preregistered fits)")
        formatter = ScalarFormatter(useMathText=True)
        formatter.set_powerlimits((-3, 4))
        ax.yaxis.set_major_formatter(formatter)
        for x, seed in enumerate(PRIMARY_SEEDS):
            row = next(r for r in points if r["parent_seed"] == parent and r["model_seed"] == seed)
            gain = row["gain_bag_seconds"]
            if gain is None:
                ax.text(x, .025, "UNAVAILABLE\n"+row["display_reason"], transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=8, color="#9F1239",
                    bbox={"facecolor": "#FFF1F2", "edgecolor": "#FDA4AF", "pad": 3})
            else:
                ax.scatter(x, gain, s=80, color=SEED_COLORS[seed], edgecolor="white",
                    linewidth=.9, zorder=3)
                ax.annotate(f"{gain:+,.3f}", (x, gain), xytext=(0, 12 if gain >= 0 else -17),
                    textcoords="offset points", ha="center", fontsize=9, color="#172033")
    axes[0].set_ylabel(f"Cost gain J({baseline}) − J(C11) [bag·s]\nPositive values favor C11")
    title = ("Primary N=22: paired-trained control versus the same-information C10 rule"
             if baseline == "C10" else
             "Primary N=22: paired-trained control versus the current-only C00 rule")
    fig.suptitle(title,
        fontsize=13, y=.97)
    fig.text(.5, .145, "J = complete-population unfinished-bag integral over 7,200–59,400 s.",
        ha="center", fontsize=9)
    fig.text(.5, .105, SOURCE_SCOPE, ha="center", fontsize=8.3, color="#475569")
    fig.text(.5, .065, ("No pooling, confidence intervals, test-based seed selection or zero-filled missing outcomes."
        if baseline == "C10" else
        "Full-row arithmetic. A gain over C10 need not beat C00; primary learning attribution still uses C10."),
        ha="center", fontsize=8.3, color="#475569")
    fig.text(.5, .025, "Aggregate gain does not certify per-job nonharm; harmed and unknown counts remain in the review.",
        ha="center", fontsize=8.3, color="#475569")
    fig.subplots_adjust(left=.10, right=.97, top=.83, bottom=.28, wspace=.15)
    watermark(fig, demo)
    return fig


def service_figure(points, *, demo=False):
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.8), sharex=True, sharey="row")
    styles = {"C00": ("--", "s"), "C10": ("-", "o"), "C11": ("-", "^")}
    for column, parent in enumerate(PARENTS):
        axes[0, column].set_title(f"Conditional synthetic parent {parent}")
        for row_number, metric in enumerate(("completed", "on_time")):
            ax = axes[row_number, column]
            ax.grid(axis="y")
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.set_xticks(FLEETS)
            ax.set_xlim(17.3, 26.7)
            missing = []
            for variant in ("C00", "C10", "C11"):
                series = [next(r for r in points if r["parent_seed"] == parent
                    and r["fleet"] == fleet and r["variant"] == variant) for fleet in FLEETS]
                values = [r[metric] if r[metric] is not None else math.nan for r in series]
                linestyle, marker = styles[variant]
                ax.plot(FLEETS, values, linestyle=linestyle, marker=marker, color=COLORS[variant],
                    lw=1.5, ms=6, zorder=3, label=variant)
                missing.extend(f"{variant}, N={r['fleet']}: {r['status']}"
                    for r in series if r[metric] is None)
            if missing:
                ax.text(.025, .97, "Unavailable (line breaks):\n"+"\n".join(missing),
                    transform=ax.transAxes, ha="left", va="top", fontsize=7.5, color="#9F1239",
                    bbox={"facecolor": "#FFF1F2", "edgecolor": "#FDA4AF", "pad": 3})
            if row_number == 1:
                ax.set_xlabel("Fixed physical fleet N")
    for row_number, metric in enumerate(("completed", "on_time")):
        if not any(row[metric] is not None for row in points):
            axes[row_number, 0].set_ylim(0., 1.)
            axes[row_number, 0].set_yticks([])
    axes[0, 0].set_ylabel("Completed by 59,400 s [bags]")
    axes[1, 0].set_ylabel("On-time completed by 59,400 s [bags]")
    legend = [Line2D([0], [0], color=COLORS[v], linestyle=styles[v][0], marker=styles[v][1],
        label={"C00": "C00: repaired current-only rule", "C10": "C10: same-information forecast rule",
            "C11": "C11: mixed-domain ranker, fixed seed 29"}[v]) for v in ("C00", "C10", "C11")]
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(.5, .925), ncol=1,
        frameon=False, fontsize=9)
    fig.suptitle("Fixed-fleet service outcomes: all preregistered resource points", fontsize=14, y=.98)
    fig.text(.5, .105, "N=22 C00/C10 reuse D; resource C11 always uses mixed_18_22_26, seed 29 (G).",
        ha="center", fontsize=8.5)
    fig.text(.5, .075, "Each line only connects the displayed fleet endpoints; it does not estimate untested fleets.",
        ha="center", fontsize=8.5, color="#475569")
    fig.text(.5, .045, SOURCE_SCOPE, ha="center", fontsize=8.3, color="#475569")
    fig.text(.5, .015, "Failed/missing branches remain absent. These curves do not certify replacement fleets or per-job protection.",
        ha="center", fontsize=8.3, color="#475569")
    fig.subplots_adjust(left=.10, right=.97, top=.78, bottom=.19, wspace=.14, hspace=.18)
    watermark(fig, demo)
    return fig


def dummy_review():
    """Hand-written illustration only, including failure, zero gain and loss."""
    rows, comparisons = [], []
    def add(batch, fleet, parent, variant, seed, cost, completed, on_time, status="complete"):
        name = f"DUMMY_{batch}_{fleet}_{parent}_{variant}_{seed}"
        row = dict(name=name, batch=batch, fleet=fleet, parent_seed=parent, variant=variant,
            model_seed=seed, training_domain=("primary_22" if batch == "D" else "mixed_18_22_26")
                if variant == "C11" else None,
            status=status, jobs_digest=f"DUMMY_ONLY_parent_{parent}",
            input_semantic_sha256=f"DUMMY_INPUT_{parent}_{fleet}",
            initial_trays_digest=f"DUMMY_TRAYS_{fleet}", binary_sha256="DUMMY_BINARY",
            full_window_cost=None if status != "complete" else dict(label_start=7200., label_end=59400.,
                physical_population=28506, backlog_integral_bag_seconds=cost,
                completed_by_end=completed, on_time_by_end=on_time))
        rows.append(row)
        return row
    for p_index, parent in enumerate(PARENTS):
        baseline = 10_000_000.+p_index*50_000.
        reference = add("D", 22, parent, "C10", None, baseline, 1000+p_index*20, 120+p_index*5)
        add("D", 22, parent, "C00", None, baseline+(-1000 if p_index == 0 else 2000),
            990+p_index*20, 118+p_index*5)
        for seed, gain in zip(PRIMARY_SEEDS, ((1500., 2400., 500.) if p_index == 0 else (0., 1700., -800.))):
            status = "failed" if parent == 901 and seed == 29 else "complete"
            candidate = add("D", 22, parent, "C11", seed, baseline-gain, 1002+p_index*20, 121, status)
            comparisons.append(dict(reference=reference["name"], candidate=candidate["name"],
                status="complete_same_resource_comparison" if status == "complete" else "unknown_incomplete_branch",
                advantage_bag_seconds=gain if status == "complete" else None,
                common_sources_and_full_warmup_verified=status == "complete"))
        for fleet in FLEETS:
            for variant in ("C00", "C10", "C11"):
                if fleet == 22 and variant != "C11":
                    continue
                offset = {"C00": 0, "C10": 10, "C11": 15}[variant]
                add("G", fleet, parent, variant, 29 if variant == "C11" else None,
                    baseline-(fleet-22)*5000, 990+(fleet-22)*30+offset+p_index*20,
                    118+(fleet-22)*3+offset//3+p_index*5,
                    "not_run" if parent == 902 and fleet == 18 and variant == "C00" else "complete")
    return dict(schema=SCHEMA, rows=rows, comparisons=comparisons, interaction=[],
        independent_parent_count=2, independent_real_airport_days=0, all_parents_conditional_synthetic=True,
        strict_nonharm_certified=False, dummy_data=True,
        dummy_notice="HAND-WRITTEN LAYOUT DEMONSTRATION; NOT EXPERIMENT EVIDENCE")


def render(review, output, *, source, demo=False):
    require(bool(review.get("dummy_data")) == demo, "dummy_flag_must_match_explicit_render_mode")
    output = Path(output)
    require(not output.exists(), "fresh_output_directory_required")
    points = extract_points(review)
    output.mkdir(parents=True)
    style()
    prefix = "DUMMY_" if demo else ""
    figures = [("primary_C11_vs_C10_gain", gain_figure(points["primary_gain"], demo=demo)),
               ("primary_C11_vs_C00_gain", gain_figure(points["primary_reactive_gain"], demo=demo,
                                                      baseline="C00")),
               ("fixed_fleet_service_curves", service_figure(points["resource_service"], demo=demo))]
    files = []
    for name, figure in figures:
        for extension in ("png", "pdf", "svg"):
            path = output/f"{prefix}{name}.{extension}"
            figure.savefig(path, facecolor="white")
            files.append({"path": str(path.resolve()), "sha256": source_hash(path)})
        plt.close(figure)
    manifest = {"schema": "g31.prospective.scientific_figures.v1", "dummy_only": demo,
        "source_review": source, "renderer": {"path": str(Path(__file__).resolve()), "sha256": source_hash(__file__)},
        "figures": files, "points": points, "selection": {
            "parents": list(PARENTS), "primary_seeds": list(PRIMARY_SEEDS), "resource_fleets": list(FLEETS),
            "resource_training_domain": "mixed_18_22_26", "resource_seed": 29,
            "defined_from_registered_grid_not_test_outcomes": True},
        "scope": SOURCE_SCOPE, "missing_outcomes_imputed": False,
        "native_jobs_started": 0, "models_fit": 0, "raw_run_or_test_inputs_opened": False}
    (output/f"{prefix}figure_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--input", type=Path, help="Explicit already-built offline review JSON; no raw run reads")
    choice.add_argument("--demo", action="store_true", help="Only hand-written dummy data")
    parser.add_argument("--output", required=True, type=Path, help="Fresh directory; existing directories refused")
    args = parser.parse_args()
    if args.demo:
        review = dummy_review()
        source = {"kind": "hand_written_dummy", "real_experiment_results_read": False}
    else:
        review = json.loads(args.input.read_text(encoding="utf8"))
        source = {"path": str(args.input.resolve()), "sha256": source_hash(args.input)}
    result = render(review, args.output, source=source, demo=args.demo)
    print(json.dumps({"dummy_only": result["dummy_only"], "files": [f["path"] for f in result["figures"]]}))


if __name__ == "__main__":
    main()
