#!/usr/bin/env python3
"""Render evidence-bound figures for the CIE activation load scan.

The activation heatmap reports a counterfactual change in the *raw scorer
argmin before feasibility filtering*.  It is deliberately not labelled as a
change in the final executed action.  Business and backlog curves are read
only from the fixed-denominator whole-population payload in each native run;
missing map/load cells remain ``NA`` and are never interpolated or filled.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402
import numpy as np  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTIVATION_CSV = ROOT / "outputs/tables/cie_component_activation.csv"
DEFAULT_RUNTIME_ROOT = ROOT / "outputs/runtime/cie_component_activation"
DEFAULT_FIGURE_ROOT = ROOT / "outputs/figures"

SCHEMA_RUN = "czr005.cie_component_activation.run.v1"
MAPS = ("map2", "nanning")
FACTORS = (1.0, 1.25, 1.5, 1.75, 2.0)
COMPONENTS = ("q", "i", "wc", "ws")
COMPONENT_LABELS = ("Q", "I", r"$w_c$", r"$w_s$")


class ActivationFigureError(RuntimeError):
    """Raised when a figure input would cross the evidence boundary."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ActivationFigureError(f"cannot read activation CSV {path}: {exc}") from exc
    if not rows:
        raise ActivationFigureError(f"activation CSV has no data rows: {path}")
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActivationFigureError(f"cannot read runtime JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ActivationFigureError(f"runtime JSON must contain an object: {path}")
    return value


def _factor(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ActivationFigureError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ActivationFigureError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ActivationFigureError(f"{label} must be finite")
    return number


def _integer(value: Any, label: str) -> int:
    number = _factor(value, label)
    if number < 0 or not number.is_integer():
        raise ActivationFigureError(f"{label} must be a non-negative integer")
    return int(number)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for name in path:
        if not isinstance(current, Mapping) or name not in current:
            raise ActivationFigureError(f"missing runtime field: {'.'.join(path)}")
        current = current[name]
    return current


def _cell_key(map_name: Any, factor: Any, source: str) -> tuple[str, float]:
    name = str(map_name).strip().lower()
    load = _factor(factor, f"{source} nominal_load_factor")
    if name not in MAPS or not any(_close(load, expected) for expected in FACTORS):
        raise ActivationFigureError(f"unexpected map/load cell in {source}: {name}:{load}")
    canonical_load = next(expected for expected in FACTORS if _close(load, expected))
    return name, canonical_load


def _activation_rates(
    rows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, float, str], float]:
    rates: dict[tuple[str, float, str], float] = {}
    seen_cells: set[tuple[str, float]] = set()
    for index, row in enumerate(rows, start=2):
        cell = _cell_key(
            row.get("map"), row.get("nominal_load_factor"), f"CSV row {index}"
        )
        if cell in seen_cells:
            raise ActivationFigureError(f"duplicate activation CSV cell: {cell}")
        seen_cells.add(cell)
        for component in COMPONENTS:
            opportunity_field = f"{component}_decision_any_candidate_nonzero_count"
            change_field = f"{component}_counterfactual_raw_argmin_change_count"
            if not str(row.get(opportunity_field, "")).strip() or not str(
                row.get(change_field, "")
            ).strip():
                continue
            opportunities = _integer(row[opportunity_field], opportunity_field)
            changes = _integer(row[change_field], change_field)
            if changes > opportunities:
                raise ActivationFigureError(
                    f"{change_field} exceeds its pre-feasibility opportunity count"
                )
            rates[(*cell, component)] = changes / opportunities if opportunities else 0.0
    return rates


def _fixed_population_point(value: Mapping[str, Any], source: Path) -> dict[str, Any]:
    """Extract only whole-population, fixed-denominator evidence."""

    detailed = _nested(value, "fixed_denominator_business", "detailed")
    if not isinstance(detailed, Mapping):
        raise ActivationFigureError(f"fixed-denominator details must be an object: {source}")
    denominator = _integer(
        detailed.get("denominator_raw_bags"), f"{source} denominator_raw_bags"
    )
    population_denominator = _integer(
        _nested(value, "population", "raw_bag_denominator"),
        f"{source} population.raw_bag_denominator",
    )
    if denominator <= 0 or population_denominator != denominator:
        raise ActivationFigureError(f"fixed raw-bag denominator mismatch: {source}")
    if detailed.get("fixed_denominator") is not True:
        raise ActivationFigureError(f"fixed-denominator flag is absent: {source}")
    if detailed.get("survivor_or_common_cohort_used") is not False:
        raise ActivationFigureError(f"survivor/common-cohort evidence is forbidden: {source}")

    completed = _integer(
        detailed.get("completed_raw_bag_count"), f"{source} completed_raw_bag_count"
    )
    on_time = _integer(
        detailed.get("on_time_raw_bag_count"), f"{source} on_time_raw_bag_count"
    )
    if completed > denominator or on_time > denominator:
        raise ActivationFigureError(f"fixed-denominator count exceeds population: {source}")
    completion_rate = _factor(detailed.get("completion_rate"), "completion_rate")
    on_time_rate = _factor(detailed.get("on_time_rate"), "on_time_rate")
    if not _close(completion_rate, completed / denominator):
        raise ActivationFigureError(f"completion rate is not fixed-denominator: {source}")
    if not _close(on_time_rate, on_time / denominator):
        raise ActivationFigureError(f"on-time rate is not fixed-denominator: {source}")

    backlog = _nested(detailed, "backlog", "raw_bag_total")
    if not isinstance(backlog, Mapping):
        raise ActivationFigureError(f"raw-bag backlog must be an object: {source}")
    arrivals = _integer(backlog.get("arrival_count"), f"{source} backlog arrival_count")
    departures = _integer(
        backlog.get("departure_count"), f"{source} backlog departure_count"
    )
    if arrivals != denominator or departures != completed:
        raise ActivationFigureError(
            f"raw-bag backlog does not use the fixed whole population: {source}"
        )
    backlog_counts = {
        name: _integer(backlog.get(name), f"{source} backlog {name}")
        for name in ("peak_backlog", "backlog_at_last_arrival", "end_backlog")
    }
    if any(count > denominator for count in backlog_counts.values()):
        raise ActivationFigureError(f"raw-bag backlog exceeds its denominator: {source}")
    return {
        "denominator": denominator,
        "completion_rate": completion_rate,
        "on_time_rate": on_time_rate,
        **{f"{name}_rate": count / denominator for name, count in backlog_counts.items()},
        "source": str(source),
    }


def _runtime_points(runtime_root: Path) -> dict[tuple[str, float], dict[str, Any]]:
    if not runtime_root.exists():
        return {}
    points: dict[tuple[str, float], dict[str, Any]] = {}
    for path in sorted(runtime_root.rglob("*.json")):
        value = _read_json(path)
        if value.get("schema") != SCHEMA_RUN or value.get("native_execution_started") is not True:
            continue
        cell = _cell_key(value.get("map"), value.get("nominal_load_factor"), str(path))
        if cell in points:
            raise ActivationFigureError(f"duplicate native runtime cell: {cell}")
        points[cell] = _fixed_population_point(value, path)
    return points


def _save(figure: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    figure.savefig(temporary, format="png", dpi=190, bbox_inches="tight")
    plt.close(figure)
    os.replace(temporary, path)


def _style_axes(axis: plt.Axes) -> None:
    axis.grid(axis="y", color="#d9d9d9", linewidth=0.7, alpha=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.set_xticks(FACTORS, [f"{factor:g}×" for factor in FACTORS])


def _missing_label(axis: plt.Axes, x: float, y: float = 0.025) -> None:
    axis.text(x, y, "NA", ha="center", va="bottom", fontsize=7, color="#777777")


def render_activation_heatmap(
    rates: Mapping[tuple[str, float, str], float], path: Path
) -> None:
    matrices = []
    for map_name in MAPS:
        matrices.append(
            np.array(
                [
                    [rates.get((map_name, factor, component), np.nan) * 100.0
                     for factor in FACTORS]
                    for component in COMPONENTS
                ],
                dtype=float,
            )
        )
    finite = np.concatenate([matrix[np.isfinite(matrix)] for matrix in matrices])
    maximum = float(finite.max()) if finite.size else 0.0
    vmax = max(0.01, maximum)
    color_map = plt.get_cmap("YlOrRd").copy()
    color_map.set_bad("#eeeeee")
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 3.9), sharey=True)
    image = None
    for axis, map_name, matrix in zip(axes, MAPS, matrices):
        image = axis.imshow(
            np.ma.masked_invalid(matrix), cmap=color_map, vmin=0.0, vmax=vmax,
            aspect="auto"
        )
        axis.set_title(map_name)
        axis.set_xticks(range(len(FACTORS)), [f"{factor:g}×" for factor in FACTORS])
        axis.set_yticks(range(len(COMPONENTS)), COMPONENT_LABELS)
        axis.set_xlabel("Nominal load factor")
        for row_index in range(len(COMPONENTS)):
            for column_index in range(len(FACTORS)):
                value = matrix[row_index, column_index]
                label = "NA" if not math.isfinite(value) else f"{value:.3g}%"
                color = "#666666" if label == "NA" else (
                    "white" if value > vmax * 0.55 else "#222222"
                )
                axis.text(column_index, row_index, label, ha="center", va="center",
                          fontsize=8, color=color)
    axes[0].set_ylabel("S4 score component removed counterfactually")
    assert image is not None
    colorbar = figure.colorbar(image, ax=axes, fraction=0.035, pad=0.04)
    colorbar.set_label("Pre-feasibility raw-argmin change rate (%)")
    figure.suptitle("CIE component activation across registered map-load cells", y=1.01)
    figure.text(
        0.5, -0.02,
        "Raw-argmin change is measured before feasibility filtering; it is not a final "
        "executed-action change. NA = missing cell; no values are imputed.",
        ha="center", va="top", fontsize=8.5,
    )
    figure.subplots_adjust(bottom=0.20, top=0.84, wspace=0.16, right=0.88)
    _save(figure, path)


def render_critical_load_curves(
    points: Mapping[tuple[str, float], Mapping[str, Any]], path: Path
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), sharey=True)
    styles = (
        ("completion_rate", "Completion", "#2a6fbb", "o"),
        ("on_time_rate", "On time", "#d95f02", "s"),
    )
    for axis, map_name in zip(axes, MAPS):
        for field, label, color, marker in styles:
            values = [
                float(points[(map_name, factor)][field])
                if (map_name, factor) in points else np.nan
                for factor in FACTORS
            ]
            axis.plot(FACTORS, values, label=label, color=color, marker=marker,
                      linewidth=1.8, markersize=5)
        for factor in FACTORS:
            if (map_name, factor) not in points:
                _missing_label(axis, factor)
        axis.set_title(map_name)
        axis.set_xlabel("Nominal load factor")
        axis.set_ylim(0.0, 1.035)
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
        _style_axes(axis)
    axes[0].set_ylabel("Rate over all original raw bags")
    axes[1].legend(loc="lower left", frameon=False)
    figure.suptitle("Critical-load business curves (fixed whole-population denominator)")
    figure.text(
        0.5, 0.01,
        "Incomplete bags remain in the denominator. NA = missing registered cell; "
        "lines are broken and no value is imputed.",
        ha="center", fontsize=8.5,
    )
    figure.subplots_adjust(bottom=0.20, top=0.84, wspace=0.12)
    _save(figure, path)


def render_backlog_curves(
    points: Mapping[tuple[str, float], Mapping[str, Any]], path: Path
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), sharey=True)
    styles = (
        ("peak_backlog_rate", "Peak", "#6a3d9a", "o"),
        ("backlog_at_last_arrival_rate", "At last arrival", "#1b9e77", "^"),
        ("end_backlog_rate", "Remaining after observed departures", "#c23b23", "s"),
    )
    for axis, map_name in zip(axes, MAPS):
        for field, label, color, marker in styles:
            values = [
                float(points[(map_name, factor)][field])
                if (map_name, factor) in points else np.nan
                for factor in FACTORS
            ]
            axis.plot(FACTORS, values, label=label, color=color, marker=marker,
                      linewidth=1.7, markersize=5)
        for factor in FACTORS:
            if (map_name, factor) not in points:
                _missing_label(axis, factor)
        axis.set_title(map_name)
        axis.set_xlabel("Nominal load factor")
        axis.set_ylim(0.0, 1.035)
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))
        _style_axes(axis)
    axes[0].set_ylabel("Raw-bag backlog / fixed raw-bag denominator")
    axes[1].legend(loc="upper left", frameon=False, fontsize=8)
    figure.suptitle("Whole-population raw-bag backlog across load")
    figure.text(
        0.5, 0.01,
        "Every released raw bag is an arrival; only completed raw bags are departures. "
        "NA = missing cell; no survivor cohort or imputation is used.",
        ha="center", fontsize=8.5,
    )
    figure.subplots_adjust(bottom=0.20, top=0.84, wspace=0.12)
    _save(figure, path)


def render_figures(
    *, activation_csv: Path, runtime_root: Path, figure_root: Path
) -> dict[str, Any]:
    rates = _activation_rates(_read_csv(activation_csv))
    points = _runtime_points(runtime_root)
    outputs = {
        "activation_heatmap": figure_root / "cie_component_activation_heatmap.png",
        "critical_load_curves": figure_root / "cie_critical_load_curves.png",
        "backlog_curves": figure_root / "cie_backlog_curves.png",
    }
    render_activation_heatmap(rates, outputs["activation_heatmap"])
    render_critical_load_curves(points, outputs["critical_load_curves"])
    render_backlog_curves(points, outputs["backlog_curves"])
    expected = {(map_name, factor) for map_name in MAPS for factor in FACTORS}
    return {
        "observed_activation_value_count": len(rates),
        "observed_fixed_denominator_cell_count": len(points),
        "missing_fixed_denominator_cells": [
            f"{map_name}:{factor:.2f}"
            for map_name, factor in sorted(expected - set(points))
        ],
        "pre_feasibility_raw_argmin_is_final_action": False,
        "survivor_or_common_cohort_used": False,
        "outputs": {name: str(path) for name, path in outputs.items()},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activation-csv", type=Path, default=DEFAULT_ACTIVATION_CSV)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--figure-root", type=Path, default=DEFAULT_FIGURE_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = render_figures(
            activation_csv=args.activation_csv.resolve(),
            runtime_root=args.runtime_root.resolve(),
            figure_root=args.figure_root.resolve(),
        )
    except ActivationFigureError as exc:
        print(f"CIE activation figure rendering failed: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
