from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import run_g4irsf17_source_wait_campaign as campaign


def _payload(mode: str) -> dict:
    row = {
        "reason": "SOURCE_SERVICE_NOT_READY",
        "wait_seconds": 0.25,
        "wait_bag_seconds": 0.5,
        "affected_bag_count": 2,
    }
    return {
        "summary": {
            "g4irsf17_source_wait_telemetry_enabled": True,
            "g4irsf17_source_wait_interval_total_count": 1,
            "g4irsf17_source_wait_interval_stored_count": 1,
            "g4irsf17_source_wait_interval_dropped_count": 0,
            "g4irsf17_source_wait_runtime_global_scan_count": 0,
            "g4irsf17_source_wait_bag_seconds": 0.5,
            "g4irsf17_source_wait_reason_bag_seconds": {
                "SOURCE_SERVICE_NOT_READY": 0.5
            },
            "mode": mode,
        },
        "g4irsf17_source_wait_blockers": [row],
        "bags": [],
    }


def test_native_wait_payload_requires_conserved_untruncated_local_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        campaign.g16,
        "_hard_gates",
        lambda summary, segments, mode: {"safety_pass": True},
    )
    result = campaign.validate_native_wait_payload(
        _payload("closed_loop"), mode="closed_loop", segments=8192
    )
    assert result["interval_count"] == 1
    assert result["wait_bag_seconds"] == 0.5

    truncated = _payload("closed_loop")
    truncated["summary"]["g4irsf17_source_wait_interval_total_count"] = 2
    truncated["summary"]["g4irsf17_source_wait_interval_dropped_count"] = 1
    with pytest.raises(campaign.CollectionError, match="trace truncated"):
        campaign.validate_native_wait_payload(
            truncated, mode="closed_loop", segments=8192
        )

    global_scan = _payload("closed_loop")
    global_scan["summary"]["g4irsf17_source_wait_runtime_global_scan_count"] = 1
    with pytest.raises(campaign.CollectionError, match="global scan"):
        campaign.validate_native_wait_payload(
            global_scan, mode="closed_loop", segments=8192
        )


def test_collection_runs_matched_h5_and_off_and_writes_diagnosis_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "czr005_cpp.pyd"
    rule = tmp_path / "rule.json"
    binary.write_bytes(b"fixture")
    rule.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def runner(**kwargs: object) -> dict:
        mode = str(kwargs["mode"])
        calls.append(mode)
        assert kwargs["enable_g4irsf17_source_wait_telemetry"] is True
        return _payload(mode)

    monkeypatch.setattr(
        campaign.g16,
        "_hard_gates",
        lambda summary, segments, mode: {"safety_pass": True},
    )
    monkeypatch.setattr(
        campaign.g16.g12,
        "load_input_prefix",
        lambda segments, root: SimpleNamespace(rows=[{"task_id": 1}]),
    )
    monkeypatch.setattr(
        campaign.g16,
        "_raw_bag_performance",
        lambda rows, payload, segments: (
            [
                {
                    "task_id": 1,
                    "source_wait_seconds": 0.5,
                    "network_time_seconds": 1.0,
                    "total_system_time_seconds": 1.5,
                }
            ],
            {"selected_segment_count": segments},
        ),
    )

    result = campaign.collect_source_wait(
        binary=binary,
        segments=8192,
        rule_bundle=rule,
        output_dir=tmp_path / "out",
        native_runner=runner,
    )
    assert calls == ["closed_loop", "off"]
    assert result["status"] == "PASS"
    assert result["binary"] == binary.name
    assert not Path(result["binary"]).is_absolute()
    assert Path(result["artifacts"]["h5_telemetry"]).is_file()
    payload = json.loads(
        Path(result["artifacts"]["h5_telemetry"]).read_text(encoding="utf-8")
    )
    assert payload["g4irsf17_source_wait_blockers"][0]["arm"] == "h5"
    assert "diagnose-source-wait" in result["next_command"]
    publication = result["publication"]
    assert publication["raw_runtime_artifacts"] == "LOCAL_ONLY_NOT_DISTRIBUTED"
    assert publication["committed_compact_evidence"] == [
        "outputs/tables/g4irsf17_source_wait_cause_ledger.csv",
        "outputs/tables/g4irsf17_source_wait_topology_attribution.csv",
        "outputs/reports/g4irsf17_source_wait_diagnosis.md",
    ]
    assert "not distributed" in publication["note"]
