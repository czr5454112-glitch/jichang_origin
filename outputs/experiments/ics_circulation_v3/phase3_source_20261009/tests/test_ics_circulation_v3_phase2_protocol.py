import json

from scripts.experiments.ics_circulation_v3.run_phase2_learning import run


def test_grouped_first_prefix_pipeline_freezes_models_and_evaluates_independent_runs(tmp_path):
    summary = run(tmp_path / "run", train=2, validation=1, test=1, deployment=1)
    assert summary["source_groups"] == {"train": 2, "validation": 1, "test": 1, "deployment": 1}
    assert summary["candidate_rows"] == 16
    assert summary["paired_branch_rollouts"] == 32
    assert summary["label_stage_forecast_model_rollouts"] == 16
    assert summary["deployment_runs"] == 6
    assert summary["invariant_checks"] > 0
    rows = [json.loads(line) for line in (tmp_path / "run/candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(row["delta_mean"] == row["timed_delta"] == row["forecast_delta"] == 0
               for row in rows if row["is_baseline"])
    assert all(row["candidate"]["legs"][0]["depart"] >= 2 for row in rows)
    records = json.loads((tmp_path / "run/validation_selection.json").read_text(encoding="utf-8"))
    assert len(records) == 10
    assert all(":validation:" in decision["source_group"] for row in records for decision in row["decisions"])
    for kind in ("direct", "residual"):
        assert (tmp_path / "run" / f"{kind}_model.json").exists()
    assert set(summary["candidate_test"]) == set(summary["independent_closed_loop"])
