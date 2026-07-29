from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil

import pytest

from scripts import validate_g4irsf15_stage_ab_freeze as validator
from scripts.eval import g4irsf15_stage_ab_freeze as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read_csv(relative: Path) -> list[dict[str, str]]:
    with (REPOSITORY_ROOT / relative).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def _copy_bundle(destination: Path) -> Path:
    for relative in validator.REQUIRED_BUNDLE_FILES:
        source = REPOSITORY_ROOT / relative
        assert source.is_file(), relative.as_posix()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return destination


def test_committed_stage_ab_bundle_validates() -> None:
    result = validator.validate_stage_ab(REPOSITORY_ROOT)
    assert result["status"] == "PASS_STAGE_15AB_BUNDLE_VALID"
    assert result["output_count"] == 10
    assert result["original_1x_request_count"] == 335_770
    assert result["original_1x_breakdown_available"] is False
    assert result["formal_causal_label_count"] == 0


def test_generator_output_inventory_uses_new_namespace_only() -> None:
    assert set(generator.OUTPUT_PATHS) == set(validator.OUTPUT_PATHS)
    assert all(path.name.startswith("g4irsf15_") for path in generator.OUTPUT_PATHS)
    assert not set(generator.OUTPUT_PATHS) & set(validator.INPUT_PATHS)


def test_original_1x_breakdown_and_false_positive_limits_are_explicit() -> None:
    churn = _read_csv(validator.CHURN_TABLE)
    full = [
        row
        for row in churn
        if row["evidence_scope"] == "G4IRSF14_ORIGINAL_1X_E4_SCREENING"
    ]
    gaps = {row["dimension"]: row for row in full if row["dimension"] != "all"}
    assert set(gaps) == validator.UNAVAILABLE_FULL_BREAKDOWNS
    assert all(row["dimension_value"] == "NOT_RETAINED" for row in gaps.values())
    assert all(row["breakdown_available"] == "false" for row in gaps.values())
    assert all(row["request_count"] == "" for row in gaps.values())

    hotspots = _read_csv(validator.HOTSPOT_TABLE)
    full_hotspots = [
        row
        for row in hotspots
        if row["evidence_scope"] == "G4IRSF14_ORIGINAL_1X_E4_SCREENING"
    ]
    assert len(full_hotspots) == 1
    assert full_hotspots[0]["destination_node"] == "NOT_RETAINED"
    assert full_hotspots[0]["extrapolation_allowed"] == "false"

    screening = _read_csv(validator.SCREENING_TABLE)
    assert {row["formal_attempt_count"] for row in screening} == {"0"}
    assert {
        row["screening_false_positive_rate_estimate"] for row in screening
    } == {""}
    assert {row["estimate_status"] for row in screening} == {
        "NOT_ESTIMABLE_ZERO_ACTION_CHANGING_TRIALS"
    }


def test_exact_binary_roles_are_content_bound_and_verified() -> None:
    e4 = json.loads(
        (REPOSITORY_ROOT / validator.E4_CONTROL).read_text(encoding="utf-8")
    )
    assert {
        role: value["sha256"]
        for role, value in e4["binary_ledger"].items()
    } == dict(validator.BINARY_SHA256)
    manifest = json.loads(
        (REPOSITORY_ROOT / validator.CAMPAIGN_MANIFEST).read_text(
            encoding="utf-8"
        )
    )
    assert set(
        manifest["generation_binary_verification"][
            "roles_verified_in_this_invocation"
        ]
    ) == set(validator.BINARY_SHA256)
    assert (
        manifest["exact_binary_requirement"]["sha256"]
        == validator.BINARY_SHA256["e4_original_1x_screening"]
    )


def test_validator_rejects_sealed_input_and_output_tampering(
    tmp_path: Path,
) -> None:
    bundle = _copy_bundle(tmp_path / "bundle")

    census_path = bundle / validator.G14_CENSUS
    original_census = census_path.read_bytes()
    census_path.write_bytes(original_census + b" ")
    with pytest.raises(
        validator.StageABValidationError,
        match="SEALED_INPUT_CONTENT_DRIFT",
    ):
        validator.validate_stage_ab(bundle)
    census_path.write_bytes(original_census)

    table_path = bundle / validator.SCREENING_TABLE
    original_table = table_path.read_text(encoding="utf-8")
    table_path.write_text(
        original_table.replace(
            "NOT_ESTIMABLE_ZERO_ACTION_CHANGING_TRIALS",
            "0.0",
            1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(
        validator.StageABValidationError,
        match="CSV_ROW_SHA256_MISMATCH",
    ):
        validator.validate_stage_ab(bundle)
