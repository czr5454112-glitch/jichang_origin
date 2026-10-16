from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import resume_chained_sealed_stream as chain


def parent(tmp_path, inherited=18.):
    binary = (tmp_path / "native024.pyd").resolve()
    cut = {"schema": chain.prior.SCHEMA, "binary": str(binary), "binary_sha256": "a" * 64,
        "suite": "full2x", "horizon": 86400., "segment_seconds": 3600., "event_budget": 1000000,
        "max_activations": 1000000, "activation_shard_budget": 500,
        "source_cut": 3, "physical_time": 3600., "known_native_seal": "c" * 64,
        "source_reconstruction_wall_seconds": inherited}
    path = tmp_path / "cut.json"; path.write_text(json.dumps(cut))
    digest = chain.base.sha(path)
    receipt = {"schema": "g31.sparse_sealed_resume_worker.v1", "status": "hard_timeout", "exit_code": None,
        "binary_sha256": cut["binary_sha256"], "cut_manifest_sha256": digest,
        "command": ["python", "-m", "original_driver", "--cut-manifest", str(path),
            "--expected-cut-sha256", digest, "--binary", str(binary), "--suite", "full2x",
            "--horizon", "86400", "--event-budget", "1000000", "--worker"]}
    return receipt, cut, path


@pytest.mark.parametrize("schema", sorted(chain.PARENTS))
def test_current_and_future_chain_scope(tmp_path, schema):
    receipt, cut, _ = parent(tmp_path); receipt["schema"] = schema
    scope = chain.source_scope(receipt)
    assert scope == {k: cut[k] for k in scope} and scope["horizon"] == 86400.


@pytest.mark.parametrize("field,value", [("--suite", "full1x"), ("--horizon", "43200"),
    ("--event-budget", "5"), ("--binary", "different.pyd"), ("--expected-cut-sha256", "b" * 64)])
def test_changed_ancestor_identity_rejected(tmp_path, field, value):
    receipt, _, _ = parent(tmp_path)
    receipt["command"][receipt["command"].index(field) + 1] = value
    with pytest.raises(ValueError): chain.ancestor_cut(receipt)


def test_duplicate_arguments_and_mutated_cut_rejected(tmp_path):
    receipt, _, path = parent(tmp_path)
    duplicate = deepcopy(receipt); duplicate["command"] += ["--horizon", "86400"]
    with pytest.raises(ValueError, match="ambiguous_ancestor_argument"): chain.ancestor_cut(duplicate)
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="ancestor_cut_changed"): chain.ancestor_cut(receipt)


def test_unfinished_heartbeat_keeps_all_ancestor_reconstruction_cost(tmp_path):
    receipt, _, _ = parent(tmp_path, inherited=183.3712)
    total, _, inherited = chain.cumulative_reconstruction(receipt, {"reconstruction_wall_seconds": 842.8983})
    assert total == inherited + 842.8983
    assert total > 842.8983
    next_receipt, _, _ = parent(tmp_path, inherited=total)
    assert chain.cumulative_reconstruction(next_receipt, {"reconstruction_wall_seconds": 300.})[0] == total + 300.


@pytest.mark.parametrize("cost", [-1., float("nan"), float("inf")])
def test_invalid_reconstruction_cost_rejected(tmp_path, cost):
    receipt, _, _ = parent(tmp_path)
    with pytest.raises(ValueError): chain.cumulative_reconstruction(receipt, {"reconstruction_wall_seconds": cost})


def test_existing_cumulative_is_not_added_twice(tmp_path):
    receipt, _, _ = parent(tmp_path)
    heartbeat = {"reconstruction_wall_seconds": 5., "cumulative_reconstruction_wall_seconds": 23.}
    assert chain.cumulative_reconstruction(receipt, heartbeat)[0] == 23.
    heartbeat["cumulative_reconstruction_wall_seconds"] = 5.
    with pytest.raises(ValueError): chain.cumulative_reconstruction(receipt, heartbeat)


def observation(tmp_path):
    source = (tmp_path / "exact output").resolve()
    command = f'python -m driver --output "{source}"'
    record = {"schema": chain.ABSENCE_SCHEMA, "observed_utc": "2026-10-15T04:00:00Z",
        "all_original_identities_absent": True, "processes": [
            {"expected": {"ProcessId": 1, "ParentProcessId": 0, "CreationDate": "2026-10-15T01:00:00Z", "CommandLine": command}, "old_identity_present": False, "observed": None},
            {"expected": {"ProcessId": 2, "ParentProcessId": 1, "CreationDate": "2026-10-15T01:00:01Z", "CommandLine": command + " --worker"}, "old_identity_present": False, "observed": None}]}
    source.mkdir()
    (source / "receipt.json").write_text(json.dumps({"schema": chain.SCHEMA,
        "command": ["python", "-m", "driver", "--output", str(source), "--worker"]}))
    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps([r["expected"] for r in record["processes"]]))
    record["prior_identity_reference"] = {"path": str(identities), "sha256": chain.base.sha(identities)}
    return source, record


def test_exact_terminated_parent_worker_absence(tmp_path):
    source, record = observation(tmp_path); path = tmp_path / "absence.json"
    path.write_text(json.dumps(record))
    assert chain.verify_absence(path, chain.base.sha(path), source) == record


@pytest.mark.parametrize("mutation", ["present", "observed", "wrong_parent", "wrong_output", "missing_worker", "wrong_driver", "missing_creation", "wrong_pid"])
def test_inexact_or_present_processes_block_resume(tmp_path, mutation):
    source, record = observation(tmp_path); row = record["processes"][1]
    if mutation == "present": row["old_identity_present"] = True
    elif mutation == "observed": row["observed"] = row["expected"]
    elif mutation == "wrong_parent": row["expected"]["ParentProcessId"] = 9
    elif mutation == "wrong_output": row["expected"]["CommandLine"] = row["expected"]["CommandLine"].replace("exact output", "exact output_extra")
    elif mutation == "wrong_driver": row["expected"]["CommandLine"] = row["expected"]["CommandLine"].replace("-m driver", "-m other")
    elif mutation == "missing_creation": del row["expected"]["CreationDate"]
    elif mutation == "wrong_pid": row["expected"]["ProcessId"] = 99
    else: record["processes"].pop()
    path = tmp_path / "absence.json"; path.write_text(json.dumps(record))
    with pytest.raises(ValueError): chain.verify_absence(path, chain.base.sha(path), source)


def test_adapters_restore_even_on_failure():
    before = chain.prior.source_scope, chain.prior.selected_metadata, chain.prior.verify_absence
    with pytest.raises(RuntimeError):
        with chain.chained_adapters():
            assert chain.prior.source_scope is chain.source_scope
            raise RuntimeError("intentional")
    assert before == (chain.prior.source_scope, chain.prior.selected_metadata, chain.prior.verify_absence)


def test_before_first_new_seal_uses_ancestor_without_mutating_heartbeat(tmp_path, monkeypatch):
    receipt, ancestor, _ = parent(tmp_path)
    heartbeat = {"latest_native_seal": None, "segment": 5, "physical_time": 3900., "reconstruction_wall_seconds": 5.}
    before = deepcopy(heartbeat)
    def fake_metadata(source, record, selected):
        assert selected["latest_native_seal"] == {"shard": 3, "physical_time": 3600., "native_state_sha256": "c" * 64}
        assert selected["segment"] == 5
        return {"source_cut": 3}
    monkeypatch.setattr(chain, "_selected_metadata", fake_metadata)
    value = chain.selected_metadata(tmp_path, receipt, heartbeat)
    assert value["selected_seal_origin"] == "ancestor_known_seal" and value["source_reconstruction_wall_seconds"] == 23.
    assert heartbeat == before


def test_tampered_ancestor_seal_blocks_fallback(tmp_path):
    receipt, ancestor, path = parent(tmp_path); ancestor["known_native_seal"] = "d" * 64
    path.write_text(json.dumps(ancestor))
    with pytest.raises(ValueError, match="ancestor_cut_changed"):
        chain.selected_metadata(tmp_path, receipt, {"latest_native_seal": None})


@pytest.mark.parametrize("status", ["running", "completed", "invalidated_source_changed"])
def test_cannot_prepare_from_active_or_successful_attempt(tmp_path, status):
    source = tmp_path / "source"; source.mkdir()
    (source / "receipt.json").write_text(json.dumps({"schema": chain.SCHEMA, "status": status}))
    with pytest.raises(ValueError, match="not_terminated_chained_source"):
        chain.prepare(source, tmp_path / "new", tmp_path / "missing_absence.json")
    assert not (tmp_path / "new").exists()
