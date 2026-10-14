from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.ics_circulation_v3.audit_nanning import audit_profile, main


def _profile(tmp_path: Path) -> Path:
    path = tmp_path / "profile.json"
    payload = {
        "map_id": "fixture",
        "counts": {"dense_node_count": 999},
        "nodes": [
            {"location": 0, "external_id": "ICS156", "alias": "storage", "system_key": "international", "node_type": 7, "outgoing": [1], "service_time": 0, "service_time_source": "IMPUTED_ZERO", "empty_pallet_storage_id": 1},
            {"location": 1, "external_id": "ICS156", "alias": "loader", "system_key": "domestic", "node_type": 1, "outgoing": [2], "service_time": 1},
            {"location": 2, "external_id": "ICS3", "alias": "unloader", "system_key": "domestic", "node_type": 2, "outgoing": [0], "service_time": 2},
        ],
        "edges": [
            {"start": 0, "end": 1, "length": 0.6, "speed": 2, "capacity": 0},
            {"start": 1, "end": 2, "length": 4, "speed": 2, "capacity": 2},
            {"start": 2, "end": 0, "length": 8, "speed": 2, "capacity": 4},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_derives_counts_and_preserves_missing_operating_data(tmp_path: Path) -> None:
    path = _profile(tmp_path)
    before = path.read_bytes()
    audit = audit_profile(path)
    assert path.read_bytes() == before
    assert audit["source"]["sha256"] == hashlib.sha256(before).hexdigest()
    assert audit["derived_counts"] == {
        "nodes": 3, "directed_edges": 3,
        "systems": {"domestic": 2, "international": 1},
        "node_types": {"1": 1, "2": 1, "7": 1},
        "cross_system_edges": 2, "unknown_system_edges": 0,
        "empty_pallet_storage_nodes": 1,
    }
    assert audit["verified_mapping"]["duplicate_external_ids"] == {"ICS156": [0, 1]}
    assert audit["empty_pallet_storage"][0]["operating_values_as_recorded"] == {}
    assert "initial_empty_count" in audit["empty_pallet_storage"][0]["missing_fields"]
    assert "old_in_transit" in audit["missing_business_fields"]["profile"]
    edge = audit["source_caveats"]["zero_capacity_edges_as_recorded"][0]
    assert edge["capacity_as_recorded"] == 0
    assert edge["travel_time_seconds_derived"] == pytest.approx(0.3)
    assert audit["source_caveats"]["imputed_service_nodes"][0]["location"] == 0


@pytest.mark.parametrize("invalid", ["endpoint", "adjacency", "duplicate_node"])
def test_rejects_invalid_source_mapping(tmp_path: Path, invalid: str) -> None:
    path = _profile(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if invalid == "endpoint":
        payload["edges"][0]["end"] = 999
    elif invalid == "adjacency":
        payload["nodes"][0]["outgoing"] = []
    else:
        payload["nodes"][1]["location"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        audit_profile(path)


def test_cli_writes_requested_report_without_overwriting_source(tmp_path: Path) -> None:
    path = _profile(tmp_path)
    original = path.read_bytes()
    output = tmp_path / "reports" / "audit.json"
    assert main(["--profile", str(path), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["source"]["map_id"] == "fixture"
    with pytest.raises(SystemExit):
        main(["--profile", str(path), "--output", str(path)])
    assert path.read_bytes() == original
