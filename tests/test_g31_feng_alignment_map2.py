"""Map identity and factor-isolation checks; these never invoke native C++."""
import csv
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_feng_alignment import (
    audit_requests, experiment, map2_experiment as map2, metrics, summarize,
)


def write_java_trace(path, canonical):
    fields = ("segment_id", "task_id", "start", "goal", "complete", "finish_epoch",
              "processed_attempt_epoch", "release_epoch")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in canonical:
            # Successful planning intentionally differs from generator release.
            release = int(row["pass_time"])
            writer.writerow({**{k: row[k] for k in fields[:4]}, "complete": "true",
                             "finish_epoch": release + 20, "processed_attempt_epoch": release + 7,
                             "release_epoch": release})


def test_six_map2_requests_preserve_official_inputs_and_isolate_factors(tmp_path, monkeypatch):
    def never_execute(**kwargs):
        raise AssertionError("request validation must not execute native C++")
    monkeypatch.setattr(map2.cpp_backend, "g4irsf11_event_runtime_from_records", never_execute)
    workload = map2.native.load_workload(1)
    official, _, rejected, _ = map2.native.prepare_native_request(
        map2.native.case_by_id(map2.CASE_ID), workload, binary=None)
    assert not rejected
    canonical = metrics.read_jsonl(map2.CANONICAL)
    trace = tmp_path / "map2_java.csv"
    write_java_trace(trace, canonical)
    releases = metrics.generator_releases(canonical, metrics.java_segments(trace))
    for mode in map2.MODES:
        for release_trace in (None, trace):
            request, rows, contract = map2.prepare_request(None, mode, release_trace)
            expected = dict(official, s4_wait_estimator=mode)
            if release_trace:
                expected["bag_records"] = [
                    (row[0], row[1], releases[row[0]], *row[3:]) for row in official["bag_records"]]
            assert experiment.normalize(request) == experiment.normalize(expected)
            assert rows == canonical
            assert contract["raw_bags"] == 28506
            assert contract["segments"] == 43603
            assert (contract["node_count"], contract["directed_edge_count"]) == (54, 69)
            assert contract["storage_in_goals"] == [47]
            assert contract["storage_out_starts"] == [52]
            assert contract["horizon"] == 98259
            assert contract["max_events"] == 60000000
            assert contract["speed_mps"] == 2.0
    assert all(path.is_file() for path in map2.source_paths())


def test_map2_rejects_nanning_ebs_roles_despite_matching_segment_ids(tmp_path):
    canonical = metrics.read_jsonl(map2.CANONICAL)
    wrong = [dict(row) for row in canonical]
    for row in wrong:
        if row["leg"] == "storage_in":
            row["goal"] = 53
        elif row["leg"] == "storage_out":
            row["start"] = 53
    trace = tmp_path / "nanning_roles.csv"
    write_java_trace(trace, wrong)
    with pytest.raises(ValueError, match="identity/OD mismatch"):
        map2.prepare_request(None, "legacy", trace)


@pytest.fixture
def small_arm(tmp_path):
    canonical = [{"segment_id": "1:direct", "task_id": 1, "leg": "direct", "start": 52,
                  "goal": 48, "original_entry_time": 10.5, "pass_time": 10.5, "std": 150.0}]
    canonical_path = tmp_path / "explicit_map2.jsonl"
    experiment.jsonl(canonical_path, canonical)
    actual = [{"segment_id": "1:direct", "task_id": 1, "start": 52, "goal": 48,
               "completed": True, "finish": 30.0, "entered": 17.0, "released": 10.5}]
    arm = tmp_path / "arm"
    arm.mkdir()
    manifest = {"arm": "small", "reused": False, "canonical": experiment.evidence(canonical_path),
                "execution_contract": experiment.NATIVE_CONTRACT,
                "release_contract": "canonical_pass_time_own_source",
                "binary": {"sha256": "same-binary"}, "score_overrides": {"s4_wait_estimator": "legacy"}}
    experiment.finish(arm, canonical, actual, manifest, horizon=200)
    return canonical_path, canonical, arm


def test_comparison_and_summary_use_explicit_map_canonical(small_arm, tmp_path, monkeypatch):
    canonical_path, _, arm = small_arm
    output = tmp_path / "audit"
    experiment.audit_arms(SimpleNamespace(arm=[f"map2={arm}"], output=output),
                          canonical_path=canonical_path, horizon=200)
    assert experiment.read(output / "audit.json")["canonical"] == experiment.evidence(canonical_path)
    report = tmp_path / "report"
    monkeypatch.setattr("sys.argv", ["summarize", "--arm", f"map2={arm}", "--output", str(report),
                                     "--canonical", str(canonical_path), "--horizon", "200"])
    summarize.main()
    saved = experiment.read(report / "report_data.json")
    assert saved["canonical"] == experiment.evidence(canonical_path)
    assert saved["arms"]["map2"]["table"]["offered_segments"] == 1


def test_request_audit_requires_explicit_map_identity(small_arm, tmp_path, monkeypatch):
    canonical_path, canonical, arm = small_arm
    trace = tmp_path / "release.csv"
    write_java_trace(trace, canonical)
    with gzip.open(arm / "request.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"s4_wait_estimator": "legacy", "bag_records": [["1:direct", 1, 10.5, 52, 48]]}, handle)
    output = tmp_path / "requests"
    monkeypatch.setattr("sys.argv", ["audit_requests", "--reference", str(arm), "--own", f"legacy={arm}",
                                     "--release-trace", str(trace), "--output", str(output),
                                     "--canonical", str(canonical_path)])
    audit_requests.main()
    saved = experiment.read(output / "audit.json")
    assert saved["canonical"] == experiment.evidence(canonical_path)
    assert saved["all_passed"] is True
