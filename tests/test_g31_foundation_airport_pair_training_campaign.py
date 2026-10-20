"""Registration and bounded orchestration tests; all primary fits are mocked."""
import copy
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_pair_ranker as ranker
from scripts.experiments.g31_ics_circulation import foundation_airport_pair_training_campaign as campaign
from test_g31_foundation_airport_pair_ranker import dataset, forecast_evidence


def pair(seed, advantage, *, split="train", fleet=22):
    result = dataset(seed, advantage, split=split)
    result["schema"] = "g31.foundation.airport_pair_dataset.v1"
    result["pair"]["parent"]["fleet"] = fleet
    if fleet != 22:
        result["pair"]["pair_id"] += "-fleet"+str(fleet)
    result["pair"]["complete_prefix_sha256"] = ranker.digest({"seed": seed, "fleet": fleet})
    for arm in ("reference_cost", "patched_cost"):
        result["pair"][arm]["label_start"] = 10.
    for row in result["rows"]:
        row["pair_id"] = result["pair"]["pair_id"]
        row["transition"] = None
        row["parent"]["fleet"] = fleet
        evidence = forecast_evidence(row)
        manifest = evidence["producer_manifest"]
        manifest.update(source_calendar_start_epoch_seconds=1699900000.,
            training_labels_closed_at_epoch_seconds=1699943200.,
            model_available_at_epoch_seconds=1699957600.)
        evidence.update(training_labels_closed_at_epoch_seconds=1699943200.,
            model_available_at_epoch_seconds=1699957600.,
            provenance_sha256=ranker.digest(manifest))
        row["forecast_evidence"] = evidence
    return result


def input_refs(directory, result, *, batch="H", name=None):
    directory.mkdir(parents=True, exist_ok=True)
    seed = result["pair"]["parent"]["parent_seed"]
    prefix = name or str(seed)
    plans = []
    for branch in ("a_ref", "a_patch"):
        plan = {"parent": result["pair"]["parent"], "batch": batch, "branch": branch,
            "window": [0., 20.], "input": {"sha256": "frozen-input"}}
        plans.append(campaign._write_new(directory/f"{prefix}_{branch}_plan.json", plan))
    return {"dataset": campaign._write_new(directory/f"{prefix}_dataset.json.gz", result),
        "reference_plan": plans[0], "patched_plan": plans[1]}


def prepared(tmp_path, monkeypatch, *, advantages=(10., -20.), domain="primary_22"):
    # Archive only dependencies needed by the artifact gate in these fixtures.
    def minimal_archive(directory):
        root = Path(campaign.__file__).resolve().parents[3]
        result = {}
        for logical, sha in (ranker.source_pins() | campaign.orchestration_source_pins()).items():
            target = directory/"source"/logical
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root/logical).read_bytes())
            result[logical] = {"sha256": sha, "archive": campaign.file_ref(target)}
        return result
    monkeypatch.setattr(campaign, "_source_archive", minimal_archive)
    train = [input_refs(tmp_path/"inputs", pair(seed, advantage)) for seed, advantage in zip(
        (701, 702), advantages, strict=True)]
    dev = [input_refs(tmp_path/"inputs", pair(seed, advantage, split="dev"), batch="C")
        for seed, advantage in ((801, 15.), (802, -10.))]
    if domain == "mixed_18_22_26":
        train.extend(input_refs(tmp_path/"inputs", pair(701, 2., fleet=fleet),
            batch="F", name="train-fleet"+str(fleet)) for fleet in (18, 26))
        dev.extend(input_refs(tmp_path/"inputs", pair(801, 2., split="dev", fleet=fleet),
            batch="F", name="dev-fleet"+str(fleet)) for fleet in (18, 26))
    addendum = campaign._write_new(tmp_path/"addendum.json", {
        "schema": "g31.action_forecast_capture_addendum.v1", "test_opened": False,
        "H_long_branches": 4, "training_fairness": "same actual received-plan datasets"})
    return campaign.prepare_manifest(output=tmp_path/"campaign", train_inputs=train,
        dev_inputs=dev, training_domain=domain, forecast_addendum=addendum,
        model_available_at_epoch_seconds=1700000000.+3*86400.)


def mock_fit(datasets, *, information_variant, seed, architecture, registration, deadline, epochs):
    # Manually fixed zero-weight fixture, not a fitted or scientific checkpoint.
    names = sorted(ranker.action_features(datasets[0]["rows"][0], information_variant=information_variant))
    model = {"schema": ranker.SCHEMA, "feature_schema": ranker.FEATURE_SCHEMA, "seed": seed,
        "information_variant": information_variant, "architecture": architecture, "epochs": epochs,
        "feature_names": names, "training_dataset_sha256": ranker.digest(datasets),
        "training_labels_closed_at_epoch_seconds": 1700000000.+2*86400.+1810.,
        "model_available_at_epoch_seconds": registration["model_available_at_epoch_seconds"],
        "forecast_contract": ranker._forecast_contract(datasets[0]["rows"][0]) if information_variant == "C11" else None,
        "parameters": {"center": [0.]*len(names), "scale": [1.]*len(names), "target_scale": 1.,
            "layers": [{"weight": [[0.]*len(names)], "bias": [0.]}]},
        "registration": registration, "wall_seconds": 0., "fixture_not_fitted": True}
    model["model_id"] = ranker.digest(model)
    return model


def test_manifest_freezes_shared_data_and_six_chains_without_fitting(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Preparation must not fit")
    monkeypatch.setattr(ranker, "fit_ranker", forbidden)
    result = prepared(tmp_path, monkeypatch)
    assert result["status"] == "registered_not_run" and result["fit_calls_started"] == 0
    manifest = campaign.read_bound(result["manifest"])
    assert len(result["chain_plans"]) == 6 and manifest["primary_fit_calls_planned"] == 12
    assert manifest["requested_training_jobs"] == 6
    gate = campaign.read_bound(manifest["transition_gate"])
    assert gate["train"]["closed_pairs"] == 2 and gate["train"]["bootstrap_authorized"] is False
    snapshots = set()
    for reference in result["chain_plans"]:
        plan = campaign.read_bound(reference)
        snapshots.add(plan["snapshots"]["train"]["sha256"])
        assert plan["wall_budget_seconds"] == 300. and plan["primary_fit_calls_planned"] == 2
        for registration in plan["registrations"].values():
            fit = campaign.read_bound(registration)
            assert fit["epochs"] == 100 and fit["test_opened"] is False
    assert len(snapshots) == 1


def test_no_effect_or_one_direction_data_creates_explicit_no_fit_receipt(tmp_path, monkeypatch):
    result = prepared(tmp_path, monkeypatch, advantages=(0., 0.))
    assert result["status"] == "blocked_insufficient_information_no_fits"
    assert result["chain_plans"] == [] and result["fit_calls_started"] == 0
    manifest = campaign.read_bound(result["manifest"])
    assert manifest["requested_training_jobs"] == manifest["primary_fit_calls_planned"] == 0
    assert manifest["blocking_reasons"]


def test_test_plan_is_rejected_before_test_dataset_is_read(tmp_path):
    item = input_refs(tmp_path, pair(901, 10., split="test"))
    item["dataset"] = {"path": str(tmp_path/"test_outcomes_must_not_be_opened.json"), "sha256": "absent"}
    with pytest.raises(ValueError, match="rejected_before_data_read"):
        campaign.load_datasets([item], split="train", training_domain="primary_22")


def test_B_cannot_silently_give_current_only_model_extra_fit_data(tmp_path):
    item = input_refs(tmp_path, pair(701, 10.), batch="B")
    with pytest.raises(ValueError, match="B_mechanism_only"):
        campaign.load_datasets([item], split="train", training_domain="primary_22")


def test_missing_actual_forecast_rejects_both_variants_fairly(tmp_path):
    result = pair(701, 10.)
    for row in result["rows"]:
        row.pop("forecast_evidence")
    item = input_refs(tmp_path, result)
    with pytest.raises(ValueError, match="C11_requires_actual"):
        campaign.load_datasets([item], split="train", training_domain="primary_22")


def test_exact_physical_duplicates_deduplicated_with_explicit_denominator(tmp_path):
    first = pair(701, 10.)
    second = copy.deepcopy(first)
    second["pair"]["pair_id"] += "-another-recording"
    for row in second["rows"]:
        row["pair_id"] = second["pair"]["pair_id"]
    inputs = [input_refs(tmp_path, first, name="first"), input_refs(tmp_path, second, name="duplicate")]
    datasets, provenance = campaign.load_datasets(inputs, split="train", training_domain="primary_22")
    assert len(datasets) == 1 and len(provenance["deduplicated"]) == 1
    assert provenance["input_artifact_count"] == 2


def test_mock_chain_counts_two_fits_and_freezes_dev_selection(tmp_path, monkeypatch):
    result = prepared(tmp_path, monkeypatch)
    calls = []
    def fit(*args, **kwargs):
        calls.append((kwargs["architecture"], kwargs["deadline"]))
        return mock_fit(*args, **kwargs)
    monkeypatch.setattr(ranker, "fit_ranker", fit)
    receipt = campaign.read_bound(campaign.run_registered_chain(result["chain_plans"][0]))
    assert receipt["status"] == "completed_two_fits_and_frozen_dev_selection"
    assert receipt["fit_calls_started"] == receipt["fit_calls_completed"] == 2
    assert [item[0] for item in calls] == ["linear", "small_mlp"] and calls[0][1] == calls[1][1]
    with pytest.raises(FileExistsError):
        campaign.run_registered_chain(result["chain_plans"][0])


def test_failed_second_fit_preserves_first_weights_and_attempt_counts(tmp_path, monkeypatch):
    result = prepared(tmp_path, monkeypatch)
    def fit(*args, **kwargs):
        if kwargs["architecture"] == "small_mlp":
            raise ValueError("fixture second fit failure")
        return mock_fit(*args, **kwargs)
    monkeypatch.setattr(ranker, "fit_ranker", fit)
    receipt = campaign.read_bound(campaign.run_registered_chain(result["chain_plans"][0]))
    assert receipt["status"] == "failed"
    assert receipt["fit_calls_started"] == 2 and receipt["fit_calls_completed"] == 1
    assert len(receipt["models"]) == 1 and Path(receipt["models"][0]["path"]).is_file()
    with pytest.raises(ValueError, match="every_chain_completed"):
        campaign.freeze_all([result["manifest"]], output=tmp_path/"forbidden_partial_manifest.json")


def test_freeze_all_requires_and_binds_all_six_mock_chains(tmp_path, monkeypatch):
    result = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(ranker, "fit_ranker", mock_fit)
    for chain in result["chain_plans"]:
        receipt = campaign.read_bound(campaign.run_registered_chain(chain))
        assert receipt["status"] == "completed_two_fits_and_frozen_dev_selection"
    reference = campaign.freeze_all([result["manifest"]], output=tmp_path/"models.json")
    final = campaign.validate_frozen_manifest(reference, required_domains=["primary_22"])
    assert len(final["models"]) == 6
    assert final["training_job_units"] == 6 and final["primary_fit_calls_completed"] == 12
    assert final["test_opened"] is False and final["protected_takeover_eligible"] is False
    with pytest.raises(ValueError, match="all_required_domains"):
        campaign.validate_frozen_manifest(reference, required_domains=["primary_22", "mixed_18_22_26"])


def test_full_two_domain_test_gate_never_reads_train_dev_or_test_outcomes(tmp_path, monkeypatch):
    manifests = []
    monkeypatch.setattr(ranker, "fit_ranker", mock_fit)
    for domain in campaign.DOMAINS:
        result = prepared(tmp_path/domain, monkeypatch, domain=domain)
        manifests.append(result["manifest"])
        for chain in result["chain_plans"]:
            campaign.run_registered_chain(chain)
    frozen = campaign.freeze_all(manifests, output=tmp_path/"all_models.json")
    original = campaign.read_bound
    def metadata_only(reference):
        assert "datasets" not in Path(reference["path"]).name
        return original(reference)
    monkeypatch.setattr(campaign, "read_bound", metadata_only)
    result = campaign.validate_frozen_manifest(frozen, required_domains=list(campaign.DOMAINS))
    assert len(result["models"]) == 12 and result["primary_fit_calls_completed"] == 24
    entry = result["models"][0]["checkpoint"]
    Path(entry["path"]).write_text("{}", encoding="utf8")
    with pytest.raises(ValueError, match="bound_artifact_bytes"):
        campaign.validate_frozen_manifest(frozen, required_domains=list(campaign.DOMAINS))
