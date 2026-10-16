"""Interrupted sealed-prefix selection must not promote its unsealed tail."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import resume_sealed_stream as selected


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def case(tmp_path, monkeypatch):
    root, source = tmp_path / "root", tmp_path / "source_campaign"
    root.mkdir(); source.mkdir()
    monkeypatch.setattr(selected, "ROOT", root)
    monkeypatch.setattr(selected.base, "ROOT", root)
    pins = {}
    for name in selected.base.REQUIRED_POLICY:
        p = root / "policy" / name
        p.parent.mkdir(exist_ok=True); p.write_text(name)
        q = source / "source_archive" / "policy" / name
        q.parent.mkdir(parents=True, exist_ok=True); q.write_bytes(p.read_bytes())
        pins[str(Path("policy") / name)] = selected.base.sha(p)
    binary = root / "binary.pyd"; binary.write_bytes(b"non executable test artifact")
    command = ["python", "-m", "test_worker", "--suite", "synthetic", "--horizon", "10",
        "--segment-seconds", "2", "--event-budget", "100", "--max-activations", "100",
        "--activation-shard-budget", "5", "--binary", str(binary)]
    receipt = {"schema": "g31.full_day_sparse_public_pool_worker.v1", "status": "running",
        "source_before": pins, "binary_sha256": selected.base.sha(binary), "command": command}
    state = {"config": {"owners": ["A", "B"]}, "owner_epochs": {"A": 3, "B": 2},
        "native_timestamp_complete": True, "pending_owners": [], "pending_causes": {}, "needs_native_drain": False}
    part = {"status": "reached", "native_state_sha256": "a" * 64, "controller_state": state,
        "control_continuation": {"status": "reached", "requested_horizon": 2., "physical_time": 2.}}
    (source / "segments").mkdir()
    selected.base.streaming.gz(source / "segments/0000.json.gz", part)
    tail = deepcopy(part); tail.pop("native_state_sha256")
    tail["control_continuation"]["physical_time"] = 2.5
    selected.base.streaming.gz(source / "segments/0001.json.gz", tail)
    selected.base.streaming.gz(source / "input.json.gz", {"jobs": [{"business_bag_id": "test"}]})
    heartbeat = {"stage": "segment_saved", "segment": 1, "physical_time": 2.5,
        "owner_activations": 7, "offered_total": 1, "controller_wall_seconds": 3.,
        "diagnostic_export_wall_seconds": .5, "diagnostic_seal_wall_seconds": .3,
        "latest_native_seal": {"shard": 0, "physical_time": 2., "native_state_sha256": "a" * 64}}
    write(source / "receipt.json", receipt); write(source / "heartbeat.json", heartbeat)
    absence = tmp_path / "absence.json"
    write(absence, {"schema": "g31.user_resume_process_observation.v1", "all_original_identities_absent": True,
        "processes": [{"expected": {"CommandLine": f'python --output "{source}" ' + suffix,
            "ProcessId": 10 + index, "ParentProcessId": 9 + index},
            "old_identity_present": False, "observed": None} for index, suffix in enumerate(("", "--worker"))]})
    monkeypatch.setattr(selected.base, "verify_input_provenance", lambda *args: {"verified_test_input": True})
    return source, tmp_path / "cut", absence


def prepared(case):
    source, output, absence = case
    cut = selected.prepare(source, output, absence)
    path = output / "cut_manifest.json"
    return cut, path, selected.base.sha(path)


def test_selects_only_actual_seal_preserves_original_tail_and_all_costs(case):
    source, output, absence = case
    original = {p.name: p.read_bytes() for p in source.glob("*.json")}
    cut, path, digest = prepared(case)
    assert selected.validate(path, digest) == cut
    assert cut["source_cut"] == 0 and cut["physical_time"] == 2.
    assert cut["owner_activations"] == 5 and cut["next_target"] == 4.
    assert cut["prior_costs"]["controller_wall_seconds"] == 3.
    assert cut["excluded_tail_shards"][0]["path"] == "segments/0001.json.gz"
    assert original == {p.name: p.read_bytes() for p in source.glob("*.json")}
    assert selected.read(output / "source_stop_receipt.json")["evidence_kind"].endswith("exit_reason_unknown")


@pytest.mark.parametrize("key,value", [("physical_time", 2.5), ("owner_activations", 7),
    ("known_native_seal", "b" * 64), ("next_target", 6.), ("max_activations", 101),
    ("source_cut", 1), ("prior_costs", {"controller_wall_seconds": 0.})])
def test_rehashing_manifest_cannot_promote_tail_change_budget_or_drop_cost(case, key, value):
    cut, path, _ = prepared(case)
    cut[key] = value; write(path, cut)
    with pytest.raises(ValueError):
        selected.validate(path, selected.base.sha(path))


def test_even_excluded_tail_bytes_are_preserved_and_pinned(case):
    cut, path, digest = prepared(case)
    (case[0] / "segments/0001.json.gz").write_bytes(b"changed excluded evidence")
    with pytest.raises(ValueError, match="source_prefix_or_tail_changed"):
        selected.validate(path, digest)


@pytest.mark.parametrize("fault", ["present", "only_worker", "same_basename_other_path", "wrong_parent",
    "unsealed", "wrong_seal", "wrong_clock", "missing_prefix"])
def test_invalid_source_rejected_before_output_or_native_session(case, fault):
    source, output, absence = case
    if fault in ("present", "only_worker", "same_basename_other_path", "wrong_parent"):
        data = selected.read(absence)
        if fault == "present": data["processes"][0]["old_identity_present"] = True
        elif fault == "only_worker": data["processes"] = data["processes"][1:]
        elif fault == "wrong_parent": data["processes"][1]["expected"]["ParentProcessId"] = 99
        else:
            for row in data["processes"]:
                row["expected"]["CommandLine"] = row["expected"]["CommandLine"].replace(str(source), str(source.parent / "other" / source.name))
        write(absence, data)
    elif fault == "missing_prefix": (source / "segments/0000.json.gz").unlink()
    else:
        part = selected.base.read_gz(source / "segments/0000.json.gz")
        if fault == "unsealed": part.pop("native_state_sha256")
        elif fault == "wrong_seal": part["native_state_sha256"] = "b" * 64
        else: part["control_continuation"]["physical_time"] = 2.1
        selected.base.streaming.gz(source / "segments/0000.json.gz", part)
    with pytest.raises((ValueError, FileNotFoundError)):
        selected.prepare(source, output, absence)
    assert not output.exists()


def test_adapter_is_process_local_and_restored_after_exception():
    original = selected.base.validate_cut
    original_reconstruct = selected.base.reconstruct
    with pytest.raises(RuntimeError):
        with selected.selected_validator():
            assert selected.base.validate_cut is selected.validate
            with pytest.raises(ValueError, match="foreign_cut_validator"):
                with selected.selected_validator(): pass
            raise RuntimeError("stop")
    assert selected.base.validate_cut is original
    assert selected.base.reconstruct is original_reconstruct
