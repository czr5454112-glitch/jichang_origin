from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "processed" / "feng_table53_segment_schedule.csv"
IDENTITY_PATH = CSV_PATH.with_suffix(".identity.json")

EXPECTED_SOURCE_SHA256 = (
    "E8EE03FE5C75FFF2BEC88251566521E3E6283D549F5676BE624C55E050F771FB"
)
EXPECTED_SCHEDULE_SHA256 = (
    "a3db0d3f495870437414af0b46a0a140f7cafe8111b40222ca59fcd78e7d4d86"
)
EXPECTED_FIELDS = [
    "raw_bag_id",
    "segment_id",
    "start",
    "goal",
    "scheduled_release_seconds",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows() -> list[tuple[int, int, int, int, int]]:
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == EXPECTED_FIELDS
        return [
            (
                int(row["raw_bag_id"]),
                int(row["segment_id"]),
                int(row["start"]),
                int(row["goal"]),
                int(row["scheduled_release_seconds"]),
            )
            for row in reader
        ]


def test_feng_table53_schedule_identity_is_frozen() -> None:
    identity = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))

    assert identity["schema"] == "czr005.feng_table53_segment_schedule.v1"
    assert identity["source"]["sha256"] == EXPECTED_SOURCE_SHA256
    assert identity["source"]["schedule_worksheet_index"] == 2
    assert not re.match(r"^[A-Za-z]:[\\/]", identity["source"]["description"])

    assert identity["artifact"]["path"] == (
        "data/processed/feng_table53_segment_schedule.csv"
    )
    assert identity["artifact"]["columns"] == EXPECTED_FIELDS
    assert identity["artifact"]["sort_order"] == ["raw_bag_id", "segment_id"]
    assert identity["artifact"]["sha256"] == EXPECTED_SCHEDULE_SHA256
    assert _sha256(CSV_PATH) == EXPECTED_SCHEDULE_SHA256

    assert identity["counts"] == {
        "raw_bag_ids": 28_506,
        "segment_rows": 43_603,
        "single_segment_bags": 13_409,
        "two_segment_bags": 15_097,
    }
    assert identity["cross_sheet_identity"] == {
        "all_exact": True,
        "dh_D_matches": 43_603,
        "dh_worksheet_index": 1,
        "hca_start_matches": 43_603,
        "hca_worksheet_index": 0,
    }
    assert identity["semantics"]["completion_fields_extracted"] is False
    assert identity["semantics"]["performance_fields_extracted"] is False


def test_feng_table53_schedule_has_only_the_frozen_segment_structure() -> None:
    rows = _rows()
    assert len(rows) == 43_603
    assert rows == sorted(rows, key=lambda row: (row[0], row[1]))
    assert len({(row[0], row[1]) for row in rows}) == len(rows)

    by_bag: defaultdict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
    for raw_bag_id, segment_id, start, goal, release in rows:
        assert raw_bag_id >= 0
        assert segment_id in (0, 1)
        assert start >= 0
        assert goal >= 0
        assert release >= 0
        assert (start == 52) == (segment_id == 1)
        by_bag[raw_bag_id].append((segment_id, start, goal, release))

    assert set(by_bag) == set(range(28_506))
    assert Counter(len(segments) for segments in by_bag.values()) == {
        1: 13_409,
        2: 15_097,
    }
    for segments in by_bag.values():
        assert [segment[0] for segment in segments] == list(range(len(segments)))
        if len(segments) == 2:
            assert segments[0][3] <= segments[1][3]
