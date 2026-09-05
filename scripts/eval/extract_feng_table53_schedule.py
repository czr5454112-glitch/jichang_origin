"""Extract the frozen shared segment-release schedule used by Feng Table 5.3.

The source workbook is accepted only at the audited SHA-256.  The extractor
reads worksheet index 2 for the schedule and reads only start-time fields from
the DH and HCA worksheets for identity checks.  Completion times and
performance results are deliberately outside this artifact's schema.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
from typing import Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_CSV = ROOT / "data" / "processed" / "feng_table53_segment_schedule.csv"
DEFAULT_IDENTITY_JSON = DEFAULT_OUTPUT_CSV.with_suffix(".identity.json")

EXPECTED_WORKBOOK_SHA256 = (
    "E8EE03FE5C75FFF2BEC88251566521E3E6283D549F5676BE624C55E050F771FB"
)
EXPECTED_RAW_BAG_COUNT = 28_506
EXPECTED_SEGMENT_COUNT = 43_603
EXPECTED_SINGLE_SEGMENT_BAGS = 13_409
EXPECTED_TWO_SEGMENT_BAGS = 15_097

SCHEDULE_SHEET_INDEX = 2
DH_SHEET_INDEX = 1
HCA_SHEET_INDEX = 0
SOURCE_DESCRIPTION = (
    "Feng thesis experiment workbook: "
    "仿真结果数据整理（与分散启发式方法对比）.xlsx"
)

CSV_FIELDS = (
    "raw_bag_id",
    "segment_id",
    "start",
    "goal",
    "scheduled_release_seconds",
)

_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CELL_REF_RE = re.compile(r"^([A-Z]+)[0-9]+$")


class ScheduleExtractionError(RuntimeError):
    """Raised when the workbook or extracted schedule violates frozen identity."""


@dataclass(frozen=True, order=True)
class SegmentSchedule:
    raw_bag_id: int
    segment_id: int
    start: int
    goal: int
    scheduled_release_seconds: int


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worksheet_paths(archive: zipfile.ZipFile) -> list[str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }

    paths: list[str] = []
    for sheet in workbook.findall(f".//{{{_SHEET_NS}}}sheet"):
        relationship_id = sheet.attrib[f"{{{_REL_NS}}}id"]
        target = targets.get(relationship_id)
        if target is None:
            raise ScheduleExtractionError(
                f"worksheet relationship is unresolved: {relationship_id}"
            )
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = posixpath.normpath(posixpath.join("xl", target))
        paths.append(PurePosixPath(path).as_posix())
    return paths


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    return [
        "".join(node.text or "" for node in item.findall(f".//{{{_SHEET_NS}}}t"))
        for item in root.findall(f"{{{_SHEET_NS}}}si")
    ]


def _cell_text(cell: ET.Element, shared_strings: Sequence[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.findall(f".//{{{_SHEET_NS}}}t")
        )

    value = cell.find(f"{{{_SHEET_NS}}}v")
    if value is None or value.text is None:
        return None
    if cell_type == "s":
        try:
            return shared_strings[int(value.text)]
        except (IndexError, ValueError) as exc:
            raise ScheduleExtractionError("invalid shared-string reference") from exc
    return value.text


def _read_columns(
    archive: zipfile.ZipFile,
    worksheet_path: str,
    columns: Sequence[str],
) -> list[dict[str, str]]:
    wanted = set(columns)
    rows: list[dict[str, str]] = []
    shared_strings = _shared_strings(archive)

    with archive.open(worksheet_path) as handle:
        for _, row in ET.iterparse(handle, events=("end",)):
            if row.tag != f"{{{_SHEET_NS}}}row":
                continue
            values: dict[str, str] = {}
            for cell in row.findall(f"{{{_SHEET_NS}}}c"):
                reference = cell.attrib.get("r", "")
                match = _CELL_REF_RE.match(reference)
                if match is None or match.group(1) not in wanted:
                    continue
                text = _cell_text(cell, shared_strings)
                if text is not None:
                    values[match.group(1)] = text
            if values:
                rows.append(values)
            row.clear()
    return rows


def _integer(value: str, *, field: str) -> int:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ScheduleExtractionError(f"{field} is not numeric: {value!r}") from exc
    integral = number.to_integral_value()
    if number != integral:
        raise ScheduleExtractionError(f"{field} is not integral: {value!r}")
    return int(integral)


def _numeric_records(
    rows: Iterable[Mapping[str, str]],
    *,
    required_columns: Sequence[str],
) -> list[dict[str, int]]:
    records: list[dict[str, int]] = []
    for row in rows:
        raw_id = row.get("A")
        if raw_id is None:
            continue
        try:
            _integer(raw_id, field="column A raw_bag_id")
        except ScheduleExtractionError:
            # Header and non-record summary rows are intentionally ignored.
            continue
        missing = [column for column in required_columns if column not in row]
        if missing:
            raise ScheduleExtractionError(
                f"numeric record is missing columns {missing}: {dict(row)!r}"
            )
        records.append(
            {
                column: _integer(row[column], field=f"column {column}")
                for column in required_columns
            }
        )
    return records


def _build_schedule(records: Sequence[Mapping[str, int]]) -> list[SegmentSchedule]:
    grouped: dict[int, list[Mapping[str, int]]] = {}
    for record in records:
        grouped.setdefault(record["A"], []).append(record)

    expected_ids = set(range(EXPECTED_RAW_BAG_COUNT))
    if set(grouped) != expected_ids:
        missing = sorted(expected_ids.difference(grouped))[:5]
        extra = sorted(set(grouped).difference(expected_ids))[:5]
        raise ScheduleExtractionError(
            f"raw bag IDs are not contiguous 0..{EXPECTED_RAW_BAG_COUNT - 1}: "
            f"missing={missing}, extra={extra}"
        )

    schedule: list[SegmentSchedule] = []
    segment_count_histogram: dict[int, int] = {}
    for raw_bag_id in sorted(grouped):
        bag_records = sorted(
            grouped[raw_bag_id],
            key=lambda row: (row["D"], row["B"], row["C"]),
        )
        segment_count_histogram[len(bag_records)] = (
            segment_count_histogram.get(len(bag_records), 0) + 1
        )
        if len(bag_records) not in (1, 2):
            raise ScheduleExtractionError(
                f"raw bag {raw_bag_id} has {len(bag_records)} segments"
            )
        for segment_id, record in enumerate(bag_records):
            if (record["B"] == 52) != (segment_id == 1):
                raise ScheduleExtractionError(
                    f"start 52 is not exactly the second leg for raw bag {raw_bag_id}"
                )
            schedule.append(
                SegmentSchedule(
                    raw_bag_id=raw_bag_id,
                    segment_id=segment_id,
                    start=record["B"],
                    goal=record["C"],
                    scheduled_release_seconds=record["D"],
                )
            )

    expected_histogram = {
        1: EXPECTED_SINGLE_SEGMENT_BAGS,
        2: EXPECTED_TWO_SEGMENT_BAGS,
    }
    if segment_count_histogram != expected_histogram:
        raise ScheduleExtractionError(
            f"unexpected per-bag segment counts: {segment_count_histogram}"
        )
    if len(schedule) != EXPECTED_SEGMENT_COUNT:
        raise ScheduleExtractionError(
            f"unexpected segment count: {len(schedule)} != {EXPECTED_SEGMENT_COUNT}"
        )
    return schedule


def _schedule_lookup(
    schedule: Sequence[SegmentSchedule],
) -> tuple[dict[tuple[int, int, int], int], dict[tuple[int, int], int]]:
    by_full_key: dict[tuple[int, int, int], int] = {}
    by_hca_key: dict[tuple[int, int], int] = {}
    for segment in schedule:
        full_key = (segment.raw_bag_id, segment.start, segment.goal)
        hca_key = (segment.raw_bag_id, segment.start)
        if full_key in by_full_key or hca_key in by_hca_key:
            raise ScheduleExtractionError(f"schedule key is not unique: {full_key}")
        by_full_key[full_key] = segment.scheduled_release_seconds
        by_hca_key[hca_key] = segment.scheduled_release_seconds
    return by_full_key, by_hca_key


def _verify_cross_sheet_identity(
    schedule: Sequence[SegmentSchedule],
    dh_records: Sequence[Mapping[str, int]],
    hca_records: Sequence[Mapping[str, int]],
) -> None:
    schedule_by_full_key, schedule_by_hca_key = _schedule_lookup(schedule)

    dh_by_key: dict[tuple[int, int, int], int] = {}
    for record in dh_records:
        key = (record["A"], record["B"], record["C"])
        if key in dh_by_key:
            raise ScheduleExtractionError(f"duplicate DH schedule key: {key}")
        dh_by_key[key] = record["D"]
    if dh_by_key != schedule_by_full_key:
        raise ScheduleExtractionError("DH sheet D does not exactly match the schedule")

    hca_by_key: dict[tuple[int, int], int] = {}
    for record in hca_records:
        key = (record["A"], record["B"])
        if key in hca_by_key:
            raise ScheduleExtractionError(f"duplicate HCA schedule key: {key}")
        hca_by_key[key] = record["C"]
    if hca_by_key != schedule_by_hca_key:
        raise ScheduleExtractionError("HCA start does not exactly match the schedule")


def _csv_bytes(schedule: Sequence[SegmentSchedule]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for segment in schedule:
        writer.writerow(
            {
                "raw_bag_id": segment.raw_bag_id,
                "segment_id": segment.segment_id,
                "start": segment.start,
                "goal": segment.goal,
                "scheduled_release_seconds": segment.scheduled_release_seconds,
            }
        )
    return output.getvalue().encode("utf-8")


def _identity_payload(schedule_sha256: str) -> dict[str, object]:
    return {
        "schema": "czr005.feng_table53_segment_schedule.v1",
        "source": {
            "description": SOURCE_DESCRIPTION,
            "sha256": EXPECTED_WORKBOOK_SHA256,
            "schedule_worksheet_index": SCHEDULE_SHEET_INDEX,
        },
        "artifact": {
            "path": "data/processed/feng_table53_segment_schedule.csv",
            "sha256": schedule_sha256,
            "columns": list(CSV_FIELDS),
            "sort_order": ["raw_bag_id", "segment_id"],
        },
        "counts": {
            "raw_bag_ids": EXPECTED_RAW_BAG_COUNT,
            "segment_rows": EXPECTED_SEGMENT_COUNT,
            "single_segment_bags": EXPECTED_SINGLE_SEGMENT_BAGS,
            "two_segment_bags": EXPECTED_TWO_SEGMENT_BAGS,
        },
        "cross_sheet_identity": {
            "dh_worksheet_index": DH_SHEET_INDEX,
            "dh_D_matches": EXPECTED_SEGMENT_COUNT,
            "hca_worksheet_index": HCA_SHEET_INDEX,
            "hca_start_matches": EXPECTED_SEGMENT_COUNT,
            "all_exact": True,
        },
        "semantics": {
            "scheduled_release_seconds": (
                "Shared, source-shaped segment release replayed identically by HCA and DH."
            ),
            "table53_timing": (
                "For each raw bag, Table 5.3 sums segment completion minus this "
                "shared scheduled release."
            ),
            "completion_fields_extracted": False,
            "performance_fields_extracted": False,
        },
    }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def extract_schedule(
    *,
    workbook_path: Path,
    output_csv: Path = DEFAULT_OUTPUT_CSV,
    identity_json: Path = DEFAULT_IDENTITY_JSON,
) -> dict[str, object]:
    actual_sha256 = _sha256_file(workbook_path).upper()
    if actual_sha256 != EXPECTED_WORKBOOK_SHA256:
        raise ScheduleExtractionError(
            f"workbook SHA-256 is not allowlisted: {actual_sha256}"
        )

    with zipfile.ZipFile(workbook_path) as archive:
        worksheet_paths = _worksheet_paths(archive)
        required_index = max(SCHEDULE_SHEET_INDEX, DH_SHEET_INDEX, HCA_SHEET_INDEX)
        if len(worksheet_paths) <= required_index:
            raise ScheduleExtractionError(
                f"workbook has only {len(worksheet_paths)} worksheets"
            )

        # Only schedule/start fields are read.  In particular, DH column E and
        # HCA column D (completion timestamps) never enter this extractor.
        schedule_records = _numeric_records(
            _read_columns(
                archive,
                worksheet_paths[SCHEDULE_SHEET_INDEX],
                ("A", "B", "C", "D"),
            ),
            required_columns=("A", "B", "C", "D"),
        )
        dh_records = _numeric_records(
            _read_columns(
                archive,
                worksheet_paths[DH_SHEET_INDEX],
                ("A", "B", "C", "D"),
            ),
            required_columns=("A", "B", "C", "D"),
        )
        hca_records = _numeric_records(
            _read_columns(
                archive,
                worksheet_paths[HCA_SHEET_INDEX],
                ("A", "B", "C"),
            ),
            required_columns=("A", "B", "C"),
        )

    schedule = _build_schedule(schedule_records)
    _verify_cross_sheet_identity(schedule, dh_records, hca_records)

    csv_content = _csv_bytes(schedule)
    schedule_sha256 = _sha256_bytes(csv_content)
    identity = _identity_payload(schedule_sha256)
    identity_content = (
        json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    _atomic_write(output_csv, csv_content)
    _atomic_write(identity_json, identity_content)
    return identity


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        required=True,
        help="Path to the allowlisted Feng experiment workbook.",
    )
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--identity-json", type=Path, default=DEFAULT_IDENTITY_JSON)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    identity = extract_schedule(
        workbook_path=args.workbook,
        output_csv=args.output_csv,
        identity_json=args.identity_json,
    )
    print(json.dumps(identity, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
