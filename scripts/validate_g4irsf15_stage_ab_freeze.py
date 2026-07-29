#!/usr/bin/env python3
"""Independent validator for the G4IRSF15 Stage 15A/15B freeze.

The validator intentionally does not import the generator.  It independently
fixes the input identities, output inventory, schemas, counters, row hashes,
content bindings, binary identities, and explicit evidence limitations.
Recorded generation-host binary paths are never resolved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
G13_PER_BAG = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
G14_BASELINE = Path("artifacts/gates/g4irsf14_baseline_registry.json")
G14_F2 = Path("artifacts/policies/g4irsf14_f2_frozen_control.json")
G14_CLONE = Path("artifacts/datasets/g4irsf14_clone_manifest.json")
G14_CENSUS = Path("outputs/tables/g4irsf14_opportunity_census.json")
G14_MERGE_CONFIG = Path(
    "artifacts/configs/g4irsf14_merge_grant_protocol.json"
)
G14_MERGE_RULE = Path("outputs/tables/g4irsf14_merge_rule_ab.csv")
G14_LIFECYCLE = Path("outputs/tables/g4irsf14_merge_grant_lifecycle.csv")
G14_EVENT_TABLE = Path("outputs/tables/g4irsf14_event_microphase_ab.csv")
G14_EVENT_REPORT = Path("outputs/reports/g4irsf14_event_microphase_ab.md")

START_REPORT = Path("outputs/reports/g4irsf15_start_state.md")
POSTMORTEM_REPORT = Path("outputs/reports/g4irsf15_g4irsf14_postmortem.md")
CHURN_REPORT = Path(
    "outputs/reports/g4irsf15_merge_request_churn_postmortem.md"
)
CHURN_TABLE = Path("outputs/tables/g4irsf15_merge_request_churn.csv")
HOTSPOT_TABLE = Path(
    "outputs/tables/g4irsf15_merge_destination_hotspots.csv"
)
SCREENING_TABLE = Path(
    "outputs/tables/g4irsf15_screening_false_positive_estimate.csv"
)
BASELINE_REGISTRY = Path("artifacts/gates/g4irsf15_baseline_registry.json")
F2_CONTROL = Path("artifacts/policies/g4irsf15_f2_frozen_control.json")
E4_CONTROL = Path(
    "artifacts/policies/g4irsf15_e4_frozen_mechanism_control.json"
)
CAMPAIGN_MANIFEST = Path(
    "artifacts/datasets/g4irsf15_campaign_source_manifest.json"
)

OUTPUT_PATHS = (
    START_REPORT,
    POSTMORTEM_REPORT,
    CHURN_REPORT,
    CHURN_TABLE,
    HOTSPOT_TABLE,
    SCREENING_TABLE,
    BASELINE_REGISTRY,
    F2_CONTROL,
    E4_CONTROL,
    CAMPAIGN_MANIFEST,
)

INPUT_PATHS = (
    MAP_PATH,
    TASK_PATH,
    G13_PER_BAG,
    G14_BASELINE,
    G14_F2,
    G14_CLONE,
    G14_CENSUS,
    G14_MERGE_CONFIG,
    G14_MERGE_RULE,
    G14_LIFECYCLE,
    G14_EVENT_TABLE,
    G14_EVENT_REPORT,
)

REQUIRED_BUNDLE_FILES = tuple(
    sorted(set(INPUT_PATHS) | set(OUTPUT_PATHS), key=lambda path: path.as_posix())
)

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
FULL_SEGMENT_COUNT = 43_603
FULL_RAW_BAG_COUNT = 28_506
REPOSITORY_SLUG = "czr5454112-glitch/jichang_origin"
REQUIRED_BASE_COMMIT = "966a063573f0419df1324708db75211c521d59db"

EXPECTED_SEMANTIC_SHA256: Mapping[Path, str] = {
    G13_PER_BAG: (
        "fc3dde5aa958d23be4a186e0727702db6895980847d1473b21c5134d002ca551"
    ),
    G14_BASELINE: (
        "331338197366eb51e604d4f18296d6c41a54a6a426eee5963648223ae9f24e46"
    ),
    G14_F2: (
        "2e2c66244ceb4ff1b514da211487d8c5223f7a29304548309856824297eccfaf"
    ),
    G14_CLONE: (
        "f5b8c2629f627728aa774bf1117f8a6f1eef90ad6be2417a35ed962ad2e0fa0f"
    ),
    G14_CENSUS: (
        "365d2a8f860944616f5e7199be2c3c86b3d07dc743ba793b978b0fedf4586de3"
    ),
    G14_MERGE_CONFIG: (
        "e36e81bcc4aafa1b3d222fdd0d634dae687fa337d706c7af28c38141585298e4"
    ),
    G14_MERGE_RULE: (
        "8808a79443a20bf2bfdee35ead5789b52d76a0ea386153ffd267a78020dc31c1"
    ),
    G14_LIFECYCLE: (
        "138f8af81d844cb2aa021f7b0667c0c1aa1133db29fb7b640e0f6fa6eec9920f"
    ),
    G14_EVENT_TABLE: (
        "86344c5f48cba6a378855129509ad5267b8300485f8609f2976aed53db15c3ce"
    ),
    G14_EVENT_REPORT: (
        "c2cd7a80f7cd5b318891e7e9393ed9c80f7c4c25263007fc85b8bac86c77720f"
    ),
}

BINARY_SHA256: Mapping[str, str] = {
    "f2_frozen_control": (
        "814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7"
    ),
    "e4_original_1x_screening": (
        "11b957890666a4ac4dd056fca4828cecb6b3f3ff29fdc590d05c4cff875ebc71"
    ),
    "e4_stage_d_mechanism": (
        "0d82141e8e650d682f812fe18582661ba6feb6dd08c88731c343d3caf07d6a38"
    ),
    "event_microphase_instrumented": (
        "e10da3f5fcf49d3522eb51e70523b2b8d2d2a747cee07d3991d9f74de1efb233"
    ),
}

CHURN_FIELDS = (
    "schema",
    "evidence_scope",
    "selection",
    "dimension",
    "dimension_value",
    "completed_movement_count",
    "unique_requesting_segment_count",
    "request_count",
    "active_grant_rejection_count",
    "arbitration_count",
    "lifecycle_transition_count",
    "lifecycle_dropped_count",
    "requests_per_completed_movement",
    "rejections_per_completed_movement",
    "arbitrations_per_completed_movement",
    "event_count",
    "events_per_completed_movement",
    "protocol_mean_grant_wait_seconds",
    "mean_successful_fifo_wait_seconds",
    "peak_pending_request_count",
    "multi_request_live_boundary_count",
    "queue_capacity_block_count",
    "exact_slot_busy_count",
    "stale_generation_count",
    "fault_count",
    "breakdown_available",
    "extrapolation_allowed",
    "source_limitation",
    "row_sha256",
)

HOTSPOT_FIELDS = (
    "schema",
    "evidence_scope",
    "rank",
    "destination_node",
    "request_count",
    "request_share",
    "active_grant_rejection_count",
    "rejection_share",
    "unique_requesting_segment_count",
    "successful_issue_count",
    "mean_successful_fifo_wait_seconds",
    "breakdown_available",
    "extrapolation_allowed",
    "source_limitation",
    "row_sha256",
)

SCREENING_FIELDS = (
    "schema",
    "intervention_kind",
    "support_semantics",
    "screening_support_count",
    "prefilter_count",
    "committed_target_descriptor_count",
    "formal_attempt_count",
    "action_changed_count",
    "complete_h_bag_count",
    "complete_h_system_count",
    "screening_false_positive_rate_estimate",
    "estimate_status",
    "campaign_source_status",
    "source_screening_manifest_sha256",
    "blocker",
    "row_sha256",
)

UNAVAILABLE_FULL_BREAKDOWNS = {
    "destination",
    "upstream",
    "hour",
    "source",
    "goal",
    "storage_direct",
    "entry_time_band",
    "deadline_slack_bucket",
    "retry_count",
    "active_grant",
    "queue_capacity",
    "stale_generation",
    "exact_slot_busy",
    "fault",
}


class StageABValidationError(RuntimeError):
    """Raised for a malformed or semantically invalid freeze bundle."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_sha256(path: Path) -> str:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StageABValidationError(f"NON_UTF8_FILE:{path}") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_json(root: Path, relative: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageABValidationError(
            f"INVALID_JSON:{relative.as_posix()}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise StageABValidationError(
            f"JSON_ROOT_NOT_OBJECT:{relative.as_posix()}"
        )
    return value


def _read_csv(
    root: Path,
    relative: Path,
    expected_fields: Sequence[str],
) -> list[dict[str, str]]:
    try:
        with (root / relative).open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            rows = list(reader)
    except OSError as exc:
        raise StageABValidationError(
            f"INVALID_CSV:{relative.as_posix()}:{exc}"
        ) from exc
    if fields != tuple(expected_fields):
        raise StageABValidationError(
            f"CSV_FIELDS_MISMATCH:{relative.as_posix()}:{fields}"
        )
    for index, row in enumerate(rows, start=2):
        declared = row.get("row_sha256", "")
        projection = dict(row)
        projection.pop("row_sha256", None)
        if declared != canonical_sha256(projection):
            raise StageABValidationError(
                f"CSV_ROW_SHA256_MISMATCH:{relative.as_posix()}:{index}"
            )
    return rows


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise StageABValidationError(code)


def _validate_self_hash(relative: Path, value: Mapping[str, Any]) -> None:
    declared = value.get("self_sha256")
    projection = dict(value)
    projection.pop("self_sha256", None)
    _require(
        isinstance(declared, str)
        and declared == canonical_sha256(projection),
        f"JSON_SELF_SHA256_MISMATCH:{relative.as_posix()}",
    )


def _validate_output_binding(
    root: Path,
    expected_relative: Path,
    binding: Mapping[str, Any],
    *,
    code: str,
) -> None:
    _require(
        binding.get("path") == expected_relative.as_posix(),
        f"{code}:PATH",
    )
    path = root / expected_relative
    _require(path.is_file(), f"{code}:MISSING")
    _require(
        binding.get("sha256") == file_sha256(path),
        f"{code}:SHA256",
    )
    _require(
        binding.get("byte_count") == path.stat().st_size,
        f"{code}:BYTE_COUNT",
    )
    _require(
        binding.get("hash_mode") == "sha256_exact_bytes",
        f"{code}:HASH_MODE",
    )


def _validate_input_binding(
    root: Path,
    expected_relative: Path,
    binding: Mapping[str, Any],
) -> None:
    _require(
        binding.get("path") == expected_relative.as_posix(),
        f"INPUT_BINDING_PATH:{expected_relative.as_posix()}",
    )
    path = root / expected_relative
    _require(
        binding.get("byte_count") == path.stat().st_size,
        f"INPUT_BINDING_BYTE_COUNT:{expected_relative.as_posix()}",
    )
    if expected_relative == MAP_PATH:
        _require(
            binding.get("raw_sha256") == MAP_RAW_SHA256,
            "MAP_BINDING_RAW_SHA256",
        )
        _require(
            binding.get("semantic_sha256") == MAP_SEMANTIC_SHA256,
            "MAP_BINDING_SEMANTIC_SHA256",
        )
    elif expected_relative == TASK_PATH:
        _require(
            binding.get("raw_sha256") == TASK_RAW_SHA256,
            "TASK_BINDING_RAW_SHA256",
        )
        _require(
            binding.get("semantic_sha256") == TASK_RAW_SHA256,
            "TASK_BINDING_SEMANTIC_SHA256",
        )
        _require(
            binding.get("segment_count") == FULL_SEGMENT_COUNT,
            "TASK_BINDING_SEGMENT_COUNT",
        )
        _require(
            binding.get("raw_bag_count") == FULL_RAW_BAG_COUNT,
            "TASK_BINDING_RAW_BAG_COUNT",
        )
    else:
        expected = EXPECTED_SEMANTIC_SHA256[expected_relative]
        _require(
            binding.get("semantic_sha256") == expected,
            f"INPUT_BINDING_SEMANTIC_SHA256:{expected_relative.as_posix()}",
        )
        _require(
            binding.get("hash_mode")
            == "sha256_utf8_after_crlf_cr_to_lf",
            f"INPUT_BINDING_HASH_MODE:{expected_relative.as_posix()}",
        )


def _float(row: Mapping[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, ValueError) as exc:
        raise StageABValidationError(
            f"INVALID_FLOAT:{name}:{row.get(name)}"
        ) from exc
    _require(math.isfinite(value), f"NON_FINITE_FLOAT:{name}")
    return value


def _int(row: Mapping[str, str], name: str) -> int:
    try:
        return int(row[name])
    except (KeyError, ValueError) as exc:
        raise StageABValidationError(
            f"INVALID_INT:{name}:{row.get(name)}"
        ) from exc


def _validate_churn(rows: Sequence[Mapping[str, str]]) -> None:
    full = [
        row
        for row in rows
        if row["evidence_scope"] == "G4IRSF14_ORIGINAL_1X_E4_SCREENING"
    ]
    _require(len(full) == 15, "FULL_1X_CHURN_ROW_COUNT")
    aggregate = [row for row in full if row["dimension"] == "all"]
    _require(len(aggregate) == 1, "FULL_1X_AGGREGATE_ROW_COUNT")
    row = aggregate[0]
    _require(row["breakdown_available"] == "true", "FULL_AGGREGATE_AVAILABLE")
    _require(row["extrapolation_allowed"] == "false", "FULL_EXTRAPOLATION")
    _require(_int(row, "completed_movement_count") == 43_603, "FULL_MOVEMENTS")
    _require(_int(row, "request_count") == 335_770, "FULL_REQUESTS")
    _require(
        _int(row, "active_grant_rejection_count") == 178_263,
        "FULL_REJECTIONS",
    )
    _require(_int(row, "arbitration_count") == 335_770, "FULL_ARBITRATIONS")
    _require(_int(row, "event_count") == 5_445_012, "FULL_EVENTS")
    _require(
        _int(row, "lifecycle_dropped_count") == 1_011_439,
        "FULL_LIFECYCLE_DROPS",
    )
    _require(
        math.isclose(
            _float(row, "requests_per_completed_movement"),
            335_770 / 43_603,
            rel_tol=0.0,
            abs_tol=1e-14,
        ),
        "FULL_REQUEST_RATE",
    )
    gaps = [row for row in full if row["dimension"] != "all"]
    _require(
        {row["dimension"] for row in gaps} == UNAVAILABLE_FULL_BREAKDOWNS,
        "FULL_BREAKDOWN_GAP_SET",
    )
    for gap in gaps:
        _require(
            gap["dimension_value"] == "NOT_RETAINED",
            f"FULL_GAP_VALUE:{gap['dimension']}",
        )
        _require(
            gap["breakdown_available"] == "false",
            f"FULL_GAP_AVAILABILITY:{gap['dimension']}",
        )
        _require(
            gap["request_count"] == ""
            and gap["active_grant_rejection_count"] == "",
            f"FULL_GAP_INVENTED_COUNTS:{gap['dimension']}",
        )
        _require(
            "not present" in gap["source_limitation"],
            f"FULL_GAP_LIMITATION:{gap['dimension']}",
        )

    diagnostic = [
        row
        for row in rows
        if row["evidence_scope"] == "G4IRSF14_STAGE_D_M0_144_DIAGNOSTIC"
    ]
    _require(diagnostic, "M0_DIAGNOSTIC_ROWS_MISSING")
    overall = [row for row in diagnostic if row["dimension"] == "all"]
    _require(len(overall) == 1, "M0_OVERALL_ROW_COUNT")
    row = overall[0]
    _require(_int(row, "completed_movement_count") == 144, "M0_MOVEMENTS")
    _require(_int(row, "request_count") == 666, "M0_REQUESTS")
    _require(
        _int(row, "active_grant_rejection_count") == 224,
        "M0_REJECTIONS",
    )
    _require(_int(row, "arbitration_count") == 666, "M0_ARBITRATIONS")
    _require(
        _int(row, "lifecycle_transition_count") == 2_658,
        "M0_LIFECYCLE_TRANSITIONS",
    )
    _require(
        _int(row, "lifecycle_dropped_count") == 0,
        "M0_LIFECYCLE_DROPS",
    )
    _require(
        _int(row, "peak_pending_request_count") == 1,
        "M0_PEAK_PENDING",
    )
    _require(row["extrapolation_allowed"] == "false", "M0_EXTRAPOLATION")

    by_dimension: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for item in diagnostic:
        if item["dimension"] != "all":
            by_dimension[item["dimension"]].append(item)
    _require(
        set(by_dimension)
        == {
            "destination",
            "upstream",
            "hour",
            "source",
            "goal",
            "bag_class",
            "storage_direct",
            "entry_time_band",
            "deadline_slack_bucket",
        },
        "M0_DIMENSION_SET",
    )
    for dimension, dimension_rows in by_dimension.items():
        _require(
            sum(_int(item, "request_count") for item in dimension_rows)
            == 666,
            f"M0_DIMENSION_REQUEST_CONSERVATION:{dimension}",
        )
        _require(
            sum(
                _int(item, "active_grant_rejection_count")
                for item in dimension_rows
            )
            == 224,
            f"M0_DIMENSION_REJECTION_CONSERVATION:{dimension}",
        )
        for item in dimension_rows:
            _require(
                item["extrapolation_allowed"] == "false",
                f"M0_DIMENSION_EXTRAPOLATION:{dimension}",
            )
            _require(
                item["requests_per_completed_movement"] == "",
                f"M0_DIMENSION_INVENTED_RATE:{dimension}",
            )


def _validate_hotspots(rows: Sequence[Mapping[str, str]]) -> None:
    full = [
        row
        for row in rows
        if row["evidence_scope"] == "G4IRSF14_ORIGINAL_1X_E4_SCREENING"
    ]
    _require(len(full) == 1, "HOTSPOT_FULL_ROW_COUNT")
    _require(full[0]["destination_node"] == "NOT_RETAINED", "HOTSPOT_FULL_VALUE")
    _require(full[0]["breakdown_available"] == "false", "HOTSPOT_FULL_AVAILABLE")
    _require(
        full[0]["extrapolation_allowed"] == "false",
        "HOTSPOT_FULL_EXTRAPOLATION",
    )
    diagnostic = [
        row
        for row in rows
        if row["evidence_scope"] == "G4IRSF14_STAGE_D_M0_144_DIAGNOSTIC"
    ]
    _require(diagnostic, "HOTSPOT_M0_ROWS_MISSING")
    _require(
        sum(_int(row, "request_count") for row in diagnostic) == 666,
        "HOTSPOT_M0_REQUEST_CONSERVATION",
    )
    _require(
        sum(_int(row, "active_grant_rejection_count") for row in diagnostic)
        == 224,
        "HOTSPOT_M0_REJECTION_CONSERVATION",
    )
    _require(
        [int(row["rank"]) for row in diagnostic]
        == list(range(1, len(diagnostic) + 1)),
        "HOTSPOT_M0_RANK_SEQUENCE",
    )
    _require(
        all(row["extrapolation_allowed"] == "false" for row in diagnostic),
        "HOTSPOT_M0_EXTRAPOLATION",
    )


def _validate_screening(rows: Sequence[Mapping[str, str]]) -> None:
    expected = {
        "I1_SOURCE_ORDER_SWAP": (41_679, 0),
        "I2_MERGE_ORDER_SWAP": (1, 0),
        "I3_NEXT_EDGE": (19_898, 0),
        "I4_HOLD_RELEASE": (59_049, 0),
        "I5_PIBT_TRIGGER": (0, 1_337),
    }
    _require(
        {row["intervention_kind"] for row in rows} == set(expected),
        "SCREENING_KIND_SET",
    )
    _require(len(rows) == len(expected), "SCREENING_ROW_COUNT")
    for row in rows:
        support, prefilter = expected[row["intervention_kind"]]
        _require(
            _int(row, "screening_support_count") == support,
            f"SCREENING_SUPPORT:{row['intervention_kind']}",
        )
        observed_prefilter = (
            _int(row, "prefilter_count") if row["prefilter_count"] else 0
        )
        _require(
            observed_prefilter == prefilter,
            f"SCREENING_PREFILTER:{row['intervention_kind']}",
        )
        for name in (
            "committed_target_descriptor_count",
            "formal_attempt_count",
            "action_changed_count",
            "complete_h_bag_count",
            "complete_h_system_count",
        ):
            _require(
                _int(row, name) == 0,
                f"SCREENING_NONZERO_{name}:{row['intervention_kind']}",
            )
        _require(
            row["screening_false_positive_rate_estimate"] == "",
            f"SCREENING_INVENTED_ESTIMATE:{row['intervention_kind']}",
        )
        _require(
            row["estimate_status"]
            == "NOT_ESTIMABLE_ZERO_ACTION_CHANGING_TRIALS",
            f"SCREENING_ESTIMATE_STATUS:{row['intervention_kind']}",
        )


def _validate_binary_ledger(ledger: Mapping[str, Any]) -> None:
    _require(set(ledger) == set(BINARY_SHA256), "BINARY_LEDGER_ROLE_SET")
    for role, expected in BINARY_SHA256.items():
        entry = ledger[role]
        _require(isinstance(entry, Mapping), f"BINARY_LEDGER_ENTRY:{role}")
        _require(entry.get("sha256") == expected, f"BINARY_LEDGER_SHA256:{role}")
        _require(
            entry.get("binding_type")
            == "CONTENT_ADDRESS_FROM_SEALED_G4IRSF14_ARTIFACT",
            f"BINARY_LEDGER_BINDING_TYPE:{role}",
        )


def validate_stage_ab(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    for relative in REQUIRED_BUNDLE_FILES:
        _require(
            (root / relative).is_file(),
            f"MISSING_REQUIRED_FILE:{relative.as_posix()}",
        )
    _require(
        all(path.name.startswith("g4irsf15_") for path in OUTPUT_PATHS),
        "OUTPUT_NAMESPACE_VIOLATION",
    )

    _require(
        file_sha256(root / MAP_PATH) == MAP_RAW_SHA256,
        "PROTECTED_MAP_RAW_SHA256_MISMATCH",
    )
    _require(
        semantic_sha256(root / MAP_PATH) == MAP_SEMANTIC_SHA256,
        "PROTECTED_MAP_SEMANTIC_SHA256_MISMATCH",
    )
    _require(
        file_sha256(root / TASK_PATH) == TASK_RAW_SHA256,
        "PROTECTED_TASK_RAW_SHA256_MISMATCH",
    )
    segment_count = 0
    raw_bags: set[int] = set()
    with (root / TASK_PATH).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            segment_count += 1
            raw_bags.add(int(row["task_id"]))
    _require(segment_count == FULL_SEGMENT_COUNT, "PROTECTED_TASK_SEGMENT_COUNT")
    _require(len(raw_bags) == FULL_RAW_BAG_COUNT, "PROTECTED_TASK_RAW_BAG_COUNT")
    for relative, expected in EXPECTED_SEMANTIC_SHA256.items():
        _require(
            semantic_sha256(root / relative) == expected,
            f"SEALED_INPUT_CONTENT_DRIFT:{relative.as_posix()}",
        )

    churn = _read_csv(root, CHURN_TABLE, CHURN_FIELDS)
    hotspots = _read_csv(root, HOTSPOT_TABLE, HOTSPOT_FIELDS)
    screening = _read_csv(root, SCREENING_TABLE, SCREENING_FIELDS)
    _validate_churn(churn)
    _validate_hotspots(hotspots)
    _validate_screening(screening)

    f2 = _read_json(root, F2_CONTROL)
    e4 = _read_json(root, E4_CONTROL)
    baseline = _read_json(root, BASELINE_REGISTRY)
    manifest = _read_json(root, CAMPAIGN_MANIFEST)
    for relative, value in (
        (F2_CONTROL, f2),
        (E4_CONTROL, e4),
        (BASELINE_REGISTRY, baseline),
        (CAMPAIGN_MANIFEST, manifest),
    ):
        _validate_self_hash(relative, value)

    _require(
        f2.get("schema") == "czr005.g4irsf15.f2_frozen_control.v1",
        "F2_SCHEMA",
    )
    _require(
        f2.get("status") == "PASS_FROZEN_BY_CONTENT_BINDING",
        "F2_STATUS",
    )
    _validate_input_binding(root, G14_F2, f2["predecessor"])
    _require(
        f2["binary"]["sha256"] == BINARY_SHA256["f2_frozen_control"],
        "F2_BINARY_SHA256",
    )
    _require(
        math.isclose(
            float(f2["comparators"]["f2_original_entry_mean_minutes"]),
            41.514218717973414,
            rel_tol=0.0,
            abs_tol=1e-15,
        ),
        "F2_MEAN",
    )
    _require(f2["hard_gates"]["complete_raw_bags"] == 28_506, "F2_BAGS")
    _require(f2["hard_gates"]["completed_segments"] == 43_603, "F2_SEGMENTS")
    _require(f2["hard_gates"]["runtime_full_astar_calls"] == 0, "F2_ASTAR")

    _require(
        e4.get("schema")
        == "czr005.g4irsf15.e4_frozen_mechanism_control.v1",
        "E4_SCHEMA",
    )
    _require(
        e4.get("status")
        == "FROZEN_CAPABILITY_CONTROL_WITH_NEGATIVE_EVIDENCE",
        "E4_STATUS",
    )
    _validate_binary_ledger(e4["binary_ledger"])
    original = e4["original_1x_counters"]
    _require(original["merge_grant_request_count"] == 335_770, "E4_REQUESTS")
    _require(
        original["destination_merge_arbitration_event_count"] == 335_770,
        "E4_ARBITRATIONS",
    )
    _require(
        original["merge_grant_active_grant_rejection_count"] == 178_263,
        "E4_REJECTIONS",
    )
    _require(
        original["merge_grant_lifecycle_dropped_count"] == 1_011_439,
        "E4_LIFECYCLE_DROPS",
    )
    _require(
        e4["negative_evidence"]["persistent_pending_queue_supported"]
        is False,
        "E4_PENDING_QUEUE_CLAIM",
    )
    _require(
        e4["negative_evidence"]["screening_false_positive_rate_estimate"]
        is None,
        "E4_INVENTED_FALSE_POSITIVE_ESTIMATE",
    )
    for raw_path, binding in e4["input_bindings"].items():
        relative = Path(raw_path)
        _require(relative in EXPECTED_SEMANTIC_SHA256, f"E4_UNKNOWN_INPUT:{raw_path}")
        _validate_input_binding(root, relative, binding)
    expected_e4_outputs = {
        POSTMORTEM_REPORT,
        CHURN_REPORT,
        CHURN_TABLE,
        HOTSPOT_TABLE,
        SCREENING_TABLE,
    }
    _require(
        set(e4["output_bindings"])
        == {path.as_posix() for path in expected_e4_outputs},
        "E4_OUTPUT_BINDING_SET",
    )
    for relative in expected_e4_outputs:
        _validate_output_binding(
            root,
            relative,
            e4["output_bindings"][relative.as_posix()],
            code=f"E4_OUTPUT_BINDING:{relative.as_posix()}",
        )

    _require(
        baseline.get("schema") == "czr005.g4irsf15.baseline_registry.v1",
        "BASELINE_SCHEMA",
    )
    _require(
        baseline.get("status") == "PASS_STAGE_15AB_EVIDENCE_FREEZE",
        "BASELINE_STATUS",
    )
    repository = baseline["repository"]
    _require(repository["repository"] == REPOSITORY_SLUG, "BASELINE_REPOSITORY")
    _require(
        repository["required_base_commit"] == REQUIRED_BASE_COMMIT,
        "BASELINE_BASE_COMMIT",
    )
    _require(repository["head_is_base_or_descendant"] is True, "BASELINE_HEAD")
    _require(
        repository["upstream_is_base_or_descendant"] is True,
        "BASELINE_UPSTREAM",
    )
    _validate_input_binding(
        root, G14_BASELINE, baseline["predecessor_registry"]
    )
    for relative in (F2_CONTROL, E4_CONTROL):
        _validate_output_binding(
            root,
            relative,
            baseline["controls"][relative.as_posix()],
            code=f"BASELINE_CONTROL_BINDING:{relative.as_posix()}",
        )
    for relative in (START_REPORT, POSTMORTEM_REPORT, CHURN_REPORT):
        _validate_output_binding(
            root,
            relative,
            baseline["reports"][relative.as_posix()],
            code=f"BASELINE_REPORT_BINDING:{relative.as_posix()}",
        )
    frozen = baseline["frozen_outcome"]
    _require(frozen["formal_complete_causal_label_count"] == 0, "BASELINE_LABELS")
    _require(frozen["h_system_pair_count"] == 0, "BASELINE_H_SYSTEM")
    _require(frozen["training_authorized"] is False, "BASELINE_TRAINING")
    _require(
        baseline["governance"][
            "sealed_g4irsf12_to_g4irsf14_artifacts_rewritten"
        ]
        is False,
        "BASELINE_SEALED_REWRITE",
    )

    _require(
        manifest.get("schema")
        == "czr005.g4irsf15.campaign_source_manifest.v1",
        "MANIFEST_SCHEMA",
    )
    _require(
        manifest.get("status")
        == "SOURCE_FAMILIES_AUDITED_TARGET_DESCRIPTORS_NOT_MATERIALIZED",
        "MANIFEST_STATUS",
    )
    _require(manifest["formal_campaign_authorized"] is False, "MANIFEST_AUTH")
    for name in (
        "target_descriptor_count",
        "causal_label_count",
        "complete_h_bag_count",
        "complete_h_system_count",
    ):
        _require(manifest[name] == 0, f"MANIFEST_NONZERO_{name}")
    _require(
        manifest["exact_binary_requirement"]["sha256"]
        == BINARY_SHA256["e4_original_1x_screening"],
        "MANIFEST_EXACT_BINARY",
    )
    families = manifest["source_families"]
    _require(
        set(families)
        == {
            "I1_SOURCE_ORDER_SWAP",
            "I2_MERGE_ORDER_SWAP",
            "I3_NEXT_EDGE",
            "I4_HOLD_RELEASE",
            "I5_PIBT_TRIGGER",
        },
        "MANIFEST_SOURCE_FAMILY_SET",
    )
    for name in ("I1_SOURCE_ORDER_SWAP", "I3_NEXT_EDGE", "I4_HOLD_RELEASE"):
        _require(
            families[name]["status"]
            == "SOURCE_FAMILY_SUPPORTED_TARGETS_REQUIRE_REMATERIALIZATION",
            f"MANIFEST_SUPPORTED_FAMILY:{name}",
        )
    _require(
        families["I2_MERGE_ORDER_SWAP"]["status"]
        == "BLOCKED_INSUFFICIENT_PRIMARY_SUPPORT",
        "MANIFEST_I2_STATUS",
    )
    _require(
        families["I5_PIBT_TRIGGER"]["status"]
        == "BLOCKED_ZERO_STRICT_APPLICABLE_SUPPORT",
        "MANIFEST_I5_STATUS",
    )
    retention = manifest["retention_contract"]
    _require(
        retention["selected_target_dropped_count_required"] == 0,
        "MANIFEST_RETENTION_DROP",
    )
    _require(
        retention["unbounded_in_memory_trace_allowed"] is False,
        "MANIFEST_UNBOUNDED_MEMORY",
    )
    limitations = manifest["evidence_limitations"]
    _require(
        limitations["original_1x_request_breakdown_available"] is False,
        "MANIFEST_BREAKDOWN_CLAIM",
    )
    _require(
        set(limitations["missing_dimensions"]) == UNAVAILABLE_FULL_BREAKDOWNS,
        "MANIFEST_MISSING_DIMENSIONS",
    )
    _require(
        limitations["screening_false_positive_rate_estimable"] is False,
        "MANIFEST_FALSE_POSITIVE_CLAIM",
    )
    _require(
        limitations["stage_d_144_extrapolation_to_original_1x_allowed"]
        is False,
        "MANIFEST_STAGE_D_EXTRAPOLATION",
    )
    _require(
        set(manifest["input_bindings"])
        == {path.as_posix() for path in INPUT_PATHS},
        "MANIFEST_INPUT_BINDING_SET",
    )
    for relative in INPUT_PATHS:
        _validate_input_binding(
            root,
            relative,
            manifest["input_bindings"][relative.as_posix()],
        )
    expected_manifest_outputs = set(OUTPUT_PATHS) - {CAMPAIGN_MANIFEST}
    _require(
        set(manifest["output_bindings"])
        == {path.as_posix() for path in expected_manifest_outputs},
        "MANIFEST_OUTPUT_BINDING_SET",
    )
    for relative in expected_manifest_outputs:
        _validate_output_binding(
            root,
            relative,
            manifest["output_bindings"][relative.as_posix()],
            code=f"MANIFEST_OUTPUT_BINDING:{relative.as_posix()}",
        )
    verified_roles = set(
        manifest["generation_binary_verification"][
            "roles_verified_in_this_invocation"
        ]
    )
    _require(
        verified_roles == set(BINARY_SHA256),
        "MANIFEST_GENERATION_BINARY_VERIFICATION_SET",
    )

    postmortem_text = (root / POSTMORTEM_REPORT).read_text(encoding="utf-8")
    churn_text = (root / CHURN_REPORT).read_text(encoding="utf-8")
    _require("NOT AVAILABLE" in postmortem_text, "POSTMORTEM_LIMITATION_TEXT")
    _require("not estimable" in postmortem_text, "POSTMORTEM_ESTIMATE_TEXT")
    _require("NOT AVAILABLE" in churn_text, "CHURN_LIMITATION_TEXT")
    _require("cannot estimate original-1x hotspots" in churn_text, "CHURN_NO_EXTRAPOLATION")

    return {
        "status": "PASS_STAGE_15AB_BUNDLE_VALID",
        "output_count": len(OUTPUT_PATHS),
        "input_count": len(INPUT_PATHS),
        "original_1x_request_count": 335_770,
        "original_1x_breakdown_available": False,
        "formal_causal_label_count": 0,
        "manifest_self_sha256": manifest["self_sha256"],
    }


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository or portable bundle root",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    try:
        result = validate_stage_ab(arguments.root)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StageABValidationError,
    ) as exc:
        print(f"G4IRSF15 Stage 15A/15B validation: FAIL: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
