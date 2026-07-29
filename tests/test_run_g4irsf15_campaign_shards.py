from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_g4irsf15_campaign_shards as orchestrator


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True),
        encoding="utf-8",
    )


def _campaign_root(
    tmp_path: Path,
    *,
    shard_count: int = 4,
) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    shards: list[dict[str, object]] = []
    for index in range(shard_count):
        shard: dict[str, object] = {
            "shard_index": index,
            "targets": [],
            "target_keys": [],
        }
        shard["shard_sha256"] = orchestrator._canonical_sha256(
            shard
        )
        shards.append(shard)
    plan: dict[str, object] = {
        "campaign": "pilot",
        "pilot_round": 1,
        "shard_count": shard_count,
        "shards": shards,
    }
    plan["self_sha256"] = orchestrator._canonical_sha256(plan)
    plan_path = root / orchestrator.PILOT_PLAN_PATHS[1]
    _write_json(plan_path, plan)
    binary = root / "fake_binary.pyd"
    binary.write_bytes(b"fake exact binary")
    build_manifest = root / "fake_build_manifest.json"
    build_manifest.write_bytes(b'{"status":"fake"}\n')
    worker = root / "fake_worker.py"
    worker.write_text(
        """
import argparse
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
subparsers = parser.add_subparsers(dest="command", required=True)
run = subparsers.add_parser("run-shard")
run.add_argument("--campaign", required=True)
run.add_argument("--shard-index", type=int, required=True)
run.add_argument("--binary", required=True)
run.add_argument("--build-manifest", required=True)
run.add_argument("--round", type=int, required=True)
args = parser.parse_args()
behavior = json.loads(
    (args.root / "fake_behavior.json").read_text(encoding="utf-8")
)
row = behavior.get(str(args.shard_index), {})
(args.root / f"started_{args.shard_index}").write_text(
    "started", encoding="utf-8"
)
sys.stdout.buffer.write(
    f"stdout shard={args.shard_index}\\n".encode("utf-8")
)
sys.stderr.buffer.write(
    f"stderr shard={args.shard_index}\\n".encode("utf-8")
)
time.sleep(float(row.get("delay", 0.01)))
raise SystemExit(int(row.get("return_code", 0)))
""".lstrip(),
        encoding="utf-8",
    )
    return root, binary, build_manifest, worker


def _fake_memory(_pid: int) -> orchestrator.MemorySample:
    return orchestrator.MemorySample(
        current_resident_bytes=1_000,
        peak_resident_bytes=2_000,
        method="FAKE_DETERMINISTIC_RSS",
    )


def test_parse_shards_supports_all_lists_and_ranges() -> None:
    available = list(range(7))
    assert orchestrator._parse_shard_tokens(
        ["all"], available_indices=available
    ) == available
    assert orchestrator._parse_shard_tokens(
        ["0,2", "4-6"], available_indices=available
    ) == [0, 2, 4, 5, 6]
    with pytest.raises(
        orchestrator.OrchestratorError,
        match="SHARDS_ALL_MUST_BE_USED_ALONE",
    ):
        orchestrator._parse_shard_tokens(
            ["all", "1"], available_indices=available
        )
    with pytest.raises(
        orchestrator.OrchestratorError,
        match="SHARD_INDEX_NOT_IN_PLAN",
    ):
        orchestrator._parse_shard_tokens(
            ["7"], available_indices=available
        )


def test_success_profile_is_atomic_self_hashed_and_complete(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(tmp_path)
    _write_json(root / "fake_behavior.json", {})
    profile = root / "outputs/profile.json"

    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=2,
        shard_tokens=["all"],
        profile_output=profile,
        max_process_rss_mib=64.0,
        worker_script=worker,
        poll_interval_seconds=0.005,
        memory_sampler=_fake_memory,
        allow_test_memory_sampler=True,
    )

    assert report["status"] == "COMPLETE"
    assert report["worker_count_requested"] == 2
    assert report["worker_count_effective"] == 2
    assert report["requested_shard_indices"] == [0, 1, 2, 3]
    assert report["scheduled_shard_indices"] == [0, 1, 2, 3]
    assert report["unscheduled_shard_indices"] == []
    assert report["successful_shard_count"] == 4
    assert report["failed_shard_count"] == 0
    assert report["process_group_peak_resident_bytes"] == 2_000
    assert report["process_rss_cap"]["configured"] is True
    assert report["process_rss_cap"][
        "required_for_publication_execution"
    ] is True
    assert report["liveness"]["heartbeat_count"] >= 2
    assert report["liveness"]["final_heartbeat_status"] == "COMPLETE"
    assert report["liveness"]["final_heartbeat_sequence"] == report[
        "liveness"
    ]["heartbeat_count"]
    assert len(
        report["liveness"]["heartbeat_timestamps_utc"]
    ) == report["liveness"]["heartbeat_count"]
    assert report["throughput"][
        "completed_shards_per_wall_second"
    ] > 0.0
    assert report["execution_mode"] == (
        "TEST_ONLY_INJECTED_MEMORY_SAMPLER"
    )
    bindings = report["input_artifact_bindings"]
    assert bindings["plan"]["file_sha256"] == orchestrator._file_sha256(
        root / orchestrator.PILOT_PLAN_PATHS[1]
    )
    assert bindings["binary"]["file_sha256"] == hashlib.sha256(
        b"fake exact binary"
    ).hexdigest()
    assert bindings["build_manifest"]["file_sha256"] == hashlib.sha256(
        b'{"status":"fake"}\n'
    ).hexdigest()
    assert "orchestrator_script" in bindings
    assert bindings["orchestrator_script"]["file_sha256"] == (
        orchestrator._file_sha256(Path(orchestrator.__file__))
    )
    assert report["plan"]["available_shard_indices"] == [0, 1, 2, 3]
    assert len(report["plan"]["shard_inventory"]) == 4
    assert report["plan"]["shard_inventory_sha256"] == (
        orchestrator._canonical_sha256(
            report["plan"]["shard_inventory"]
        )
    )
    assert report["input_artifact_drift"] == []
    assert (
        report["ending_input_artifact_bindings"] == bindings
    )
    assert all(
        row["return_code"] == 0
        and row["peak_resident_bytes"] == 2_000
        and row["rss_sample_method"] == "FAKE_DETERMINISTIC_RSS"
        and isinstance(row["argv"], list)
        and "run-shard" in row["argv"]
        for row in report["shards"]
    )
    expected_stdout = hashlib.sha256(
        b"stdout shard=0\n"
    ).hexdigest()
    assert report["shards"][0]["stdout"]["sha256"] == expected_stdout
    projection = dict(report)
    declared = projection.pop("self_sha256")
    assert declared == orchestrator._canonical_sha256(projection)
    assert json.loads(profile.read_text(encoding="utf-8")) == report
    heartbeat_path = root / report["liveness"]["heartbeat_path"]
    heartbeat = json.loads(
        heartbeat_path.read_text(encoding="utf-8")
    )
    heartbeat_projection = dict(heartbeat)
    heartbeat_declared = heartbeat_projection.pop("self_sha256")
    assert heartbeat_declared == orchestrator._canonical_sha256(
        heartbeat_projection
    )
    assert heartbeat["status"] == "COMPLETE"
    assert heartbeat["input_artifact_bindings"] == bindings
    assert heartbeat["available_shard_indices"] == [0, 1, 2, 3]
    assert heartbeat["max_process_rss_bytes"] == 64 * 1024 * 1024
    assert (
        report["liveness"]["heartbeat_file_sha256"]
        == orchestrator._file_sha256(heartbeat_path)
    )
    assert not list(profile.parent.glob(f".{profile.name}.*.tmp"))
    assert not list(
        profile.parent.glob(".g4irsf15-shard-streams-*")
    )


def test_failure_stops_new_scheduling_but_reaps_running_workers(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=5
    )
    _write_json(
        root / "fake_behavior.json",
        {
            "0": {"delay": 0.01, "return_code": 7},
            "1": {"delay": 0.15, "return_code": 0},
        },
    )
    profile = root / "outputs/failure_profile.json"

    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=2,
        shard_tokens=["all"],
        profile_output=profile,
        max_process_rss_mib=64.0,
        worker_script=worker,
        poll_interval_seconds=0.005,
        heartbeat_interval_seconds=0.02,
        memory_sampler=_fake_memory,
        allow_test_memory_sampler=True,
    )

    assert report["status"] == "FAILED_STOPPED_SCHEDULING"
    assert report["scheduled_shard_indices"] == [0, 1]
    assert report["unscheduled_shard_indices"] == [2, 3, 4]
    assert report["first_failure_shard_index"] == 0
    assert report["successful_shard_count"] == 1
    assert report["failed_shard_count"] == 1
    assert report["liveness"]["heartbeat_count"] >= 3
    assert report["liveness"]["final_heartbeat_status"] == (
        "FAILED_STOPPED_SCHEDULING"
    )
    heartbeat_times = [
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in report["liveness"]["heartbeat_timestamps_utc"]
    ]
    assert all(
        left < right
        for left, right in zip(heartbeat_times, heartbeat_times[1:])
    )
    assert any(
        (right - left).total_seconds() >= 0.015
        for left, right in zip(heartbeat_times, heartbeat_times[1:])
    )
    assert {
        row["shard_index"]: row["return_code"]
        for row in report["shards"]
    } == {0: 7, 1: 0}
    assert (root / "started_0").is_file()
    assert (root / "started_1").is_file()
    assert not (root / "started_2").exists()
    assert json.loads(profile.read_text(encoding="utf-8")) == report


def test_rss_cap_fails_closed_terminates_offenders_and_stops_scheduling(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=4
    )
    _write_json(
        root / "fake_behavior.json",
        {
            "0": {"delay": 1.0, "return_code": 0},
            "1": {"delay": 1.0, "return_code": 0},
        },
    )
    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=2,
        shard_tokens=["all"],
        profile_output=root / "outputs/cap_profile.json",
        worker_script=worker,
        poll_interval_seconds=0.005,
        heartbeat_interval_seconds=0.02,
        max_process_rss_mib=0.001,
        memory_sampler=_fake_memory,
        allow_test_memory_sampler=True,
    )

    assert report["status"] == "FAILED_PROCESS_RSS_CAP"
    assert report["scheduled_shard_indices"] == [0, 1]
    assert report["unscheduled_shard_indices"] == [2, 3]
    assert report["successful_shard_count"] == 0
    assert report["failed_shard_count"] == 2
    cap = report["process_rss_cap"]
    assert cap["configured"] is True
    assert cap["max_process_rss_bytes"] == int(
        0.001 * 1024 * 1024
    )
    assert cap["exceeded_shard_indices"] == [0, 1]
    assert cap["unattestable_shard_indices"] == []
    assert all(
        row["orchestration_failure_reason"]
        == "PROCESS_RSS_CAP_EXCEEDED"
        for row in report["shards"]
    )
    assert report["liveness"]["final_heartbeat_status"] == (
        "FAILED_PROCESS_RSS_CAP"
    )


def test_configured_rss_cap_fails_closed_when_sampling_unavailable(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=2
    )
    _write_json(
        root / "fake_behavior.json",
        {"0": {"delay": 1.0}, "1": {"delay": 1.0}},
    )

    def unavailable(_pid: int) -> orchestrator.MemorySample:
        return orchestrator.MemorySample(
            None, None, "FAKE_UNAVAILABLE"
        )

    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=2,
        shard_tokens=["all"],
        profile_output=root / "outputs/unattestable_profile.json",
        worker_script=worker,
        poll_interval_seconds=0.005,
        max_process_rss_mib=64.0,
        memory_sampler=unavailable,
        allow_test_memory_sampler=True,
    )

    assert report["status"] == "FAILED_PROCESS_RSS_CAP"
    assert report["process_rss_cap"][
        "unattestable_shard_indices"
    ] == [0, 1]
    assert all(
        row["orchestration_failure_reason"]
        == "PROCESS_RSS_CAP_UNATTESTABLE"
        for row in report["shards"]
    )


def test_worker_count_must_be_positive(tmp_path: Path) -> None:
    root, binary, build_manifest, worker = _campaign_root(tmp_path)
    _write_json(root / "fake_behavior.json", {})
    with pytest.raises(
        orchestrator.OrchestratorError,
        match="WORKERS_MUST_BE_POSITIVE",
    ):
        orchestrator.run_campaign_shards(
            root=root,
            campaign="pilot",
            pilot_round=1,
            binary=binary,
            build_manifest=build_manifest,
            workers=0,
            shard_tokens=["0"],
            profile_output=root / "outputs/profile.json",
            max_process_rss_mib=64.0,
            worker_script=worker,
            memory_sampler=_fake_memory,
            allow_test_memory_sampler=True,
        )


def test_fast_success_without_any_rss_sample_fails_closed(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=1
    )
    _write_json(root / "fake_behavior.json", {"0": {"delay": 0.0}})

    def delayed_unavailable(_pid: int) -> orchestrator.MemorySample:
        # Let even a cold Windows Python process finish before the first
        # deliberately unavailable RSS observation.
        time.sleep(0.75)
        return orchestrator.MemorySample(
            None, None, "FAKE_FAST_PROCESS_ALREADY_EXITED"
        )

    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=1,
        shard_tokens=["all"],
        profile_output=root / "outputs/fast_unattestable.json",
        max_process_rss_mib=64.0,
        worker_script=worker,
        poll_interval_seconds=0.005,
        memory_sampler=delayed_unavailable,
        allow_test_memory_sampler=True,
    )

    assert report["status"] == "FAILED_PROCESS_RSS_CAP"
    assert report["process_rss_cap"][
        "unattestable_shard_indices"
    ] == [0]
    assert report["shards"][0]["return_code"] == 0
    assert report["shards"][0]["peak_resident_bytes"] is None
    assert report["shards"][0]["orchestration_failure_reason"] == (
        "PROCESS_RSS_CAP_UNATTESTABLE"
    )
    assert report["publication_execution_attestation"][
        "profile_status_complete"
    ] is False


def test_cli_requires_publication_rss_cap() -> None:
    with pytest.raises(SystemExit):
        orchestrator._parser().parse_args(
            [
                "--root",
                ".",
                "--campaign",
                "pilot",
                "--binary",
                "worker.exe",
                "--build-manifest",
                "build.json",
                "--profile-output",
                "profile.json",
            ]
        )


def test_injected_sampler_is_rejected_without_explicit_test_mode(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=1
    )
    _write_json(root / "fake_behavior.json", {})
    with pytest.raises(
        orchestrator.OrchestratorError,
        match="INJECTED_MEMORY_SAMPLER_REQUIRES_EXPLICIT_TEST_MODE",
    ):
        orchestrator.run_campaign_shards(
            root=root,
            campaign="pilot",
            pilot_round=1,
            binary=binary,
            build_manifest=build_manifest,
            workers=1,
            shard_tokens=["all"],
            profile_output=root / "outputs/rejected.json",
            max_process_rss_mib=64.0,
            worker_script=worker,
            memory_sampler=_fake_memory,
        )


@pytest.mark.parametrize(
    ("argument", "value", "message"),
    [
        (
            "max_process_rss_mib",
            orchestrator.MAX_PUBLICATION_PROCESS_RSS_MIB + 1.0,
            "MAX_PROCESS_RSS_MIB_EXCEEDS_PUBLICATION_LIMIT",
        ),
        (
            "heartbeat_interval_seconds",
            orchestrator.MAX_HEARTBEAT_INTERVAL_SECONDS + 1.0,
            "HEARTBEAT_INTERVAL_OUT_OF_PUBLICATION_RANGE",
        ),
    ],
)
def test_publication_resource_contract_has_hard_upper_bounds(
    tmp_path: Path,
    argument: str,
    value: float,
    message: str,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=1
    )
    _write_json(root / "fake_behavior.json", {})
    arguments: dict[str, object] = {
        "root": root,
        "campaign": "pilot",
        "pilot_round": 1,
        "binary": binary,
        "build_manifest": build_manifest,
        "workers": 1,
        "shard_tokens": ["all"],
        "profile_output": root / "outputs/bounds.json",
        "max_process_rss_mib": 64.0,
        "worker_script": worker,
    }
    arguments[argument] = value
    with pytest.raises(orchestrator.OrchestratorError, match=message):
        orchestrator.run_campaign_shards(**arguments)


def test_process_tree_sample_fails_if_any_enumerated_child_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orchestrator,
        "_windows_process_tree_pids",
        lambda _pid: [10, 11],
    )

    def sample_windows(pid: int) -> orchestrator.MemorySample:
        if pid == 10:
            return orchestrator.MemorySample(100, 120, "DIRECT")
        return orchestrator.MemorySample(None, None, "UNREADABLE")

    monkeypatch.setattr(
        orchestrator,
        "_windows_process_memory_sample",
        sample_windows,
    )
    windows = orchestrator._windows_process_tree_memory_sample(10)
    assert windows.current_resident_bytes is None
    assert windows.peak_resident_bytes is None

    monkeypatch.setattr(
        orchestrator,
        "_linux_process_tree_pids",
        lambda _pid: [20, 21],
    )

    def sample_linux(pid: int) -> orchestrator.MemorySample:
        if pid == 20:
            return orchestrator.MemorySample(100, 120, "DIRECT")
        return orchestrator.MemorySample(None, None, "UNREADABLE")

    monkeypatch.setattr(
        orchestrator,
        "_linux_process_memory_sample",
        sample_linux,
    )
    linux = orchestrator._linux_process_tree_memory_sample(20)
    assert linux.current_resident_bytes is None
    assert linux.peak_resident_bytes is None


def test_termination_escalates_after_bounded_grace_and_reap_timeout() -> None:
    class StubbornProcess:
        def __init__(self) -> None:
            self.terminate_count = 0
            self.kill_count = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminate_count += 1

        def kill(self) -> None:
            self.kill_count += 1

    process = StubbornProcess()
    shard = SimpleNamespace(
        shard_index=7,
        process=process,
        termination_requested_monotonic=None,
        kill_requested_monotonic=None,
        forced_kill=False,
    )
    orchestrator._request_termination(
        shard, now_monotonic=10.0
    )
    assert process.terminate_count == 1
    assert (
        orchestrator._advance_termination_escalation(
            {7: shard},
            now_monotonic=14.9,
            termination_grace_seconds=5.0,
            kill_reap_timeout_seconds=3.0,
        )
        == []
    )
    assert process.kill_count == 0
    assert (
        orchestrator._advance_termination_escalation(
            {7: shard},
            now_monotonic=15.0,
            termination_grace_seconds=5.0,
            kill_reap_timeout_seconds=3.0,
        )
        == []
    )
    assert process.kill_count == 1
    assert shard.forced_kill is True
    assert orchestrator._advance_termination_escalation(
        {7: shard},
        now_monotonic=18.0,
        termination_grace_seconds=5.0,
        kill_reap_timeout_seconds=3.0,
    ) == [7]


def test_success_worker_emits_periodic_intermediate_heartbeats(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=1
    )
    _write_json(
        root / "fake_behavior.json",
        {"0": {"delay": 0.25, "return_code": 0}},
    )
    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=1,
        shard_tokens=["all"],
        profile_output=root / "outputs/periodic.json",
        max_process_rss_mib=64.0,
        worker_script=worker,
        poll_interval_seconds=0.005,
        heartbeat_interval_seconds=0.02,
        memory_sampler=_fake_memory,
        allow_test_memory_sampler=True,
    )

    assert report["status"] == "COMPLETE"
    assert report["elapsed_wall_seconds"] > 2 * 0.02
    timestamps = [
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in report["liveness"]["heartbeat_timestamps_utc"]
    ]
    assert len(timestamps) >= 3
    gaps = [
        (right - left).total_seconds()
        for left, right in zip(timestamps, timestamps[1:])
    ]
    assert all(gap > 0.0 for gap in gaps)
    assert max(gaps) <= 0.15


@pytest.mark.skipif(
    os.name != "nt" and not os.sys.platform.startswith("linux"),
    reason="production process-tree RSS sampler is Windows/Linux only",
)
def test_production_profile_uses_native_process_tree_sampler(
    tmp_path: Path,
) -> None:
    root, binary, build_manifest, worker = _campaign_root(
        tmp_path, shard_count=1
    )
    _write_json(
        root / "fake_behavior.json",
        {"0": {"delay": 0.2, "return_code": 0}},
    )
    report = orchestrator.run_campaign_shards(
        root=root,
        campaign="pilot",
        pilot_round=1,
        binary=binary,
        build_manifest=build_manifest,
        workers=1,
        shard_tokens=["all"],
        profile_output=root / "outputs/production.json",
        max_process_rss_mib=512.0,
        worker_script=worker,
        poll_interval_seconds=0.01,
    )

    assert report["status"] == "COMPLETE"
    assert report["execution_mode"] == (
        "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
    )
    assert report["memory_sampling"][
        "production_native_sampler"
    ] is True
    assert report["publication_execution_attestation"][
        "production_native_memory_sampling"
    ] is True
    row = report["shards"][0]
    assert row["rss_sample_method"] in orchestrator.PRODUCTION_RSS_METHODS
    assert row["memory_sampling_supported"] is True
    assert row["rss_successful_sample_count"] > 0
