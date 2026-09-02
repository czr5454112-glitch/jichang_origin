#!/usr/bin/env python3
"""Render the frozen CIE baseline protocol matrix and lineage diagram.

The artifact is intentionally descriptive: it records which executor and
release protocol produced each evidence row.  It never reads performance
metrics and therefore cannot manufacture a ranking across P0/P1/P2.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
LINEAGE_DOC = ROOT / "docs/baselines/baseline_lineage_and_protocols.md"
FENG_CONFIG = ROOT / "configs/baselines/feng_native_cie_dh.yaml"
CIE_DH_CONFIG = ROOT / "configs/baselines/cie_dh_replica.yaml"
TARAU_CONFIG = ROOT / "configs/baselines/tarau_distributed_2010.yaml"

DEFAULT_CSV = ROOT / "outputs/tables/cie_baseline_protocol_matrix.csv"
DEFAULT_FIGURE = ROOT / "outputs/figures/baseline_lineage_protocol_diagram.png"

BLOCKED_NATIVE_DH = "BLOCKED_FENG_NATIVE_DH_SOURCE_NOT_RECOVERED"
NO_CROSS_PROTOCOL_RANKING = "PROHIBITED_P0_P1_P2_MUST_REMAIN_SEPARATE"


class LineageError(RuntimeError):
    """Raised when the frozen lineage sources no longer support the diagram."""


@dataclass(frozen=True)
class ProtocolRow:
    protocol: str
    protocol_role: str
    method_id: str
    display_name: str
    family: str
    executor: str
    release_protocol: str
    coordination: str
    implementation_class: str
    evidence_label: str
    availability: str
    native_claim_allowed: bool
    comparison_eligibility: str
    ranking_scope: str
    cross_protocol_ranking: str
    survivor_timing_allowed: bool
    blocker: str
    source_config: str
    source_doc: str
    map_load_scope: str
    speed_mps: str


CSV_FIELDS = tuple(ProtocolRow.__dataclass_fields__)


def _require_markers(path: Path, markers: Sequence[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LineageError(f"cannot read lineage source {path}: {exc}") from exc
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise LineageError(
            f"lineage source {path} is missing frozen marker(s): {missing}"
        )


def validate_lineage_sources() -> None:
    """Fail closed if source labels or protocol boundaries have drifted."""

    _require_markers(
        LINEAGE_DOC,
        (
            "P0：Feng 原生 Java 执行器",
            "P1：公共 C++ 事件执行器",
            "P2：端到端系统对照",
            "禁止跨协议排名",
            "neutral FIFO",
        ),
    )
    _require_markers(
        FENG_CONFIG,
        (
            "executor: FENG_NATIVE_JAVA",
            f"status: {BLOCKED_NATIVE_DH}",
            "substitute_common_executor_results: false",
            "no_cross_protocol_ranking: true",
        ),
    )
    _require_markers(
        CIE_DH_CONFIG,
        (
            "family: TARAU_LOCAL_2009_CIE_DH",
            "evidence_label: ADAPTED_BASELINE",
            "exact_reproduction: false",
        ),
    )
    _require_markers(
        TARAU_CONFIG,
        (
            "formal_name: TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY",
            "evidence_label: ADAPTED_BASELINE",
            "exact_reproduction: false",
        ),
    )


def build_protocol_rows() -> list[ProtocolRow]:
    """Return one row per method/protocol identity, never one row per alias."""

    doc = "docs/baselines/baseline_lineage_and_protocols.md"
    feng = "configs/baselines/feng_native_cie_dh.yaml"
    cie_dh = "configs/baselines/cie_dh_replica.yaml"
    tarau = "configs/baselines/tarau_distributed_2010.yaml"
    p1_release = "same_hca_release@1x;canonical_release@2x"

    return [
        ProtocolRow(
            "P0",
            "native_algorithm_reproduction",
            "FENG_NATIVE_HCA",
            "Feng-native HCA",
            "FENG_CIE",
            "FENG_NATIVE_JAVA",
            "feng_original_native_release@map2_1x",
            "centralized_HCA_reservation_scheduler",
            "native_original",
            "NATIVE_ORIGINAL_BASELINE",
            "AVAILABLE_HCA_REGRESSION_ONLY",
            True,
            "HCA_REGRESSION_ONLY_NO_NATIVE_DH_PAIR",
            "WITHIN_P0_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            feng,
            doc,
            "map2@1x",
            "2.5",
        ),
        ProtocolRow(
            "P0",
            "native_algorithm_reproduction",
            "FENG_NATIVE_CIE_DH",
            "Feng-native CIE-DH",
            "FENG_CIE",
            "FENG_NATIVE_JAVA",
            "feng_original_native_release@map2_1x",
            "native_position_level_local_switching_unrecovered",
            "native_original_unrecovered",
            BLOCKED_NATIVE_DH,
            "BLOCKED",
            False,
            "NOT_ELIGIBLE",
            "WITHIN_P0_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            BLOCKED_NATIVE_DH,
            feng,
            doc,
            "map2@1x",
            "2.5",
        ),
        ProtocolRow(
            "P1",
            "common_executor_mechanism_comparison",
            "G31_S4_NEUTRAL_FIFO",
            "G31/S4 neutral-FIFO route scorer",
            "CZR005_G31",
            "COMMON_CPP_EVENT_EXECUTOR",
            p1_release,
            "neutral_fifo",
            "project_native",
            "PROJECT_METHOD",
            "AVAILABLE",
            True,
            "ELIGIBLE_WITHIN_MATCHED_P1_CELL",
            "WITHIN_P1_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            "configs/eval/cie_revision_manifest.yaml",
            doc,
            "map2+nanning@1x+2x",
            "2.5",
        ),
        ProtocolRow(
            "P1",
            "common_executor_mechanism_comparison",
            "CIE_DH_ADAPTED_H_FF",
            "CIE-DH adapted (H_FF)",
            "TARAU_LOCAL_2009_CIE_DH",
            "COMMON_CPP_EVENT_EXECUTOR",
            p1_release,
            "neutral_fifo",
            "adapted_common_executor",
            "ADAPTED_BASELINE_NOT_NATIVE",
            "AVAILABLE",
            False,
            "ELIGIBLE_WITHIN_MATCHED_P1_CELL",
            "WITHIN_P1_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            cie_dh,
            doc,
            "map2+nanning@1x+2x",
            "2.5",
        ),
        ProtocolRow(
            "P1",
            "common_executor_mechanism_comparison",
            "CIE_DH_ADAPTED_H_SA",
            "CIE-DH adapted (H_SA)",
            "TARAU_LOCAL_2009_CIE_DH",
            "COMMON_CPP_EVENT_EXECUTOR",
            p1_release,
            "neutral_fifo",
            "adapted_common_executor",
            "ADAPTED_BASELINE_NOT_NATIVE",
            "AVAILABLE",
            False,
            "ELIGIBLE_WITHIN_MATCHED_P1_CELL",
            "WITHIN_P1_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            cie_dh,
            doc,
            "map2+nanning@1x+2x",
            "2.5",
        ),
        ProtocolRow(
            "P1",
            "common_executor_mechanism_comparison",
            "TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY",
            "Tarau distributed 2010 adapted route-only",
            "TARAU_DISTRIBUTED_2010",
            "COMMON_CPP_EVENT_EXECUTOR",
            p1_release,
            "neutral_fifo",
            "adapted_route_only",
            "ADAPTED_BASELINE",
            "AVAILABLE",
            False,
            "ELIGIBLE_WITHIN_MATCHED_P1_CELL",
            "WITHIN_P1_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            tarau,
            doc,
            "map2+nanning@1x+2x",
            "2.5",
        ),
        ProtocolRow(
            "P2",
            "end_to_end_system_comparison",
            "FENG_NATIVE_HCA_SYSTEM",
            "Feng-native HCA system",
            "FENG_CIE",
            "FENG_NATIVE_JAVA",
            "system_native_population_matched",
            "centralized_HCA_reservation_scheduler",
            "native_original_system",
            "NATIVE_ORIGINAL_BASELINE",
            "AVAILABLE",
            True,
            "END_TO_END_SYSTEM_COMPARISON_ONLY",
            "WITHIN_P2_SYSTEM_OUTCOMES_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            feng,
            doc,
            "population-matched formal map/load cells",
            "2.5",
        ),
        ProtocolRow(
            "P2",
            "end_to_end_system_comparison",
            "G31_S4_NATIVE_SYSTEM",
            "G31/S4 native event system",
            "CZR005_G31",
            "COMMON_CPP_EVENT_EXECUTOR",
            "system_native_population_matched",
            "decentralized_junction_coordination",
            "project_native_system",
            "PROJECT_METHOD",
            "AVAILABLE",
            True,
            "END_TO_END_SYSTEM_COMPARISON_ONLY",
            "WITHIN_P2_SYSTEM_OUTCOMES_ONLY",
            NO_CROSS_PROTOCOL_RANKING,
            False,
            "",
            "configs/eval/cie_revision_manifest.yaml",
            doc,
            "population-matched formal map/load cells",
            "2.5",
        ),
    ]


def validate_rows(rows: Sequence[ProtocolRow]) -> None:
    if {row.protocol for row in rows} != {"P0", "P1", "P2"}:
        raise LineageError("protocol matrix must contain P0, P1, and P2")
    identities = [(row.protocol, row.method_id) for row in rows]
    if len(identities) != len(set(identities)):
        raise LineageError("duplicate method identity within a protocol")
    if any(row.cross_protocol_ranking != NO_CROSS_PROTOCOL_RANKING for row in rows):
        raise LineageError("every row must explicitly prohibit cross-protocol ranking")
    native_dh = [row for row in rows if row.method_id == "FENG_NATIVE_CIE_DH"]
    if len(native_dh) != 1 or native_dh[0].blocker != BLOCKED_NATIVE_DH:
        raise LineageError("native Feng CIE-DH must remain explicitly blocked")
    if any(row.survivor_timing_allowed for row in rows):
        raise LineageError("survivor-only timing cannot enter the protocol matrix")


def write_protocol_csv(rows: Sequence[ProtocolRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def render_lineage(rows: Sequence[ProtocolRow], output: Path, dpi: int = 180) -> None:
    """Render a compact evidence-lineage diagram, not a performance chart."""

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    except ImportError as exc:
        raise LineageError("matplotlib is required to render the lineage figure") from exc

    validate_rows(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(15.5, 8.4))
    ax.set_xlim(0, 15.5)
    ax.set_ylim(0, 8.4)
    ax.axis("off")

    colors = {"P0": "#4C78A8", "P1": "#2A9D8F", "P2": "#8F5AA2"}

    def box(
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
        color: str,
        *,
        linestyle: str = "-",
        alpha: float = 0.13,
        fontsize: float = 9.0,
    ) -> tuple[float, float]:
        patch = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.06,rounding_size=0.08",
            facecolor=color,
            edgecolor=color,
            linewidth=1.6,
            linestyle=linestyle,
            alpha=alpha,
        )
        ax.add_patch(patch)
        ax.text(
            x + width / 2,
            y + height / 2,
            text,
            ha="center",
            va="center",
            fontsize=fontsize,
            color="#17202A",
            linespacing=1.25,
        )
        return x + width / 2, y + height / 2

    def arrow(
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        color: str = "#65727E",
        linestyle: str = "-",
    ) -> None:
        ax.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=12,
                linewidth=1.4,
                color=color,
                linestyle=linestyle,
                connectionstyle="arc3,rad=0",
            )
        )

    def routed_arrow(
        points: Sequence[tuple[float, float]],
        *,
        color: str = "#65727E",
        linestyle: str = "-",
    ) -> None:
        if len(points) < 2:
            raise LineageError("routed arrow requires at least two points")
        xs = [point[0] for point in points[:-1]]
        ys = [point[1] for point in points[:-1]]
        ax.plot(xs, ys, color=color, linewidth=1.4, linestyle=linestyle)
        arrow(points[-2], points[-1], color=color, linestyle=linestyle)

    ax.text(
        0.4,
        8.05,
        "CIE baseline lineage and protocol boundaries",
        ha="left",
        va="center",
        fontsize=17,
        weight="bold",
        color="#17202A",
    )
    ax.text(
        0.4,
        7.62,
        "P0 / P1 / P2 are separate evidence strata — cross-protocol ranking is prohibited",
        ha="left",
        va="center",
        fontsize=11,
        weight="bold",
        color="#B23A48",
    )

    ax.text(0.55, 7.08, "Lineage / implementation", fontsize=11, weight="bold")
    ax.text(4.55, 7.08, "P0 · native reproduction", fontsize=11, weight="bold", color=colors["P0"])
    ax.text(8.28, 7.08, "P1 · common executor", fontsize=11, weight="bold", color=colors["P1"])
    ax.text(12.22, 7.08, "P2 · system outcomes", fontsize=11, weight="bold", color=colors["P2"])

    feng_source = box(
        0.45,
        5.45,
        3.25,
        1.05,
        "Recovered Feng Java source\n(original HCA only)",
        colors["P0"],
    )
    hca_p0 = box(
        4.25,
        5.45,
        3.05,
        1.05,
        "Feng-native HCA\nFENG_NATIVE_JAVA · available",
        colors["P0"],
    )
    arrow((3.7, feng_source[1]), (4.25, hca_p0[1]), color=colors["P0"])

    paper_dh = box(
        0.45,
        3.94,
        3.25,
        1.05,
        "Published native CIE-DH semantics\n(source/call chain not recovered)",
        "#C44E52",
        linestyle="--",
    )
    dh_p0 = box(
        4.25,
        3.94,
        3.05,
        1.05,
        "Feng-native CIE-DH\nBLOCKED · no substitute",
        "#C44E52",
        linestyle="--",
    )
    arrow((3.7, paper_dh[1]), (4.25, dh_p0[1]), color="#C44E52", linestyle="--")

    project = box(
        0.45,
        2.42,
        3.25,
        1.05,
        "czr005 G31/S4\ndecentralized event method",
        colors["P1"],
    )
    g31_p1 = box(
        8.0,
        4.95,
        3.45,
        0.95,
        "G31/S4 · project native\nneutral FIFO",
        colors["P1"],
    )
    routed_arrow(
        ((3.7, project[1]), (7.65, project[1]), (7.65, g31_p1[1]), (8.0, g31_p1[1])),
        color=colors["P1"],
    )

    adapted = box(
        0.45,
        0.88,
        3.25,
        1.05,
        "CIE-DH / Tarau literature families\nadapted implementations",
        "#E09F3E",
    )
    dh_p1 = box(
        8.0,
        3.55,
        3.45,
        1.00,
        "CIE-DH adapted · H_FF / H_SA\nnot native; aliases count once",
        "#E09F3E",
    )
    tarau_p1 = box(
        8.0,
        2.18,
        3.45,
        0.95,
        "Tarau-2010 adapted route-only\nnot native",
        "#E09F3E",
    )
    routed_arrow(
        ((3.7, adapted[1] + 0.16), (7.48, adapted[1] + 0.16), (7.48, dh_p1[1]), (8.0, dh_p1[1])),
        color="#E09F3E",
    )
    routed_arrow(
        ((3.7, adapted[1] - 0.16), (7.28, adapted[1] - 0.16), (7.28, tarau_p1[1]), (8.0, tarau_p1[1])),
        color="#E09F3E",
    )

    common = box(
        8.0,
        0.67,
        3.45,
        0.95,
        "COMMON_CPP_EVENT_EXECUTOR\n1x same-HCA · 2x canonical",
        colors["P1"],
        alpha=0.08,
    )
    routed_arrow(
        ((11.45, g31_p1[1]), (11.68, g31_p1[1]), (11.68, common[1]), (11.45, common[1])),
        color=colors["P1"],
        linestyle=":",
    )
    routed_arrow(
        ((11.45, dh_p1[1]), (11.68, dh_p1[1]), (11.68, common[1]), (11.45, common[1])),
        color=colors["P1"],
        linestyle=":",
    )
    routed_arrow(
        ((11.45, tarau_p1[1]), (11.68, tarau_p1[1]), (11.68, common[1]), (11.45, common[1])),
        color=colors["P1"],
        linestyle=":",
    )

    p2 = box(
        12.05,
        3.48,
        3.05,
        1.62,
        "End-to-end system comparison\n\nFeng-native HCA system\nvs\nG31/S4 native event system",
        colors["P2"],
    )
    routed_arrow(
        ((7.3, hca_p0[1]), (7.62, hca_p0[1]), (7.62, 6.72), (11.82, 6.72), (11.82, p2[1] + 0.32), (12.05, p2[1] + 0.32)),
        color=colors["P2"],
    )
    arrow((11.45, g31_p1[1]), (12.05, p2[1] - 0.32), color=colors["P2"])
    ax.text(
        p2[0],
        2.97,
        "Interpretation: system-combination gap only\n(not strict scorer dominance)",
        ha="center",
        va="center",
        fontsize=9.1,
        color=colors["P2"],
        weight="bold",
    )

    ax.text(
        12.0,
        1.18,
        "Shared publication gates\n• canonical population first\n• full-population latency only\n• survivor timing forbidden",
        ha="left",
        va="center",
        fontsize=9.3,
        color="#34495E",
        linespacing=1.35,
    )

    fig.savefig(output, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument(
        "--skip-source-validation",
        action="store_true",
        help="Only for isolated tests; publication generation must validate sources.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.skip_source_validation:
        validate_lineage_sources()
    rows = build_protocol_rows()
    validate_rows(rows)
    write_protocol_csv(rows, args.output_csv)
    render_lineage(rows, args.output_figure, dpi=args.dpi)
    print(f"wrote {args.output_csv}")
    print(f"wrote {args.output_figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
