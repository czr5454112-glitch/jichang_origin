#!/usr/bin/env python3
"""Render four evidence-bound CIE paper figures from committed JSON/CSV rows."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402
import numpy as np  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
HCA_REPORT = Path("outputs/tables/g4irsf31_reporting.json")
ABLATION_PAIRWISE = Path("outputs/tables/cie_ablation_pairwise.csv")
P1 = Path("outputs/runtime/cie_baselines/p1_neutral_fifo")
P1_FINAL = Path("outputs/runtime/cie_baselines/p1_neutral_fifo_final")
SPEED_MPS = 2.5
MAPS = ("map2", "nanning")
SCALES = (1, 2)
METHODS = ("hca", "g31", "cie_dh", "tarau")
METHOD_LABELS = {
    "hca": "HCA",
    "g31": "G31 P1",
    "cie_dh": "CIE-DH adapted",
    "tarau": "Tarau-2010 adapted",
}
METHOD_COLORS = {
    "hca": "#4c78a8",
    "g31": "#2a9d8f",
    "cie_dh": "#f28e2b",
    "tarau": "#c44e52",
}
VARIANTS = (
    "a0_h_only",
    "a1_h_q",
    "a2_h_q_i",
    "a4_full",
    "b1_full_minus_q",
    "b2_full_minus_i",
    "b5_full_minus_strict_descent",
    "c_fifo",
    "f1_service_rate_normalized",
)
VARIANT_LABELS = {
    "a0_h_only": "A0",
    "a1_h_q": "A1",
    "a2_h_q_i": "A2",
    "a4_full": "A4",
    "b1_full_minus_q": "B1",
    "b2_full_minus_i": "B2",
    "b5_full_minus_strict_descent": "B5",
    "c_fifo": "C_FIFO",
    "f1_service_rate_normalized": "F1",
}
EFFECT_METRICS = ("mean", "p95", "p99", "max")


class PlotInputError(RuntimeError):
    """Raised when a figure input would violate the evidence boundary."""


@dataclass(frozen=True)
class RunPoint:
    method: str
    map_name: str
    scale: int
    release: str
    completion_rate: float
    wall_seconds: float
    source: Path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlotInputError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PlotInputError(f"JSON object required: {path}")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlotInputError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PlotInputError(f"{label} must be finite")
    return result


def _finite_csv(value: Any, label: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise PlotInputError(f"{label} must be a populated numeric CSV field")
    try:
        result = float(value)
    except ValueError as exc:
        raise PlotInputError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise PlotInputError(f"{label} must be finite")
    return result


def _resolve(root: Path, relative: Path) -> Path:
    return (root / relative).resolve()


def _hca_capacity(root: Path) -> dict[tuple[str, int], float]:
    path = _resolve(root, HCA_REPORT)
    report = _read_json(path)
    if report.get("schema") != "czr005.g4irsf31.cross_map_reporting.v1":
        raise PlotInputError("unexpected G31 reporting schema")
    row_sets: dict[str, Any] = {
        "nanning": report.get("primary_rows"),
        "map2": (
            report.get("map2_context", {}).get("capacity", {}).get("rows")
            if isinstance(report.get("map2_context"), Mapping)
            else None
        ),
    }
    result: dict[tuple[str, int], float] = {}
    for map_name in MAPS:
        rows = row_sets[map_name]
        if not isinstance(rows, list):
            raise PlotInputError(f"HCA {map_name} capacity rows are missing")
        for scale in SCALES:
            matches = [
                row
                for row in rows
                if isinstance(row, Mapping)
                and row.get("case_group") == "stable_speed"
                and row.get("scale") == scale
                and _finite(row.get("speed_mps"), "HCA speed_mps") == SPEED_MPS
            ]
            if len(matches) != 1:
                raise PlotInputError(
                    f"expected one HCA {map_name} {scale}x stable 2.5 row"
                )
            row = matches[0]
            capacity = row.get("capacity", row)
            if not isinstance(capacity, Mapping) or capacity.get("evidence_ready") is not True:
                raise PlotInputError(f"HCA {map_name} {scale}x capacity is not ready")
            denominator = _finite(
                row.get("fixed_raw_bag_denominator"), "HCA denominator"
            )
            completed = _finite(
                capacity.get("hca_completed_raw_bags"), "HCA completed"
            )
            if denominator <= 0.0 or not 0.0 <= completed <= denominator:
                raise PlotInputError(f"invalid HCA {map_name} {scale}x capacity")
            result[(map_name, scale)] = completed / denominator
    return result


def _run_path(root: Path, method: str, map_name: str, scale: int, release: str) -> Path:
    filename = f"{map_name}_{scale}x.json"
    if method == "g31":
        return _resolve(root, P1_FINAL / "g31" / release / filename)
    if method == "tarau":
        return _resolve(
            root, P1_FINAL / "tarau_distributed_2010" / release / filename
        )
    if method == "cie_dh":
        if release == "canonical":
            return _resolve(
                root, P1 / "tarau_local_2009" / "canonical" / filename
            )
        if scale != 1:
            raise PlotInputError("same-HCA CIE-DH is available only at 1x")
        return _resolve(root, P1 / "tarau_local_2009" / filename)
    raise PlotInputError(f"unknown runtime method: {method}")


def _load_run(
    root: Path,
    method: str,
    map_name: str,
    scale: int,
    release: str,
    *,
    allow_missing: bool = False,
) -> RunPoint | None:
    path = _run_path(root, method, map_name, scale, release)
    if not path.exists():
        if allow_missing:
            return None
        raise PlotInputError(f"required runtime result is missing: {path}")
    data = _read_json(path)
    expected_arm = {
        "g31": "g31",
        "cie_dh": "tarau_local_2009",
        "tarau": "tarau_distributed_2010",
    }[method]
    if data.get("schema") != "czr005.g4irsf35.full_population_single_arm.v1":
        raise PlotInputError(f"unexpected runtime schema: {path}")
    if (
        data.get("native_execution_started") is not True
        or data.get("status") != "COMPLETE"
        or data.get("arm") != expected_arm
        or data.get("map") != map_name
        or data.get("scale") != scale
    ):
        raise PlotInputError(f"runtime identity/status mismatch: {path}")
    fixed = data.get("fixed_window")
    if not isinstance(fixed, Mapping) or _finite(
        fixed.get("speed_mps"), f"{path} speed"
    ) != SPEED_MPS:
        raise PlotInputError(f"runtime speed mismatch: {path}")
    release_block = data.get("release_protocol")
    if not isinstance(release_block, Mapping) or release_block.get("mode") != release:
        raise PlotInputError(f"runtime release mismatch: {path}")
    algorithm = data.get("algorithm")
    if (
        not isinstance(algorithm, Mapping)
        or algorithm.get("coordination_protocol") != "neutral_fifo"
    ):
        raise PlotInputError(f"runtime is not the P1 neutral-FIFO protocol: {path}")
    integrity = data.get("execution_integrity")
    gates = integrity.get("gates") if isinstance(integrity, Mapping) else None
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("pass") is not True
        or not isinstance(gates, Mapping)
        or not gates
        or any(value is not True for value in gates.values())
    ):
        raise PlotInputError(f"runtime integrity gate failed/incomplete: {path}")
    population = data.get("population")
    capacity = (
        data.get("paper_subjects", {}).get("fixed_horizon_capacity")
        if isinstance(data.get("paper_subjects"), Mapping)
        else None
    )
    runtime = data.get("runtime")
    if not all(isinstance(value, Mapping) for value in (population, capacity, runtime)):
        raise PlotInputError(f"runtime capacity/cost block is missing: {path}")
    denominator = _finite(capacity.get("denominator_raw_bags"), "denominator")
    completed = _finite(capacity.get("completed_raw_bag_count"), "completed")
    rate = _finite(capacity.get("completion_rate"), "completion_rate")
    wall = _finite(runtime.get("wall_seconds"), "wall_seconds")
    if (
        population.get("whole_population") is not True
        or denominator != _finite(population.get("raw_bag_count"), "raw_bag_count")
        or denominator <= 0.0
        or not 0.0 <= completed <= denominator
        or not math.isclose(rate, completed / denominator, rel_tol=0.0, abs_tol=1e-12)
        or wall <= 0.0
    ):
        raise PlotInputError(f"invalid runtime capacity/cost values: {path}")
    return RunPoint(method, map_name, scale, release, rate, wall, path)


def _capacity_inputs(
    root: Path,
) -> tuple[dict[str, dict[tuple[str, int], float]], list[str]]:
    values = {method: {} for method in METHODS}
    values["hca"] = _hca_capacity(root)
    pending: list[str] = []
    for method in ("g31", "cie_dh", "tarau"):
        for map_name in MAPS:
            for scale in SCALES:
                allow_missing = method == "tarau" and map_name == "nanning" and scale == 2
                run = _load_run(
                    root,
                    method,
                    map_name,
                    scale,
                    "canonical",
                    allow_missing=allow_missing,
                )
                if run is None:
                    pending.append(f"{method}:{map_name}:{scale}x:canonical")
                    values[method][(map_name, scale)] = math.nan
                else:
                    values[method][(map_name, scale)] = run.completion_rate
    return values, pending


def _load_ablation_effects(root: Path) -> dict[str, dict[str, list[float]]]:
    path = _resolve(root, ABLATION_PAIRWISE)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PlotInputError(f"cannot read ablation pairwise CSV {path}: {exc}") from exc
    effects = {map_name: {} for map_name in MAPS}
    for row in rows:
        if (
            row.get("scale") != "1"
            or row.get("release") != "same_hca"
            or row.get("comparison_status")
            != "MATCHED_SAME_SHA_A4_CAPACITY_AND_FORMAL_1X_TIMING"
        ):
            continue
        map_name = row.get("map")
        variant = row.get("variant")
        if map_name not in effects or variant not in VARIANTS:
            continue
        if variant in effects[map_name]:
            raise PlotInputError(f"duplicate ablation row: {map_name}/{variant}")
        values: list[float] = []
        for metric in EFFECT_METRICS:
            key = f"formal_timing_{metric}_seconds_relative_delta"
            values.append(
                100.0 * _finite_csv(row.get(key), f"{map_name}/{variant}/{key}")
            )
        effects[map_name][variant] = values
    for map_name in MAPS:
        missing = set(VARIANTS) - set(effects[map_name])
        if missing:
            raise PlotInputError(f"missing formal ablation rows for {map_name}: {missing}")
    return effects


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "figure.dpi": 120,
            "savefig.dpi": 240,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fig.savefig(
        temporary,
        format="png",
        dpi=240,
        bbox_inches="tight",
        metadata={"Software": "czr005 plot_cie_results.py"},
    )
    os.replace(temporary, path)
    plt.close(fig)


def _completion_lower(values: Mapping[str, Mapping[tuple[str, int], float]]) -> float:
    reported = [
        value
        for method in values.values()
        for value in method.values()
        if math.isfinite(value)
    ]
    return max(0.0, math.floor((min(reported) - 0.03) * 20.0) / 20.0)


def _plot_load_completion(
    values: Mapping[str, Mapping[tuple[str, int], float]], output: Path
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 4.2), sharey=True)
    lower = _completion_lower(values)
    markers = {"hca": "o", "g31": "s", "cie_dh": "^", "tarau": "D"}
    linestyles = {"hca": "-", "g31": "--", "cie_dh": "-.", "tarau": ":"}
    for ax, map_name in zip(axes, MAPS, strict=True):
        for method in METHODS:
            y = np.array(
                [values[method].get((map_name, scale), math.nan) for scale in SCALES]
            )
            ax.plot(
                SCALES,
                y,
                color=METHOD_COLORS[method],
                marker=markers[method],
                linestyle=linestyles[method],
                linewidth=1.8,
                markersize=5,
                label=METHOD_LABELS[method],
            )
            for scale, rate in zip(SCALES, y, strict=True):
                if not math.isfinite(float(rate)):
                    ax.text(
                        0.98,
                        0.035,
                        f"{METHOD_LABELS[method]} {scale}x: N/A",
                        transform=ax.transAxes,
                        ha="right",
                        color=METHOD_COLORS[method],
                        fontsize=7.5,
                        fontweight="bold",
                    )
        ax.set_title("map2" if map_name == "map2" else "Nanning")
        ax.set_xlabel("Load scale")
        ax.set_xticks(SCALES, ["1x", "2x"])
        ax.set_xlim(0.85, 2.15)
        ax.set_ylim(lower, 1.015)
        ax.grid(axis="y", alpha=0.25)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[0].set_ylabel("Fixed-horizon completion rate")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.90),
        ncol=4,
        frameon=False,
    )
    fig.suptitle(
        "Stable-load completion at 2.5 m/s (canonical scheduled arrivals)", y=0.99
    )
    fig.text(
        0.5,
        0.025,
        "HCA native; G31/CIE-DH/Tarau route arms use P1 neutral-FIFO.",
        ha="center",
        fontsize=7.5,
        color="#555555",
    )
    fig.subplots_adjust(top=0.72, bottom=0.22, wspace=0.20)
    _save(fig, output)


def _plot_completion_grid(
    values: Mapping[str, Mapping[tuple[str, int], float]], output: Path
) -> None:
    rows = (("map2", 1), ("map2", 2), ("nanning", 1), ("nanning", 2))
    matrix = np.array(
        [[values[method].get(cell, math.nan) for method in METHODS] for cell in rows]
    )
    cmap = plt.get_cmap("YlGnBu").copy()
    cmap.set_bad("#d9d9d9")
    lower = _completion_lower(values)
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    image = ax.imshow(matrix, vmin=lower, vmax=1.0, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(METHODS)), [METHOD_LABELS[m] for m in METHODS])
    ax.tick_params(axis="x", labelsize=8)
    ax.set_yticks(
        range(len(rows)),
        [f"{'map2' if m == 'map2' else 'Nanning'} {s}x" for m, s in rows],
    )
    ax.set_title(
        "Fixed-horizon completion grid (2.5 m/s, canonical)\n"
        "HCA native; G31/CIE-DH/Tarau route arms use P1 neutral-FIFO"
    )
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            text = "N/A" if not math.isfinite(float(value)) else f"{100.0 * value:.1f}%"
            color = "black" if not math.isfinite(float(value)) or value < 0.88 else "white"
            ax.text(
                column_index,
                row_index,
                text,
                ha="center",
                va="center",
                color=color,
                fontsize=9,
                fontweight="bold",
            )
    colorbar = fig.colorbar(image, ax=ax, pad=0.02)
    colorbar.set_label("Completion rate")
    colorbar.ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    _save(fig, output)


def _plot_ablation_effect(
    effects: Mapping[str, Mapping[str, list[float]]], output: Path
) -> None:
    matrices = {
        map_name: np.array([effects[map_name][variant] for variant in VARIANTS])
        for map_name in MAPS
    }
    limit = max(float(np.max(np.abs(matrix))) for matrix in matrices.values())
    limit = max(limit, 0.01)
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 5.1), sharey=True)
    images = []
    for ax, map_name in zip(axes, MAPS, strict=True):
        matrix = matrices[map_name]
        image = ax.imshow(matrix, cmap="coolwarm", norm=norm, aspect="auto")
        images.append(image)
        ax.set_xticks(range(len(EFFECT_METRICS)), [m.upper() for m in EFFECT_METRICS])
        ax.set_yticks(
            range(len(VARIANTS)), [VARIANT_LABELS[v] for v in VARIANTS]
        )
        ax.set_title("map2" if map_name == "map2" else "Nanning")
        ax.set_xlabel("Full-population same-HCA latency metric")
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                value = float(matrix[row_index, column_index])
                text_color = "white" if abs(value) > 0.55 * limit else "black"
                ax.text(
                    column_index,
                    row_index,
                    f"{value:+.3f}%",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=7.4,
                )
    axes[0].set_ylabel("Ablation variant")
    colorbar = fig.colorbar(images[0], ax=axes, pad=0.02, shrink=0.86)
    colorbar.set_label("Relative delta vs same-map A4 (%)")
    fig.suptitle("Paired 1x ablation effects (negative / blue is better)", y=1.02)
    _save(fig, output)


def _pareto_inputs(root: Path) -> tuple[list[RunPoint], list[str]]:
    points: list[RunPoint] = []
    pending: list[str] = []
    for method in ("g31", "cie_dh", "tarau"):
        for map_name in MAPS:
            for scale in SCALES:
                allow_missing = method == "tarau" and map_name == "nanning" and scale == 2
                run = _load_run(
                    root,
                    method,
                    map_name,
                    scale,
                    "canonical",
                    allow_missing=allow_missing,
                )
                if run is None:
                    pending.append(f"{method}:{map_name}:{scale}x:canonical")
                else:
                    points.append(run)
            same_hca = _load_run(root, method, map_name, 1, "same_hca")
            if same_hca is not None:
                points.append(same_hca)
    return points, pending


def _plot_runtime_pareto(
    points: Sequence[RunPoint], pending: Sequence[str], output: Path
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 4.5), sharey=True)
    markers = {
        ("canonical", 1): "o",
        ("canonical", 2): "^",
        ("same_hca", 1): "s",
    }
    reported_rates = [point.completion_rate for point in points]
    lower = max(0.0, math.floor((min(reported_rates) - 0.02) * 20.0) / 20.0)
    for ax, map_name in zip(axes, MAPS, strict=True):
        selected = [point for point in points if point.map_name == map_name]
        for point in selected:
            ax.scatter(
                point.wall_seconds,
                point.completion_rate,
                s=58,
                marker=markers[(point.release, point.scale)],
                color=METHOD_COLORS[point.method],
                edgecolor="white",
                linewidth=0.6,
                zorder=3,
            )
        ax.set_xscale("log")
        ax.set_ylim(lower, 1.015)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.grid(alpha=0.22)
        ax.set_xlabel("Wall time (s, log scale)")
        ax.set_title("map2" if map_name == "map2" else "Nanning")
    axes[0].set_ylabel("Fixed-horizon completion rate")
    if any(item.startswith("tarau:nanning:2x") for item in pending):
        axes[1].text(
            0.98,
            0.04,
            "Tarau 2x canonical: N/A (pending)",
            transform=axes[1].transAxes,
            ha="right",
            fontsize=7.5,
            color=METHOD_COLORS["tarau"],
        )
    pareto_algorithm_labels = {
        "g31": "G31 P1",
        "cie_dh": "CIE-DH P1",
        "tarau": "Tarau-2010 P1",
    }
    algorithm_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            color=METHOD_COLORS[method],
            label=pareto_algorithm_labels[method],
            markersize=6,
        )
        for method in ("g31", "cie_dh", "tarau")
    ]
    protocol_labels = {
        ("canonical", 1): "Canonical 1x",
        ("canonical", 2): "Canonical 2x",
        ("same_hca", 1): "Same-HCA 1x",
    }
    protocol_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="none",
            color="#555555",
            label=protocol_labels[key],
            markersize=6,
        )
        for key, marker in markers.items()
    ]
    fig.legend(
        algorithm_handles + protocol_handles,
        [handle.get_label() for handle in algorithm_handles + protocol_handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.89),
        ncol=6,
        frameon=False,
    )
    fig.suptitle(
        "Completion/runtime trade-off (upper-left is better; HCA wall time unavailable)",
        y=0.99,
    )
    fig.subplots_adjust(top=0.72, bottom=0.16, wspace=0.20)
    _save(fig, output)


def generate(root: Path, output_dir: Path) -> tuple[list[Path], list[str]]:
    root = root.resolve(strict=True)
    output_dir = output_dir.resolve()
    _style()
    capacity, pending_capacity = _capacity_inputs(root)
    effects = _load_ablation_effects(root)
    pareto, pending_pareto = _pareto_inputs(root)
    paths = [
        output_dir / "cie_load_completion_rate.png",
        output_dir / "cie_fixed_horizon_completion_grid.png",
        output_dir / "cie_ablation_paired_effect.png",
        output_dir / "cie_throughput_runtime_pareto.png",
    ]
    _plot_load_completion(capacity, paths[0])
    _plot_completion_grid(capacity, paths[1])
    _plot_ablation_effect(effects, paths[2])
    _plot_runtime_pareto(pareto, pending_pareto, paths[3])
    pending = sorted(set(pending_capacity) | set(pending_pareto))
    return paths, pending


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/figures")
    )
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True)
    output = args.output_dir
    if not output.is_absolute():
        output = root / output
    try:
        paths, pending = generate(root, output)
    except (PlotInputError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "generated": [str(path) for path in paths],
                "pending_not_imputed": pending,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
