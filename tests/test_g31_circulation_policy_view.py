"""Only internal policy reads may omit unused client history serialization."""
from copy import deepcopy
import json
import os

import pytest

from scripts.experiments.g31_ics_circulation.event_protocol_control import run_event_protocol_control
from scripts.experiments.g31_ics_circulation.local_context import LocalContextToken
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle
from scripts.experiments.g31_ics_circulation.protocol_control import ProtocolClient, run_protocol_control


HISTORY = ("client_requests", "client_commands", "delivered_transfer_acks", "delivered_command_acks")
TIMINGS = {"wall_seconds", "submit_compute_ms", "compute_wall_ms", "compute_cpu_ms", "wall_ms", "cpu_ms",
           "compute_ms", "preparation_compute_ms"}


def without_times(value):
    if isinstance(value, dict):
        return {k: without_times(v) for k, v in value.items() if k not in TIMINGS}
    if isinstance(value, list):
        return [without_times(v) for v in value]
    return value


def observation():
    return {"schema": "g31.owner_protocol_observation.v1", "owner_id": "A", "now": 2.,
        "node_records": [], "edge_records": [], "node_contracts": [], "edge_contracts": [],
        "trays": [], "jobs": [], "known_faults": [], "client_transfer_ledger": [{"request_id": "transfer"}],
        "client_requests": [{"request_id": "transfer", "attempt": 2}],
        "client_commands": [{"request_id": "forecast", "attempt": 3}],
        "delivered_transfer_acks": [{"request_id": "transfer", "sequence": 1, "delivered_at": 1.}],
        "delivered_command_acks": [{"request_id": "forecast", "sequence": 2, "delivered_at": 1.}],
        "delivered_messages": [
            {"kind": "service_forecast", "message_id": "old", "source_owner": "B", "target_owner": "A",
             "observed_at": 0., "delivered_at": .1, "status": "conditional"},
            {"kind": "service_forecast", "message_id": "withdrawn", "source_owner": "B", "target_owner": "A",
             "observed_at": 0., "delivered_at": .1, "status": "withdrawn"}]}


class LegacyEndpoint:
    def __init__(self):
        self.data = observation()
        self.reads = []
        self.physical_time = self.data["now"]

    def observe_protocol_control(self, owner):
        self.reads.append("compact")
        return deepcopy(self.data)

    def observe_protocol(self, owner):
        self.reads.append("full")
        return deepcopy(self.data)


class PolicyEndpoint(LegacyEndpoint):
    def observe_protocol_control_policy(self, owner):
        self.reads.append("policy")
        result = deepcopy(self.data)
        for key in HISTORY:
            del result[key]
        result["observation_scope"] = "controller_policy"
        return result


def test_private_projection_preserves_public_view_context_and_expiry_contract():
    endpoint = PolicyEndpoint()
    client = ProtocolClient(endpoint, forecast_validity=1.)
    public = client.view("A")
    context = LocalContextToken.from_observation(client.view("A", compact=False))
    policy = client._policy_view("A")
    assert set(public) - set(policy) == set(HISTORY)
    assert set(policy) - set(public) == {"observation_scope"}
    assert {k: v for k, v in policy.items() if k != "observation_scope"} == {
        k: v for k, v in public.items() if k not in HISTORY}
    assert policy["transfers"] == public["client_transfer_ledger"]
    assert [m["status"] for m in policy["delivered_messages"]] == ["expired", "withdrawn"]
    assert len(policy["delivered_messages"]) == 2  # no older-message resurrection
    policy["client_transfer_ledger"][0]["request_id"] = "mutated"
    policy["delivered_messages"].clear()
    assert client.view("A") == public
    assert LocalContextToken.from_observation(client.view("A", compact=False)) == context
    assert endpoint.data["delivered_messages"][0]["status"] == "conditional"


@pytest.mark.parametrize("endpoint_type", [LegacyEndpoint, PolicyEndpoint])
@pytest.mark.parametrize("enabled", [False, True])
def test_fallback_full_mode_and_runtime_option_do_not_enter_state(endpoint_type, enabled):
    endpoint = endpoint_type()
    client = ProtocolClient(endpoint, _use_policy_view=enabled)
    before = deepcopy(client.state)
    client._policy_view("A")
    assert endpoint.reads[-1] == ("policy" if enabled and endpoint_type is PolicyEndpoint else "compact")
    assert set(HISTORY) <= client._policy_view("A", compact=False).keys()
    assert endpoint.reads[-1] == "full"
    assert client.state == before
    restored = ProtocolClient(endpoint, state=json.loads(json.dumps(client.state)), _use_policy_view=not enabled)
    assert restored.state == before


def test_forwarding_proxy_cannot_silently_bypass_its_compact_view_hook():
    class Proxy:
        def __init__(self, session):
            self.session = session

        def __getattr__(self, name):
            return getattr(self.session, name)

        def observe_protocol_control(self, owner):
            result = self.session.observe_protocol_control(owner)
            result["proxy_hook"] = True
            return result

    endpoint = PolicyEndpoint()
    client = ProtocolClient(Proxy(endpoint))
    assert client._policy_view("A")["proxy_hook"] is True
    assert endpoint.reads == ["compact"]


@pytest.fixture(scope="module")
def native():
    module = load_native(os.environ["G31_CIRCULATION_BINARY"])
    assert hasattr(module.NativeSession, "observe_protocol_control_policy"), "native018 policy endpoint required"
    return module


def scene(protocol=None):
    data = tiny_cycle()
    data["transfers"] = []
    for job in data["jobs"]:
        job["allow_suffix_reroute"] = True
    data["owner_protocol"] = {"enabled": True, "timeout": .2, "ack_delay": 0., **(protocol or {})}
    data["owner_notifications"] = {"enabled": True}
    return data


@pytest.mark.parametrize("compact", [False, True])
def test_native_public_key_insertion_order_remains_legacy_contract(native, compact):
    session = native.NativeSession(scene())
    session.advance_to(0.)
    view = session.observe_protocol_control("A") if compact else session.observe_protocol("A")
    assert list(view)[-5:] == ["client_requests", "delivered_transfer_acks", "client_transfer_ledger",
                              "client_commands", "delivered_command_acks"]


OPTIONS = dict(control_period=1., command_delay=0., publication_delay=0., retry_period=.5,
               forecast_validity=2., forecast_refresh_period=1., lease_seconds=2.)


@pytest.mark.parametrize("execute", [run_protocol_control, run_event_protocol_control])
@pytest.mark.parametrize("compact", [True, False])
@pytest.mark.parametrize("protocol", [{}, {"drop_ack_packets": 2},
    {"duplicate_acks": True, "duplicate_ack_delay": 0.},
    {"owner_outages": [{"owner": "B", "start": .2, "end": 12.}]}])
def test_native_policy_history_omission_preserves_full_tape_refresh_and_retries(native, execute, compact, protocol):
    runs, hashes = [], []
    for enabled in (False, True):
        session = native.NativeSession(scene(protocol))
        runs.append(execute(session, ["A", "B"], horizon=30., compact=compact,
                            _use_policy_view=enabled, **OPTIONS))
        hashes.append(session.offline_state_sha256())
        client = ProtocolClient(session)
        assert set(HISTORY) <= client.view("A").keys()
        assert set(HISTORY) <= client.view("A", compact=False).keys()
        assert set(HISTORY).isdisjoint(client._policy_view("A"))
    assert without_times(runs[0]) == without_times(runs[1])
    assert hashes[0] == hashes[1]
    if protocol.get("drop_ack_packets"):
        assert any(call["retry"] for call in runs[1]["client_calls"])
    assert any(row["refreshed"] for row in runs[1]["control_records"])


def test_native_policy_view_option_can_switch_after_json_native_restore(native):
    data = scene({"drop_ack_packets": 1})
    continuous = native.NativeSession(data)
    full = run_event_protocol_control(continuous, ["A", "B"], horizon=30., _use_policy_view=False, **OPTIONS)
    split = native.NativeSession(data)
    prefix = run_event_protocol_control(split, ["A", "B"], horizon=7.37, _use_policy_view=False, **OPTIONS)
    branch = split.fork()
    suffix = run_event_protocol_control(branch, ["A", "B"], horizon=30., _use_policy_view=True,
        state=json.loads(json.dumps(prefix["controller_state"])), **OPTIONS)
    assert without_times(prefix["client_calls"] + suffix["client_calls"]) == without_times(full["client_calls"])
    assert suffix["controller_state"] == full["controller_state"]
    assert continuous.offline_state_sha256() == branch.offline_state_sha256()


def test_native_policy_budget_cut_keeps_same_timestamp_drain_and_checkpoint(native):
    data = scene({"drop_ack_packets": 1})
    continuous = native.NativeSession(data)
    full = run_event_protocol_control(continuous, ["A", "B"], horizon=12., _use_policy_view=False, **OPTIONS)
    split = native.NativeSession(data)
    calls, state = [], None
    for index in range(2000):
        part = run_event_protocol_control(split, ["A", "B"], horizon=12., state=state,
            event_budget=1, max_activations=1, _use_policy_view=bool(index % 2), **OPTIONS)
        calls.extend(part["client_calls"])
        state = json.loads(json.dumps(part["controller_state"]))
        if part["status"] == "reached":
            break
        split = split.fork()
    else:
        pytest.fail("budget continuation did not converge")
    assert without_times(calls) == without_times(full["client_calls"])
    assert state == full["controller_state"]
    assert split.offline_state_sha256() == continuous.offline_state_sha256()
