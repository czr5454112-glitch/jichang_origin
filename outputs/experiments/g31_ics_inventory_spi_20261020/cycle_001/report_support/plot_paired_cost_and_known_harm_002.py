"""Render all 36 frozen training/development pairs; no formal data or refits.

Example:
  python -I -B plot_paired_cost_and_known_harm_002.py --output <fresh-directory>

Only the two SHA-pinned summary JSONs are experimental inputs. No dataset,
model, native result, callback stream, or formal/test artifact is opened.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
INPUTS = (
    ("pi0_training_label_summary_001.json",
     "7409b1038cbb705eb3e8944d34db2499e0078b3117fa31fe79a716c8b95f8e86",
     "g31.inventory_spi.training_label_summary.v1", 24),
    ("pi1_training_label_summary_001.json",
     "9867bb4995b51fee0a1cffbfd91c2d5d3f01ba329e2baeee77512103bbca7279",
     "g31.inventory_spi.round1_label_summary.v2", 12),
)
CAT = ("exact_harmed", "exact_improved", "exact_equal", "reference_only_finished",
       "candidate_only_finished", "both_arrived_unfinished", "both_not_yet_arrived")
TEAL, ORANGE = "#087e80", "#b85a24"
HARM, CENSORED = "#a33747", "#e6a0aa"
INK, MUTED, DEV_BG = "#152536", "#536273", "#eef4fa"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_summary(path, stage):
    path = Path(path).resolve()
    raw = path.read_bytes()
    filename, digest, schema, count = INPUTS[stage]
    if len(raw) > 2 * 1024**2 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Input bytes must match the frozen summary: " + filename)
    value = json.loads(raw)
    if value["schema"] != schema or len(value["pairs"]) != count:
        raise ValueError("Frozen stage schema/count mismatch")
    if value["test_data_opened"] is not False or value["models_read"] is not False:
        raise ValueError("Summary scope mismatch")
    rows = []
    for item in value["pairs"]:
        match = re.fullmatch(rf"r{stage}:P(\d+):root(\d+)", item["pair_slot_id"])
        if match is None or int(match[1]) != item["parent_seed"]:
            raise ValueError("Pair identity mismatch")
        parent, root = map(int, match.groups())
        split = "train" if 1101 <= parent <= 1108 else "dev"
        if item["split"] != split or not (1101 <= parent <= 1108 or 1201 <= parent <= 1204):
            raise ValueError("Unexpected split/parent")
        categories = item["completion_categories"]
        if any(type(categories[k]) is not int or categories[k] < 0 for k in CAT):
            raise ValueError("Non-integer completion count")
        if sum(categories[k] for k in CAT) != 28506:
            raise ValueError("Full population not retained")
        harm = categories["exact_harmed"] + categories["reference_only_finished"]
        if harm != item["known_direction_harm"]:
            raise ValueError("Known harm definition mismatch")
        gain = item["J_reference_minus_patch"]
        if not isinstance(gain, (float, int)) or not math.isfinite(gain):
            raise ValueError("Missing/nonfinite observed label")
        if abs(item["label_end"] - item["label_start"] - 1800.0) > 1e-6:
            raise ValueError("Unexpected label horizon")
        rows.append({
            "stage": stage, "pair_slot_id": item["pair_slot_id"], "parent_seed": parent,
            "root": root, "split": split, "gain_bag_seconds": gain,
            "known_direction_harm": harm, "exact_harmed": categories["exact_harmed"],
            "reference_only_finished": categories["reference_only_finished"],
        })
    rows.sort(key=lambda r: (r["parent_seed"], r["root"]))
    expected = {(p, k) for p in (*range(1101, 1109), *range(1201, 1205))
                for k in (range(2) if stage == 0 else range(1))}
    if {(r["parent_seed"], r["root"]) for r in rows} != expected or len(rows) != len(expected):
        raise ValueError("Must retain each fixed pair once; no subset selection")
    return rows, {"path": str(path), "sha256": digest, "schema": schema}


def counts(rows):
    result = {}
    for split in ("train", "dev", "all"):
        selected = [r for r in rows if split == "all" or r["split"] == split]
        signs = Counter("positive" if r["gain_bag_seconds"] > 0 else
                        "negative" if r["gain_bag_seconds"] < 0 else "zero" for r in selected)
        result[split] = {
            "pairs": len(selected),
            "gain_signs": {k: signs[k] for k in ("positive", "negative", "zero")},
            "positive_gain_and_known_harm_pairs": sum(
                r["gain_bag_seconds"] > 0 and r["known_direction_harm"] > 0 for r in selected),
            "known_harm_pair_job_count": sum(r["known_direction_harm"] for r in selected),
        }
    return result


def setup_font():
    for family in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei"):
        try:
            path = font_manager.findfont(font_manager.FontProperties(family=family),
                                        fallback_to_default=False)
            plt.rcParams.update({
                "font.family": family, "axes.unicode_minus": False,
                "font.size": 10.5, "axes.titlesize": 11.5, "axes.labelsize": 10.5,
                "svg.fonttype": "path", "svg.hashsalt": "g31-pairs-cost-harm-002",
                "savefig.facecolor": "white", "figure.facecolor": "white",
            })
            return {"family": family, "path": path, "sha256": sha(path)}
        except ValueError:
            pass
    raise RuntimeError("A Chinese font is required; install Microsoft YaHei or Noto Sans CJK SC.")


def draw_stage(fig, grid, rows, stage):
    gain_ax = fig.add_subplot(grid[0])
    harm_ax = fig.add_subplot(grid[1], sharey=gain_ax)
    n = len(rows)
    n_train = sum(r["split"] == "train" for r in rows)
    y = list(range(n))
    for ax in (gain_ax, harm_ax):
        ax.axhspan(n_train - .5, n - .5, facecolor=DEV_BG, zorder=0)
        ax.axhline(n_train - .5, color="#7e95ac", linewidth=1, linestyle=(0, (3, 3)))
        for line in ("top", "right", "left"):
            ax.spines[line].set_visible(False)
        ax.spines["bottom"].set_color("#9ba9b7")
        ax.grid(axis="x", color="#dfe5eb", linewidth=.65, zorder=0)
        ax.set_ylim(n - .45, -.65)
        ax.tick_params(axis="both", colors=MUTED, length=0, pad=6)
    gains = [r["gain_bag_seconds"] / 1000.0 for r in rows]
    gain_ax.barh(y, gains, height=.63,
                 color=[TEAL if v > 0 else ORANGE if v < 0 else "#82909e" for v in gains],
                 zorder=3)
    gain_ax.axvline(0, color="#8995a1", linewidth=1, zorder=2)
    for pos, val in enumerate(gains):
        if val == 0:
            gain_ax.plot(0, pos, "o", color="#82909e", markersize=3.2, zorder=4)
        gain_ax.annotate(f"{val:+.3f}" if val else "0.000", (val, pos),
                         xytext=(4 if val >= 0 else -4, 0), textcoords="offset points",
                         ha="left" if val >= 0 else "right", va="center",
                         fontsize=9.3, color=INK)
    gain_ax.set_xlim(-4.3, 8.65)
    gain_ax.set_xticks([-3, 0, 3, 6])
    gain_ax.set_xlabel("ΔJ（10³ bag·s）\n正值：总成本下降", labelpad=10)
    gain_ax.set_yticks(y)
    gain_ax.set_yticklabels([f"P{r['parent_seed']} / {r['root']}" for r in rows],
                           fontsize=10, color=INK)
    gain_ax.set_title("总成本变化", loc="left", color=INK, pad=12, fontweight="bold")
    exact = [r["exact_harmed"] for r in rows]
    censored = [r["reference_only_finished"] for r in rows]
    harm_ax.barh(y, exact, height=.63, color=HARM, zorder=3)
    harm_ax.barh(y, censored, left=exact, height=.63, color=CENSORED, hatch="///",
                 edgecolor=HARM, linewidth=0, zorder=3)
    for pos, row in enumerate(rows):
        harm = row["known_direction_harm"]
        if harm == 0:
            harm_ax.plot(0, pos, "o", markersize=3.2, color="#82909e", zorder=4)
        harm_ax.annotate(str(harm), (harm, pos), xytext=(4, 0), textcoords="offset points",
                         ha="left", va="center", fontsize=10, color=INK)
    harm_ax.set_xlim(-.6, 30)
    harm_ax.set_xticks([0, 10, 20, 30])
    harm_ax.tick_params(axis="y", left=False, labelleft=False)
    harm_ax.set_xlabel("已知完成方向受损\n件 / 配对", labelpad=10)
    harm_ax.set_title("已知完成方向受损", loc="left", color=INK, pad=12, fontweight="bold")
    # Group labels use axes-relative positions to avoid touching pair identifiers.
    gain_ax.text(-.37, 1.015, "父 / 根", transform=gain_ax.transAxes,
                 color=MUTED, fontsize=10, va="bottom")
    for ax in (gain_ax, harm_ax):
        ax.set_axisbelow(True)
    bbox = gain_ax.get_position()
    fig.text(bbox.x0, .875, f"π{stage}   {n} 个真实配对｜训练 {n_train} · 开发 {n - n_train}",
             fontsize=13, fontweight="bold", color=INK)
    return gain_ax, harm_ax


def main(pi0, pi1, output):
    rows0, ref0 = load_summary(pi0, 0)
    rows1, ref1 = load_summary(pi1, 1)
    all_rows = rows0 + rows1
    summary = {"pi0": counts(rows0), "pi1": counts(rows1), "all": counts(all_rows)}
    positive = summary["all"]["all"]["gain_signs"]["positive"]
    harmed_positive = summary["all"]["all"]["positive_gain_and_known_harm_pairs"]
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Use a fresh output directory; existing figures are preserved.")
    font = setup_font()
    fig = plt.figure(figsize=(17, 13.2), layout=None)
    outer = fig.add_gridspec(1, 2, left=.09, right=.965, bottom=.235, top=.835, wspace=.36)
    for stage, rows in enumerate((rows0, rows1)):
        inner = outer[stage].subgridspec(1, 2, width_ratios=[1.8, 1.1], wspace=.14)
        draw_stage(fig, inner, rows, stage)
    fig.text(.055, .963, "总成本改善，并不等于完成服务无损", fontsize=23,
             fontweight="bold", color=INK, va="top")
    fig.text(.055, .922,
             f"全部 36 个配对：{positive} 个 ΔJ > 0，其中 {harmed_positive} 个仍有已知完成方向受损",
             fontsize=14, color=HARM)
    fig.legend(handles=[
        Patch(facecolor=TEAL, label="ΔJ > 0：成本改善"),
        Patch(facecolor=ORANGE, label="ΔJ < 0：成本恶化"),
        Patch(facecolor=HARM, label="精确完成变晚"),
        Patch(facecolor=CENSORED, hatch="///", edgecolor=HARM, label="仅 reference 完成（删失方向）"),
        Patch(facecolor=DEV_BG, label="浅蓝底：开发集；白底：训练集"),
    ], loc="lower left", bbox_to_anchor=(.05, .112), ncol=3, frameon=False,
       fontsize=10.4, handlelength=1.8, columnspacing=2.1)
    notes = [
        "ΔJ = Jreference − Jpatch；每项为预登记单次替代后的 1800 s 标签，每个配对保留全部 28,506 件任务。",
        "已知完成方向受损 = 精确完成变晚 + 仅 reference 完成；不是纯精确延误计数。0 表示未观察到该方向伤害，≠ 全指标非劣。",
        "两阶段复用 12 个合成父谱系；36 个配对不是 36 个独立机场日。此图不是正式检验、冻结策略收益或 RL 增益证明。",
    ]
    for index, line in enumerate(notes):
        fig.text(.055, .087 - index * .023, line, fontsize=10.5, color=MUTED, va="top")
    output.mkdir()
    png = output / "paired_cost_and_known_harm_002.png"
    svg = output / "paired_cost_and_known_harm_002.svg"
    fig.savefig(png, dpi=240, metadata={"Software": "matplotlib; fixed paired summaries"})
    fig.savefig(svg, metadata={"Date": None, "Description": "All 36 fixed registered paired labels; no formal data."})
    plt.close(fig)
    receipt = {
        "schema": "g31.inventory_spi.paired_cost_known_harm_figure.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "rendered_all_frozen_pairs_no_experiment_or_formal_data",
        "inputs": [ref0, ref1], "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
        "outputs": [{"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size} for p in (png, svg)],
        "software": {"python": platform.python_version(), "matplotlib": matplotlib.__version__, "font": font},
        "statistics": summary, "plotted_pairs": all_rows,
        "scope": {
            "population_per_pair": 28506, "label_horizon_seconds": 1800,
            "all_registered_pairs_included": True, "pair_filtering": False,
            "known_harm": "exact_harmed + reference_only_finished; includes a censored direction",
            "known_harm_totals": "Repeated pair-job counts, not unique bags or independent airport days.",
            "zero_harm_is_strict_nonharm": False,
            "learned_policy_gain_or_formal_test": False,
            "formal_outcomes_read": 0, "native_runs": 0, "fits": 0, "new_tests": 0,
        },
        "reproduction": "Run the script with the exact pinned summaries and a fresh --output directory. "
                        "Numbers/order are pinned; byte-identical rendering also depends on the saved software/font versions.",
    }
    path = output / "figure_receipt.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": {"path": str(path), "sha256": sha(path)},
                      "outputs": receipt["outputs"], "statistics": summary}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi0", default=str(HERE / INPUTS[0][0]))
    parser.add_argument("--pi1", default=str(HERE / INPUTS[1][0]))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    main(args.pi0, args.pi1, args.output)
