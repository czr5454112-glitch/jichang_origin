"""Failure-denominator and finite-endpoint controls for the paired runner."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json

import pytest

from scripts.experiments.ics_circulation_v3 import run_empty_improvement as runner


def row(scene, policy, *, status="controller_quiescent", cost=10.0):
    metrics = {"total_cost": cost, "completed": 2, "on_time": 1}
    return {"identity": scene + ":" + policy, "scene": scene, "tape": "nominal", "policy": policy,
        "status": status, "h80": dict(metrics), "final": dict(metrics),
        "invocation_cpu_seconds": 1.0, "invocation_wall_seconds": 2.0,
        "source_changed_during_case": False}


def test_worker_exception_preserves_all_predeclared_identities_and_unknown_resource_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ProcessPoolExecutor", ThreadPoolExecutor)
    source = "run_empty_improvement.py"
    monkeypatch.setattr(runner, "source_hashes", lambda: {
        source: sha256((runner.CODE / source).read_bytes()).hexdigest()})
    calls = []

    def fake_worker(output, si, ti, policy, expected):
        calls.append((si, ti, policy))
        if (si, ti, policy) == (2, 0, "empty12_h40"):
            raise OSError("injected failure before the worker can return accounting")
        result = row(f"s{si}", policy)
        result["identity"] = f"s{si}_t{ti}_{policy}"
        return result

    monkeypatch.setattr(runner, "worker", fake_worker)
    output = tmp_path / "fresh"
    result = runner.run(output, workers=2, pilot=True)
    assert len(calls) == len(set(calls)) == 28
    assert result["planned_episodes"] == result["recorded_episodes"] == 28
    assert len({r["identity"] for r in result["rows"]}) == 28
    assert result["statuses"] == {"controller_quiescent": 27, "worker_failure": 1}
    assert result["cases_with_unavailable_invocation_accounting"] == 1
    assert result["case_invocation_cpu_seconds_recorded"] == 27.0
    failed = next(r for r in result["rows"] if r["status"] == "worker_failure")
    assert failed["invocation_cpu_seconds"] is failed["invocation_wall_seconds"] is None
    assert "h80" not in failed and "final" not in failed
    saved = output / "cases" / failed["file"]
    assert sha256(saved.read_bytes()).hexdigest() == failed["sha256"]
    assert json.loads(saved.read_text())["failure"]["type"] == "OSError"
    with pytest.raises(ValueError):
        runner.run(output, workers=1, pilot=True)


def test_censored_pairs_and_missing_outcomes_are_explicit_not_zero_filled():
    rows = [row(f"s{i}", "greedy") for i in range(3)]
    rows.extend((row("s0", "empty2_h40", cost=8),
                 row("s1", "empty2_h40", status="tick_cap_censored", cost=0)))
    failure = row("s2", "empty2_h40", status="worker_failure")
    failure.pop("h80")
    failure.pop("final")
    failure["invocation_cpu_seconds"] = failure["invocation_wall_seconds"] = None
    rows.append(failure)
    result = runner.summarize(rows, 6)
    assert result["recorded_episodes"] == result["planned_episodes"] == 6
    for endpoint in ("h80", "final"):
        pair = result["pairs"]["empty2_h40:" + endpoint]
        assert pair["pairs"] == 2 and pair["both_quiescent"] == 1
        assert pair["cost_delta"] == -12  # Finite censored endpoint stays visible.
    assert result["statuses"]["tick_cap_censored"] == result["statuses"]["worker_failure"] == 1
    assert result["cases_with_unavailable_invocation_accounting"] == 1
