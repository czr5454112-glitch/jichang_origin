from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.eval import render_cie_baseline_lineage as lineage


def test_protocol_rows_preserve_identity_and_comparison_boundaries() -> None:
    rows = lineage.build_protocol_rows()
    lineage.validate_rows(rows)

    assert {row.protocol for row in rows} == {"P0", "P1", "P2"}
    assert len({(row.protocol, row.method_id) for row in rows}) == len(rows)
    assert all(
        row.cross_protocol_ranking == lineage.NO_CROSS_PROTOCOL_RANKING
        for row in rows
    )
    assert all(row.survivor_timing_allowed is False for row in rows)

    native_dh = next(row for row in rows if row.method_id == "FENG_NATIVE_CIE_DH")
    assert native_dh.protocol == "P0"
    assert native_dh.availability == "BLOCKED"
    assert native_dh.blocker == lineage.BLOCKED_NATIVE_DH
    assert native_dh.native_claim_allowed is False

    assert all(row.map_load_scope for row in rows)
    assert {row.speed_mps for row in rows} == {"2.5"}

    adapted = [row for row in rows if "ADAPTED" in row.method_id]
    assert adapted
    assert all(row.native_claim_allowed is False for row in adapted)
    assert all(row.executor == "COMMON_CPP_EVENT_EXECUTOR" for row in adapted)


def test_render_writes_identity_csv_and_nonempty_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    output_csv = tmp_path / "protocol.csv"
    output_png = tmp_path / "lineage.png"

    assert (
        lineage.main(
            [
                "--output-csv",
                str(output_csv),
                "--output-figure",
                str(output_png),
                "--dpi",
                "72",
            ]
        )
        == 0
    )

    with output_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    assert {row["protocol"] for row in rows} == {"P0", "P1", "P2"}
    assert all(
        row["cross_protocol_ranking"] == lineage.NO_CROSS_PROTOCOL_RANKING
        for row in rows
    )
    assert next(
        row for row in rows if row["method_id"] == "FENG_NATIVE_CIE_DH"
    )["blocker"] == lineage.BLOCKED_NATIVE_DH
    assert output_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output_png.stat().st_size > 10_000
