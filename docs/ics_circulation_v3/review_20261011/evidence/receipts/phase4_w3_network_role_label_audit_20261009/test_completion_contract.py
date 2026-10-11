import importlib.util
import json
from pathlib import Path
from dataclasses import dataclass

import pytest

spec = importlib.util.spec_from_file_location("completion_contract", Path(__file__).with_name("complete_missing.py"))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def row(status="not_executed", **changes):
    result = {"scene": "cross_cycle", "sample": "sample0", "group": 0, "candidate": 0, "draw": 0,
              "horizon_ticks": 80, "future_sha256": "future", "status": status, "total_cost": -100.}
    result.update(changes)
    result["request_key"] = driver.request_key(result)
    return result


def test_request_identity_includes_candidate_sample_and_every_requested_draw():
    base = row()
    assert len({driver.request_key(r) for r in (base, row(candidate=1), row(sample="sample1"),
        row(group=1), row(draw=1), row(horizon_ticks=40))}) == 6
    assert driver.request_key(row(total_cost=1000.)) == driver.request_key(base)


def test_recollection_compares_all_saved_fields_including_cache_only_fingerprint_excluded(monkeypatch):
    monkeypatch.setattr(driver, "sample_artifact", lambda sample: sample)
    old = {"checkpoint_sha256": "wall_old", "state": {"now": 5}, "routing_cache": {"lower": [1, 2]}, "cursor": {"route_index": 1}}
    live = {**old, "checkpoint_sha256": "wall_new"}
    assert driver.exact_decision_comparison(old, live)["equal"]
    assert not driver.exact_decision_comparison(old, {**live, "routing_cache": {"lower": [1]}})["equal"]
    assert not driver.exact_decision_comparison(old, {**live, "cursor": {"route_index": 0}})["equal"]
    assert not driver.exact_decision_comparison(old, {**live, "new_private_policy_state": 1})["equal"]


def write_history(prior, folder, outcomes):
    folder.mkdir()
    driver.write_new_json(folder / "protocol.json", {"primary_manifest_sha256": driver.sha(prior / "manifest.json"), "source_sha256": {}})
    driver.write_new_json(folder / "summary.json", {"request_outcomes": outcomes, "source_unchanged": True})
    driver.write_new_json(folder / "manifest.json", {p.name: driver.sha(p) for p in folder.iterdir()})


def test_missing_selection_uses_status_never_cost_and_history_cannot_replace_success(tmp_path):
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "manifest.json").write_text("{}")
    (prior / "protocol.json").write_text('{"source_sha256": {}}')
    original = [row("reached_horizon", total_cost=9999.), row("budget_exhausted", candidate=1, total_cost=-9999.),
                row("execution_failure", candidate=2, total_cost=0.), row("not_executed", candidate=3)]
    resolved, _ = driver.resolve_history(prior, original, ())
    assert list(resolved) == [original[0]["request_key"]]
    history = tmp_path / "history"
    write_history(prior, history, [{**original[1], "status": "reached_horizon", "total_cost": 0.}])
    resolved, _ = driver.resolve_history(prior, original, (history,))
    assert set(resolved) == {original[0]["request_key"], original[1]["request_key"]}
    duplicate = tmp_path / "duplicate"
    write_history(prior, duplicate, [original[0]])
    with pytest.raises(ValueError, match="rerun/replaced"):
        driver.resolve_history(prior, original, (duplicate,))


def test_history_cannot_change_original_future_or_action(tmp_path):
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "manifest.json").write_text("{}")
    (prior / "protocol.json").write_text('{"source_sha256": {}}')
    original = row()
    history = tmp_path / "bad"
    write_history(prior, history, [{**original, "status": "reached_horizon", "future_sha256": "different"}])
    with pytest.raises(ValueError, match="identity or future"):
        driver.resolve_history(prior, [original], (history,))


@dataclass
class Result:
    total_cost: float = 80.
    cost_components: dict = None
    completed: tuple = ("a", "b")
    uncompleted_bag_ids: tuple = ("c",)


def test_success_replaces_every_old_partial_metric_and_failure_marks_partial(tmp_path):
    artifact = tmp_path / "branch.json"
    artifact.write_text("{}")
    old = row("budget_exhausted", total_cost=5., cost_components={"old": 5.},
              completed_bags=0, uncompleted_bags=5, file="old-partial.json", reason="old_cpu_cap")
    outcome = {"status": "reached_horizon", "result": Result(cost_components={"new": 80.}),
               "cpu_seconds": 1., "wall_seconds": 2., "search_calls": 3, "search_work": 4}
    new = driver.outcome_value(old, outcome, artifact)
    assert (new["total_cost"], new["cost_components"], new["completed_bags"], new["uncompleted_bags"]) == (80., {"new": 80.}, 2, 1)
    assert not new["result_is_partial"]
    assert new["original_status"] == "budget_exhausted" and new["original_file"] == "old-partial.json"
    assert new["reason"] is None and new["original_reason"] == "old_cpu_cap"
    failure = driver.outcome_value(old, {**outcome, "status": "execution_failure", "result": None}, artifact)
    assert all(failure[field] is None for field in ("total_cost", "cost_components", "completed_bags", "uncompleted_bags"))
    assert failure["result_is_partial"]
    skipped = driver.not_executed_value(old, "new_cpu_cap")
    assert skipped["original_reason"] == "old_cpu_cap" and skipped["reason"] == "new_cpu_cap"
    assert all(skipped[field] is None for field in ("total_cost", "cost_components", "completed_bags", "uncompleted_bags"))


def test_exception_after_call_is_attempted_failure_and_preserves_known_physical_result(monkeypatch, tmp_path):
    def crash(*args, **kwargs):
        raise RuntimeError("physical failure")
    monkeypatch.setattr(driver, "branch_network_decision", crash)
    sample = {"checkpoint": None, "pool": [None]}
    value, outcome, failure = driver.execute_request(row(), sample, [], None, tmp_path / "b.json.gz")
    assert value["status"] == "execution_failure" and outcome is None
    assert value["search_calls"] is None and value["total_cost"] is None
    physical = {"status": "reached_horizon", "result": Result(cost_components={"new": 80.}),
               "cpu_seconds": 1., "wall_seconds": 2., "search_calls": 3, "search_work": 4}
    monkeypatch.setattr(driver, "branch_network_decision", lambda *args, **kwargs: physical)
    value, outcome, failure = driver.execute_request(row(), sample, [], None, tmp_path / "absent" / "b.json.gz")
    assert value["status"] == "evidence_write_failure" and outcome == physical
    assert value["physical_status"] == "reached_horizon" and value["physical_result"]["total_cost"] == 80.
    assert value["search_calls"] == 3 and value["total_cost"] is None


def test_shards_are_disjoint_complete_and_keep_identical_future_requests_together():
    original = [row(candidate=c, group=g, draw=d, future_sha256="same" if d < 2 else "other")
                for c in range(4) for g in range(4) for d in range(3)]
    all_keys = set()
    assignments = []
    for shard in range(3):
        selected, manifest = driver.shard_requests(original, shard, 3)
        keys = {r["request_key"] for r in selected}
        assert not all_keys & keys
        all_keys |= keys
        assignments.append(manifest)
        for selected_row in selected:
            assert all(r in selected for r in original if driver.memo_key(r) == driver.memo_key(selected_row))
    assert all_keys == {r["request_key"] for r in original}
    assert assignments[0] == assignments[1] == assignments[2]
    changed_values = [{**r, "total_cost": 1000.} for r in original]
    assert driver.shard_requests(changed_values, 0, 3)[1] == assignments[0]


@pytest.mark.parametrize("violation", ["source_changed", "source_contract", "unlisted_file"])
def test_history_rejects_unstable_source_and_incomplete_file_set(tmp_path, violation):
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "manifest.json").write_text("{}")
    (prior / "protocol.json").write_text('{"source_sha256": {}}')
    original = row()
    history = tmp_path / "history"
    write_history(prior, history, [{**original, "status": "reached_horizon"}])
    if violation == "unlisted_file":
        (history / "extra.txt").write_text("unlisted")
    else:
        target = history / ("summary.json" if violation == "source_changed" else "protocol.json")
        data = driver.read(target)
        data["source_unchanged" if violation == "source_changed" else "source_sha256"] = False if violation == "source_changed" else {"changed.py": "other"}
        target.write_text(json.dumps(data))
        manifest = driver.read(history / "manifest.json")
        manifest[target.name] = driver.sha(target)
        (history / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="file set|unchanged original source"):
        driver.resolve_history(prior, [original], (history,))


@pytest.mark.parametrize("flag", ["source_changed_during_run", "profile_changed_during_run"])
def test_primary_drift_alarm_cannot_be_hidden_by_matching_current_bytes(tmp_path, flag):
    summary = {"scene_summaries_received": 3, "worker_failures": [], "complete_resource_accounting": True,
        "source_changed_during_run": False, "profile_changed_during_run": False, flag: True}
    driver.write_new_json(tmp_path / "summary.json", summary)
    driver.write_new_json(tmp_path / "protocol.json", {"source_sha256": {}})
    driver.write_new_json(tmp_path / "manifest.json", {"summary_sha256": driver.sha(tmp_path / "summary.json"),
        "protocol_sha256": driver.sha(tmp_path / "protocol.json")})
    with pytest.raises(ValueError, match="source/profile drift"):
        driver.load_primary(tmp_path)
