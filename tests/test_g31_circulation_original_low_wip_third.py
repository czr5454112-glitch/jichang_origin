from copy import deepcopy
from functools import lru_cache

import pytest

from scripts.experiments.g31_ics_circulation import research_original_low_wip_third as m
from test_g31_circulation_original_low_wip_reuse import FakeClient, FakeSession, final_fixture, proof_fixture


@lru_cache(maxsize=1)
def saved_two():
    for name, digest in m.PREDECESSOR_PINS.items():
        assert m.base.sha(m.PREDECESSOR / name) == digest
    return m.base.gzread(m.PREDECESSOR / "raw_final.json.gz"), m.base.read(m.PREDECESSOR / "preregistered_protocol.json")


def invitation():
    """Deliberately synthetic next-return body; not an executed third cycle."""
    args = proof_fixture(); owner, peer, token = args[3:6]
    env = deepcopy(args[1][args[-1]]["client_view"]["last_delivered_ack"]["planning_snapshot_v2"])
    local, ext = env["capture"]["local_capture"], env["capture"]["extension"]
    local["captured_at"] = 20822.
    tray = deepcopy(args[2]["trays"][0]); tray["available_at"] = 20813.
    local["trays"] = [tray]
    ext["submitted_physical_actions"] = [{"request_id": m.base.owner_request_id(owner, "second-supply"),
        "kind": "transfer", "last_delivered_ack": {"status": "received", "delivered_at": 20383.}}]
    ext["terminal_receipts"][0].update(completed_at=20812., business_bag_id="second-job")
    return env, token, owner, {r["node"]: r for r in args[2]["node_contracts"]}


def test_second_return_reply_requires_actual_post_second_received_completion():
    args = invitation()
    assert m.second_return_invitation(*args)
    # The actual first completion predates the second transfer ACK.
    args[0]["capture"]["extension"]["terminal_receipts"][0]["completed_at"] = 19772.
    assert not m.second_return_invitation(*args)


@pytest.mark.parametrize("change", ["missing", "wrong_request", "departed", "future_ack", "loaded", "inflight",
    "incoming", "unavailable", "no_receipt", "wrong_token", "wrong_owner", "future_receipt"])
def test_invitation_cannot_relabel_incomplete_return(change):
    args = invitation(); env, token, owner, nodes = args
    local = env["capture"]["local_capture"]; ext = env["capture"]["extension"]
    action, receipt, tray = ext["submitted_physical_actions"][0], ext["terminal_receipts"][0], local["trays"][0]
    if change == "missing": args = (None, token, owner, nodes)
    elif change == "wrong_request": action["request_id"] = m.base.owner_request_id(owner, "single-supply")
    elif change == "departed": action["last_delivered_ack"]["status"] = "departed"
    elif change == "future_ack": action["last_delivered_ack"]["delivered_at"] = 30000.
    elif change == "loaded": tray["mode"] = "loaded"
    elif change == "inflight": tray["edge_to"] = 10
    elif change == "incoming": tray["reception_node"] = 10
    elif change == "unavailable": tray["available_at"] = 30000.
    elif change == "no_receipt": ext["terminal_receipts"] = []
    elif change == "wrong_token": receipt["tray_id"] = "different"
    elif change == "wrong_owner": receipt["source_owner"] = "different"
    else: receipt["completed_at"] = 30000.
    assert not m.second_return_invitation(*args)


def next_owner():
    raw, plan = saved_two(); source = next(o for o in raw["owners"] if o["second_supply"])
    args = proof_fixture(); view = deepcopy(args[2]); view["now"] = 20840.
    view["trays"][0]["available_at"] = 20813.397
    session = FakeSession(view); owner = m.ThirdOwner(session, source["owner"], plan["parking_plan"])
    owner.index = len(owner.rows); owner.quiet = True
    owner.supply = deepcopy(source["supply"]); owner.second_supply = deepcopy(source["second_supply"])
    owner.client = FakeClient(source["outbox"]["outbox"])
    return owner, session


def setup_third(monkeypatch, *, peer_at=20832., own_at=20832.):
    owner, session = next_owner()
    peer = deepcopy(owner.second_supply["choice"]["delivered_message"])
    peer["capture"]["local_capture"]["captured_at"] = peer_at
    peer["capture"]["extension"]["submitted_physical_actions"] = []
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: peer)
    proof = {"own_delivered_self_copy": {"envelope": {"capture": {"local_capture": {"captured_at": own_at}}}}}
    monkeypatch.setattr(m.reuse, "return_proof", lambda *args: deepcopy(proof))
    choice = deepcopy(owner.second_supply["choice"])
    choice["job"].update(business_bag_id="fresh-message-head-not-hardcoded", origin=49)
    choice["tray"] = deepcopy(session.view["trays"][0])
    monkeypatch.setattr(m.base, "eligible_head", lambda *args: deepcopy(choice))
    return owner, session


def test_one_third_request_uses_runtime_selected_head_and_keeps_retry_refresh(monkeypatch):
    owner, session = setup_third(monkeypatch)
    owner.activate(); read_count = len(session.reads); owner.activate()
    assert owner.third_supply["choice"]["job"]["business_bag_id"] == "fresh-message-head-not-hardcoded"
    assert [c["kind"] for c in owner.client.calls] == ["planning_snapshot_v2", "transfer"]
    assert owner.client.calls[-1]["request_id"] == m.base.owner_request_id(owner.owner, "third-supply")
    assert owner.client.calls[-1]["payload"]["message_delay"] == 2.
    assert owner.client.refreshed == 2 and len(session.reads) == read_count


def test_rejected_third_request_does_not_select_another_head(monkeypatch):
    owner, session = setup_third(monkeypatch)
    owner.activate()
    request_id = owner.third_supply["request_id"]
    owner.client.state["outbox"][request_id] = {"kind": "transfer", "terminal": True,
        "client_view": {"last_delivered_ack": {"status": "rejected", "reason": "receiving_full"}}}
    monkeypatch.setattr(m.base, "eligible_head", lambda *args: pytest.fail("reselected after rejection"))
    owner.activate()
    assert sum(c["kind"] == "transfer" for c in owner.client.calls) == 1
    assert owner.client.state["outbox"][request_id]["client_view"]["last_delivered_ack"]["status"] == "rejected"


@pytest.mark.parametrize("reason", ["old_peer", "missing_proof", "missing_second_ack", "holding", "same_job"])
def test_third_is_not_issued_from_old_or_incomplete_evidence(monkeypatch, reason):
    owner, session = setup_third(monkeypatch, peer_at=20822. if reason == "old_peer" else 20832.)
    if reason == "missing_proof": monkeypatch.setattr(m.reuse, "return_proof", lambda *args: None)
    if reason == "missing_second_ack": owner.client.state["outbox"][owner.second_supply["request_id"]]["client_view"]["last_delivered_ack"]["status"] = "departed"
    if reason == "holding": session.view["trays"][0]["mode"] = "holding"
    if reason == "same_job":
        monkeypatch.setattr(m.base, "eligible_head", lambda *args: deepcopy(owner.second_supply["choice"]))
        with pytest.raises(ValueError, match="repeat_completed_job"): owner.activate()
    else: owner.activate()
    assert owner.third_supply is None and not any(c["kind"] == "transfer" for c in owner.client.calls)


def test_peer_third_seen_is_sticky_and_does_not_reopen_on_expiry(monkeypatch):
    raw, plan = saved_two(); source = next(o for o in raw["owners"] if o["second_supply"])
    owner, session = next_owner(); other = m.ThirdOwner(session, owner.peer, plan["parking_plan"])
    other.index = len(other.rows); other.quiet = other.second_seen = True
    other._reuse_nodes = {r["node"]: r for r in session.view["node_contracts"]}; other.client = FakeClient({})
    env = {"capture": {"extension": {"submitted_physical_actions": [{"request_id": m.base.owner_request_id(source["owner"], "third-supply")}]}}}
    monkeypatch.setattr(m.base, "delivered_peer", lambda *args: env)
    other.activate(); assert other.third_seen
    reads = len(session.reads); monkeypatch.setattr(m.base, "delivered_peer", lambda *args: None)
    other.activate()
    assert len(session.reads) == reads and other.client.calls == [] and other.client.refreshed == 2


def test_saved_two_supply_actual_api_prefix_is_exact_through_second_issue():
    raw, plan = saved_two(); tape = m.base.ReplayTape(m.PREDECESSOR / "api")
    owners = [m.ThirdOwner(tape, o, plan["parking_plan"]) for o in plan["parking_plan"]["owners"]]
    while not any(o.second_supply for o in owners):
        for o in owners: o.activate()
        if any(o.second_supply for o in owners): break
        tape.advance_to(tape.physical_time + m.base.PERIOD, max_events=100000)
    assert tape.physical_time == 19800.
    chosen = next(o for o in owners if o.second_supply)
    assert chosen.second_supply == next(o for o in raw["owners"] if o["second_supply"])["second_supply"]
    assert all(o.third_supply is None and o.third_observations == 0 for o in owners)


def test_public_fifo_fixture_after_job6_selects49_without_skipping26():
    owner, session = next_owner()
    peer = deepcopy(owner.second_supply["choice"]["delivered_message"])
    local = peer["capture"]["local_capture"]
    # Synthetic post-completion fixture: not a claim to have received this body.
    local["captured_at"] = session.physical_time
    local["jobs"] = [j for j in local["jobs"] if j["business_bag_id"] != "projected:1x:6"]
    job = m.base.eligible_head(peer, session.view, owner.plan["token_tray_id"])["job"]
    assert job["origin"] == 49 and job["business_bag_id"] == "projected:1x:8"
    assert any(j["business_bag_id"] == "projected:1x:14" for j in local["jobs"])
    first49 = next(j for j in local["jobs"] if j["business_bag_id"] == "projected:1x:8")
    first49["destination"] = 99  # Later reachable source49 jobs cannot jump it.
    assert m.base.eligible_head(peer, session.view, owner.plan["token_tray_id"]) is None


def three_fixture():
    raw, plan = final_fixture()
    source = raw["owners"][0]
    source["third_supply"] = {"at": 10., "choice": {"job": {"business_bag_id": "j3", "origin": 49, "destination": 46}}}
    source["outbox"]["outbox"]["24"] = {"kind": "transfer", "client_view": {"last_delivered_ack": {"status": "received"}}}
    raw["result"]["receipts"] += [{"event": e, "business_bag_id": "j3", "tray_id": "token", "time": t,
        "node": 49 if e.startswith("LOAD") else 46} for e, t in zip(
            ("LOAD_START", "LOAD_COMPLETE", "UNLOAD_COMPLETE", "HOLD_COMPLETE"), (11., 11., 13., 14.))]
    raw["result"]["trays"][0]["available_at"] = 14.
    return raw, plan


def test_three_actual_lifecycles_are_required_not_just_transfer_acks():
    raw, plan = three_fixture(); result = m.assess(raw, plan)
    assert result["third_cycle_proved"] and result["actual_supply_count"] == 3
    assert not result["complete_100ms_certified"] and result["strict_protection"] == "not_assessed"


@pytest.mark.parametrize("mutation", ["no_third", "no_hold", "other_token", "same_job", "overlap", "open_ack", "extra_load", "not_empty", "censored", "failed_audit"])
def test_incomplete_third_remains_unknown_in_denominator(mutation):
    raw, plan = three_fixture(); source = raw["owners"][0]; rows = raw["result"]["receipts"]
    if mutation == "no_third": source["third_supply"] = None
    elif mutation == "no_hold": rows.pop()
    elif mutation == "other_token": rows[-1]["tray_id"] = "different"
    elif mutation == "same_job": source["third_supply"]["choice"]["job"]["business_bag_id"] = "j1"
    elif mutation == "overlap": source["third_supply"]["at"] = 8.
    elif mutation == "open_ack": source["outbox"]["outbox"]["24"]["client_view"]["last_delivered_ack"]["status"] = "departed"
    elif mutation == "extra_load": rows.append({"event": "LOAD_START", "business_bag_id": "j4", "tray_id": "token"})
    elif mutation == "not_empty": raw["result"]["trays"][0]["mode"] = "holding"
    elif mutation == "censored": raw["result"]["advance"]["horizon_complete"] = False
    else: raw["physical_audit"]["status"] = "failed"
    result = m.assess(raw, plan)
    assert not result["third_cycle_proved"] and result["offered"] == 28506


def test_install_is_local_and_restores_frozen_modules_after_exception():
    fields = ("Owner", "assess", "source_paths", "verify_pins", "SCHEMA", "HORIZON", "MAX_TICKS", "MAX_PHYSICAL")
    before = {k: getattr(m.base, k) for k in fields}
    with pytest.raises(RuntimeError):
        with m.installed():
            assert m.base.Owner is m.ThirdOwner and m.base.MAX_PHYSICAL == 25
            with pytest.raises(ValueError):
                with m.installed(): pass
            raise RuntimeError("test")
    assert {k: getattr(m.base, k) for k in fields} == before
    assert m.base.sha(m.base.__file__) == m.BASE_SHA and m.base.sha(m.reuse.__file__) == m.REUSE_SHA


def test_source_closure_contains_new_and_both_frozen_policy_modules():
    names = {p.relative_to(m.ROOT).as_posix() for p in m.source_paths()}
    for name in ("research_original_low_wip", "research_original_low_wip_reuse", "research_original_low_wip_third"):
        assert f"scripts/experiments/g31_ics_circulation/{name}.py" in names
    assert "src/czr005/cpp_backend.py" in names


def test_budget_is_shared_between_native_and_verification(monkeypatch, tmp_path):
    clock = [25.]; limits = []
    monkeypatch.setattr(m.time, "perf_counter", lambda: clock[0])
    def run(command, **kw):
        limits.append(kw["timeout"])
        clock[0] += 5.
        return type("Done", (), {"returncode": 0})()
    monkeypatch.setattr(m.subprocess, "run", run)
    m.run_remaining(["worker"], tmp_path / "first.log", 0.)
    clock[0] = 599.
    result = m.run_remaining(["verify"], tmp_path / "second.log", 0.)
    assert limits == [575., 1.] and result["status"] == "unknown_shared_parent_timeout"
    assert m.run_remaining(["not-launched"], tmp_path / "third.log", 0.)["status"] == "unknown_parent_budget_before_child"
    assert not (tmp_path / "third.log").exists()


def test_predecessor_authority_cannot_be_omitted_before_archive_verification(tmp_path):
    with pytest.raises(ValueError, match="predecessor_pins_missing"):
        m.verify_pins(tmp_path, {"authority_pins": {}})
