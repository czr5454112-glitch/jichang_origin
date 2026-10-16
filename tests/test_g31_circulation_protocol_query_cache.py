from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.protocol_query_cache import cache_protocol_queries


class Session:
    def __init__(self):
        self.physical_time = 0.
        self.queries = 0
        self.view = {"request_id": "r", "status": "pending", "attempt": 1}
        self.notice = {}
        self.complete = True
        self.reply = {"status": "pending"}

    def protocol_request(self, owner, identity):
        self.queries += 1
        return deepcopy(self.view)

    protocol_command = protocol_request

    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        return {"status": "notified" if self.notice else "horizon_reached",
            "timestamp_complete": self.complete, "notifications": deepcopy(self.notice)}

    def submit_protocol_transfer(self, request):
        self.view["attempt"] += 1
        return deepcopy(self.reply)

    submit_protocol_command = submit_protocol_transfer

    def checkpoint(self):
        return deepcopy(self.view)

    def restore(self, state):
        self.view = deepcopy(state)

    def fork(self):
        child = Session(); child.view = deepcopy(self.view)
        return child

    def advance_to(self, horizon):
        self.physical_time = horizon
        self.view["status"] = "timeout_unknown"

    def future_unclassified_method(self):
        self.view["status"] = "unknown_changed"


class Recent(Session):
    def observe_protocol_control_policy(self, owner):
        return {"owner_id": owner}

    def observe_protocol_control_policy_recent(self, owner, forecast_validity):
        return {"owner_id": owner, "forecast_validity": forecast_validity}


def fixture():
    raw = Session(); proxy = cache_protocol_queries(raw, ["A", "B"])
    advance(proxy, raw, {})
    return raw, proxy


def advance(proxy, raw, notices, after=None, owners=None):
    raw.notice = notices
    if after is None:
        after = proxy._cursor or {"A": 0, "B": 0}
    return proxy.advance_until_owner_notification(owners or ["A", "B"], after, raw.physical_time, max_events=100)


def notice(sequence, mask, at=0.):
    return {"sequence": sequence, "change_mask": mask, "observed_at": at}


def test_uncertified_queries_never_reuse_before_initial_boundary():
    raw = Session(); proxy = cache_protocol_queries(raw, ["A", "B"])
    proxy.protocol_request("A", "r"); proxy.protocol_request("A", "r")
    assert raw.queries == 2


def test_unrelated_owner_arrivals_and_periodic_timer_reuse_fresh_copies():
    raw, proxy = fixture()
    original = proxy.protocol_request("A", "r")
    original["attempt"] = 700
    advance(proxy, raw, {"A": notice(1, 1 | 2 | 4 | 8 | 64 | 128)})
    got = proxy.protocol_request("A", "r")
    assert got == raw.view and got is not original
    advance(proxy, raw, {})
    assert proxy.protocol_request("A", "r") == raw.view
    assert raw.queries == 1 and proxy._counters["reused_queries"] == 2


@pytest.mark.parametrize("mask,status", [(16, "acknowledged"), (32, "timeout_unknown"), (48, "acknowledged")])
def test_delivered_ack_and_timeout_invalidate_all_owner_pending_rows(mask, status):
    raw, proxy = fixture()
    proxy.protocol_request("A", "r"); proxy.protocol_command("A", "q"); proxy.protocol_request("B", "b")
    raw.view["status"] = status
    advance(proxy, raw, {"A": notice(1, mask)})
    assert proxy.protocol_request("A", "r")["status"] == status
    assert proxy.protocol_command("A", "q")["status"] == status
    # B's projection cannot change in the real engine without B's own notice.
    assert proxy.protocol_request("B", "b")["status"] == "pending"
    assert raw.queries == 5


@pytest.mark.parametrize("kind", ["transfer", "command"])
@pytest.mark.parametrize("reply", ["pending", "rejected"])
def test_retry_or_rejected_submit_invalidates_exact_id(kind, reply):
    raw, proxy = fixture()
    query = getattr(proxy, "protocol_request" if kind == "transfer" else "protocol_command")
    query("A", "r"); raw.reply = {"status": reply}
    getattr(proxy, "submit_protocol_"+kind)({"owner_id": "A", "request_id": "r"})
    assert query("A", "r")["attempt"] == 2 and raw.queries == 2


def test_same_timestamp_second_ack_after_other_owner_action_invalidates_again():
    raw, proxy = fixture(); proxy.protocol_request("A", "r")
    raw.view["last_delivered_ack"] = {"sequence": 1, "status": "granted"}
    advance(proxy, raw, {"A": notice(1, 16)})
    first = proxy.protocol_request("A", "r")
    raw.view["last_delivered_ack"] = {"sequence": 2, "status": "received"}
    advance(proxy, raw, {"A": notice(2, 16 | 2)})
    assert proxy.protocol_request("A", "r")["last_delivered_ack"]["sequence"] == 2
    assert first["last_delivered_ack"]["sequence"] == 1


def test_arbitrary_advance_loses_old_mask_and_must_drop_cache():
    raw, proxy = fixture(); proxy.protocol_request("A", "r")
    proxy.advance_to(10.)  # timeout at t5, overwritten by arrival t10
    advance(proxy, raw, {"A": notice(2, 1, 10.)}, after={"A": 0, "B": 0})
    assert proxy.protocol_request("A", "r")["status"] == "timeout_unknown"
    assert raw.queries == 2


@pytest.mark.parametrize("cause", ["cursor_gap", "subset", "incomplete", "invalid_notice", "unknown_mask"])
def test_boundary_uncertainty_fails_closed(cause):
    raw, proxy = fixture(); proxy.protocol_request("A", "r")
    raw.view["status"] = "changed"
    if cause == "cursor_gap":
        advance(proxy, raw, {}, after={"A": 9, "B": 0})
    elif cause == "subset":
        advance(proxy, raw, {}, after={"A": 0}, owners=["A"])
    elif cause == "incomplete":
        raw.complete = False; advance(proxy, raw, {})
    elif cause == "invalid_notice":
        advance(proxy, raw, {"A": notice(1, 1, 100.)})
    else:
        advance(proxy, raw, {"A": notice(1, 256)})
    assert proxy.protocol_request("A", "r")["status"] == "changed"
    assert raw.queries == 2


def test_checkpoint_restore_and_fork_never_share_cache_or_proof():
    raw, proxy = fixture(); proxy.protocol_request("A", "r")
    saved = proxy.checkpoint()
    assert not proxy._certified and not proxy._cached
    raw.view["attempt"] = 9
    proxy.restore(saved)
    assert proxy.protocol_request("A", "r")["attempt"] == 1
    advance(proxy, raw, {}); proxy.protocol_request("A", "r")
    child = proxy.fork()
    assert not child._certified and not child._cached and not proxy._certified
    child._session.view["attempt"] = 3
    assert child.protocol_request("A", "r")["attempt"] == 3
    assert proxy.protocol_request("A", "r")["attempt"] == 1


def test_unknown_method_invalidates_and_recent_capability_is_preserved():
    raw, proxy = fixture(); proxy.protocol_request("A", "r")
    proxy.future_unclassified_method()
    assert proxy.protocol_request("A", "r")["status"] == "unknown_changed"
    assert getattr(type(proxy), "observe_protocol_control_policy_recent", None) is None
    recent = cache_protocol_queries(Recent(), ["A"])
    assert recent.observe_protocol_control_policy_recent("A", 123.) == {"owner_id": "A", "forecast_validity": 123.}


@pytest.mark.parametrize("terminal", ["received", "rejected"])
def test_actual_client_retry_ack_cooldown_and_checkpoint_state_remain_equal(terminal):
    from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient
    from scripts.experiments.g31_ics_circulation.profile_request_bundles import semantics

    def run(use_cache):
        raw = Session()
        session = cache_protocol_queries(raw, ["A", "B"]) if use_cache else raw
        cursor = {"A": 0, "B": 0}
        def boundary(mask=None):
            if mask is not None:
                cursor["A"] += 1
                raw.notice = {"A": notice(cursor["A"], mask, raw.physical_time)}
                after = {**cursor, "A": cursor["A"]-1}
            else:
                raw.notice = {}; after = dict(cursor)
            session.advance_until_owner_notification(["A", "B"], after, raw.physical_time, max_events=100)
        boundary()
        client = ProtocolClient(session, retry_period=1., rejection_cooldown=.2)
        identity, _ = client.submit("A", "transfer", {"tray_id": "T", "source": 0, "destination": 1})
        raw.view["request_id"] = identity
        results = [client.refresh(owner_id="A")]
        boundary(1); results.append(client.refresh(owner_id="A"))  # no ACK: cached pending is still pending
        raw.physical_time = 1.
        raw.view["status"] = "timeout_unknown"
        boundary(32); results.append(client.refresh(owner_id="A"))  # exact immutable retry remains due
        boundary(); results.append(client.refresh(owner_id="A"))  # retry invalidated local attempt
        raw.physical_time = 1.2
        raw.view.update(status="acknowledged", last_delivered_ack={"sequence": 1, "status": terminal, "delivered_at": 1.2})
        boundary(16); results.append(client.refresh(owner_id="A"))
        raw.physical_time = 1.5
        boundary(); results.append(client.refresh(owner_id="A"))
        assert len(client.calls) == 2 and client.calls[1]["retry"] is True
        assert client.calls[0]["request"] == client.calls[1]["request"]
        assert client.state["outbox"][identity]["terminal"] is True
        if terminal == "rejected":
            assert client.state["outbox"][identity]["cooldown_consumed"] is True
        return results, client.state, semantics(client.calls), raw.queries
    plain, reused = run(False), run(True)
    assert plain[:3] == reused[:3]
    assert reused[3] < plain[3]
