from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse

from scripts.eval.g4irsf12_literature_to_design import (
    ALLOWED_PRIMARY_HOSTS,
    EXPECTED_IDENTIFIERS,
    EXPECTED_IDS,
    FIELDS,
    LITERATURE_ROWS,
    REPORT_PATH,
    ROOT,
    TABLE_PATH,
    check_outputs,
    render_outputs,
    validate_rows,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_all_thirteen_required_sources_are_present_once_and_in_plan_order() -> None:
    assert validate_rows() == []
    assert len(LITERATURE_ROWS) == 13
    assert tuple(row["literature_id"] for row in LITERATURE_ROWS) == EXPECTED_IDS
    assert len({row["literature_id"] for row in LITERATURE_ROWS}) == 13
    assert tuple(row["order"] for row in LITERATURE_ROWS) == tuple(range(1, 14))


def test_identifiers_and_primary_urls_are_exact_and_auditable() -> None:
    for row in LITERATURE_ROWS:
        row_id = row["literature_id"]
        assert row["identifier"] == EXPECTED_IDENTIFIERS[row_id]
        parsed = urlparse(row["primary_source_url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in ALLOWED_PRIMARY_HOSTS
        assert not any(
            token in parsed.hostname
            for token in (
                "wikipedia",
                "researchgate",
                "semanticscholar",
                "scirp",
                "scribd",
            )
        )


def test_each_row_has_the_six_required_design_mapping_fields() -> None:
    required_mapping_fields = (
        "applicable_problem",
        "transferable_mechanism",
        "conflicting_assumptions",
        "target_module",
        "required_ab",
        "prohibited_overclaim",
    )
    for row in LITERATURE_ROWS:
        assert tuple(row.keys()) == FIELDS
        assert all(str(row[field]).strip() for field in required_mapping_fields)
        assert str(row["primary_evidence"]).strip()
        assert str(row["access_status"]).strip()


def test_access_limitations_are_explicit_instead_of_backfilled() -> None:
    access = {row["literature_id"]: row["access_status"] for row in LITERATURE_ROWS}
    assert access["JOHNSTONE_MERGE_2015"] == (
        "PRIMARY_PUBLISHER_ABSTRACT_AND_SECTION_SNIPPETS"
    )
    assert access["VARAIYA_MAX_PRESSURE_2013"] == (
        "PRIMARY_PUBLISHER_ABSTRACT_ONLY"
    )
    assert access["SORENSEN_DRL_BHS_2020"] == (
        "PRIMARY_PUBLISHER_ABSTRACT_ONLY"
    )
    assert access["IATA_ADRM_12"] == "OFFICIAL_SCOPE_PAGE_ONLY"

    by_id = {row["literature_id"]: row for row in LITERATURE_ROWS}
    assert "Full subscription text was not relied on" in by_id[
        "JOHNSTONE_MERGE_2015"
    ]["primary_evidence"]
    assert "paid manual text was not used" in by_id["IATA_ADRM_12"][
        "primary_evidence"
    ]


def test_required_claim_boundaries_are_fail_closed() -> None:
    by_id = {row["literature_id"]: row for row in LITERATURE_ROWS}

    pibt = by_id["PIBT_IJCAI_2019"]
    assert "31 directed SCCs" in pibt["conflicting_assumptions"]
    assert "11 weak-projection bridges" in pibt["conflicting_assumptions"]
    assert "classic PIBT completeness" in pibt["prohibited_overclaim"]
    assert "PIBT-inspired bounded local coordination" in pibt[
        "prohibited_overclaim"
    ]

    tassiulas = by_id["TASSIULAS_EPHREMIDES_1992"]
    varaiya = by_id["VARAIYA_MAX_PRESSURE_2013"]
    assert "throughput-optimal" in tassiulas["prohibited_overclaim"]
    assert "throughput-optimal" in varaiya["prohibited_overclaim"]
    assert "bounded local differential term" in tassiulas[
        "prohibited_overclaim"
    ]
    assert "not automatically max-pressure" in varaiya["prohibited_overclaim"]

    iata = by_id["IATA_ADRM_12"]
    acrp82 = by_id["ACRP_REPORT_82"]
    acrp163 = by_id["ACRP_REPORT_163"]
    assert "airport scope" in iata["prohibited_overclaim"]
    assert "1.25" in acrp82["prohibited_overclaim"]
    assert "finite realistic scale envelope" in acrp163["prohibited_overclaim"]


def test_ab_mappings_cover_architecture_resource_policy_and_demand_stages() -> None:
    mappings = " ".join(str(row["required_ab"]) for row in LITERATURE_ROWS)
    for required in (
        "B5 versus B6",
        "P0/P1/P2/P3/P4",
        "R2 versus R4",
        "C0-C6",
        "S0/S3/S4",
        "Phase L",
    ):
        assert required in mappings


def test_committed_report_and_csv_are_deterministic_and_complete() -> None:
    outputs = render_outputs()
    assert set(outputs) == {REPORT_PATH, TABLE_PATH}
    assert check_outputs(ROOT, outputs) == []

    rows = _read_csv(ROOT / TABLE_PATH)
    assert len(rows) == 13
    assert tuple(rows[0]) == FIELDS
    assert tuple(row["literature_id"] for row in rows) == EXPECTED_IDS

    report = (ROOT / REPORT_PATH).read_text(encoding="utf-8")
    assert "coverage: `13/13 COMPLETE`" in report
    assert "source_policy: `PRIMARY_OR_OFFICIAL_ONLY`" in report
    assert "PIBT-inspired bounded local coordination" in report
    assert "is **not throughput-optimal** by citation" in report
    assert "airport, terminal, local/transfer scope" in report
    assert report.count("### ") == 13
    for row in LITERATURE_ROWS:
        assert row["primary_source_url"] in report
