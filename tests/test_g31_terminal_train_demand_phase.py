"""TRAIN collection registration and evaluation isolation; no native starts."""
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as campaign
from scripts.experiments.g31_ics_circulation.foundation_airport_transport_allocation import DEFAULT_CONFIG
from test_g31_terminal_transport_campaign import save, run_plan, change_plan, block


@pytest.fixture
def registered(tmp_path, monkeypatch):
    cycle = tmp_path/"cycle"
    source = save(tmp_path/"source.json", {"files": {}})
    calibration = save(cycle/"runtime_calibration_001.json", dict(before_training=True,
        horizon=59400., soft_seconds=2280., hard_seconds=2400., estimated_evidence_bytes=256*1024**2))
    save(cycle/"training/mapping_fit_001/mapping.json", {})
    save(cycle/"campaign_budget.json", dict(native_start_limit=160,
        allocations=dict(initial=24, reserve=8, bridge=20), active_seconds_limit=172800.,
        new_evidence_bytes_limit=40*1024**3, free_space_floor_bytes=30*1024**3))
    state = dict(open_runners=[], unfinished_native_tasks=[], by_batch=dict(initial=22, reserve=8, bridge=7),
                 native_starts=40, active_seconds=0., evidence_bytes=0, free_bytes=100*1024**3)
    monkeypatch.setattr(campaign.campaign, "CYCLE", cycle)
    monkeypatch.setattr(campaign, "ROOT", cycle/"terminal_flow")
    monkeypatch.setattr(campaign.budget, "status", lambda _: state)
    events, attempts = [], []
    monkeypatch.setattr(campaign.budget, "append", lambda *a, **kw: events.append((a, kw)))

    def plan(directory, method, seed, *, horizon=59400., task_id=None, **changes):
        ref = run_plan(directory, method, source_hash=source["sha256"], parent=seed, horizon=horizon)
        return change_plan(ref, task_id=task_id or f"{directory.name}_{method}_{seed}",
            parent=dict(parent_seed=seed, split="train"), source_bundle=source,
            batch="initial", calibration=calibration,
            soft_seconds=2280., hard_seconds=2400., estimated_evidence_bytes=256*1024**2, **changes)

    def gate(*, source_override=None, closed=True):
        refs = [plan(tmp_path/"gate-runs", method, 2101, horizon=18000.)
                for method in campaign.METHODS["export_gate"]]
        if not closed:
            (Path(refs[0]["path"]).parent/"receipt.json").unlink()
        if source_override:
            refs = [change_plan(ref, source_bundle=source_override) for ref in refs]
        path = campaign.ROOT/"export_gate"/"block.json"
        save(path, dict(schema=campaign.SCHEMA, name="export_gate", phase="export_gate", parents=[2101],
            methods=list(campaign.METHODS["export_gate"]), source_bundle=source_override or source,
            fixed_allocator=DEFAULT_CONFIG, task_plans=refs, dependencies=[]))
        return path

    def prepare(identity, **options):
        attempts.append((identity, options))
        ref = plan(tmp_path/"runs"/str(options["seed"]), options["method"], options["seed"],
                   horizon=options["horizon"], task_id=identity)
        return Path(ref["path"]).parent
    monkeypatch.setattr(campaign.campaign, "prepare", prepare)
    return dict(cycle=cycle, source=source, calibration=calibration, state=state,
                events=events, attempts=attempts, gate=gate, plan=plan, tmp=tmp_path)


def collect(registered, **kwargs):
    return campaign.prepare_block("train", phase="train_demand", source=registered["source"]["path"], **kwargs)


def test_full_train_registration_uses_original_calibration_and_remaining_initial_quota(registered):
    prior = registered["gate"]()
    result = collect(registered)
    assert result["parents"] == [2101, 2102] and result["methods"] == ["TF-B1-300"]
    assert result["batch"] == "initial" and result["purpose"] == "training_demand_label_collection"
    assert result["scientific_comparison"] is False and len(result["dependencies"]) == 1
    assert result["dependencies"][0]["path"] == str(prior.resolve())
    assert result["prior_budget"]["by_batch"]["reserve"] == 8
    assert len(registered["attempts"]) == 2
    for identity, options in registered["attempts"]:
        assert options["seed"] in (2101, 2102) and options["method"] == "TF-B1-300"
        assert options["batch"] == "initial" and options["calibration"] == registered["calibration"]
        assert (options["horizon"], options["soft_seconds"], options["hard_seconds"]) == (59400., 2280., 2400.)
        assert options["demand_model"] is None
    assert len(registered["events"]) == 1


@pytest.mark.parametrize("parents", [[2201], [2301], [2101, 2201], [2103]])
def test_DEV_TEST_and_unregistered_training_parents_rejected_before_prepare(registered, parents):
    with pytest.raises(ValueError, match="registered_parent_block"):
        collect(registered, parents=parents)
    assert registered["attempts"] == [] and registered["events"] == []


@pytest.mark.parametrize("problem", ["missing", "unfinished", "different_source"])
def test_training_collection_requires_closed_same_source_native_gate(registered, problem):
    if problem == "unfinished":
        registered["gate"](closed=False)
    elif problem == "different_source":
        registered["gate"](source_override={"path": "old.json", "sha256": "old-source"})
    with pytest.raises(ValueError, match="closed_dependency_required:native_gate"):
        collect(registered)
    assert registered["attempts"] == [] and registered["events"] == []


@pytest.mark.parametrize("limit", ["initial", "native", "time", "evidence"])
def test_whole_training_collection_is_budgeted_before_any_task_preparation(registered, limit):
    registered["gate"]()
    if limit == "initial":
        registered["state"]["by_batch"]["initial"] = 23
    elif limit == "native":
        registered["state"]["native_starts"] = 159
    elif limit == "time":
        registered["state"]["active_seconds"] = 172800. - 2400.
    else:
        registered["state"]["evidence_bytes"] = 40*1024**3 - 256*1024**2
    with pytest.raises(ValueError, match="whole_block"):
        collect(registered)
    assert registered["attempts"] == [] and registered["events"] == []


@pytest.mark.parametrize("mutation", ["dev_split", "test_split", "short_horizon", "batch", "calibration", "timing"])
def test_registered_training_plan_is_rechecked_for_split_horizon_and_runtime_contract(registered, mutation):
    registered["gate"]()
    result = collect(registered)
    ref = result["task_plans"][0]
    if mutation.endswith("split"):
        updates = dict(parent=dict(parent_seed=2101, split=mutation.split("_")[0]))
    elif mutation == "short_horizon":
        updates = dict(horizon=18000.)
    elif mutation == "batch":
        updates = dict(batch="development")
    elif mutation == "calibration":
        updates = dict(calibration={"path": "other.json", "sha256": "other"})
    else:
        updates = dict(hard_seconds=720.)
    result["task_plans"][0] = change_plan(ref, **updates)
    with pytest.raises(ValueError, match="TRAIN_only|registered_phase_horizon|fixed_runtime_calibration|calibration_limits_binding"):
        campaign._validate_block_manifest(result)


def test_closed_training_collection_is_explicitly_not_a_scientific_pair(registered):
    registered["gate"]()
    collect(registered)
    report = campaign.evaluate([campaign.ROOT/"train"/"block.json"])
    assert report["all_registered_closed"] is True
    assert report["training_label_collection_runs"] == 2
    assert report["paired_comparison_complete"] is False and report["paired"] == []
    assert len(report["missing_pair_reasons"]) == 2
    assert {r["reason"] for r in report["missing_pair_reasons"]} == {
        "training_label_collection_not_a_scientific_comparison"}
    assert all(not row["comparison_eligible"] for row in report["runs"])
    assert "TRAIN label collection only" in report["conclusions"]


def test_training_collection_is_neither_comparison_candidate_nor_baseline_in_mixed_evaluation(registered):
    registered["gate"]()
    collect(registered)
    # These have the same physical contract, so purpose is the decisive barrier.
    baseline = registered["plan"](registered["tmp"]/"science60", "TF-B1-60", 2101)
    candidate = registered["plan"](registered["tmp"]/"scienceperiod", "TF-B1-300-replan300", 2101)
    science = block(registered["tmp"]/"science", [baseline, candidate])
    report = campaign.evaluate([campaign.ROOT/"train"/"block.json", science])
    assert report["paired"] == []
    period = next(row for row in report["runs"] if row["method"] == "TF-B1-300-replan300")
    assert any(row["task_id"] == period["task_id"] and
               row["reason"] == "missing_closed_paired_baseline_or_candidate"
               for row in report["missing_pair_reasons"])


def test_closed_label_collection_cannot_itself_replace_native_gate(registered):
    registered["gate"]()
    collect(registered)
    dependency = campaign.bound(campaign.ROOT/"train"/"block.json")
    with pytest.raises(ValueError, match="dependency_phase_or_source_mismatch"):
        campaign._validate_dependencies(dict(phase="bridge", parents=[2201],
            source_bundle=registered["source"], dependencies=[dependency]))


def test_short_runtime_calibration_cannot_prepare_training_collection(registered):
    registered["gate"]()
    path = Path(registered["calibration"]["path"])
    value = campaign.read(path)
    value["horizon"] = 18000.
    save(path, value)
    with pytest.raises(ValueError, match="full_registered_horizon_required"):
        collect(registered)
    assert registered["attempts"] == [] and registered["events"] == []
