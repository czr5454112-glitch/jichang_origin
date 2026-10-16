"""Pure wrapper/evidence guards; test doubles never certify native behavior."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import run_original_notification_probe as campaign
from scripts.experiments.g31_ics_circulation import verify_original_notification_probe as verifier
from scripts.experiments.g31_ics_circulation import original_notification_probe as engine
from scripts.experiments.g31_ics_circulation import replay_original_notification_probe as replay
from scripts.experiments.g31_ics_circulation.original_notification_contract import contract


def test_native_advance_measurement_is_retained_but_not_semantic_parity():
    plain = [{"ordinal": 1, "endpoint": "advance_to", "args": [2.], "kwargs": {},
        "physical_before": 1., "physical_after": 2., "start_ns": 10, "end_ns": 20,
        "result": {"wall_seconds": .001, "physical_time": 2., "processed_events": 1,
            "status": "reached", "horizon_complete": True}}]
    before = deepcopy(plain); timed = deepcopy(plain)
    timed[0].update(start_ns=30, end_ns=50); timed[0]["result"]["wall_seconds"] = .002
    assert verifier.semantic_service_tape(plain) == verifier.semantic_service_tape(timed)
    assert plain == before and timed[0]["result"]["wall_seconds"] == .002
    for key, value in (("physical_time", 3.), ("processed_events", 2),
                       ("status", "budget_exhausted"), ("horizon_complete", False)):
        altered = deepcopy(timed); altered[0]["result"][key] = value
        assert verifier.semantic_service_tape(plain) != verifier.semantic_service_tape(altered)
    other = deepcopy(plain); other[0]["endpoint"] = "observe_protocol"
    assert "wall_seconds" in verifier.semantic_service_tape(other)[0]["result"]


@pytest.mark.parametrize("duration", [-1., float("nan"), float("inf"), True, "0.001"])
def test_invalid_native_advance_clock_is_not_ignored(duration):
    with pytest.raises((ValueError, TypeError)):
        verifier.semantic_service_tape([{"endpoint": "advance_to", "result": {"wall_seconds": duration}}])


def test_missing_native_advance_clock_fails_closed():
    with pytest.raises(KeyError):
        verifier.semantic_service_tape([{"endpoint": "advance_to", "result": {"physical_time": 2.}}])


def test_source_graph_includes_src_layout_and_preserves_duplicate_basenames():
    paths = campaign.source_paths()
    assert campaign.ROOT/"src/czr005/__init__.py" in paths
    assert campaign.ROOT/"src/czr005/cpp_backend.py" in paths
    assert len([p for p in paths if p.name == "__init__.py"]) > 1
    assert len(paths) == len(set(p.relative_to(campaign.ROOT).as_posix() for p in paths))


def test_fresh_worker_import_closure_is_fully_inventoried_without_native():
    code = "from scripts.experiments.g31_ics_circulation import run_original_notification_probe as c; assert not c.unarchived_loaded_sources({'source_sha256':{str(p):'' for p in c.source_paths()}})"
    result = subprocess.run([sys.executable, "-c", code], cwd=campaign.ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_unknown_project_module_is_not_silently_accepted(monkeypatch, tmp_path):
    module = ModuleType("czr005.unpinned_fixture"); module.__file__ = str(tmp_path/"unpinned.py")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    missing = campaign.unarchived_loaded_sources({"source_sha256": {str(p): "" for p in campaign.source_paths()}})
    assert str(Path(module.__file__).resolve()) in missing


@pytest.mark.parametrize("outcome,expected", [(2, "process_exited"), ("timeout", "hard_timeout"), ("launch", "unknown_launch_failure")])
def test_failed_process_is_persisted_without_success_or_denominator_loss(tmp_path, outcome, expected):
    campaign.write(tmp_path/"plan.json", {"process_timeout_seconds": 1})
    def runner(command, **kwargs):
        if outcome == "timeout": raise subprocess.TimeoutExpired(command, 1)
        if outcome == "launch": raise OSError("fixture launch failure")
        return SimpleNamespace(returncode=outcome)
    result = campaign.execute_cell(tmp_path, "withhold_ack", "timed", runner=runner)
    assert result["status"] == expected
    assert result["exit_code"] != 0
    assert campaign.read(tmp_path/"withhold_ack_timed.process.json") == result
    unknown = verifier.verify_or_unknown(tmp_path)
    assert len(unknown["declared_cells"]) == 6 and unknown["source_offered_jobs_per_cell"] == 28506
    assert unknown["original_business_request_100ms_certified"] is False


def test_complete_original_source_rebuild_is_exact_and_keeps_permissions():
    profile = campaign.ROOT/"outputs/experiments/g31_ics_lt2_sustained_20261014/full_stream_native024_001/full1x"
    data, manifest = campaign.rebuild_input({"profile": str(profile)}, "drop_first_ack")
    frozen = campaign.read(profile/"input.json.gz"); frozen["owner_protocol"]["drop_ack_packets"] = 1
    assert replay.canonical(data) == replay.canonical(frozen)
    assert len(data["jobs"]) == manifest["offered_business_count"] == 28506
    assert not any(job.get("allow_suffix_reroute", False) for job in data["jobs"])


class Clock:
    def __init__(self): self.value = 0
    def __call__(self): self.value += 10; return self.value


class Session:
    """Explicit public-output fixture, not a native physical simulation."""
    def __init__(self): self.physical_time = 0.; self.sequence = 0
    def advance_until_owner_notification(self, owners, cursors, horizon, *, max_events):
        self.physical_time += 1; self.sequence += 1
        return {"status": "notified", "timestamp_complete": True, "physical_time": self.physical_time,
            "notifications": {"A": {"sequence": self.sequence, "observed_at": self.physical_time, "change_mask": 1}}}
    def observe_protocol(self, owner):
        return {"schema": "g31.owner_protocol_observation.v1", "owner_id": owner, "now": self.physical_time,
            "jobs": [], "trays": [], "node_contracts": [{"node": 0, "resource_owner": owner}],
            "client_transfer_ledger": [], "delivered_messages": []}
    def advance_to(self, at, *, max_events):
        self.physical_time = at
        return {"status": "reached", "horizon_complete": True, "physical_time": at, "wall_seconds": 0.}


def no_action(*args): return {"selected": None}


@pytest.fixture
def saved(tmp_path, monkeypatch):
    """Outer saved-file guards, with separate ABI authority/native fixtures.

    The real policy/tape replay is used with an explicit no-action test policy;
    accepted ABI parsing already has its own independent/native test suites.
    """
    source = tmp_path/"driver_fixture.py"; source.write_text("# fixture")
    monkeypatch.setattr(campaign, "ROOT", tmp_path)
    monkeypatch.setattr(campaign, "source_paths", lambda: [source])
    frozen = {"jobs": [{"business_bag_id": str(i)} for i in range(28506)],
        "node_contracts": [{"node": 0, "resource_owner": "A", "zone": "A"}], "owner_protocol": {"drop_ack_packets": 0}}
    profile = tmp_path/"profile"; profile.mkdir()
    campaign.write(profile/"input.json.gz", frozen)
    campaign.write(profile/"input_manifest.json", {"source_sha256": {}})
    (tmp_path/"source").mkdir(); (tmp_path/"source"/source.name).write_bytes(source.read_bytes())
    authority = {"binary": "fixture_native_not_executed", "binary_sha256": "a"*64}
    campaign.write(tmp_path/"accepted_contract.json", authority)
    reference = {"path": str(tmp_path/"accepted_contract.json"), "sha256": campaign.sha(tmp_path/"accepted_contract.json")}
    campaign.write(tmp_path/"accepted_reference.json", reference)
    monkeypatch.setattr(verifier.abi, "verify_contract", lambda *a, **k: {"contract": authority})
    monkeypatch.setattr(verifier.abi, "analyze_native025_timing", lambda *a: {"status": "validated_partial_native025_phase_partition"})
    actual_replay = replay.verify_raw
    monkeypatch.setattr(replay, "verify_raw", lambda *a, **k: actual_replay(*a, **k, proposal=no_action))
    plan = {"contract": contract(), "cases": campaign.CASES, "arms": list(campaign.ARMS), "profile": str(profile),
        "source_sha256": {str(source): campaign.sha(source)},
        "input_source_sha256": {str(profile/name): campaign.sha(profile/name) for name in ("input.json.gz", "input_manifest.json")},
        "contract_reference": reference, "accepted_reference_sha256": campaign.sha(tmp_path/"accepted_reference.json"),
        "accepted_contract_sha256": reference["sha256"], **authority}
    campaign.write(tmp_path/"plan.json", plan)
    receipt = {"source_changed": [], "plan_sha256": campaign.sha(tmp_path/"plan.json"), "declared_cells": [], "process_sha256": {}, "completion_sha256": {}}
    for case in campaign.CASES:
        for arm in campaign.ARMS:
            key = case+"/"+arm; cell = tmp_path/key; cell.mkdir(parents=True)
            refs = []
            def sink(chunk):
                path = cell/("tape_%04d.json.gz" % chunk["index"]); campaign.write(path, chunk)
                ref = {"path": path.name, "sha256": campaign.sha(path), "index": chunk["index"]}; refs.append(ref); return ref
            raw = engine.run_cohort(Session(), ["A"], clock=Clock(), proposal=no_action, chunk_sink=sink)
            data = deepcopy(frozen); data["owner_protocol"]["drop_ack_packets"] = campaign.CASES[case]
            raw.update(mandatory_setup_start_ns=0, capture_setup={"start_ns": 0, "end_ns": 0}, owners=["A"],
                input_sha256=campaign.original.json_digest(data), source_offered_jobs=28506, case=case, arm=arm,
                native_binary_sha256="a"*64, native_state_sha256="b"*64, source_changed=[], unarchived_loaded_sources=[])
            if arm == "timed":
                rows = [row for ref in refs for row in campaign.read(cell/ref["path"])["service_tape"]]
                raw["timing"] = {"errors": [], "batches": [], "envelopes": [{"call_ordinal": r["ordinal"], "api_endpoint": r["endpoint"],
                    "start_ns": r["start_ns"], "end_ns": r["end_ns"]} for r in rows]}
            campaign.write(cell/"input.json.gz", data); campaign.write(cell/"raw.json.gz", raw)
            campaign.write(cell/"completion.json", {"status": raw["status"], "source_changed": [], "unarchived_loaded_sources": [],
                "input_sha256": campaign.sha(cell/"input.json.gz"), "raw_sha256": campaign.sha(cell/"raw.json.gz"), "chunks": refs})
            process = tmp_path/(case+"_"+arm+".process.json")
            campaign.write(process, {"status": "process_exited", "exit_code": 0, "wall_seconds": 1.5,
                "command": [sys.executable, "-m", campaign.__name__, "--output", str(tmp_path), "--worker", "--case", case, "--arm", arm]})
            receipt["declared_cells"].append(key); receipt["process_sha256"][key] = campaign.sha(process)
            receipt["completion_sha256"][key] = campaign.sha(cell/"completion.json")
    campaign.write(tmp_path/"receipt.json", receipt)
    return tmp_path


def test_saved_wrapper_checks_every_cell_and_keeps_full_setup_scope(saved):
    result = verifier.verify_saved(saved)
    assert result["cell_count"] == 6 and result["source_offered_jobs_per_cell"] == 28506
    assert not result["unconditional_complete_100ms_certified"]
    assert result["cases"]["baseline"]["timed"]["root_count"] == 12


@pytest.mark.parametrize("mutation", ["wrong_command", "nonzero", "missing_chunk", "bad_seal", "omitted_envelope", "missing_input_pin", "duplicate_cell", "omitted_source", "completion_status"])
def test_saved_campaign_tampering_fails_closed_with_complete_declared_domain(saved, mutation):
    receipt = campaign.read(saved/"receipt.json"); plan = campaign.read(saved/"plan.json")
    key = "baseline/timed"; cell = saved/key; raw = campaign.read(cell/"raw.json.gz")
    completion = campaign.read(cell/"completion.json"); process_path = saved/"baseline_timed.process.json"; process = campaign.read(process_path)
    if mutation == "wrong_command": process["command"][-1] = "plain"
    elif mutation == "nonzero": process["exit_code"] = 2
    elif mutation == "missing_chunk": (cell/completion["chunks"][0]["path"]).unlink()
    elif mutation == "bad_seal": raw["native_state_sha256"] = None
    elif mutation == "omitted_envelope": raw["timing"]["envelopes"].pop()
    elif mutation == "missing_input_pin": plan["input_source_sha256"].pop(next(iter(plan["input_source_sha256"])))
    elif mutation == "duplicate_cell": receipt["declared_cells"].append(key)
    elif mutation == "omitted_source": plan["source_sha256"] = {}
    elif mutation == "completion_status": completion["status"] = "failed"
    campaign.write(cell/"raw.json.gz", raw); completion["raw_sha256"] = campaign.sha(cell/"raw.json.gz")
    campaign.write(cell/"completion.json", completion); receipt["completion_sha256"][key] = campaign.sha(cell/"completion.json")
    campaign.write(process_path, process); receipt["process_sha256"][key] = campaign.sha(process_path)
    campaign.write(saved/"plan.json", plan); receipt["plan_sha256"] = campaign.sha(saved/"plan.json")
    campaign.write(saved/"receipt.json", receipt)
    result = verifier.verify_or_unknown(saved)
    assert result["status"] == "unknown_invalid_or_incomplete_original_notification_campaign"
    assert len(result["declared_cells"]) == 6 and result["source_offered_jobs_per_cell"] == 28506
