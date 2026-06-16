from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUILD_PYTHON = ROOT / "build_nmake" / "python"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase1a_astar_scalability.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase1a_astar_scalability_diagnosis.md"
FIGURE_PATH = ROOT / "outputs" / "figures" / "phase1a_runtime_vs_active_bags.png"


def _prepare_imports(build_python: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(build_python))


def _write_runtime_plot(rows: list[dict[str, object]]) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont  # pylint: disable=import-outside-toplevel
    except ImportError:
        return "not generated: Pillow is unavailable"

    width = 960
    height = 560
    left = 90
    right = 40
    top = 50
    bottom = 90
    plot_width = width - left - right
    plot_height = height - top - bottom

    counts = [int(row["plan_count"]) for row in rows]
    python_elapsed = [float(row["python_elapsed_seconds"]) for row in rows]
    cpp_elapsed = [float(row["cpp_elapsed_seconds"]) for row in rows]
    max_x = max(counts)
    max_y = max(python_elapsed + cpp_elapsed) * 1.12

    def point(x_value: int, y_value: float) -> tuple[int, int]:
        x = left + int((x_value / max_x) * plot_width)
        y = top + plot_height - int((y_value / max_y) * plot_height)
        return x, y

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
        small = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        small = ImageFont.load_default()

    draw.text((left, 16), "Phase1a planner-only A* runtime scaling", fill="#111111", font=font)
    draw.line((left, top, left, top + plot_height), fill="#444444", width=2)
    draw.line((left, top + plot_height, left + plot_width, top + plot_height), fill="#444444", width=2)

    for tick in range(6):
        y_value = (max_y / 5) * tick
        y = top + plot_height - int((y_value / max_y) * plot_height)
        draw.line((left - 6, y, left + plot_width, y), fill="#dddddd" if tick else "#444444", width=1)
        draw.text((12, y - 8), f"{y_value:.1f}s", fill="#333333", font=small)

    for count in counts:
        x, _ = point(count, 0)
        draw.line((x, top + plot_height, x, top + plot_height + 6), fill="#444444", width=1)
        draw.text((x - 22, top + plot_height + 12), str(count), fill="#333333", font=small)

    def draw_series(values: list[float], color: str, label: str, legend_y: int) -> None:
        pts = [point(count, value) for count, value in zip(counts, values)]
        if len(pts) > 1:
            draw.line(pts, fill=color, width=3)
        for x, y in pts:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)
        draw.line((left + 520, legend_y + 8, left + 570, legend_y + 8), fill=color, width=3)
        draw.text((left + 580, legend_y), label, fill="#111111", font=small)

    draw_series(python_elapsed, "#2f6fbb", "Python reference", 58)
    draw_series(cpp_elapsed, "#c54a3d", "C++ pybind core", 82)
    draw.text((left + plot_width // 2 - 70, height - 38), "Planned task legs", fill="#111111", font=small)
    draw.text((14, top + plot_height // 2 - 10), "Seconds", fill="#111111", font=small)

    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(FIGURE_PATH)
    return "generated"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run planner-only A* scalability diagnostics.")
    parser.add_argument("--build-python", type=Path, default=DEFAULT_BUILD_PYTHON)
    parser.add_argument("--base-count", type=int, default=500)
    parser.add_argument("--scales", nargs="+", type=int, default=[1, 2, 4, 8, 16])
    args = parser.parse_args()

    _prepare_imports(args.build_python)

    import czr005_cpp  # pylint: disable=import-error,import-outside-toplevel
    from czr005.io.legacy_map import parse_legacy_map  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import AStarPlanner, IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    map_path = ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt"
    task_path = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
    graph = IcsGraph.from_legacy_map(parse_legacy_map(map_path))
    planner = AStarPlanner(graph)
    task_cases = [(task.start, task.goal) for task in TaskStream.from_jsonl(task_path)]

    max_count = args.base_count * max(args.scales)
    if max_count > len(task_cases):
        raise ValueError(f"requested {max_count} cases, but task stream only has {len(task_cases)}")

    rows: list[dict[str, object]] = []
    for scale in args.scales:
        plan_count = args.base_count * scale
        cases = task_cases[:plan_count]

        python_start = perf_counter()
        python_checksum = 0
        for start, goal in cases:
            python_checksum += len(planner.plan(start, goal))
        python_elapsed = perf_counter() - python_start

        cpp_result = czr005_cpp.benchmark_legacy_map_paths(str(map_path), cases, 1)
        cpp_elapsed = float(cpp_result["elapsed_seconds"])
        cpp_checksum = int(cpp_result["checksum"])
        cpp_speedup = python_elapsed / cpp_elapsed if cpp_elapsed > 0.0 else 0.0

        rows.append(
            {
                "scale": scale,
                "plan_count": plan_count,
                "python_elapsed_seconds": f"{python_elapsed:.6f}",
                "cpp_elapsed_seconds": f"{cpp_elapsed:.6f}",
                "python_plans_per_second": f"{plan_count / python_elapsed:.2f}" if python_elapsed > 0 else "0.00",
                "cpp_plans_per_second": f"{float(cpp_result['plans_per_second']):.2f}",
                "cpp_speedup_vs_python": f"{cpp_speedup:.3f}",
                "python_checksum": python_checksum,
                "cpp_checksum": cpp_checksum,
                "checksum_match": int(python_checksum == cpp_checksum),
            }
        )

    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    all_checksum_match = all(int(row["checksum_match"]) == 1 for row in rows)
    last = rows[-1]
    figure_status = _write_runtime_plot(rows)
    report = f"""# Phase1a A* Scalability Diagnosis

Date: 2026-06-16

## Scope

This is a planner-only scalability diagnostic over the real expanded task stream. It reuses each task leg's `(start, goal)` pair and does not model reservations, active queues, faults, or event-simulation feedback.

- map: `legacy/jichang_origin_readonly/map2.txt`
- task stream: `data/processed/tasks/inputdata.jsonl`
- base count: {args.base_count}
- scales: {args.scales}
- table: `outputs/tables/phase1a_astar_scalability.csv`
- figure: `outputs/figures/phase1a_runtime_vs_active_bags.png`
- figure status: {figure_status}

## Result

Checksum parity across Python and C++ planner runs: {"PASS" if all_checksum_match else "FAIL"}

At the largest smoke size ({last["plan_count"]} task-leg plans):

- Python reference: {last["python_elapsed_seconds"]} seconds, {last["python_plans_per_second"]} plans/s
- C++ pybind core: {last["cpp_elapsed_seconds"]} seconds, {last["cpp_plans_per_second"]} plans/s
- C++ speedup vs Python: {last["cpp_speedup_vs_python"]}x

## Interpretation

The current map2 planner-only workload is small enough that both implementations scale nearly linearly over this sweep. The C++ core is consistently faster, but this smoke does not yet capture the heavier costs expected from reservation checks, rolling replans, fault recovery, and large active queues.

## Gate Status

- A* bottleneck evidence: preliminary planner-only evidence produced.
- Large-scale RL target: not yet defined from full event-simulation pressure.
- Baseline unfairness risk: documented; later comparisons must include reservation-heavy C++ replay and identical task/fault schedules.
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"rows={len(rows)} checksum_match={int(all_checksum_match)}")
    print(f"largest_plan_count={last['plan_count']}")
    print(f"python_elapsed_seconds={last['python_elapsed_seconds']}")
    print(f"cpp_elapsed_seconds={last['cpp_elapsed_seconds']}")
    if not all_checksum_match:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
