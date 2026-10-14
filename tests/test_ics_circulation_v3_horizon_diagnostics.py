from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.horizon_diagnostics import (
    audit_old_twenty, horizon_outcomes, outcome_metrics, same_saved_decision)
from scripts.experiments.ics_circulation_v3.label_stability import sustained_scenes
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, PublishedRoutingSelector
from scripts.experiments.ics_circulation_v3.role_coverage import (
    branch_role_decision, checkpoint_fingerprint, collect_role_decisions, sample_artifact)


@pytest.fixture(scope="module")
def sample():
    scene = sustained_scenes()[0]
    spec = ControlSpec(planning_horizon=20)
    found = collect_role_decisions(scene, spec)
    return scene, spec, found.samples[0]


@pytest.mark.parametrize("index", [0, 1, 3])
def test_reporting_at_intermediate_endpoints_equals_direct_replay(sample, index):
    scene, spec, decision = sample
    prior = checkpoint_fingerprint(decision["checkpoint"])
    policy = PublishedRoutingSelector(spec, scene.forecasts)
    multi = horizon_outcomes(decision["checkpoint"], decision["pool"][index], scene.future_bags,
                             (20, 40, 80), continuation_selector=policy)
    for h in (20, 40, 80):
        single = branch_role_decision(decision["checkpoint"], decision["pool"][index], scene.future_bags,
            h, continuation_selector=policy, selector_manifest={"kind": "timed"})
        assert multi[h].final_snapshot == single.final_snapshot
        assert multi[h].trace == single.trace
        assert multi[h].cost_components == single.cost_components
        assert multi[h].total_cost == single.total_cost
        assert multi[h].invariant_checks == single.invariant_checks
    assert multi[20].final_snapshot.now == 20  # Later advance did not mutate it.
    assert checkpoint_fingerprint(decision["checkpoint"]) == prior


def test_terminal_free_view_is_arithmetic_without_mutating_the_outcome(sample):
    scene, spec, decision = sample
    outcome = horizon_outcomes(decision["checkpoint"], decision["pool"][0], scene.future_bags, (1,))[1]
    before = asdict(outcome)
    row = outcome_metrics(outcome)
    assert row["terminal_cost"] > 0
    assert row["total_cost"] == pytest.approx(row["terminal_cost"] + row["nonterminal_cost_same_trajectory"])
    assert asdict(outcome) == before
    old = {**row, "failed": False}
    assert audit_old_twenty(old, row)
    assert not audit_old_twenty({**old, "total_cost": old["total_cost"] + .1}, row)
    assert not audit_old_twenty({**old, "completed": {"imaginary": 1}}, row)


@pytest.mark.parametrize("offsets", [(), (20, 20), (40, 20), (0, 20), (1.5,), (True,)])
def test_invalid_evaluation_endpoints_are_rejected(sample, offsets):
    scene, spec, decision = sample
    with pytest.raises(ValueError, match="strictly increasing"):
        horizon_outcomes(decision["checkpoint"], decision["pool"][0], scene.future_bags, offsets)


def test_recollection_validation_excludes_only_explicit_audit_provenance(sample):
    import json
    scene, spec, decision = sample
    old = json.loads(json.dumps(sample_artifact(decision)))
    old["checkpoint_sha256"] = "different-instance"
    old["search_work"] += 1
    assert same_saved_decision(old, decision)["equal"]
    old["checkpoint_metadata"]["next_slow_trigger_at"] += 1
    assert not same_saved_decision(old, decision)["equal"]
    old = json.loads(json.dumps(sample_artifact(decision)))
    old["continuation_contract"]["spec"]["candidate_count"] += 1
    assert not same_saved_decision(old, decision)["equal"]


def test_substituted_tape_rejects_observed_or_duplicate_tasks(sample):
    scene, spec, decision = sample
    for bad in ((scene.future_bags[0], scene.future_bags[0]),
                (replace(scene.future_bags[0], arrival=decision["time"]),)):
        with pytest.raises(ValueError, match="future contains"):
            horizon_outcomes(decision["checkpoint"], decision["pool"][0], bad, (20,))


def test_budget_stop_preserves_partial_work_cache_hits_and_unexecuted_denominator(sample, tmp_path):
    from scripts.experiments.ics_circulation_v3.role_coverage import digest
    from scripts.experiments.ics_circulation_v3.run_horizon_diagnostics import label_sample
    scene, spec, decision = sample
    tape = [asdict(b) for b in scene.future_bags]
    outcome = horizon_outcomes(decision["checkpoint"], decision["pool"][0], scene.future_bags, (20,),
        continuation_selector=PublishedRoutingSelector(spec, scene.forecasts))[20]
    row = {**outcome_metrics(outcome), "failed": False, "future_sha256": digest(tape)}
    old = {"groups": 4, "futures_per_group": 8, "candidate_count": 4,
           "future_groups_offline_only": [{"tapes": [tape] * 8} for _ in range(4)],
           "raw_branches": [{**row, "group": g, "candidate": c, "future_index": f}
                            for g in range(4) for c in range(4) for f in range(8)]}
    attempts = []
    def budget():
        attempts.append(1)
        if len(attempts) > 1:
            raise TimeoutError("test physical branch budget")
    # Production owner/scene nesting puts the parent near this depth. Full
    # SHA filenames exceeded legacy Windows MAX_PATH; ordinal names must work.
    target = tmp_path / ("x" * max(1, 200 - len(str(tmp_path.resolve())) - 1))
    target.mkdir()
    result = label_sample(decision, old, target, scene, budget)
    assert result["requested_branches"] == 128
    assert result["actual_branches"] == 1
    assert result["cache_reused"] == 31
    assert result["not_executed_requests"] == 96
    assert result["endpoint_reads"] == 96
    assert result["actual_unique_endpoint_reads"] == 3
    assert result["actual_unique_endpoint_reads_exact"]
    assert len(result["failures"]) == 96
    assert len(list((target / "branches").glob("*.json.gz"))) == 1
    assert all(len(str((target / r["evidence"]).resolve())) < 259
               for r in result["raw_branches"] if "evidence" in r)
    assert result["actual_branches"] + result["cache_reused"] + result["not_executed_requests"] == 128
