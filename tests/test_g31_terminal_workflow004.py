"""The finite driver must fail closed before dispatching any native work."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("terminal_workflow004", Path(__file__).resolve().parents[1]
    / "outputs/terminal_flow_workflow004.py")
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


def save(path, value, *, size=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf8") as stream:
            json.dump(value, stream)
    else:
        path.write_text(json.dumps(value), encoding="utf8")
    result = workflow.bound(path)
    if size:
        result["bytes"] = path.stat().st_size
    return result


@pytest.fixture
def environment(tmp_path, monkeypatch):
    current = tmp_path/"current"
    cycle = tmp_path/"cycle"
    current.mkdir()
    cycle.mkdir()
    monkeypatch.setattr(workflow, "ROOT", current)
    monkeypatch.setattr(workflow.campaign, "CYCLE", cycle)
    monkeypatch.setattr(workflow.flow, "ROOT", cycle/"terminal_flow")
    limits = dict(native_start_limit=160, allocations={"bridge": 20, "development": 24, "initial": 24},
                  active_seconds_limit=172800., new_evidence_bytes_limit=40*1024**3,
                  free_space_floor_bytes=30*1024**3)
    calibration = dict(hard_seconds=2400., estimated_evidence_bytes=512*1024**2)
    state = dict(native_starts=0, by_batch={"bridge": 0, "development": 0, "initial": 0},
                 active_seconds=0., open_runners=[], unfinished_native_tasks=[], evidence_bytes=0,
                 free_bytes=100*1024**3)
    budget_ref = save(cycle/"campaign_budget.json", limits)
    calibration_ref = save(cycle/"runtime_calibration_001.json", calibration)
    monkeypatch.setattr(workflow.budget, "status", lambda _: copy.deepcopy(state))
    stages = [dict(name="run_"+phase, phase=phase,
                   parents=[2101] if phase == "export_gate" else [2101, 2102] if phase == "train_demand"
                   else [2201,2202,2203,2204])
              for phase in ("export_gate", "train_demand", "bridge", "bins", "period", "predictor")]
    supplemental = current/"outputs/experiments/g31_ics_terminal_flow_20261021"
    supplemental.mkdir(parents=True)
    registration = dict(stages=stages, export_equivalence_references={"C00": "C00", "TF-B1-300": "TF-B1-300"},
        model_output=str(supplemental/"new-model"), supplemental_evidence_root=str(supplemental), fit_active_seconds_allowance=300.,
        fit_estimated_evidence_bytes=256*1024**2, campaign_budget=budget_ref,
        runtime_calibration=calibration_ref)
    monkeypatch.setattr(workflow, "closed_run", lambda method: (dict(method=method, horizon=18000.,
        parent=dict(parent_seed=2101, split="train")), None, None))
    return dict(current=current, cycle=cycle, registration=registration, state=state, limits=limits,
                calibration=calibration)


def test_registration_accepts_only_fixed_six_stage_roster(environment):
    workflow.validate_registration(environment["registration"])


@pytest.mark.parametrize("case", ["empty_export_refs", "one_export_ref", "other_export_ref", "TEST_parent",
    "missing_stage", "reordered_stage", "repeated_name", "traversal_name", "absolute_name", "zero_fit_time",
    "nan_fit_time", "bool_fit_time", "zero_fit_bytes", "float_fit_bytes", "changed_budget", "changed_calibration"])
def test_registration_rejects_missing_gate_or_drift_before_dispatch(environment, case):
    value = environment["registration"]
    if case == "empty_export_refs":
        value["export_equivalence_references"] = {}
    elif case == "one_export_ref":
        value["export_equivalence_references"].pop("C00")
    elif case == "other_export_ref":
        value["export_equivalence_references"]["C10"] = "C10"
    elif case == "TEST_parent":
        value["stages"][2]["parents"] = [2301]
    elif case == "missing_stage":
        value["stages"].pop()
    elif case == "reordered_stage":
        value["stages"][2:4] = list(reversed(value["stages"][2:4]))
    elif case == "repeated_name":
        value["stages"][1]["name"] = value["stages"][0]["name"]
    elif case == "traversal_name":
        value["stages"][0]["name"] = "../elsewhere"
    elif case == "absolute_name":
        value["stages"][0]["name"] = str(environment["cycle"].resolve())
    elif case in ("zero_fit_time", "nan_fit_time", "bool_fit_time"):
        value["fit_active_seconds_allowance"] = {"zero_fit_time": 0, "nan_fit_time": float("nan"),
                                                 "bool_fit_time": True}[case]
    elif case in ("zero_fit_bytes", "float_fit_bytes"):
        value["fit_estimated_evidence_bytes"] = 0 if case == "zero_fit_bytes" else 1.5
    elif case == "changed_budget":
        save(environment["cycle"]/"campaign_budget.json", {**environment["limits"], "native_start_limit": 999})
    elif case == "changed_calibration":
        save(environment["cycle"]/"runtime_calibration_001.json", {**environment["calibration"], "hard_seconds": 999.})
    with pytest.raises(ValueError):
        workflow.validate_registration(value)


@pytest.mark.parametrize("change", [dict(method="C10"), dict(horizon=59400.),
    dict(parent=dict(parent_seed=2102, split="train")), dict(parent=dict(parent_seed=2101, split="dev"))])
def test_export_equivalence_reference_is_exact_original_short_train_run(environment, monkeypatch, change):
    def wrong(method):
        return {**dict(method=method, horizon=18000., parent=dict(parent_seed=2101, split="train")), **change}, None, None
    monkeypatch.setattr(workflow, "closed_run", wrong)
    with pytest.raises(ValueError, match="registered_export_reference"):
        workflow.validate_registration(environment["registration"])


def test_source_requires_both_current_and_frozen_files_unchanged(environment):
    current = environment["current"]
    frozen = environment["cycle"]/"frozen"
    frozen.mkdir()
    (current/"code.py").write_text("code", encoding="utf8")
    (frozen/"code.py").write_text("code", encoding="utf8")
    files = {"code.py": workflow.campaign.common.sha(current/"code.py")}
    source = save(frozen/"source_manifest.json", dict(schema=workflow.campaign.SCHEMA+".sources",
        worker_evidence_contract=workflow.campaign.EVIDENCE_EXPORT, root=str(frozen), files=files,
        source_manifest_sha256=workflow.campaign.common.digest(files)))
    workflow.validate_source(source)
    (current/"code.py").write_text("edited", encoding="utf8")
    with pytest.raises(ValueError, match="working_or_frozen_source_changed"):
        workflow.validate_source(source)
    (current/"code.py").write_text("code", encoding="utf8")
    (frozen/"code.py").write_text("edited", encoding="utf8")
    with pytest.raises(ValueError, match="working_or_frozen_source_changed"):
        workflow.validate_source(source)


def test_source_manifest_cannot_pin_files_outside_root(environment):
    current = environment["current"]
    outside = current.parent/"outside.py"
    outside.write_text("code", encoding="utf8")
    files = {"../outside.py": workflow.campaign.common.sha(outside)}
    source = save(current/"source_manifest.json", dict(schema=workflow.campaign.SCHEMA+".sources",
        worker_evidence_contract=workflow.campaign.EVIDENCE_EXPORT, root=str(current), files=files,
        source_manifest_sha256=workflow.campaign.common.digest(files)))
    with pytest.raises(ValueError, match="source_path_outside_root"):
        workflow.validate_source(source)


def block_fixture(environment, monkeypatch, *, evaluation=None, model=None):
    entry = environment["registration"]["stages"][0]
    source = dict(path="source", sha256="fixed")
    block = dict(phase=entry["phase"], parents=entry["parents"], source_bundle=source, batch="bridge",
                 demand_model=workflow.model_reference(model), task_plans=[])
    save(workflow.flow.ROOT/entry["name"]/"block.json", block)
    calls = []
    monkeypatch.setattr(workflow, "validate_source", lambda _: {})
    monkeypatch.setattr(workflow.flow, "_validate_block_manifest", lambda _: calls.append("manifest"))
    monkeypatch.setattr(workflow.flow, "_validate_dependencies", lambda _: calls.append("dependencies"))
    result = evaluation or dict(runs=[dict(status="closed", closure_verified=True)], all_registered_closed=True)
    monkeypatch.setattr(workflow.flow, "evaluate", lambda _: result)
    monkeypatch.setattr(workflow.flow, "run_block", lambda _: pytest.fail("closed or invalid task must not dispatch"))
    return entry, source, block, calls


def test_closed_block_resume_revalidates_contract_and_dependencies_without_relaunch(environment, monkeypatch):
    entry, source, block, calls = block_fixture(environment, monkeypatch)
    assert workflow.run_registered_block(entry, source) == block
    assert calls == ["manifest", "dependencies"]


@pytest.mark.parametrize("status", ["hard_timeout", "partial", "closed", "exception"])
def test_existing_nonclosed_or_invalid_closed_receipt_stops_without_relaunch(environment, monkeypatch, status):
    entry, source, _, _ = block_fixture(environment, monkeypatch,
        evaluation=dict(runs=[dict(status=status, closure_verified=False)], all_registered_closed=False))
    with pytest.raises(ValueError, match="existing_nonclosed_run_requires_explicit_audit"):
        workflow.run_registered_block(entry, source)


def test_block_cannot_resume_with_foreign_model_but_ignores_size_metadata(environment, monkeypatch):
    model = dict(path=str(environment["cycle"]/"model.json"), sha256="model", bytes=123)
    entry, source, block, _ = block_fixture(environment, monkeypatch, model=model)
    assert workflow.run_registered_block(entry, source, model) == block
    with pytest.raises(ValueError, match="existing_block_registration_differs"):
        workflow.run_registered_block(entry, source, {**model, "sha256": "foreign-model"})


def test_whole_workflow_reserves_exact_32_native_tasks_without_TEST(environment):
    result = workflow.preflight_budget(environment["registration"], {}, environment["cycle"], {})
    assert result == dict(remaining_native_starts=32,
        remaining_by_batch=dict(bridge=2, initial=10, development=20),
        reserved_active_seconds=2*720.+30*2400.+300.,
        reserved_evidence_bytes=2*128*1024**2+30*512*1024**2+256*1024**2,
        supplemental_existing_evidence_bytes=0)


@pytest.mark.parametrize("case, reason", [
    ("native", "whole_workflow_native_budget"), ("batch", "whole_workflow_batch_budget"),
    ("time", "whole_workflow_active_time_budget"), ("evidence", "whole_workflow_disk_budget"),
    ("free", "whole_workflow_disk_budget"), ("runner", "active_or_unresolved_work"),
    ("unfinished", "active_or_unresolved_work"), ("orphan_fit", "unclosed_fit_requires_explicit_audit")])
def test_whole_workflow_fails_before_first_launch_when_remaining_budget_is_insufficient(environment, case, reason):
    state = environment["state"]
    if case == "native": state["native_starts"] = 129
    elif case == "batch": state["by_batch"]["development"] = 5
    elif case == "time": state["active_seconds"] = 172800.-73740.+1.
    elif case == "evidence": state["evidence_bytes"] = 39*1024**3
    elif case == "free": state["free_bytes"] = 35*1024**3
    elif case == "runner": state["open_runners"] = ["another-runner"]
    elif case == "unfinished": state["unfinished_native_tasks"] = ["previous-attempt"]
    elif case == "orphan_fit": Path(environment["registration"]["model_output"]).mkdir()
    with pytest.raises(ValueError, match=reason):
        workflow.preflight_budget(environment["registration"], {}, environment["cycle"], {})


def test_resume_reserves_only_unstarted_native_tasks(environment, monkeypatch):
    entry = environment["registration"]["stages"][0]
    plans = [save(environment["cycle"]/str(index)/"plan.json", dict(task_id=str(index),
        hard_seconds=720., estimated_evidence_bytes=128*1024**2)) for index in range(2)]
    save(workflow.flow.ROOT/entry["name"]/"block.json", {})
    monkeypatch.setattr(workflow, "checked_block", lambda *args, **kwargs: (dict(task_plans=plans),
        dict(runs=[dict(task_id="0", status="closed"), dict(task_id="1", status="not_started")])))
    environment["state"]["native_starts"] = 1
    environment["state"]["by_batch"]["bridge"] = 1
    result = workflow.preflight_budget(environment["registration"], {}, environment["cycle"], {})
    assert result["remaining_native_starts"] == 31
    assert result["remaining_by_batch"] == dict(bridge=1, initial=10, development=20)
    assert result["reserved_active_seconds"] == 73740.-720.


def fit_fixture(environment, monkeypatch):
    model_directory = Path(environment["registration"]["model_output"])
    rows = [dict(window=index) for index in range(580)]
    model = dict(sha256="internal-model-sha", base_calibration=dict(training_labels_sha256=workflow.demand.digest(rows),
        training_row_count=580, bin_edges_seconds=workflow.demand.bin_edges("300"), prior_exposure=8.,
        train_parent_ids=["parent2101", "parent2102"]),
        support_by_station={str(station): [[7200., 59400.]] for station in range(10)})
    source = dict(path="registered-source", sha256="source-sha")
    mapping = dict(path="mapping", sha256="mapping-sha")
    sources, plans = [], []
    for parent in (2101, 2102):
        directory = environment["cycle"]/str(parent)
        plan = dict(parent=dict(parent_seed=parent, parent_group="parent"+str(parent), split="train"),
                    source_bundle=source, mapping=mapping)
        plan_ref = save(directory/"plan.json", plan)
        plans.append(plan_ref)
        provenance = {"plan.json": plan_ref}
        for name in ("worker_report.json", "receipt.json", "terminal_evidence.json.gz", "decisions.json.gz"):
            provenance["decision_stream" if name == "decisions.json.gz" else name] = save(directory/name, {}, size=True)
        sources.append(dict(parent=plan["parent"], source_bundle=source, mapping=mapping, provenance=provenance))
    files, producers = {}, {}
    for name in workflow.PRODUCER_FILES:
        relative = "scripts/experiments/g31_ics_circulation/"+name
        path = environment["current"]/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("frozen producer", encoding="utf8")
        producers[name] = workflow.bound(path)
        files[relative] = producers[name]["sha256"]
    provenance = dict(schema=workflow.TRAINING_SCHEMA, row_count=580, training_labels_sha256=workflow.demand.digest(rows),
        model_sha256=model["sha256"], DEV_or_TEST_labels_read=False, native_starts=0, sources=sources,
        source_files=producers, producer_sources_unchanged=True, common_time_support=[7200., 59400.],
        forecast_bin_seconds=300., forecast_horizon_seconds=1800., prior_exposure=8.)
    fit = dict(schema=workflow.TRAINING_SCHEMA, row_count=580, native_starts=0, model_sha256=model["sha256"],
        model=save(model_directory/"model.json", model, size=True),
        training_rows=save(model_directory/"training_rows.json.gz", rows, size=True),
        provenance=save(model_directory/"provenance.json", provenance, size=True))
    monkeypatch.setattr(workflow.supported, "validate_model", lambda _: None)
    return dict(fit=fit, training=dict(task_plans=plans), source=source, manifest=dict(files=files),
                model_directory=model_directory)


def test_fit_resume_reads_gzip_and_binds_exact_training_and_producer_sources(environment, monkeypatch):
    values = fit_fixture(environment, monkeypatch)
    assert workflow.validate_fit(**values) == values["fit"]


@pytest.mark.parametrize("case", ["changed_rows_file", "rows_digest", "foreign_model_labels", "foreign_training_plan",
    "duplicate_training_source", "foreign_source_bundle", "changed_receipt", "foreign_evidence_path",
    "changed_producer", "foreign_producer_binding", "omitted_producer", "short_support", "foreign_model_parents",
    "DEV_labels", "foreign_model_directory"])
def test_fit_resume_rejects_foreign_or_changed_training_evidence(environment, monkeypatch, case):
    values = fit_fixture(environment, monkeypatch)
    fit = values["fit"]
    provenance = workflow.read_artifact(fit["provenance"])
    model = workflow.read_artifact(fit["model"])
    if case == "changed_rows_file":
        save(Path(fit["training_rows"]["path"]), [])
    elif case == "rows_digest":
        fit["training_rows"] = save(Path(fit["training_rows"]["path"]), [dict(window="wrong")]*580)
    elif case == "foreign_model_labels":
        model["base_calibration"]["training_labels_sha256"] = "foreign-labels"
    elif case == "foreign_training_plan":
        values["training"]["task_plans"][0] = save(environment["cycle"]/"other-plan.json", {})
    elif case == "duplicate_training_source":
        provenance["sources"][1] = copy.deepcopy(provenance["sources"][0])
    elif case == "foreign_source_bundle":
        provenance["sources"][0]["source_bundle"] = dict(path="foreign", sha256="foreign")
    elif case == "changed_receipt":
        save(Path(provenance["sources"][0]["provenance"]["receipt.json"]["path"]), {"edited": True})
    elif case == "foreign_evidence_path":
        provenance["sources"][0]["provenance"]["decision_stream"] = save(environment["cycle"]/"foreign.json.gz", {})
    elif case == "changed_producer":
        Path(next(iter(provenance["source_files"].values()))["path"]).write_text("edited", encoding="utf8")
    elif case == "foreign_producer_binding":
        next(iter(provenance["source_files"].values()))["sha256"] = "foreign-sha"
    elif case == "omitted_producer":
        provenance["source_files"].pop(next(iter(provenance["source_files"])))
    elif case == "short_support":
        model["support_by_station"]["0"] = [[7200., 18000.]]
    elif case == "foreign_model_parents":
        model["base_calibration"]["train_parent_ids"] = ["parent2101", "parent2103"]
    elif case == "DEV_labels":
        provenance["DEV_or_TEST_labels_read"] = True
    elif case == "foreign_model_directory":
        fit["model"] = save(environment["cycle"]/"foreign-model.json", model)
    if case != "foreign_model_directory":
        fit["model"] = save(Path(fit["model"]["path"]), model, size=True)
    fit["provenance"] = save(Path(fit["provenance"]["path"]), provenance, size=True)
    with pytest.raises(ValueError):
        workflow.validate_fit(**values)


def test_fit_receipt_without_registered_training_block_stops_preflight(environment):
    save(environment["cycle"]/"training_fit_receipt.json", {})
    with pytest.raises(ValueError, match="fit_without_registered_training_block"):
        workflow.preflight_budget(environment["registration"], {}, environment["cycle"], {})


def test_supplemental_reports_are_accounted_once_even_when_model_is_inside(environment):
    root = Path(environment["registration"]["supplemental_evidence_root"])
    (root/"report.txt").write_bytes(b"report")
    # A previous failed/complete report directory, distinct from the future fit output.
    (root/"old-model").mkdir()
    (root/"old-model"/"artifact.txt").write_bytes(b"artifact")
    result = workflow.preflight_budget(environment["registration"], {}, environment["cycle"], {})
    assert result["supplemental_existing_evidence_bytes"] == 14
    environment["state"]["evidence_bytes"] = (environment["limits"]["new_evidence_bytes_limit"]
        - result["reserved_evidence_bytes"] - 14)
    with pytest.raises(ValueError, match="whole_workflow_disk_budget"):
        workflow.preflight_budget(environment["registration"], {}, environment["cycle"], {})


@pytest.mark.parametrize("case", ["different_root", "unaccounted_model", "root_is_model"])
def test_supplemental_accounting_paths_cannot_be_moved_outside_fixed_scope(environment, case):
    registration = environment["registration"]
    if case == "different_root":
        registration["supplemental_evidence_root"] = str(environment["cycle"])
    elif case == "unaccounted_model":
        registration["model_output"] = str(environment["cycle"].parent/"unaccounted-model")
    else:
        registration["model_output"] = registration["supplemental_evidence_root"]
    with pytest.raises(ValueError):
        workflow.validate_registration(registration)


def main_fixture(environment, monkeypatch, *, equivalent=True, fit_fails=False):
    registration = environment["registration"]
    registration.update(schema="g31.terminal_flow.finite_development_workflow.v1",
        source_bundle=dict(path="registered-source", sha256="source"), driver=workflow.bound(workflow.__file__))
    registration_path = environment["cycle"]/"workflow"/"registration.json"
    save(registration_path, registration)
    events = []
    monkeypatch.setattr(workflow.sys, "argv", [workflow.__file__, str(registration_path)])
    monkeypatch.setattr(workflow, "validate_source", lambda _: {})
    monkeypatch.setattr(workflow, "validate_registration", lambda _: events.append("registration_checked"))
    monkeypatch.setattr(workflow, "preflight_budget", lambda *args: events.append("budget_checked") or {})
    monkeypatch.setattr(workflow.budget, "append", lambda _, event, **kwargs: events.append(event))
    monkeypatch.setattr(workflow, "baseline_equivalence", lambda *args: dict(same_finite_run_behavior=equivalent))
    monkeypatch.setattr(workflow, "validate_fit", lambda fit, *args: fit)
    monkeypatch.setattr(workflow.flow, "evaluate", lambda _: dict(all_registered_closed=True))

    def block(entry, source, model=None):
        events.append("stage:"+entry["phase"])
        if entry["phase"] == "predictor":
            assert model["sha256"] == "fitted-model"
        else:
            assert model is None
        methods = ["C00", "TF-B1-300"] if entry["phase"] == "export_gate" else [entry["phase"]]
        plans = [save(environment["cycle"]/"runs"/(entry["phase"]+method)/"plan.json", dict(method=method))
                 for method in methods]
        value = dict(task_plans=plans)
        save(workflow.flow.ROOT/entry["name"]/"block.json", value)
        return value

    def fit(directories, destination):
        events.append("fit")
        if fit_fails:
            raise ValueError("simulated fit failure")
        assert len(directories) == 1  # Mock training block; real count is checked by full-training producer.
        return dict(row_count=580, model=dict(path=str(destination/"model.json"), sha256="fitted-model", bytes=100))

    monkeypatch.setattr(workflow, "run_registered_block", block)
    monkeypatch.setattr(workflow, "run_training", fit)
    return events, registration_path


def test_main_executes_only_fixed_stages_and_accounts_fit_interval_then_reuses_receipt(environment, monkeypatch):
    events, registration_path = main_fixture(environment, monkeypatch)
    workflow.main()
    assert [event for event in events if event.startswith("stage:")] == ["stage:"+entry["phase"]
        for entry in environment["registration"]["stages"]]
    assert events.index("runner_open") < events.index("fit") < events.index("runner_close") < events.index("stage:bridge")
    assert events.count("budget_checked") == 7  # Initial, post-gate, pre-fit, then every four DEV stages.
    result = workflow.flow.read(registration_path.parent/"completion.json")
    assert result["TEST_unlocked"] is False and result["R1_enabled"] is False
    assert result["scientific_service_audit_and_claim_review_required"] is True
    events.clear()
    workflow.main()
    assert "fit" not in events and "runner_open" not in events


def test_main_export_equivalence_failure_prevents_training_and_every_later_stage(environment, monkeypatch):
    events, _ = main_fixture(environment, monkeypatch, equivalent=False)
    with pytest.raises(ValueError, match="export_equivalence_failed"):
        workflow.main()
    assert [event for event in events if event.startswith("stage:")] == ["stage:export_gate"]
    assert "fit" not in events and "runner_open" not in events


def test_main_fit_failure_closes_owned_time_interval_and_never_dispatches_development(environment, monkeypatch):
    events, registration = main_fixture(environment, monkeypatch, fit_fails=True)
    with pytest.raises(ValueError, match="simulated fit failure"):
        workflow.main()
    assert events[-1] == "runner_close"
    assert "stage:bridge" not in events and not (registration.parent/"training_fit_receipt.json").exists()
