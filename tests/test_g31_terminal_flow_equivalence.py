"""A finite export bridge must preserve all observable execution evidence."""
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_flow_audit as audit


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf8") as stream:
            json.dump(value, stream)
    else:
        path.write_text(json.dumps(value), encoding="utf8")
    return audit.binding(path)


def fixture(directory):
    source = save(directory/"source.json", {"files": {"implementation.py": "same-code"}})
    plan = dict(task_id=directory.name, method="C00", parent={"parent_seed": 2101}, horizon=18000.,
        input={"path": "input.json", "sha256": "same-input"}, binary={"path": "native030.pyd", "sha256": "same-binary"},
        source_bundle=source, controller={"control_period": 60., "command_delay": 2.},
        activation=7200., supply_mode="committed_only", projection_horizon_seconds=600.)
    reference = save(directory/"plan.json", plan)
    worker = dict(scientific_status="closed", process_status="completed", final_physical_time=18000.,
                  cost={"backlog_integral_bag_seconds": 10.})
    save(directory/"worker_report.json", worker)
    save(directory/"receipt.json", dict(plan_sha256=reference["sha256"], process={"exitcode": 0}, worker=worker))
    save(directory/"trajectory.json.gz", dict(scientific_status="closed_finite_horizon", process_status="completed",
        physical_clock=18000., logs_complete=True, system_J=10., rows=[dict(owner_id="A", decision_time=7200.,
            requested_action={"kind": "transfer", "tray_id": "E", "source": 1, "destination": 2})]))
    save(directory/"controller_checkpoint_scope.json", dict(physical_time=18000., native_state_sha256="a"*64))
    save(directory/"terminal_evidence.json.gz", dict(physical_clock=18000.,
        advance=dict(status="reached", horizon_complete=True), jobs=[], trays=[],
                                                   transfers=[], receipts=[], leg_identities=[]))
    save(directory/"observations.json.gz", [{"digest": "same-public-view"}])
    save(directory/"calls.json.gz", [dict(at=7200., kind="transfer", retry=False,
        request={"request_id": "live:A:1", "tray_id": "E"}, reply={"status": "pending"})])
    return directory


def mutate(directory, name, apply):
    path = directory/name
    value = audit.read(path)
    apply(value)
    reference = save(path, value)
    if name == "plan.json":
        receipt = audit.read(directory/"receipt.json")
        receipt["plan_sha256"] = reference["sha256"]
        save(directory/"receipt.json", receipt)
    if name == "worker_report.json":
        receipt = audit.read(directory/"receipt.json")
        receipt["worker"] = value
        save(directory/"receipt.json", receipt)


def test_equal_closed_run_is_only_finite_empirical_bridge_not_source_interchangeability(tmp_path):
    left, right = fixture(tmp_path/"left"), fixture(tmp_path/"right")
    source = save(right/"changed-source.json", {"files": {"implementation.py": "different-code", "extra.py": "new"}})
    mutate(right, "plan.json", lambda p: p.update(source_bundle=source, worker_evidence_contract="new-offline-export"))
    result = audit.baseline_equivalence(left, right)
    assert result["same_finite_run_behavior"] is True
    assert result["sources_interchangeable"] is False
    assert result["failed_equivalence_checks"] == []
    assert result["changed_source_files"] == ["implementation.py"]
    assert result["added_source_files"] == ["extra.py"]


@pytest.mark.parametrize("case", ["observation", "payload", "reply", "time", "retry", "cost", "J",
                                  "action", "jobs", "bin_width", "recompute", "allocator", "mapping", "native_state"])
def test_any_observable_or_policy_contract_difference_fails_even_if_physical_outcomes_match(tmp_path, case):
    left, right = fixture(tmp_path/"left"), fixture(tmp_path/"right")
    changes = {
        "observation": ("observations.json.gz", lambda rows: rows[0].update(digest="different-public-view")),
        "payload": ("calls.json.gz", lambda rows: rows[0]["request"].update(tray_id="another-tray")),
        "reply": ("calls.json.gz", lambda rows: rows[0]["reply"].update(status="rejected")),
        "time": ("calls.json.gz", lambda rows: rows[0].update(at=7201.)),
        "retry": ("calls.json.gz", lambda rows: rows[0].update(retry=True)),
        "cost": ("worker_report.json", lambda report: report["cost"].update(backlog_integral_bag_seconds=11.)),
        "J": ("trajectory.json.gz", lambda trajectory: trajectory.update(system_J=11.)),
        "action": ("trajectory.json.gz", lambda trajectory: trajectory["rows"][0]["requested_action"].update(destination=3)),
        "jobs": ("terminal_evidence.json.gz", lambda terminal: terminal["jobs"].append({"business_bag_id": "extra"})),
        "bin_width": ("plan.json", lambda plan: plan.update(forecast_bin_edges_seconds=list(range(0, 1801, 300)))),
        "recompute": ("plan.json", lambda plan: plan.update(recompute_period_seconds=300.)),
        "allocator": ("plan.json", lambda plan: plan.update(transport_config={"transport_penalty_weight": 99.})),
        "mapping": ("plan.json", lambda plan: plan.update(mapping={"sha256": "changed-mapping"})),
        "native_state": ("controller_checkpoint_scope.json", lambda state: state.update(native_state_sha256="b"*64)),
    }
    mutate(right, *changes[case])
    result = audit.baseline_equivalence(left, right)
    assert result["same_finite_run_behavior"] is False
    assert result["failed_equivalence_checks"]


@pytest.mark.parametrize("case", ["missing_both", "null_both", "wrong_clock_both", "missing_cost_both",
                                  "incomplete_timestamp_both", "invalid_digest_both", "wrong_checkpoint_clock_both"])
def test_equal_missing_or_incomplete_evidence_is_not_equivalence(tmp_path, case):
    left, right = fixture(tmp_path/"left"), fixture(tmp_path/"right")
    for directory in (left, right):
        if case == "missing_cost_both":
            mutate(directory, "worker_report.json", lambda value: value.update(cost={}))
        elif case == "incomplete_timestamp_both":
            mutate(directory, "terminal_evidence.json.gz", lambda value: value["advance"].update(horizon_complete=False))
        elif case == "invalid_digest_both":
            mutate(directory, "controller_checkpoint_scope.json", lambda value: value.update(native_state_sha256=None))
        elif case == "wrong_checkpoint_clock_both":
            mutate(directory, "controller_checkpoint_scope.json", lambda value: value.update(physical_time=9000.))
        elif case == "missing_both":
            mutate(directory, "terminal_evidence.json.gz", lambda value: value.pop("receipts"))
        elif case == "null_both":
            mutate(directory, "terminal_evidence.json.gz", lambda value: value.update(receipts=None))
        else:
            mutate(directory, "terminal_evidence.json.gz", lambda value: value.update(physical_clock=9000.))
    assert audit.baseline_equivalence(left, right)["same_finite_run_behavior"] is False


@pytest.mark.parametrize("case", ["partial_worker", "wrong_worker_clock", "missing_worker", "mismatched_worker", "partial_logs", "partial_trajectory"])
def test_closed_string_cannot_certify_incomplete_or_unbound_run(tmp_path, case):
    left, right = fixture(tmp_path/"left"), fixture(tmp_path/"right")
    if case == "partial_worker":
        mutate(right, "worker_report.json", lambda value: value.update(process_status="timeout"))
    elif case == "wrong_worker_clock":
        mutate(right, "worker_report.json", lambda value: value.update(final_physical_time=9000.))
    elif case == "missing_worker":
        (right/"worker_report.json").unlink()
    elif case == "mismatched_worker":
        save(right/"worker_report.json", {"different": True})
    elif case == "partial_logs":
        mutate(right, "trajectory.json.gz", lambda value: value.update(logs_complete=False))
    else:
        mutate(right, "trajectory.json.gz", lambda value: value.update(process_status="timeout"))
    with pytest.raises(ValueError, match="closed_native|worker_report|closed_trajectory"):
        audit.baseline_equivalence(left, right)
