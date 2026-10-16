"""The policy projection omits duplicate client history, never local sensors."""
from copy import deepcopy
import os

import pytest

from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.validate_protocol_control import scenarios
from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control


HISTORY = {"client_requests", "client_commands", "delivered_transfer_acks", "delivered_command_acks"}


@pytest.fixture(scope="module")
def native():
    return load_native(os.environ["G31_CIRCULATION_BINARY"])


def check_projection(session, owners):
    before = session.offline_state_sha256()
    for owner in owners:
        full = session.observe_protocol_control(owner)
        policy = session.observe_protocol_control_policy(owner)
        expected = {key: value for key, value in full.items() if key not in HISTORY}
        expected["observation_scope"] = "controller_policy"
        assert policy == expected
        assert not HISTORY.intersection(policy)
        assert HISTORY.issubset(full)
        for row in full["client_commands"]:
            assert session.protocol_command(owner, row["request_id"]) == row
        for row in full["client_requests"]:
            assert session.protocol_request(owner, row["request_id"]) == row
        policy["node_contracts"].clear()
        policy["client_transfer_ledger"].clear()
        assert session.observe_protocol_control_policy(owner) == expected
    assert session.offline_state_sha256() == before


@pytest.mark.parametrize("name,data,owners", scenarios(), ids=lambda x: x if isinstance(x, str) else None)
def test_fault_histories_remain_queryable_and_restore_preserves_projection(native, name, data, owners):
    data = deepcopy(data)
    data["owner_notifications"] = {"enabled": True}
    session = native.NativeSession(data)
    session.advance_to(.11)
    initial = session.checkpoint()
    run = run_event_protocol_control(session, owners, horizon=30., control_period=.5,
        command_delay=.01, publication_delay=.02, retry_period=.5, max_activations=20000)
    assert run["status"] == "reached"
    assert run["client_calls"]
    check_projection(session, owners)
    end = session.checkpoint()
    check_projection(session.fork(), owners)
    session.restore(initial)
    check_projection(session, owners)
    assert all(not session.observe_protocol_control(owner)["client_commands"] for owner in owners)
    session.restore(end)
    check_projection(session, owners)


def test_policy_view_rejects_unknown_owner_and_disabled_protocol(native):
    _, data, _ = scenarios()[0]
    session = native.NativeSession(data)
    session.advance_to(.11)
    with pytest.raises(Exception, match="owner"):
        session.observe_protocol_control_policy("not-a-real-owner")
    data["owner_protocol"]["enabled"] = False
    disabled = native.NativeSession(data)
    disabled.advance_to(.11)
    with pytest.raises(Exception, match="protocol"):
        disabled.observe_protocol_control_policy("A")
