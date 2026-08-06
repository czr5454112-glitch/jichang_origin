#!/usr/bin/env python3
"""Render the G4IRSF17 evidence bundle without filling experimental gaps.

The campaign has several independently resumable tracks.  This reporter reads
their append-only CSV/JSON artifacts and makes one deterministic set of PNG
figures and Markdown decisions.  A missing or structurally insufficient input
produces a visible ``NOT_RUN / NO_EVIDENCE`` panel; it is never converted into
zero, a pass, or a promotion.

The final A--E research decision is emitted only after the matched ladder,
native-fault, and fixed-map scale tracks are all complete.  Before then the
report explicitly defers the decision instead of using an early canary as a
surrogate for full evidence.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]

MANIFEST = Path("artifacts/manifests/g4irsf17_campaign_manifest.json")
SYSTEM_PLAN = Path("artifacts/manifests/g4irsf17_system_campaign_plan.json")
G2_MATCHED_PILOT = Path("outputs/tables/g4irsf17_g2_matched_pilot.json")

WAIT_LEDGER = Path("outputs/tables/g4irsf17_source_wait_cause_ledger.csv")
WAIT_TOPOLOGY = Path("outputs/tables/g4irsf17_source_wait_topology_attribution.csv")
I1_EFFECTS = Path("outputs/tables/g4irsf17_i1_effects.csv")
FEATURE_ABLATION = Path("outputs/tables/g4irsf17_feature_ablation.csv")
ALIASING_REPORT = Path("outputs/reports/g4irsf17_state_aliasing_audit.md")
LADDER_TABLE = Path("outputs/tables/g4irsf17_closed_loop_ladder.csv")
FAULT_TABLE = Path("outputs/tables/g4irsf17_fault_results.csv")
SCALE_TABLE = Path("outputs/tables/g4irsf17_scale_results.csv")
INFLIGHT_MERGE_RECOVERY_COUNTER = (
    "merge_grant_inflight_fault_generation_recovery_count"
)
CAPACITY_CENSOR_CONTROL_STATUS = "CAPACITY_CENSORED_BY_EQUIVALENT_CONTROL"
CAPACITY_CENSOR_TREATMENT_STATUS = "NOT_RUN_CONTROL_CENSORED"
CAPACITY_CENSOR_TRACK_STATUS = "TERMINAL_WITH_CAPACITY_CENSORING"
CAPACITY_CENSOR_FINAL_DECISION = (
    "TERMINAL_WITH_CAPACITY_CENSORING_ACTIONABLE_PIVOT"
)
BASELINE_ONLY_LADDER_DECISION = "BASELINE_ONLY_NO_AUTHORIZED_CANDIDATE"
I1_SUPPORT_REPORT = Path("outputs/reports/g4irsf17_i1_causal_support.md")
I1_MODEL_REPORT = Path("outputs/reports/g4irsf17_i1_model_decision.md")

FIGURE_DIR = Path("outputs/figures")
REPORT_DIR = Path("outputs/reports")
EVIDENCE_INDEX = REPORT_DIR / "g4irsf17_evidence_index.md"
G2_REPORT = REPORT_DIR / "g4irsf17_g2_decision.md"
FAULT_REPORT = REPORT_DIR / "g4irsf17_native_fault_campaign.md"
SCALE_REPORT = REPORT_DIR / "g4irsf17_scale_benchmark.md"
FINAL_REPORT = REPORT_DIR / "g4irsf17_final_joint_decision.md"

LADDER_SEGMENTS = (144, 512, 2_048, 8_192, 43_603)
SCALE_FACTORS = (1, 2, 4, 8, 16)
FAULT_LOADS = (1, 4)
FAULT_CATEGORIES = (
    "single_noncritical_edge",
    "single_critical_bottleneck",
    "merge_edge_or_node",
    "source_first_edge",
    "ebs_related_edge",
    "two_nonadjacent_faults",
    "two_propagating_faults",
    "delayed_beacon",
    "dropped_intermediate_beacon",
    "repair_after_fault",
)
G2_SCREEN_SEGMENTS = (144, 512, 2_048, 8_192)
G2_SCREEN_RULES = ("M2", "M3", "M4", "M5", "M6")
G2_NEXT_PIVOT = "strictly-local just-in-time service-slot arbitration over a bounded pending set"
G2_EAGER_DIAGNOSTIC_STATUS = "CURRENT_EAGER_SEAM_DIAGNOSTIC_COMPLETE"

FIGURE_PATHS: dict[str, Path] = {
    "wait_reason_stacked": FIGURE_DIR / "g4irsf17_wait_reason_stacked.png",
    "source_blocker_time_heatmap": FIGURE_DIR / "g4irsf17_source_blocker_time_heatmap.png",
    "i1_effect_distribution": FIGURE_DIR / "g4irsf17_i1_effect_distribution.png",
    "i1_effect_coverage": FIGURE_DIR / "g4irsf17_i1_effect_coverage.png",
    "aliasing_before_after": FIGURE_DIR / "g4irsf17_aliasing_before_after.png",
    "ladder_tth": FIGURE_DIR / "g4irsf17_ladder_tth.png",
    "source_network_decomposition": FIGURE_DIR / "g4irsf17_source_network_decomposition.png",
    "scale_tth": FIGURE_DIR / "g4irsf17_scale_tth.png",
    "scale_compute": FIGURE_DIR / "g4irsf17_scale_compute.png",
    "fault_timeline": FIGURE_DIR / "g4irsf17_fault_timeline.png",
}

COLORS = ("#2f6690", "#d1495b", "#3a7d44", "#edae49", "#7353ba", "#4f6d7a")


@dataclass(frozen=True)
class FigureEvidence:
    key: str
    path: str
    status: str
    evidence_paths: tuple[str, ...]
    note: str


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    except (OSError, csv.Error):
        return []


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null", "nan", "—"}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _finite(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "pass", "passed"}:
            return True
        if lowered in {"false", "no", "0", "fail", "failed"}:
            return False
    return None


def _first_number(row: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        if name in row:
            value = _finite(row.get(name))
            if value is not None:
                return value
    return None


def _sort_key(value: Any) -> tuple[int, float | str]:
    number = _finite(value)
    return (0, number) if number is not None else (1, str(value))


def _configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "figure.titlesize": 12,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.20,
            "grid.linewidth": 0.6,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def _save_figure(fig: plt.Figure, path: Path, *, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "czr005 G4IRSF17 evidence reporter"},
    )
    plt.close(fig)


def _placeholder(
    root: Path,
    key: str,
    title: str,
    note: str,
    *,
    dpi: int,
    evidence_paths: Iterable[Path] = (),
    status: str = "NOT_RUN/NO_EVIDENCE",
    headline: str = "NOT_RUN / NO_EVIDENCE",
) -> FigureEvidence:
    path = root / FIGURE_PATHS[key]
    fig, axis = plt.subplots(figsize=(8.0, 3.6))
    axis.set_axis_off()
    axis.text(0.5, 0.60, headline, ha="center", va="center", fontsize=15, weight="bold")
    axis.text(0.5, 0.40, note, ha="center", va="center", fontsize=9, wrap=True)
    fig.suptitle(title)
    _save_figure(fig, path, dpi=dpi)
    return FigureEvidence(
        key=key,
        path=_relative(path, root),
        status=status,
        evidence_paths=tuple(_relative(value, root) for value in evidence_paths if value.is_file()),
        note=note,
    )


def _evidence(
    root: Path,
    key: str,
    note: str,
    evidence_paths: Iterable[Path],
) -> FigureEvidence:
    return FigureEvidence(
        key=key,
        path=FIGURE_PATHS[key].as_posix(),
        status="EVIDENCE",
        evidence_paths=tuple(_relative(value, root) for value in evidence_paths if value.is_file()),
        note=note,
    )


def _wait_reason_rows(
    topology: Sequence[Mapping[str, Any]], ledger: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = [row for row in topology if str(row.get("aggregation", "")).upper() == "CAUSE"]
    if rows:
        return [dict(row) for row in rows]
    grouped: dict[str, dict[str, float]] = {}
    for row in ledger:
        reason = str(row.get("reason", "UNKNOWN"))
        bucket = grouped.setdefault(reason, {"h5": 0.0, "off": 0.0, "positive": 0.0})
        bucket["h5"] += _finite(row.get("h5_native_wait_seconds")) or 0.0
        bucket["off"] += _finite(row.get("off_native_wait_seconds")) or 0.0
        bucket["positive"] += _finite(row.get("attributed_positive_additional_wait_seconds")) or 0.0
    return [
        {
            "reason": reason,
            "h5_native_wait_seconds": value["h5"],
            "off_native_wait_seconds": value["off"],
            "attributed_positive_additional_wait_seconds": value["positive"],
        }
        for reason, value in grouped.items()
    ]


def plot_wait_reason_stacked(root: Path, *, dpi: int) -> FigureEvidence:
    topology_path = root / WAIT_TOPOLOGY
    ledger_path = root / WAIT_LEDGER
    rows = _wait_reason_rows(_read_csv(topology_path), _read_csv(ledger_path))
    usable = [
        row
        for row in rows
        if _first_number(row, ("h5_native_wait_seconds", "off_native_wait_seconds")) is not None
    ]
    if not usable:
        return _placeholder(
            root,
            "wait_reason_stacked",
            "Source wait by explicit native reason",
            "No cause-level native source-wait ledger is available.",
            dpi=dpi,
            evidence_paths=(topology_path, ledger_path),
        )
    usable.sort(
        key=lambda row: -(
            _finite(row.get("attributed_positive_additional_wait_seconds"))
            or abs(
                (_finite(row.get("h5_native_wait_seconds")) or 0.0)
                - (_finite(row.get("off_native_wait_seconds")) or 0.0)
            )
        )
    )
    labels = [str(row.get("reason", "UNKNOWN")) for row in usable]
    off = np.asarray([_finite(row.get("off_native_wait_seconds")) or 0.0 for row in usable])
    h5 = np.asarray([_finite(row.get("h5_native_wait_seconds")) or 0.0 for row in usable])
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 4.8), gridspec_kw={"width_ratios": (1.45, 1.0)})
    axis = axes[0]
    bottoms = np.zeros(2)
    for index, (label, off_value, h5_value) in enumerate(zip(labels, off, h5)):
        values = np.asarray([off_value, h5_value])
        axis.bar([0, 1], values, bottom=bottoms, width=0.58, label=label, color=COLORS[index % len(COLORS)])
        bottoms += values
    axis.set_xticks([0, 1], ["Matched E4/off", "H5"])
    axis.set_ylabel("Native attributed wait (s)")
    axis.set_title("Total native wait by reason")
    legend_handles, legend_labels = axis.get_legend_handles_labels()
    axis.grid(axis="x", visible=False)
    delta_axis = axes[1]
    positive = np.asarray(
        [
            _finite(row.get("attributed_positive_additional_wait_seconds"))
            or max(0.0, h5_value - off_value)
            for row, h5_value, off_value in zip(usable, h5, off)
        ]
    )
    positions = np.arange(len(labels))
    delta_axis.barh(positions, positive, color=[COLORS[index % len(COLORS)] for index in range(len(labels))])
    delta_axis.set_yticks(positions, labels)
    delta_axis.tick_params(axis="y", labelsize=8)
    delta_axis.invert_yaxis()
    delta_axis.set_xlabel("Attributed positive H5−off wait (s)")
    delta_axis.set_title("Observed additional wait")
    delta_axis.grid(axis="y", visible=False)
    fig.suptitle("Source wait by mutually exclusive native blocker reason")
    fig.legend(legend_handles, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.03), ncol=2, frameon=False)
    fig.subplots_adjust(bottom=0.18, wspace=0.42)
    _save_figure(fig, root / FIGURE_PATHS["wait_reason_stacked"], dpi=dpi)
    return _evidence(root, "wait_reason_stacked", f"{len(usable)} explicit reason categories", (topology_path, ledger_path))


def plot_source_blocker_heatmap(root: Path, *, dpi: int) -> FigureEvidence:
    topology_path = root / WAIT_TOPOLOGY
    ledger_path = root / WAIT_LEDGER
    topology = _read_csv(topology_path)
    rows = [row for row in topology if str(row.get("aggregation", "")).upper() == "SOURCE_BLOCKER_TIME_LEG"]
    if not rows:
        rows = _read_csv(ledger_path)
    cells: dict[tuple[str, str], float] = {}
    for row in rows:
        source = str(row.get("source_node", "?") or "?")
        blocker = str(row.get("blocker_node", "?") or "?")
        leg = str(row.get("leg_type", "unknown") or "unknown")
        time_bucket = str(row.get("time_bucket", "?") or "?")
        value = _first_number(
            row,
            ("attributed_positive_additional_wait_seconds", "native_reason_wait_delta_seconds"),
        )
        if value is None:
            continue
        label = f"{source}→{blocker} ({leg})"
        cells[(label, time_bucket)] = cells.get((label, time_bucket), 0.0) + max(0.0, value)
    if not cells:
        return _placeholder(
            root,
            "source_blocker_time_heatmap",
            "Additional source wait: source / blocker / time",
            "No source-blocker-time attribution cells are available.",
            dpi=dpi,
            evidence_paths=(topology_path, ledger_path),
        )
    row_labels = sorted({key[0] for key in cells})
    col_labels = sorted({key[1] for key in cells}, key=_sort_key)
    matrix = np.asarray([[cells.get((left, right), 0.0) for right in col_labels] for left in row_labels])
    fig_height = max(3.8, min(9.0, 1.2 + 0.42 * len(row_labels)))
    fig, axis = plt.subplots(figsize=(max(7.2, 0.75 * len(col_labels) + 3.0), fig_height))
    image = axis.imshow(matrix, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    axis.set_xticks(range(len(col_labels)), col_labels)
    axis.set_yticks(range(len(row_labels)), row_labels)
    axis.set_xlabel("Hour bucket")
    axis.set_ylabel("Source → blocker (leg)")
    axis.set_title("Positive H5-minus-off source-wait attribution")
    colorbar = fig.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("Attributed additional wait (s)")
    axis.grid(False)
    _save_figure(fig, root / FIGURE_PATHS["source_blocker_time_heatmap"], dpi=dpi)
    return _evidence(root, "source_blocker_time_heatmap", f"{len(cells)} observed attribution cells", (topology_path, ledger_path))


def _i1_cost(row: Mapping[str, Any]) -> float | None:
    value = _first_number(
        row,
        (
            "system_cost_delta_seconds",
            "direct_bag_tth_sum_delta_seconds",
            "raw_bag_mean_tth_delta_seconds",
            "bag_tth_delta_seconds",
            "tth_delta_seconds",
            "effect_seconds",
        ),
    )
    if value is not None:
        return value
    utility = _finite(row.get("system_utility"))
    return -utility if utility is not None else None


def plot_i1_effect_distribution(root: Path, *, dpi: int) -> FigureEvidence:
    path = root / I1_EFFECTS
    rows = _read_csv(path)
    values = [value for row in rows if str(row.get("effect_label", "")).upper() != "EXCLUDED" for value in (_i1_cost(row),) if value is not None]
    if not values:
        return _placeholder(
            root,
            "i1_effect_distribution",
            "I1 paired causal effect distribution",
            "The real I1 paired-effect table is absent or has no eligible numeric effects.",
            dpi=dpi,
            evidence_paths=(path,),
        )
    fig, axis = plt.subplots(figsize=(8.2, 4.3))
    bins = min(40, max(8, int(math.sqrt(len(values))) * 2))
    axis.hist(values, bins=bins, color=COLORS[0], alpha=0.82, edgecolor="white")
    axis.axvline(0.0, color="#333333", linewidth=1.2)
    axis.set_xlabel("System cost delta (treatment − baseline, s; negative is better)")
    axis.set_ylabel("Eligible I1 opportunities")
    axis.set_title("I1 counterfactual system-effect distribution")
    _save_figure(fig, root / FIGURE_PATHS["i1_effect_distribution"], dpi=dpi)
    return _evidence(root, "i1_effect_distribution", f"{len(values)} eligible numeric paired effects", (path,))


def plot_i1_coverage(root: Path, *, dpi: int) -> FigureEvidence:
    path = root / I1_EFFECTS
    rows = _read_csv(path)
    labels = ("BENEFICIAL", "HARMFUL", "NEUTRAL", "EXCLUDED")
    if not rows or not any(str(row.get("effect_label", "")).upper() in labels for row in rows):
        return _placeholder(
            root,
            "i1_effect_coverage",
            "I1 beneficial / harmful coverage",
            "No labelled real I1 paired-effect rows are available.",
            dpi=dpi,
            evidence_paths=(path,),
        )
    splits = sorted({str(row.get("diagnostic_split", "all") or "all") for row in rows})
    counts = {
        split: [sum(str(row.get("diagnostic_split", "all") or "all") == split and str(row.get("effect_label", "")).upper() == label for row in rows) for label in labels]
        for split in splits
    }
    fig, axis = plt.subplots(figsize=(8.4, 4.4))
    bottoms = np.zeros(len(splits))
    for index, label in enumerate(labels):
        values = np.asarray([counts[split][index] for split in splits], dtype=float)
        axis.bar(range(len(splits)), values, bottom=bottoms, label=label, color=COLORS[index])
        bottoms += values
    axis.set_xticks(range(len(splits)), splits)
    axis.set_ylabel("Opportunity count")
    axis.set_xlabel("Diagnostic split")
    axis.set_title("I1 effect-label coverage (counts, not inferred rates)")
    axis.legend(frameon=False, ncol=2)
    axis.grid(axis="x", visible=False)
    _save_figure(fig, root / FIGURE_PATHS["i1_effect_coverage"], dpi=dpi)
    return _evidence(root, "i1_effect_coverage", f"{len(rows)} labelled/attempted rows across {len(splits)} splits", (path,))


def _aliasing_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def plot_aliasing(root: Path, *, dpi: int) -> FigureEvidence:
    report_path = root / ALIASING_REPORT
    ablation_path = root / FEATURE_ABLATION
    payload = _aliasing_payload(report_path)
    legacy = payload.get("legacy") if isinstance(payload.get("legacy"), Mapping) else {}
    augmented = payload.get("augmented") if isinstance(payload.get("augmented"), Mapping) else {}
    variance = [_finite(legacy.get("conditional_variance")), _finite(augmented.get("conditional_variance"))]
    disagreement = [_finite(legacy.get("sign_disagreement_rate")), _finite(augmented.get("sign_disagreement_rate"))]
    if all(value is None for value in (*variance, *disagreement)):
        return _placeholder(
            root,
            "aliasing_before_after",
            "State aliasing before / after local temporal features",
            "No completed before/after aliasing audit is available; an ablation table alone is not treated as a before/after result.",
            dpi=dpi,
            evidence_paths=(report_path, ablation_path),
        )
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 4.0))
    names = ("Legacy 29D", "Augmented local")
    for axis, values, title, ylabel in (
        (axes[0], variance, "Conditional variance", "Outcome variance"),
        (axes[1], disagreement, "Sign disagreement", "Rate"),
    ):
        numeric = [0.0 if value is None else value for value in values]
        bars = axis.bar(names, numeric, color=(COLORS[1], COLORS[2]), width=0.62)
        for bar, value in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), "N/A" if value is None else f"{value:.4g}", ha="center", va="bottom")
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.grid(axis="x", visible=False)
    fig.suptitle("Observed state aliasing: frozen representation vs bounded-local augmentation")
    _save_figure(fig, root / FIGURE_PATHS["aliasing_before_after"], dpi=dpi)
    return _evidence(root, "aliasing_before_after", "Completed legacy/augmented audit metrics", (report_path, ablation_path))


def _matched_ladder(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        segments = _integer(row.get("segments"))
        if segments is None:
            continue
        if str(row.get("comparison_status", "")).upper() not in {"MATCHED_COMPLETE", "COMPLETE", ""}:
            continue
        output.append(dict(row))
    return output


def plot_ladder(
    root: Path,
    *,
    dpi: int,
    manifest: Mapping[str, Any] | None = None,
) -> FigureEvidence:
    path = root / LADDER_TABLE
    rows = _matched_ladder(_read_csv(path))
    stage = _stage(manifest or {}, ("closed_loop_ladder",))
    metrics = (
        ("mean_tth_delta_seconds", "Mean Δ TTH (s)"),
        ("p95_tth_delta_seconds", "P95 Δ TTH (s)"),
        ("p99_tth_delta_seconds", "P99 Δ TTH (s)"),
    )
    if not rows or not any(_finite(row.get(name)) is not None for row in rows for name, _ in metrics):
        if (
            str(stage.get("status", "")).upper() == "COMPLETE"
            and str(stage.get("decision", "")).upper()
            == BASELINE_ONLY_LADDER_DECISION
        ):
            return _placeholder(
                root,
                "ladder_tth",
                "Matched closed-loop ladder: mean / P95 / P99",
                (
                    "The frozen E4/off baseline ladder completed at every planned "
                    "level, but no runtime candidate was authorized; therefore no "
                    "matched candidate delta can be plotted."
                ),
                dpi=dpi,
                evidence_paths=(path,),
                status=BASELINE_ONLY_LADDER_DECISION,
                headline="BASELINE ONLY / NO AUTHORIZED CANDIDATE",
            )
        return _placeholder(
            root,
            "ladder_tth",
            "Matched closed-loop ladder: mean / P95 / P99",
            "No matched G17 closed-loop ladder rows with numeric TTH deltas are available.",
            dpi=dpi,
            evidence_paths=(path,),
        )
    candidates = sorted({str(row.get("candidate_id", "candidate")) for row in rows})
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 3.8), sharex=True)
    for metric_index, (metric, ylabel) in enumerate(metrics):
        axis = axes[metric_index]
        for candidate_index, candidate in enumerate(candidates):
            pairs = sorted(
                [(_integer(row.get("segments")), _finite(row.get(metric))) for row in rows if str(row.get("candidate_id", "candidate")) == candidate],
                key=lambda pair: pair[0] or 0,
            )
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            if pairs:
                axis.plot([x for x, _ in pairs], [y for _, y in pairs], marker="o", label=candidate, color=COLORS[candidate_index % len(COLORS)])
        axis.axhline(0.0, color="#333333", linewidth=0.8)
        axis.set_xscale("log")
        axis.set_xlabel("Segments")
        axis.set_ylabel(ylabel)
        axis.set_title(ylabel.replace(" (s)", ""))
    if candidates:
        axes[-1].legend(frameon=False, loc="best")
    fig.suptitle("G17 candidate minus matched E4/off; negative is better")
    _save_figure(fig, root / FIGURE_PATHS["ladder_tth"], dpi=dpi)
    return _evidence(root, "ladder_tth", f"{len(rows)} matched ladder rows", (path,))


def _source_summary(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    stages = manifest.get("stages")
    if not isinstance(stages, Mapping):
        return {}
    direct = stages.get("source_wait_diagnosis")
    if isinstance(direct, Mapping) and isinstance(direct.get("summary"), Mapping):
        return direct["summary"]
    for name, value in stages.items():
        if "source_wait" in str(name).lower() and isinstance(value, Mapping) and isinstance(value.get("summary"), Mapping):
            return value["summary"]
    return {}


def plot_decomposition(root: Path, *, dpi: int, manifest: Mapping[str, Any]) -> FigureEvidence:
    ladder_path = root / LADDER_TABLE
    rows = [
        row
        for row in _matched_ladder(_read_csv(ladder_path))
        if _finite(row.get("source_wait_delta_mean_seconds")) is not None
        and _finite(row.get("network_time_delta_mean_seconds")) is not None
    ]
    evidence_paths: list[Path] = [ladder_path]
    labels: list[str] = []
    source: list[float] = []
    network: list[float] = []
    total: list[float] = []
    if rows:
        for row in sorted(rows, key=lambda value: (str(value.get("candidate_id", "")), _integer(value.get("segments")) or 0)):
            labels.append(f"{row.get('candidate_id', 'candidate')}\n{_integer(row.get('segments'))}")
            source.append(float(row["source_wait_delta_mean_seconds"]))
            network.append(float(row["network_time_delta_mean_seconds"]))
            total.append(_finite(row.get("mean_tth_delta_seconds")) or source[-1] + network[-1])
    else:
        summary = _source_summary(manifest)
        source_value = _finite(summary.get("source_wait_delta_mean_seconds_per_raw_bag"))
        network_value = _finite(summary.get("network_time_delta_mean_seconds_per_raw_bag"))
        total_value = _finite(summary.get("tth_delta_mean_seconds_per_raw_bag"))
        if source_value is not None and network_value is not None:
            labels = ["H5 @ 8,192"]
            source = [source_value]
            network = [network_value]
            total = [total_value if total_value is not None else source_value + network_value]
            evidence_paths.append(root / MANIFEST)
    if not labels:
        return _placeholder(
            root,
            "source_network_decomposition",
            "Source-wait vs network-time decomposition",
            "No matched decomposition with both source-wait and network-time deltas is available.",
            dpi=dpi,
            evidence_paths=evidence_paths,
        )
    x = np.arange(len(labels), dtype=float)
    width = 0.25
    fig, axis = plt.subplots(figsize=(max(7.2, 1.05 * len(labels) + 3.2), 4.4))
    axis.bar(x - width, source, width=width, label="Source wait Δ", color=COLORS[1])
    axis.bar(x, network, width=width, label="Network time Δ", color=COLORS[0])
    axis.bar(x + width, total, width=width, label="Total TTH Δ", color=COLORS[2])
    axis.axhline(0.0, color="#333333", linewidth=0.9)
    axis.set_xticks(x, labels)
    axis.set_ylabel("Seconds per raw bag (candidate − matched off)")
    axis.set_title("Where the observed time delta occurs")
    axis.legend(frameon=False, ncol=3)
    axis.grid(axis="x", visible=False)
    _save_figure(fig, root / FIGURE_PATHS["source_network_decomposition"], dpi=dpi)
    return _evidence(root, "source_network_decomposition", f"{len(labels)} matched decompositions", evidence_paths)


def _complete_scale(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if _integer(row.get("scale")) is not None
        and str(row.get("status", "")).upper() in {"COMPLETE", "HARD_GATE_FAILED"}
    ]


def plot_scale_tth(root: Path, *, dpi: int) -> FigureEvidence:
    path = root / SCALE_TABLE
    rows = _complete_scale(_read_csv(path))
    absolute = any(_finite(row.get("mean_tth_seconds")) is not None for row in rows)
    metrics = (
        ("mean_tth_seconds", "Mean TTH (s)"),
        ("p95_tth_seconds", "P95 TTH (s)"),
        ("p99_tth_seconds", "P99 TTH (s)"),
    ) if absolute else (
        ("mean_tth_delta_seconds", "Mean Δ TTH (s)"),
        ("p95_tth_delta_seconds", "P95 Δ TTH (s)"),
        ("p99_tth_delta_seconds", "P99 Δ TTH (s)"),
    )
    if not rows or not any(_finite(row.get(name)) is not None for row in rows for name, _ in metrics):
        return _placeholder(
            root,
            "scale_tth",
            "Fixed-map load scale vs TTH",
            "No completed G17 fixed-map scale rows with numeric TTH metrics are available.",
            dpi=dpi,
            evidence_paths=(path,),
        )
    candidates = sorted({str(row.get("candidate_id", "candidate")) for row in rows})
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 3.8), sharex=True)
    for metric_index, (metric, label) in enumerate(metrics):
        axis = axes[metric_index]
        for candidate_index, candidate in enumerate(candidates):
            pairs = sorted(
                [(_integer(row.get("scale")), _finite(row.get(metric))) for row in rows if str(row.get("candidate_id", "candidate")) == candidate],
                key=lambda pair: pair[0] or 0,
            )
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            if pairs:
                axis.plot([x for x, _ in pairs], [y for _, y in pairs], marker="o", color=COLORS[candidate_index % len(COLORS)], label=candidate)
        if not absolute:
            axis.axhline(0.0, color="#333333", linewidth=0.8)
        axis.set_xticks(SCALE_FACTORS, [f"{value}×" for value in SCALE_FACTORS])
        axis.set_xlabel("Fixed-map task-flow scale")
        axis.set_ylabel(label)
        axis.set_title(label.replace(" (s)", ""))
    axes[-1].legend(frameon=False, loc="best")
    fig.suptitle("Business time across fixed-map load scale" + ("" if absolute else "; candidate − matched off"))
    _save_figure(fig, root / FIGURE_PATHS["scale_tth"], dpi=dpi)
    return _evidence(root, "scale_tth", f"{len(rows)} completed scale rows", (path,))


def plot_scale_compute(root: Path, *, dpi: int) -> FigureEvidence:
    path = root / SCALE_TABLE
    rows = _complete_scale(_read_csv(path))
    if not rows or not any(_finite(row.get(name)) is not None for row in rows for name in ("wall_seconds", "peak_rss_mb", "peak_rss_overhead_mb")):
        return _placeholder(
            root,
            "scale_compute",
            "Fixed-map load scale vs wall time / RSS",
            "No completed scale rows with wall-time or RSS measurements are available.",
            dpi=dpi,
            evidence_paths=(path,),
        )
    candidates = sorted({str(row.get("candidate_id", "candidate")) for row in rows})
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0), sharex=True)
    for candidate_index, candidate in enumerate(candidates):
        selected = sorted([row for row in rows if str(row.get("candidate_id", "candidate")) == candidate], key=lambda row: _integer(row.get("scale")) or 0)
        wall = [(_integer(row.get("scale")), _finite(row.get("wall_seconds"))) for row in selected]
        wall = [(x, y) for x, y in wall if x is not None and y is not None]
        if wall:
            axes[0].plot([x for x, _ in wall], [y for _, y in wall], marker="o", color=COLORS[candidate_index % len(COLORS)], label=candidate)
        rss = [
            (
                _integer(row.get("scale")),
                _first_number(row, ("peak_rss_mb", "peak_rss_overhead_mb")),
            )
            for row in selected
        ]
        rss = [(x, y) for x, y in rss if x is not None and y is not None]
        if rss:
            axes[1].plot([x for x, _ in rss], [y for _, y in rss], marker="s", color=COLORS[candidate_index % len(COLORS)], label=candidate)
    axes[0].set_title("Wall time")
    axes[0].set_ylabel("Wall seconds")
    axes[1].set_title("Peak RSS (or reported Δ)")
    axes[1].set_ylabel("MB")
    for axis in axes:
        axis.set_xticks(SCALE_FACTORS, [f"{value}×" for value in SCALE_FACTORS])
        axis.set_xlabel("Fixed-map task-flow scale")
    axes[-1].legend(frameon=False, loc="best")
    fig.suptitle("Compute scaling is reported separately from business TTH")
    _save_figure(fig, root / FIGURE_PATHS["scale_compute"], dpi=dpi)
    return _evidence(root, "scale_compute", f"{len(rows)} completed resource rows", (path,))


def _fault_timeline_rows(root: Path, table_rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[Path]]:
    rows: list[dict[str, Any]] = []
    evidence: list[Path] = []
    for row in table_rows:
        onset = _first_number(row, ("fault_onset_seconds", "fault_onset", "onset_seconds"))
        repair = _first_number(row, ("repair_time_seconds", "repair_time", "reopen_time_seconds"))
        recovery = _first_number(row, ("fault_recovery_timestamp_seconds", "recovery_timestamp_seconds"))
        recovery_duration = _first_number(row, ("fault_recovery_time_seconds", "recovery_time_seconds"))
        if recovery is None and onset is not None and recovery_duration is not None:
            recovery = onset + recovery_duration
        if onset is not None and (repair is not None or recovery is not None):
            rows.append({"label": f"{row.get('candidate_id', '?')} | {row.get('scenario_id', row.get('fault_category', '?'))} | {row.get('scale', '?')}×", "onset": onset, "repair": repair, "recovery": recovery})
    runstate = root / "outputs/runstate/g4irsf17_system_campaign"
    if runstate.is_dir():
        for path in sorted(runstate.rglob("*.json")):
            payload = _read_json(path)
            job = payload.get("job") if isinstance(payload.get("job"), Mapping) else {}
            if str(job.get("track", "")) != "fault":
                continue
            descriptor = payload.get("fault_descriptor") if isinstance(payload.get("fault_descriptor"), Mapping) else {}
            onset = _first_number(descriptor, ("fault_onset", "fault_onset_seconds", "onset_seconds"))
            repair = _first_number(descriptor, ("repair_time", "repair_time_seconds", "reopen_time_seconds"))
            recovery = _first_number(payload, ("fault_recovery_timestamp_seconds", "recovery_timestamp_seconds"))
            recovery_duration = _first_number(payload, ("fault_recovery_time_seconds", "recovery_time_seconds"))
            if recovery is None and onset is not None and recovery_duration is not None:
                recovery = onset + recovery_duration
            if onset is None or (repair is None and recovery is None):
                continue
            rows.append(
                {
                    "label": f"{job.get('candidate_id', '?')} | {descriptor.get('scenario_id', job.get('job_id', '?'))} | {job.get('scale', '?')}×",
                    "onset": onset,
                    "repair": repair,
                    "recovery": recovery,
                }
            )
            evidence.append(path)
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        unique[(row["label"], row["onset"], row["repair"], row["recovery"])] = row
    return list(unique.values()), evidence


def plot_fault_timeline(root: Path, *, dpi: int) -> FigureEvidence:
    table_path = root / FAULT_TABLE
    rows, runstate_paths = _fault_timeline_rows(root, _read_csv(table_path))
    if not rows:
        return _placeholder(
            root,
            "fault_timeline",
            "Native fault onset / repair / recovery timeline",
            "No native fault result contains explicit onset plus repair/recovery time; recovery duration alone is not converted into a fabricated timeline.",
            dpi=dpi,
            evidence_paths=(table_path,),
        )
    rows.sort(key=lambda row: (str(row["label"]), float(row["onset"])))
    fig, axis = plt.subplots(figsize=(9.4, max(3.8, min(10.0, 1.3 + 0.38 * len(rows)))))
    for index, row in enumerate(rows):
        endpoints = [value for value in (row["repair"], row["recovery"]) if value is not None]
        axis.hlines(index, row["onset"], max(endpoints), color="#777777", linewidth=1.0)
        axis.scatter(row["onset"], index, color=COLORS[1], marker="x", s=40, label="Fault onset" if index == 0 else None)
        if row["repair"] is not None:
            axis.scatter(row["repair"], index, color=COLORS[3], marker="s", s=34, label="Repair/reopen" if index == 0 else None)
        if row["recovery"] is not None:
            axis.scatter(row["recovery"], index, color=COLORS[2], marker="o", s=34, label="Observed recovery endpoint" if index == 0 else None)
    axis.set_yticks(range(len(rows)), [str(row["label"]) for row in rows])
    axis.set_xlabel("Native runtime time (s, as recorded)")
    axis.set_title("Fault onset, repair/reopen, and observed recovery")
    axis.legend(frameon=False, ncol=3)
    axis.grid(axis="y", visible=False)
    _save_figure(fig, root / FIGURE_PATHS["fault_timeline"], dpi=dpi)
    return _evidence(root, "fault_timeline", f"{len(rows)} explicit native fault timelines", (table_path, *runstate_paths))


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    rendered = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    rendered.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(rendered)


def _stage(manifest: Mapping[str, Any], names: Sequence[str]) -> Mapping[str, Any]:
    stages = manifest.get("stages")
    if not isinstance(stages, Mapping):
        return {}
    for name in names:
        value = stages.get(name)
        if isinstance(value, Mapping):
            return value
    return {}


def _stage_complete(manifest: Mapping[str, Any], names: Sequence[str]) -> bool:
    return str(_stage(manifest, names).get("status", "")).upper() == "COMPLETE"


def _downstream_share(manifest: Mapping[str, Any], topology_rows: Sequence[Mapping[str, Any]]) -> float | None:
    value = _finite(_source_summary(manifest).get("downstream_backpressure_share"))
    if value is not None:
        return value
    cause_rows = [row for row in topology_rows if str(row.get("aggregation", "")).upper() == "CAUSE"]
    total = sum(_finite(row.get("attributed_positive_additional_wait_seconds")) or 0.0 for row in cause_rows)
    downstream = sum(
        _finite(row.get("attributed_positive_additional_wait_seconds")) or 0.0
        for row in cause_rows
        if str(row.get("cause_class", "")).upper() == "DOWNSTREAM_BACKPRESSURE"
    )
    return downstream / total if total > 0.0 else None


def _g2_screen_summary(root: Path) -> dict[str, Any]:
    path = root / G2_MATCHED_PILOT
    payload = _read_json(path)
    comparisons_value = payload.get("comparisons")
    comparisons = [row for row in comparisons_value if isinstance(row, Mapping)] if isinstance(comparisons_value, list) else []
    if not payload or not comparisons:
        return {
            "available": False,
            "complete": False,
            "decision": "NOT_RUN/NO_EVIDENCE",
            "next_pivot": G2_NEXT_PIVOT,
        }

    segments = sorted({_integer(row.get("segments")) for row in comparisons if _integer(row.get("segments")) is not None})
    baseline_rules = sorted({str(row.get("baseline_rule", "")) for row in comparisons})
    candidate_rules = sorted({str(row.get("candidate_rule", "")) for row in comparisons})
    cells = {
        (_integer(row.get("segments")), str(row.get("candidate_rule", "")))
        for row in comparisons
    }
    expected_cells = {(segments_value, rule) for segments_value in G2_SCREEN_SEGMENTS for rule in G2_SCREEN_RULES}
    exact_baseline = [_integer(row.get("baseline_exact_competitive_boundary_count")) for row in comparisons]
    exact_candidate = [_integer(row.get("candidate_exact_competitive_boundary_count")) for row in comparisons]
    mean_tth_deltas = [
        _finite(performance.get("mean_tth_delta_seconds"))
        for row in comparisons
        for performance in (row.get("performance") if isinstance(row.get("performance"), Mapping) else {},)
    ]
    mean_decomposition_deltas = [
        _finite(performance.get(name))
        for row in comparisons
        for performance in (row.get("performance") if isinstance(row.get("performance"), Mapping) else {},)
        for name in (
            "mean_tth_delta_seconds",
            "source_wait_delta_mean_seconds",
            "network_time_delta_mean_seconds",
        )
    ]
    hard_safety_count = sum(row.get("hard_safety_pass") is True for row in comparisons)
    shortlist_value = payload.get("recommended_for_same_state_causal_followup")
    shortlist = list(shortlist_value) if isinstance(shortlist_value, list) else []
    authorization = payload.get("causal_authorization") if isinstance(payload.get("causal_authorization"), Mapping) else {}
    causal_authorized = authorization.get("authorized") is True
    same_state_count = _integer(authorization.get("same_state_causal_opportunity_count"))
    comparison_count = _integer(payload.get("comparison_count"))
    complete = (
        str(payload.get("status", "")).upper() == "COMPLETE_MATCHED_SCREEN"
        and comparison_count == 20
        and len(comparisons) == 20
        and cells == expected_cells
        and baseline_rules == ["M1"]
        and candidate_rules == list(G2_SCREEN_RULES)
    )
    all_exact_zero = (
        len(exact_baseline) == len(comparisons)
        and len(exact_candidate) == len(comparisons)
        and all(value == 0 for value in (*exact_baseline, *exact_candidate))
    )
    all_mean_tth_zero = len(mean_tth_deltas) == len(comparisons) and all(
        value is not None and abs(value) <= 1e-12 for value in mean_tth_deltas
    )
    all_mean_zero = len(mean_decomposition_deltas) == 3 * len(comparisons) and all(
        value is not None and abs(value) <= 1e-12 for value in mean_decomposition_deltas
    )
    hard_safety_all_pass = hard_safety_count == len(comparisons)
    no_support = (
        complete
        and all_exact_zero
        and all_mean_zero
        and hard_safety_all_pass
        and not shortlist
        and not causal_authorized
        and same_state_count == 0
    )
    return {
        "available": True,
        "complete": complete,
        "decision": "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT" if no_support else "G2_MATCHED_SCREEN_REQUIRES_REVIEW",
        "artifact_status": str(payload.get("status", "UNKNOWN")),
        "evidence_kind": str(payload.get("evidence_kind", "UNKNOWN")),
        "comparison_count": len(comparisons),
        "segments": segments,
        "baseline_rules": baseline_rules,
        "candidate_rules": candidate_rules,
        "all_exact_competitive_boundaries_zero": all_exact_zero,
        "all_mean_tth_deltas_zero": all_mean_tth_zero,
        "all_mean_decomposition_deltas_zero": all_mean_zero,
        "hard_safety_pass_count": hard_safety_count,
        "hard_safety_all_pass": hard_safety_all_pass,
        "causal_authorized": causal_authorized,
        "same_state_causal_opportunity_count": same_state_count,
        "causal_followup_shortlist_count": len(shortlist),
        "screen_statuses": sorted({str(row.get("screen_status", "UNKNOWN")) for row in comparisons}),
        "no_support": no_support,
        "scope_status": (
            G2_EAGER_DIAGNOSTIC_STATUS
            if no_support
            else "G2_MATCHED_SCREEN_REQUIRES_REVIEW"
        ),
        "global_g2_scientific_no_go": False,
        "jit_choice_seam_status": "NOT_IMPLEMENTED",
        "next_pivot": G2_NEXT_PIVOT,
        "evidence_path": G2_MATCHED_PILOT.as_posix(),
    }


def _g2_decision(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    system_plan_path = root / SYSTEM_PLAN
    system_plan = _read_json(system_plan_path)
    plan_value = system_plan.get("g2_decision") if isinstance(system_plan.get("g2_decision"), Mapping) else {}
    screen = _g2_screen_summary(root)
    share = _downstream_share(manifest, _read_csv(root / WAIT_TOPOLOGY))
    source_pivot = share is not None and share >= 0.5
    causal_pass = screen.get("causal_authorized") is True if screen.get("available") else plan_value.get("causal_gate_pass") is True
    triggered = source_pivot or plan_value.get("triggered") is True or screen.get("available") is True
    causal_status = (
        "COMPLETE_MATCHED_SCREEN_NOT_SAME_STATE_CAUSAL"
        if screen.get("complete")
        else str(plan_value.get("causal_evidence_status", "MISSING")).upper()
    )
    if screen.get("no_support") is True:
        decision = "CURRENT_EAGER_TOKEN_ACTION_SEAM_NO_SUPPORT"
        status = "NO_SUPPORT_EVIDENCE"
    elif causal_pass:
        decision = "G2_CAUSAL_GATE_PASS"
        status = "EVIDENCE"
    elif triggered and plan_value:
        decision = str(plan_value.get("decision", "G2_TRIGGERED_PILOT_REQUIRED"))
        status = (
            "G2_CAUSAL_NO_GO"
            if "NO_GO" in causal_status
            else "PIVOT_EVIDENCE_ONLY; CAUSAL_PILOT_NOT_RUN/NO_EVIDENCE"
        )
    elif triggered:
        decision = "G2_TRIGGERED_BUT_CAUSAL_PILOT_NOT_RUN"
        status = "NOT_RUN/NO_EVIDENCE"
    else:
        decision = "G2_NOT_DECIDABLE_NO_TRIGGER_OR_CAUSAL_EVIDENCE"
        status = "NOT_RUN/NO_EVIDENCE"
    return {
        "decision": decision,
        "status": status,
        "scope_status": screen.get("scope_status", "G2_DIAGNOSTIC_IN_PROGRESS"),
        "global_g2_scientific_no_go": False,
        "downstream_backpressure_share": share,
        "triggered": triggered,
        "causal_gate_pass": causal_pass,
        "causal_evidence_status": causal_status,
        "plan": dict(plan_value),
        "matched_screen": screen,
        "next_pivot": G2_NEXT_PIVOT,
        "evidence_paths": [path.as_posix() for path in (WAIT_TOPOLOGY, SYSTEM_PLAN, G2_MATCHED_PILOT) if (root / path).is_file()],
    }


def _first_report_decision(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in (
        r"Decision:\s*\*\*`([^`]+)`\*\*",
        r"Decision:\s*`([^`]+)`",
        r"\*\*`([A-Z][A-Z0-9_\-]+)`\*\*",
        r"Status:\s*\*\*`([^`]+)`\*\*",
        r"Status:\s*`([^`]+)`",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _i1_evidence_state(root: Path) -> str:
    effects = _read_csv(root / I1_EFFECTS)
    model_decision = _first_report_decision(root / I1_MODEL_REPORT)
    support_decision = _first_report_decision(root / I1_SUPPORT_REPORT)
    if model_decision:
        return model_decision
    if support_decision:
        return support_decision
    if effects:
        return "I1_EFFECT_ROWS_AVAILABLE_MODEL_DECISION_NOT_RUN"
    return "NOT_RUN/NO_EVIDENCE"


def _write_g2_report(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    result = _g2_decision(root, manifest)
    screen = result["matched_screen"]
    summary = _source_summary(manifest)
    share = result["downstream_backpressure_share"]
    share_text = "NO_EVIDENCE" if share is None else f"{100.0 * share:.2f}%"
    causal = "PASS" if result["causal_gate_pass"] else "NOT_RUN/NO_EVIDENCE"
    matched = _integer(summary.get("matched_bag_count"))
    source_delta = _finite(summary.get("source_wait_delta_mean_seconds_per_raw_bag"))
    network_delta = _finite(summary.get("network_time_delta_mean_seconds_per_raw_bag"))
    tth_delta = _finite(summary.get("tth_delta_mean_seconds_per_raw_bag"))
    positive_seconds = _finite(summary.get("positive_additional_source_wait_seconds"))
    verified = (
        f"Matched bags **{matched}**; H5−off source wait **{source_delta:+.6f} s/raw bag**, "
        f"network time **{network_delta:+.6f} s/raw bag**, total TTH **{tth_delta:+.6f} s/raw bag**, "
        f"and positive additional source wait **{positive_seconds:.3f} s**."
        if None not in (matched, source_delta, network_delta, tth_delta, positive_seconds)
        else "Phase-A numeric decomposition: **NOT_RUN/NO_EVIDENCE**."
    )
    if screen.get("available"):
        screen_text = "\n".join(
            [
                "## Completed M1–M6 matched screen",
                "",
                f"The native screen completed **{screen.get('comparison_count')} comparisons**: M1 versus M2–M6 at "
                + ", ".join(f"{value:,}" for value in screen.get("segments", []))
                + " segments.",
                "",
                f"- Exact competitive boundary count was zero in every baseline and candidate arm: **{screen.get('all_exact_competitive_boundaries_zero')}**.",
                f"- All matched mean TTH/source-wait/network deltas were exactly zero: **{screen.get('all_mean_decomposition_deltas_zero')}**.",
                f"- Hard safety passed **{screen.get('hard_safety_pass_count')}/{screen.get('comparison_count')}** comparisons.",
                f"- Same-state causal opportunities: **{screen.get('same_state_causal_opportunity_count')}**; causal follow-up shortlist: **{screen.get('causal_followup_shortlist_count')}**.",
                f"- Causal authorization remains **{screen.get('causal_authorized')}**.",
                "",
                "The zero deltas are not evidence that M1-M6 have equivalent successful performance. They occurred with zero exact competitive boundaries, so the current eager-token action seam never exposed a grant choice on which the rules could differ. Hard-safety PASS is an engineering result, not causal performance authorization.",
                f"Evidence scope: **`{screen.get('scope_status')}`**. This completes only the current eager-token seam diagnostic, not a global G2 scientific no-go; the bounded JIT choice seam remains unimplemented.",
                "",
                f"Next pivot: **{screen.get('next_pivot')}**.",
            ]
        )
    else:
        screen_text = "## M1–M6 matched screen\n\nStatus: **`NOT_RUN/NO_EVIDENCE`**."
    body = "\n".join(
        [
            "# G4IRSF17 G2 decision",
            "",
            f"Decision: **`{result['decision']}`**.",
            "",
            f"- Phase-A downstream merge/capacity share: **{share_text}**.",
            f"- G2 pivot triggered: **{result['triggered']}**.",
            f"- Real 64+ opportunity G2 causal authorization gate: **{causal}**.",
            f"- G2 causal evidence artifact status: **{result['causal_evidence_status']}**.",
            "",
            verified,
            "",
            screen_text,
            "",
            "A source-wait attribution pivot is not a G2 performance result. A G2 candidate may enter the matched ladder only after a real causal pilot and hard-safety gate pass.",
            "",
            "Evidence: " + (", ".join(f"`{value}`" for value in result["evidence_paths"]) or "NOT_RUN/NO_EVIDENCE"),
        ]
    )
    _atomic_write_text(root / G2_REPORT, body)
    return result


def _fault_status(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NOT_RUN/NO_EVIDENCE",
            "matrix_complete": False,
            "advantage_supported": False,
            "inflight_merge_recovery_count": 0,
            "inflight_merge_recovery_available_cells": 0,
            "inflight_merge_recovery_unavailable_cells": 0,
            "candidates": {},
        }
    four_x_rows = [row for row in rows if _integer(row.get("scale")) == 4]
    reused_capacity_controls = [
        row
        for row in four_x_rows
        if str(row.get("status", "")).upper()
        == CAPACITY_CENSOR_CONTROL_STATUS
    ]
    control_censored_treatments = [
        row
        for row in four_x_rows
        if str(row.get("status", "")).upper()
        == CAPACITY_CENSOR_TREATMENT_STATUS
    ]
    amended_terminal = bool(
        len(reused_capacity_controls) == 1
        and control_censored_treatments
        and len(reused_capacity_controls) + len(control_censored_treatments)
        == len(four_x_rows)
    )
    terminal = [
        row
        for row in rows
        if str(row.get("status", "")).upper()
        in {"COMPLETE", "HARD_GATE_FAILED", "CENSORED_TIMEOUT", "CENSORED_OOM"}
    ]
    if not terminal and not amended_terminal:
        return {
            "status": "NOT_RUN/NO_EVIDENCE",
            "matrix_complete": False,
            "advantage_supported": False,
            "inflight_merge_recovery_count": 0,
            "inflight_merge_recovery_available_cells": 0,
            "inflight_merge_recovery_unavailable_cells": len(rows),
            "candidates": {},
        }
    candidates: dict[str, Any] = {}
    for candidate in sorted({str(row.get("candidate_id", "unknown")) for row in rows}):
        selected = [row for row in rows if str(row.get("candidate_id", "unknown")) == candidate]
        observed = {
            (str(row.get("fault_category", "")), _integer(row.get("scale")))
            for row in selected
            if str(row.get("status", "")).upper() in {"COMPLETE", "HARD_GATE_FAILED"}
        }
        required = {(category, load) for category in FAULT_CATEGORIES for load in FAULT_LOADS}
        relevant = [row for row in selected if (str(row.get("fault_category", "")), _integer(row.get("scale"))) in required]
        pass_all = required <= observed and all(_boolean(row.get("fault_gate_pass")) is True for row in relevant)
        deltas = [_finite(row.get("mean_tth_delta_vs_fault_off_seconds")) for row in relevant]
        comparative = [value for value in deltas if value is not None]
        available_recovery_counts = [
            value
            for row in selected
            for value in (_integer(row.get(INFLIGHT_MERGE_RECOVERY_COUNTER)),)
            if _boolean(
                row.get(f"{INFLIGHT_MERGE_RECOVERY_COUNTER}_available")
            )
            is True
            and value is not None
            and value >= 0
        ]
        candidates[candidate] = {
            "observed_required_cells": len(observed & required),
            "required_cells": len(required),
            "matrix_pass": pass_all,
            "comparative_row_count": len(comparative),
            "all_observed_mean_deltas_nonpositive": bool(comparative) and all(value <= 0.0 for value in comparative),
            "inflight_merge_recovery_count": sum(available_recovery_counts),
            "inflight_merge_recovery_available_cells": len(
                available_recovery_counts
            ),
        }
    complete = any(value["matrix_pass"] for value in candidates.values())
    advantage = any(value["matrix_pass"] and value["all_observed_mean_deltas_nonpositive"] for value in candidates.values())
    available_cells = sum(
        value["inflight_merge_recovery_available_cells"]
        for value in candidates.values()
    )
    return {
        "status": (
            "COMPLETE"
            if complete
            else CAPACITY_CENSOR_TRACK_STATUS
            if amended_terminal
            else "PARTIAL_EVIDENCE"
        ),
        "matrix_complete": complete,
        "scientific_matrix_complete": complete,
        "workflow_terminal": complete or amended_terminal,
        "protocol_amended": amended_terminal,
        "advantage_supported": advantage,
        "inflight_merge_recovery_count": sum(
            value["inflight_merge_recovery_count"]
            for value in candidates.values()
        ),
        "inflight_merge_recovery_available_cells": available_cells,
        "inflight_merge_recovery_unavailable_cells": len(rows) - available_cells,
        "candidates": candidates,
    }


def _write_fault_report(root: Path) -> dict[str, Any]:
    path = root / FAULT_TABLE
    rows = _read_csv(path)
    result = _fault_status(rows)
    if not rows:
        body = "\n".join(
            [
                "# G4IRSF17 native fault campaign",
                "",
                "Status: **`NOT_RUN/NO_EVIDENCE`**.",
                "",
                "No `g4irsf17_fault_results.csv` rows exist. Native onset/repair/recovery, completion, safety, affected-bag and A*=0 claims are therefore not made.",
            ]
        )
    else:
        compact = []
        for row in rows[:80]:
            compact.append(
                [
                    row.get("candidate_id", "—"),
                    f"{row.get('scale', '—')}×",
                    row.get("fault_category", "—"),
                    row.get("status", "—"),
                    row.get("fault_affected_bag_count", "—") or "—",
                    row.get("fault_recovery_time_seconds", "—") or "—",
                    (
                        row.get(INFLIGHT_MERGE_RECOVERY_COUNTER, "0") or "0"
                        if _boolean(
                            row.get(
                                f"{INFLIGHT_MERGE_RECOVERY_COUNTER}_available"
                            )
                        )
                        is True
                        else "UNAVAILABLE"
                    ),
                    row.get("fault_gate_pass", "—") or "—",
                ]
            )
        body = "\n".join(
            [
                "# G4IRSF17 native fault campaign",
                "",
                f"Status: **`{result['status']}`**. Complete required 1×/4× matrix: **{result['matrix_complete']}**. Comparative fault advantage supported: **{result['advantage_supported']}**.",
                "",
                _markdown_table(["Candidate", "Load", "Fault category", "Status", "Affected", "Recovery s", "In-flight merge recovery", "Gate"], compact),
                "",
                f"Observed exact in-flight merge-generation recoveries: **{result['inflight_merge_recovery_count']}** across **{result['inflight_merge_recovery_available_cells']}** cells; **{result['inflight_merge_recovery_unavailable_cells']}** cells are explicitly unavailable.",
                "",
                f"Evidence: `{FAULT_TABLE.as_posix()}`. Censored, uninformative, and missing cells remain non-passes.",
            ]
        )
    _atomic_write_text(root / FAULT_REPORT, body)
    return result


def _scale_status(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "NOT_RUN/NO_EVIDENCE", "matrix_complete": False, "high_load_supported": False, "candidates": {}}
    terminal = [
        row
        for row in rows
        if str(row.get("status", "")).upper()
        in {"COMPLETE", "HARD_GATE_FAILED", "CENSORED_TIMEOUT", "CENSORED_OOM"}
    ]
    if not terminal:
        return {"status": "NOT_RUN/NO_EVIDENCE", "matrix_complete": False, "high_load_supported": False, "candidates": {}}
    candidates: dict[str, Any] = {}
    for candidate in sorted({str(row.get("candidate_id", "unknown")) for row in rows}):
        selected = [row for row in rows if str(row.get("candidate_id", "unknown")) == candidate]
        completed = {
            _integer(row.get("scale"))
            for row in selected
            if str(row.get("status", "")).upper() in {"COMPLETE", "HARD_GATE_FAILED"}
        }
        high_load = sum(_boolean(row.get("high_load_non_regression")) is True for row in selected if (_integer(row.get("scale")) or 0) > 1)
        candidates[candidate] = {
            "completed_scales": sorted(value for value in completed if value is not None),
            "matrix_complete": set(SCALE_FACTORS) <= completed,
            "high_load_non_regression_count": high_load,
        }
    complete = any(value["matrix_complete"] for value in candidates.values())
    high_load = any(value["matrix_complete"] and value["high_load_non_regression_count"] >= 2 for value in candidates.values())
    return {"status": "COMPLETE" if complete else "PARTIAL_EVIDENCE", "matrix_complete": complete, "high_load_supported": high_load, "candidates": candidates}


def _write_scale_report(root: Path) -> dict[str, Any]:
    rows = _read_csv(root / SCALE_TABLE)
    result = _scale_status(rows)
    if not rows:
        body = "\n".join(
            [
                "# G4IRSF17 fixed-map scale benchmark",
                "",
                "Status: **`NOT_RUN/NO_EVIDENCE`**.",
                "",
                "No 1×–16× G17 scale table exists. Business TTH, wall time, throughput and RSS scaling claims are therefore deferred.",
            ]
        )
    else:
        queue_available_rows = sum(
            _boolean(row.get("queue_fields_available")) is True
            for row in rows
        )
        queue_required_rows = len(rows)
        queue_fields_available = (
            queue_required_rows > 0
            and queue_available_rows == queue_required_rows
        )
        result.update(
            {
                "queue_telemetry_available_rows": queue_available_rows,
                "queue_telemetry_required_rows": queue_required_rows,
                "queue_peak_bound_supported": queue_fields_available,
            }
        )
        compact = [
            [
                row.get("candidate_id", "—"),
                f"{row.get('scale', '—')}×",
                row.get("status", "—"),
                row.get("mean_tth_seconds", row.get("mean_tth_delta_seconds", "—")) or "—",
                row.get("p95_tth_seconds", row.get("p95_tth_delta_seconds", "—")) or "—",
                row.get("wall_seconds", "—") or "—",
                row.get("peak_rss_mb", row.get("peak_rss_overhead_mb", "—")) or "—",
            ]
            for row in rows[:80]
        ]
        body = "\n".join(
            [
                "# G4IRSF17 fixed-map scale benchmark",
                "",
                f"Status: **`{result['status']}`**. Complete 1×–16× matrix: **{result['matrix_complete']}**. At least two high-load non-regression gates: **{result['high_load_supported']}**.",
                "",
                "Business time and compute resource columns are kept separate. A timeout/OOM row is censored, never a win.",
                "",
                *(
                    []
                    if queue_fields_available
                    else [
                        (
                            "Per-node source/junction queue telemetry is available for "
                            f"**{queue_available_rows}/{queue_required_rows}** required scale rows"
                            + (
                                " (all rows have `queue_fields_available=false`)"
                                if queue_available_rows == 0
                                else ""
                            )
                            + "; because coverage is incomplete across the matrix, a cross-scale "
                            "queue-peak bound must not be inferred from aggregate TTH, source-wait, "
                            "event, or resource columns."
                        ),
                        "",
                    ]
                ),
                _markdown_table(["Candidate", "Load", "Status", "Mean TTH/Δs", "P95/Δs", "Wall s", "RSS/ΔMB"], compact),
                "",
                f"Evidence: `{SCALE_TABLE.as_posix()}`.",
            ]
        )
    _atomic_write_text(root / SCALE_REPORT, body)
    return result


def _ladder_status(
    rows: Sequence[Mapping[str, Any]],
    *,
    stage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_rows = [
        row
        for row in rows
        if str(row.get("record_type", "")).upper() != "TRACK_STATUS"
    ]
    stage = stage or {}
    if (
        not candidate_rows
        and str(stage.get("status", "")).upper() == "COMPLETE"
        and str(stage.get("decision", "")).upper()
        == BASELINE_ONLY_LADDER_DECISION
    ):
        return {
            "status": BASELINE_ONLY_LADDER_DECISION,
            "matrix_complete": False,
            "workflow_terminal": True,
            "baseline_only": True,
            "promoted": [],
        }
    if not candidate_rows:
        return {"status": "NOT_RUN/NO_EVIDENCE", "matrix_complete": False, "promoted": []}
    candidates: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidate_rows:
        candidates.setdefault(str(row.get("candidate_id", "unknown")), []).append(row)
    complete = False
    promoted: list[dict[str, str]] = []
    for candidate, selected in candidates.items():
        levels = {
            _integer(row.get("segments"))
            for row in selected
            if str(row.get("candidate_status", row.get("status", ""))).upper() in {"COMPLETE", "HARD_GATE_FAILED"}
            and str(row.get("off_status", "COMPLETE")).upper() in {"COMPLETE", "HARD_GATE_FAILED"}
        }
        complete = complete or set(LADDER_SEGMENTS) <= levels
        full = next((row for row in selected if _integer(row.get("segments")) == LADDER_SEGMENTS[-1]), None)
        if full is not None and _boolean(full.get("ladder_gate_pass")) is True:
            promoted.append(
                {
                    "candidate_id": candidate,
                    "policy_family": str(full.get("policy_family", "unknown")).lower(),
                }
            )
    return {"status": "COMPLETE" if complete else "PARTIAL_EVIDENCE", "matrix_complete": complete, "promoted": promoted}


def _explicit_advantage(stage: Mapping[str, Any]) -> bool:
    decision = str(stage.get("decision", "")).upper()
    summary = stage.get("summary") if isinstance(stage.get("summary"), Mapping) else {}
    return "ADVANTAGE_SUPPORTED" in decision or summary.get("advantage_supported") is True


def _final_decision(
    manifest: Mapping[str, Any],
    ladder: Mapping[str, Any],
    scale: Mapping[str, Any],
    fault: Mapping[str, Any],
    g2: Mapping[str, Any],
) -> dict[str, Any]:
    recorded_final = (
        manifest.get("final_joint_decision")
        if isinstance(manifest.get("final_joint_decision"), Mapping)
        else {}
    )
    if recorded_final.get("decision") == CAPACITY_CENSOR_FINAL_DECISION:
        recorded_next_pivot = str(recorded_final.get("next_pivot", "")).strip()
        if not recorded_next_pivot or recorded_next_pivot.upper() == "UNKNOWN":
            recorded_next_pivot = str(
                g2.get("next_pivot") or G2_NEXT_PIVOT
            ).strip()
        return {
            "decision": CAPACITY_CENSOR_FINAL_DECISION,
            "reason": str(
                recorded_final.get(
                    "reason",
                    "The workflow is terminal under an explicit capacity-censor amendment; the scientific fault matrix and A--E decision remain incomplete.",
                )
            ),
            "complete": False,
            "terminal": True,
            "protocol_amended": True,
            "scientific_matrix_complete": False,
            "next_pivot": recorded_next_pivot,
        }
    stages_complete = (
        _stage_complete(manifest, ("closed_loop_ladder",))
        and _stage_complete(manifest, ("native_fault_campaign",))
        and _stage_complete(manifest, ("scale_benchmark",))
    )
    evidence_complete = bool(stages_complete and ladder["matrix_complete"] and scale["matrix_complete"] and fault["matrix_complete"])
    if not evidence_complete:
        return {
            "decision": "NOT_RUN/NO_EVIDENCE — A–E DECISION DEFERRED",
            "reason": "The full matched ladder, native 1×/4× fault matrix, and fixed-map 1×–16× scale matrix are not all complete.",
            "complete": False,
            "next_pivot": str(g2.get("next_pivot", G2_NEXT_PIVOT)),
        }
    promoted = list(ladder.get("promoted", []))
    high_load_candidates = {
        candidate
        for candidate, value in scale.get("candidates", {}).items()
        if value.get("matrix_complete") and value.get("high_load_non_regression_count", 0) >= 2
    }
    fault_candidates = {
        candidate
        for candidate, value in fault.get("candidates", {}).items()
        if value.get("matrix_pass") is True
    }
    promoted = [
        row
        for row in promoted
        if row["candidate_id"] in high_load_candidates and row["candidate_id"] in fault_candidates
    ]
    learned = [row for row in promoted if row["policy_family"] in {"learned", "joint"}]
    deterministic = [row for row in promoted if row["policy_family"] == "deterministic"]
    g2_promoted = [row for row in promoted if row["policy_family"] == "g2"]
    if learned:
        return {"decision": "A. LEARNED_LOCAL_FLOW_CONTROL_PROMOTED", "reason": "A learned/joint candidate passed full 1× and at least two high-load non-regression gates.", "complete": True, "candidates": [row["candidate_id"] for row in learned]}
    if deterministic:
        return {"decision": "B. DETERMINISTIC_LOCAL_FLOW_CONTROL_PROMOTED_LEARNING_NOT_YET", "reason": "A deterministic local candidate passed the promotion gates; no learned candidate did.", "complete": True, "candidates": [row["candidate_id"] for row in deterministic]}
    if g2_promoted:
        return {"decision": "C. I1_NO_GO_G2_PROMOTED", "reason": "A G2 candidate passed the full promotion gates while I1 did not.", "complete": True, "candidates": [row["candidate_id"] for row in g2_promoted]}
    scale_stage = _stage(manifest, ("scale_benchmark",))
    fault_stage = _stage(manifest, ("native_fault_campaign",))
    if _explicit_advantage(scale_stage) and _explicit_advantage(fault_stage):
        return {"decision": "D. PERFORMANCE_NO_GO_BUT_SCALE_AND_FAULT_ADVANTAGE_SUPPORTED", "reason": "No flow candidate passed performance promotion, while both completed track manifests explicitly record scale and fault advantage.", "complete": True}
    pivot = str(g2.get("next_pivot", G2_NEXT_PIVOT))
    return {"decision": "E. FULL_NO_GO_WITH_SPECIFIC_NEXT_PIVOT", "reason": f"No candidate passed the full promotion gates; next pivot: {pivot}.", "complete": True, "next_pivot": pivot}


def _write_final_report(
    root: Path,
    manifest: Mapping[str, Any],
    ladder: Mapping[str, Any],
    scale: Mapping[str, Any],
    fault: Mapping[str, Any],
    g2: Mapping[str, Any],
) -> dict[str, Any]:
    decision = _final_decision(manifest, ladder, scale, fault, g2)
    i1_state = _i1_evidence_state(root)
    source_summary = _source_summary(manifest)
    matched = _integer(source_summary.get("matched_bag_count"))
    source_delta = _finite(source_summary.get("source_wait_delta_mean_seconds_per_raw_bag"))
    network_delta = _finite(source_summary.get("network_time_delta_mean_seconds_per_raw_bag"))
    tth_delta = _finite(source_summary.get("tth_delta_mean_seconds_per_raw_bag"))
    positive_seconds = _finite(source_summary.get("positive_additional_source_wait_seconds"))
    downstream_share = _finite(source_summary.get("downstream_backpressure_share"))
    phase_a_result = (
        f"At 8,192, the matched Phase-A run covered **{matched} raw bags**: H5−off source wait "
        f"was **{source_delta:+.6f} s/bag**, network time **{network_delta:+.6f} s/bag**, and total "
        f"TTH **{tth_delta:+.6f} s/bag**. The **{positive_seconds:.3f} s** positive additional "
        f"source wait was **{100.0 * downstream_share:.2f}% downstream backpressure**, which verifies "
        "the bounded I1 pilot + G2 pivot; it does not authorize G2. Attribution remains at the native "
        "aggregate-interval granularity; no per-bag blocker identity is inferred from aggregate rows."
        if None not in (matched, source_delta, network_delta, tth_delta, positive_seconds, downstream_share)
        else "The 8,192 Phase-A numeric decomposition is **NOT_RUN/NO_EVIDENCE**."
    )
    body = "\n".join(
        [
            "# G4IRSF17 final joint decision",
            "",
            f"Decision: **`{decision['decision']}`**.",
            "",
            str(decision["reason"]),
            "",
            f"Next pivot: **{decision.get('next_pivot', g2.get('next_pivot', G2_NEXT_PIVOT))}**.",
            "",
            "## Verified Phase-A result",
            "",
            phase_a_result,
            "",
            "## Evidence gates",
            "",
            _markdown_table(
                ["Evidence gate", "Status"],
                [
                    ["Phase-A source-wait attribution", "COMPLETE" if _source_summary(manifest) else "NOT_RUN/NO_EVIDENCE"],
                    ["I1 causal/model evidence", i1_state],
                    ["G2 M1–M6 matched action screen", g2["decision"]],
                    ["G2 causal authorization", "PASS" if g2.get("causal_gate_pass") else "FALSE / NOT AUTHORIZED"],
                    ["144→43,603 matched ladder", ladder["status"]],
                    ["Native 1×/4× fault matrix", fault["status"]],
                    ["Fixed-map 1×–16× scale matrix", scale["status"]],
                ],
            ),
            "",
            "A missing experiment is neither a zero effect nor a pass. Levels A–E are assigned only after all three system tracks are complete.",
        ]
    )
    _atomic_write_text(root / FINAL_REPORT, body)
    return decision


def _write_index(
    root: Path,
    figures: Sequence[FigureEvidence],
    decision: Mapping[str, Any],
    g2: Mapping[str, Any],
) -> None:
    rows = []
    for figure in figures:
        evidence = ", ".join(f"`{value}`" for value in figure.evidence_paths) or "NOT_RUN/NO_EVIDENCE"
        rows.append([figure.key, figure.status, f"[{Path(figure.path).name}](../figures/{Path(figure.path).name})", evidence])
    screen = g2.get("matched_screen") if isinstance(g2.get("matched_screen"), Mapping) else {}
    if screen.get("available"):
        g2_section = "\n".join(
            [
                "## G2 matched M1–M6 action screen",
                "",
                f"Decision: **`{g2['decision']}`**.",
                "",
                _markdown_table(
                    ["Screen fact", "Observed value"],
                    [
                        ["Matched comparisons", screen.get("comparison_count")],
                        ["Segment levels", ", ".join(f"{value:,}" for value in screen.get("segments", []))],
                        ["Rules", "M1 vs M2–M6"],
                        ["All exact competitive boundary counts", "0" if screen.get("all_exact_competitive_boundaries_zero") else "NOT_ZERO/INCOMPLETE"],
                        ["All mean TTH/source-wait/network deltas", "0" if screen.get("all_mean_decomposition_deltas_zero") else "NOT_ZERO/INCOMPLETE"],
                        ["Hard safety", f"{screen.get('hard_safety_pass_count')}/{screen.get('comparison_count')} PASS"],
                        ["Same-state causal opportunities", screen.get("same_state_causal_opportunity_count")],
                        ["Causal follow-up shortlist", screen.get("causal_followup_shortlist_count")],
                        ["Causal authorization", screen.get("causal_authorized")],
                    ],
                ),
                "",
                "Zero deltas with zero competitive boundaries mean that the eager-token seam exposed no effective rule choice; they are not evidence of successful or equivalent M1–M6 performance.",
                "",
                f"Next pivot: **{screen.get('next_pivot')}**. Evidence: `{screen.get('evidence_path')}`.",
            ]
        )
    else:
        g2_section = "## G2 matched M1–M6 action screen\n\nStatus: **`NOT_RUN/NO_EVIDENCE`**."
    body = "\n".join(
        [
            "# G4IRSF17 evidence figure index",
            "",
            f"Current joint decision: **`{decision['decision']}`**.",
            "",
            _markdown_table(["Figure", "Status", "PNG", "Evidence input"], rows),
            "",
            "`NOT_RUN/NO_EVIDENCE` panels are intentional: they prevent missing campaigns from appearing as zero-effect results.",
            "",
            "## Publication boundary",
            "",
            "Raw `*.source_wait.json`, `*.raw_bag_timings.csv`, and `outputs/runstate/**` files are local resumable inputs and are intentionally not distributed with the repository. The committed CSV tables, Markdown reports, and rendered figures in this index are the compact publication evidence; any raw runstate path shown in provenance is not a promised repository file.",
            "",
            g2_section,
        ]
    )
    _atomic_write_text(root / EVIDENCE_INDEX, body)


def generate_evidence(*, root: Path = ROOT, dpi: int = 140) -> dict[str, Any]:
    root = root.resolve()
    _configure_plotting()
    manifest = _read_json(root / MANIFEST)
    figures = [
        plot_wait_reason_stacked(root, dpi=dpi),
        plot_source_blocker_heatmap(root, dpi=dpi),
        plot_i1_effect_distribution(root, dpi=dpi),
        plot_i1_coverage(root, dpi=dpi),
        plot_aliasing(root, dpi=dpi),
        plot_ladder(root, dpi=dpi, manifest=manifest),
        plot_decomposition(root, dpi=dpi, manifest=manifest),
        plot_scale_tth(root, dpi=dpi),
        plot_scale_compute(root, dpi=dpi),
        plot_fault_timeline(root, dpi=dpi),
    ]
    g2 = _write_g2_report(root, manifest)
    fault = _write_fault_report(root)
    scale = _write_scale_report(root)
    ladder = _ladder_status(
        _read_csv(root / LADDER_TABLE),
        stage=_stage(manifest, ("closed_loop_ladder",)),
    )
    decision = _write_final_report(root, manifest, ladder, scale, fault, g2)
    _write_index(root, figures, decision, g2)
    return {
        "schema": "czr005.g4irsf17.evidence_bundle.v1",
        "figures": [asdict(value) for value in figures],
        "reports": [
            G2_REPORT.as_posix(),
            FAULT_REPORT.as_posix(),
            SCALE_REPORT.as_posix(),
            FINAL_REPORT.as_posix(),
            EVIDENCE_INDEX.as_posix(),
        ],
        "g2": g2,
        "fault": fault,
        "scale": scale,
        "ladder": ladder,
        "final": decision,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--dpi", type=int, default=140, help="PNG resolution")
    parser.add_argument("--json", action="store_true", help="Print the evidence-bundle summary as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = generate_evidence(root=args.root, dpi=args.dpi)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"generated {len(result['figures'])} evidence figures; final={result['final']['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
