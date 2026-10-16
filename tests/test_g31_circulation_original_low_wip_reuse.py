from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import subprocess
import pytest

from scripts.experiments.g31_ics_circulation import research_original_low_wip_reuse as m


@lru_cache(maxsize=1)
def saved005():
    directory = m.OUT / "original_low_wip_prepare_005"
    assert m.base.sha(directory / "raw_final.json.gz") == "8d6e8ee81ac6961a32accbe22119c352691a1719fc5a68852a76de52b9255f58"
    return m.base.gzread(directory / "raw_final.json.gz"), m.base.read(directory / "preregistered_protocol.json")


def proof_fixture():
    """Synthetic modifications of a real typed body, never native evidence."""
    raw, plan = saved005()
    source = next(o for o in raw["owners"] if o["supply"])
    owner = source["owner"]
    peer = next(o for o in plan["parking_plan"]["owners"] if o != owner)
    supply = deepcopy(source["supply"])
    snapshots = [(key, row) for key, row in source["outbox"]["outbox"].items() if row["kind"] == "planning_snapshot_v2"]
    key, row = deepcopy(snapshots[-1])
    ack = row["client_view"]["last_delivered_ack"]
    env = ack["planning_snapshot_v2"]
    body = env["capture"]; local = body["local_capture"]; extension = body["extension"]
    local["captured_at"] = 20000.; local["valid_until"] = 20120.
    extension["captured_at"] = 20000.
    for scope in ("completion_coverage", "action_coverage"): extension[scope]["through"] = 20000.
    env["delivered_at"] = 20002.
    ack.update(executed_at=20000., completed_at=20002., delivered_at=20002.2)
    job = supply["choice"]["job"]
    receipt = {"receipt_id": f"completion:{len(owner.encode('utf8'))}:{owner}:1", "source_local_sequence": 1,
        "source_owner": owner, "event": "UNLOAD_COMPLETE", "status": "completed", "business_bag_id": job["business_bag_id"],
        "tray_id": plan["parking_plan"]["token_tray_id"], "destination": job["destination"], "completed_at": 19772.591999999997}
    extension["terminal_receipts"] = [receipt]
    extension["completion_coverage"]["completed_business_bag_ids"] = [job["business_bag_id"]]
    env["payload_sha256"] = m.base.capture_digest_v2(body)
    token = deepcopy(next(t for t in raw["result"]["trays"] if t["tray_id"] == plan["parking_plan"]["token_tray_id"]))
    token["business_bag_id"] = ""
    view = {**deepcopy(plan["public_contract"]), "owner_id": owner, "now": 20010., "trays": [token]}
    outbox = {supply["request_id"]: deepcopy(source["outbox"]["outbox"][supply["request_id"]]), key: row}
    return supply, outbox, view, owner, peer, token["tray_id"], key


def proof(args):
    return m.return_proof(*args[:6])


def rehash(args):
    row = args[1][args[-1]]
    env = row["client_view"]["last_delivered_ack"]["planning_snapshot_v2"]
    env["payload_sha256"] = m.base.capture_digest_v2(env["capture"])


def test_own_delivered_completion_and_current_empty_both_required():
    args = proof_fixture(); before = deepcopy(args)
    result = proof(args)
    assert result["terminal_receipt"]["business_bag_id"] == args[0]["choice"]["job"]["business_bag_id"]
    assert result["current_token"]["tray_id"] == args[5] and result["observed_at"] == 20010.
    result["current_token"]["node"] = -999
    assert args == before


@pytest.mark.parametrize("mutation", ["no_first_ack", "no_self_ack", "no_receipt", "loaded", "edge", "reception", "not_available", "foreign_token", "expired"])
def test_missing_or_incomplete_return_stays_unknown(mutation):
    args = proof_fixture(); supply, outbox, view, owner, peer, token, key = args
    row = outbox[key]; ack = row["client_view"]["last_delivered_ack"]; body = ack["planning_snapshot_v2"]["capture"]
    if mutation == "no_first_ack": outbox[supply["request_id"]]["client_view"]["last_delivered_ack"]["status"] = "departed"
    elif mutation == "no_self_ack": ack.pop("planning_snapshot_v2")
    elif mutation == "no_receipt":
        body["extension"]["terminal_receipts"] = []; body["extension"]["completion_coverage"]["completed_business_bag_ids"] = []; rehash(args)
    elif mutation == "loaded": view["trays"][0]["mode"] = "loaded"
    elif mutation == "edge": view["trays"][0]["edge_to"] = 8
    elif mutation == "reception": view["trays"][0]["reception_node"] = 8
    elif mutation == "not_available": view["trays"][0]["available_at"] = view["now"] + 1
    elif mutation == "foreign_token": view["trays"][0]["tray_id"] = "other"
    else: body["local_capture"]["valid_until"] = view["now"]; rehash(args)
    assert proof(args) is None


@pytest.mark.parametrize("mutation", ["future_ack", "result_id", "wrong_source", "other_tray", "other_destination", "wrong_event", "wrong_status", "future_receipt", "digest", "early_empty"])
def test_conflicting_self_copy_fails_closed(mutation):
    args = proof_fixture(); supply, outbox, view, owner, peer, token, key = args
    ack = outbox[key]["client_view"]["last_delivered_ack"]; env = ack["planning_snapshot_v2"]; body = env["capture"]; r = body["extension"]["terminal_receipts"][0]
    if mutation == "future_ack": ack["delivered_at"] = view["now"] + 1
    elif mutation == "result_id": ack["result_id"] = "other"
    elif mutation == "wrong_source": body["local_capture"]["source_owner"] = peer
    elif mutation == "other_tray": r["tray_id"] = "other"
    elif mutation == "other_destination": r["destination"] = 112
    elif mutation == "wrong_event": r["event"] = "LOAD_COMPLETE"
    elif mutation == "wrong_status": r["status"] = "pending"
    elif mutation == "future_receipt": r["completed_at"] = body["local_capture"]["captured_at"] + 1
    elif mutation == "early_empty": view["trays"][0]["available_at"] = r["completed_at"] - 1
    rehash(args)
    if mutation == "digest": env["payload_sha256"] = "wrong"
    with pytest.raises(ValueError): proof(args)


def test_newest_expired_self_copy_prevents_older_resurrection():
    args = proof_fixture(); outbox = args[1]; key = args[-1]
    newer = deepcopy(outbox[key]); new_key = key + ":new"
    newer["payload"]["request_id"] = new_key
    ack = newer["client_view"]["last_delivered_ack"]; env = ack["planning_snapshot_v2"]; local = env["capture"]["local_capture"]
    local["publication_sequence"] += 1; local["valid_until"] = args[2]["now"]
    env["status"] = "expired"; env["payload_sha256"] = m.base.capture_digest_v2(env["capture"])
    outbox[new_key] = newer
    assert proof(args) is None


def test_duplicate_publication_sequence_is_rejected():
    args = proof_fixture(); key = args[-1]; duplicate = deepcopy(args[1][key]); duplicate["payload"]["request_id"] = key + ":duplicate"
    args[1][key + ":duplicate"] = duplicate
    with pytest.raises(ValueError, match="duplicate_self_revision"): proof(args)


def invitation_fixture():
    args = proof_fixture()
    env = deepcopy(args[1][args[-1]]["client_view"]["last_delivered_ack"]["planning_snapshot_v2"])
    body = env["capture"]; local = body["local_capture"]
    local["trays"] = [deepcopy(args[2]["trays"][0])]
    body["extension"]["submitted_physical_actions"] = [{"request_id": m.base.owner_request_id(args[3], "single-supply"),
        "kind": "transfer", "last_delivered_ack": {"status": "received", "delivered_at": 9300.}}]
    nodes = {r["node"]: r for r in args[2]["node_contracts"]}
    return env, args[5], args[3], nodes


def test_peer_reply_requires_actual_return_invitation_not_old_empty_before_supply():
    args = invitation_fixture()
    assert m.returned_invitation(*args)
    args[0]["capture"]["extension"]["terminal_receipts"] = []
    assert not m.returned_invitation(*args)


@pytest.mark.parametrize("mutation", ["loaded", "incoming", "not_available", "no_received", "no_action", "foreign_tray", "foreign_owner", "pre_received", "future_completion"])
def test_reply_invitation_guards(mutation):
    args = invitation_fixture(); body = args[0]["capture"]; local = body["local_capture"]; r = body["extension"]["terminal_receipts"][0]
    if mutation == "loaded": local["trays"][0]["mode"] = "loaded"
    elif mutation == "incoming": local["trays"][0]["reception_node"] = 116
    elif mutation == "not_available": local["trays"][0]["available_at"] = local["captured_at"] + 1
    elif mutation == "no_received": body["extension"]["submitted_physical_actions"][0]["last_delivered_ack"]["status"] = "departed"
    elif mutation == "no_action": body["extension"]["submitted_physical_actions"] = []
    elif mutation == "foreign_tray": r["tray_id"] = "other"
    elif mutation == "foreign_owner": r["source_owner"] = "other"
    elif mutation == "pre_received": r["completed_at"] = 9299.
    else: r["completed_at"] = local["captured_at"] + 1
    assert not m.returned_invitation(*args)


class FakeClient:
    def __init__(self, outbox):
        self.state = {"outbox": deepcopy(outbox)}; self.calls = []; self.refreshed = 0
    def refresh(self, **kwargs): self.refreshed += 1
    def submit(self, owner, kind, payload, *, request_id):
        self.calls.append({"owner": owner, "kind": kind, "payload": deepcopy(payload), "request_id": request_id})


class FakeSession:
    def __init__(self, view): self.view = deepcopy(view); self.physical_time = view["now"]; self.reads = []
    def observe_protocol_control_policy_recent(self, owner, validity):
        self.reads.append(("view", owner)); return {**deepcopy(self.view), "owner_id": owner, "now": self.physical_time}
    def protocol_planning_snapshots_v2(self, owner):
        self.reads.append(("snapshots", owner)); return []


def owner_fixture():
    args = proof_fixture(); _, plan = saved005()
    session = FakeSession(args[2]); owner = m.ReuseOwner(session, args[3], plan["parking_plan"])
    owner.index = len(owner.rows); owner.quiet = True; owner.supply = deepcopy(args[0]); owner.client = FakeClient(args[1])
    return owner, session, args


def test_second_supply_is_once_and_still_refreshes_afterward(monkeypatch):
    owner, session, args = owner_fixture()
    env = {"capture": {"extension": {"submitted_physical_actions": []}}}
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: env)
    monkeypatch.setattr(m, "return_proof", lambda *args: {"proof": "separately tested"})
    next_job = deepcopy(args[0]["choice"]["job"]); next_job["business_bag_id"] = "second"
    monkeypatch.setattr(m.base, "eligible_head", lambda *args: {"job": next_job, "tray": deepcopy(owner.session.view["trays"][0])})
    owner.activate(); count = len(session.reads); owner.activate()
    assert [r["kind"] for r in owner.client.calls] == ["planning_snapshot_v2", "transfer"]
    assert owner.client.calls[-1]["request_id"] == m.base.owner_request_id(owner.owner, "second-supply")
    assert owner.client.calls[-1]["payload"]["message_delay"] == 2.
    assert owner.client.refreshed == 2 and len(session.reads) == count


def test_peer_second_seen_stays_stopped_after_message_expiry(monkeypatch):
    _, plan = saved005(); args = proof_fixture()
    session = FakeSession(args[2]); owner = m.ReuseOwner(session, args[4], plan["parking_plan"])
    owner.index = len(owner.rows); owner.quiet = True; owner.client = FakeClient({})
    env = {"capture": {"extension": {"submitted_physical_actions": [{"request_id": m.base.owner_request_id(owner.peer, "second-supply")}]}}}
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: env)
    owner.activate(); assert owner.second_seen
    reads = len(session.reads); session.physical_time += 1000.
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: None)
    owner.activate()
    assert owner.client.refreshed == 2 and owner.client.calls == [] and len(session.reads) == reads


def test_source_does_not_publish_until_current_token_returned(monkeypatch):
    owner, session, args = owner_fixture(); session.view["trays"] = []
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: None)
    owner.activate()
    assert owner.client.calls == [] and owner.second_supply is None


def test_peer_without_invitation_queries_only_own_received_messages_after_static_read(monkeypatch):
    _, plan = saved005(); args = proof_fixture()
    session = FakeSession(args[2]); owner = m.ReuseOwner(session, args[4], plan["parking_plan"])
    owner.index = len(owner.rows); owner.quiet = True; owner.client = FakeClient({})
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: None)
    owner.activate(); owner.activate()
    assert session.reads == [("view", owner.owner), ("snapshots", owner.owner), ("snapshots", owner.owner)]
    assert owner.client.calls == []


def test_context_restores_every_original_global_after_exception():
    fields = ("Owner", "assess", "source_paths", "verify_pins", "SCHEMA", "HORIZON", "MAX_TICKS", "MAX_PHYSICAL")
    before = {k: getattr(m.base, k) for k in fields}
    with pytest.raises(RuntimeError):
        with m.installed():
            assert m.base.Owner is m.ReuseOwner and m.base.MAX_PHYSICAL == 24
            with pytest.raises(ValueError, match="overlapping_context"):
                with m.installed(): pass
            raise RuntimeError("test")
    assert {k: getattr(m.base, k) for k in fields} == before and not m._installed
    assert m.base.sha(m.base.__file__) == m.BASE_SHA


def test_source_closure_covers_new_module_and_frozen_base_and_loader():
    paths = {p.relative_to(m.ROOT).as_posix() for p in m.source_paths()}
    assert "scripts/experiments/g31_ics_circulation/research_original_low_wip_reuse.py" in paths
    assert "scripts/experiments/g31_ics_circulation/research_original_low_wip.py" in paths
    assert "src/czr005/cpp_backend.py" in paths


def final_fixture():
    supplies = [{"at": t, "choice": {"job": {"business_bag_id": job, "origin": 26, "destination": 116}}}
                for t, job in [(0., "j1"), (5., "j2")]]
    events = [{"event": event, "business_bag_id": job, "tray_id": "token", "time": t,
               "node": 26 if event.startswith("LOAD") else 116}
              for job, times in [("j1", (1., 1., 3., 4.)), ("j2", (6., 6., 8., 9.))]
              for event, t in zip(("LOAD_START", "LOAD_COMPLETE", "UNLOAD_COMPLETE", "HOLD_COMPLETE"), times)]
    raw = {"status": "horizon_complete", "physical_time": m.HORIZON, "physical_audit": {"status": "passed"},
        "owners": [{"index": 22, "supply": supplies[0], "second_supply": supplies[1],
            "outbox": {"outbox": {str(i): {"kind": "transfer", "client_view": {"last_delivered_ack": {"status": "received"}}} for i in range(24)}}}],
        "result": {"advance": {"horizon_complete": True}, "receipts": events,
            "trays": [{"tray_id": "token", "mode": "empty", "job": -1, "edge_to": -1, "available_at": 9.}]}}
    return raw, {"parking_plan": {"token_tray_id": "token"}}


def test_second_witness_requires_full_same_token_lifecycles():
    raw, plan = final_fixture()
    result = m.assess(raw, plan)
    assert result["second_reuse_proved"] and result["actual_supply_count"] == 2
    assert result["strict_protection"] == "not_assessed" and not result["complete_100ms_certified"]


@pytest.mark.parametrize("mutation", ["ack_only", "other_tray", "same_job", "overlap", "no_hold", "wrong_node", "not_drained", "no_final_empty", "third_load", "open_ack", "missing_parking", "failed_audit"])
def test_assessment_negative_cases(mutation):
    raw, plan = final_fixture(); rows = raw["result"]["receipts"]
    if mutation == "ack_only": del rows[4:]
    elif mutation == "other_tray": rows[-1]["tray_id"] = "other"
    elif mutation == "same_job": raw["owners"][0]["second_supply"]["choice"]["job"]["business_bag_id"] = "j1"
    elif mutation == "overlap": raw["owners"][0]["second_supply"]["at"] = 3.
    elif mutation == "no_hold": rows.pop()
    elif mutation == "wrong_node": rows[-1]["node"] = 115
    elif mutation == "not_drained": raw["result"]["advance"]["horizon_complete"] = False
    elif mutation == "no_final_empty": raw["result"]["trays"][0]["mode"] = "holding"
    elif mutation == "third_load": rows.append({"event": "LOAD_START", "business_bag_id": "third", "tray_id": "token", "time": 10.})
    elif mutation == "open_ack": raw["owners"][0]["outbox"]["outbox"]["23"]["client_view"]["last_delivered_ack"]["status"] = "departed"
    elif mutation == "missing_parking": raw["owners"][0]["index"] = 21
    else: raw["physical_audit"]["status"] = "failed"
    assert not m.assess(raw, plan)["second_reuse_proved"]


def test_saved005_first_phase_exact_api_prefix_is_unchanged():
    directory = m.OUT / "original_low_wip_prepare_005"
    assert m.base.sha(directory / "api/manifest.jsonl") == "131f4598404e8199162087faf70beb090a384cfa795e933ec8764616e5540d7e"
    _, plan = saved005(); replay = m.base.ReplayTape(directory / "api")
    owners = [m.ReuseOwner(replay, owner, plan["parking_plan"]) for owner in plan["parking_plan"]["owners"]]
    while True:
        for owner in owners: owner.activate()
        supplied = [owner for owner in owners if owner.supply is not None]
        if supplied:
            assert len(supplied) == 1 and replay.physical_time == 8890.
            assert supplied[0].supply["choice"]["job"]["business_bag_id"] == "projected:1x:2"
            assert all(owner.second_supply is None for owner in owners)
            break
        replay.advance_to(replay.physical_time + m.base.PERIOD, max_events=100000)
    assert replay.index > 8000


def test_children_share_remaining_parent_budget(monkeypatch, tmp_path):
    clock = [125.]
    seen = []
    monkeypatch.setattr(m.time, "perf_counter", lambda: clock[0])
    def child(command, **kwargs):
        seen.append((command, kwargs["timeout"]))
        clock[0] += 5.
        return type("Result", (), {"returncode": 0})()
    monkeypatch.setattr(m.subprocess, "run", child)
    first = m.run_remaining(["native-worker"], tmp_path / "worker.log", 0.)
    clock[0] = 590.
    second = m.run_remaining(["pure-verify"], tmp_path / "verify.log", 0.)
    assert seen == [(["native-worker"], 475.), (["pure-verify"], 10.)]
    assert first["status"] == second["status"] == "child_finished"


def test_exhausted_parent_budget_never_launches_next_child(monkeypatch, tmp_path):
    monkeypatch.setattr(m.time, "perf_counter", lambda: 600.)
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: pytest.fail("launched after deadline"))
    result = m.run_remaining(["verify"], tmp_path / "verify.log", 0.)
    assert result["status"] == "unknown_parent_budget_before_child" and result["allowed_seconds"] == 0.
    assert not (tmp_path / "verify.log").exists()


@pytest.mark.parametrize("behavior", ["timeout", "late_success", "nonzero"])
def test_timeout_late_success_and_nonzero_never_look_complete(monkeypatch, tmp_path, behavior):
    clock = [590.]
    monkeypatch.setattr(m.time, "perf_counter", lambda: clock[0])
    def child(command, **kwargs):
        assert kwargs["timeout"] == 10.
        if behavior == "timeout":
            clock[0] = 600.1
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if behavior == "late_success": clock[0] = 601.
        return type("Result", (), {"returncode": 7 if behavior == "nonzero" else 0})()
    monkeypatch.setattr(m.subprocess, "run", child)
    result = m.run_remaining(["verify"], tmp_path / "verify.log", 0.)
    assert result["status"].startswith("unknown_")


@pytest.mark.parametrize("verify_seconds,expected", [(8., "worker_finished"), (11., "unknown_shared_parent_timeout")])
def test_parent_main_budgets_execution_review_and_pure_verification(monkeypatch, tmp_path, verify_seconds, expected):
    plan = {"source_before": {}}
    m.base.write(tmp_path / "preregistered_protocol.json", plan)
    clock = [0.]; seen = []
    monkeypatch.setattr(m.time, "perf_counter", lambda: clock[0])
    def verify_pins(*args, **kwargs): clock[0] += 4.
    def claim(*args): clock[0] += 1.
    monkeypatch.setattr(m, "verify_pins", verify_pins)
    monkeypatch.setattr(m.base, "claim_execution", claim)
    def child(command, **kwargs):
        seen.append((command, kwargs["timeout"]))
        if "--worker" in command:
            clock[0] += 585.
        else:
            assert "--verify" in command and "--verification-output" in command
            clock[0] += verify_seconds
            m.base.write(tmp_path / "independent_verification.json", {"status": "passed_saved_raw_replay"})
        return type("Result", (), {"returncode": 0})()
    monkeypatch.setattr(m.subprocess, "run", child)
    monkeypatch.setattr(m.sys, "argv", ["program", "--output", str(tmp_path), "--execute"])
    m.main()
    receipt = m.base.read(tmp_path / "receipt.json")
    assert seen[0][1] == 595. and seen[1][1] == 10.
    assert receipt["status"] == expected
    assert receipt["wall_seconds"] == 590. + verify_seconds
    assert receipt["verification_process"]["allowed_seconds"] == 10.
