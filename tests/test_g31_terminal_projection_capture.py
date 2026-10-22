"""Real prepared views must order receipt evidence and peer captures by time."""
import copy
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from test_g31_airport_inventory_rule import observation, snapshot
from test_g31_foundation_airport_joint_projection import add_request
from test_g31_terminal_transport_claims import policy_context


def sender_context(*, captured_at=2., received_at=30., status="received", issued_at=10.):
    obs = observation(source=0, stock=2, remote=True)
    obs.update(now=60., observation_scope="controller_policy", version=7)
    obs["static_role_contract"]["loader_nodes"] = [0, 1, 2]
    obs["planning_snapshots"] = [snapshot(stock=1, capture=captured_at,
        delivery=captured_at+2., expiry=captured_at+120.)]
    add_request(obs, status=status, identity="B0", received_at=received_at)
    for key in ("client_transfer_ledger", "transfers"):
        obs[key][0]["issued_at"] = issued_at
        if received_at is None:
            obs[key][0].pop("received_at")
    state = {}
    orders.ledger(state)["orders"]["own"] = dict(status=status.upper(), request_id="r1",
        physical_tray_id="B0", destination_terminal=2, source_terminal=0, owner_scope="A",
        proposed_at=issued_at, received_at=received_at)
    if received_at is None:
        orders.ledger(state)["orders"]["own"].pop("received_at")
    return (*policy_context(obs), state)


@pytest.mark.parametrize("captured_at", [2., 20., 29.999])
def test_sender_received_old_destination_capture_is_one_inbound_not_old_actual(captured_at):
    current, _, prepared, state = sender_context(captured_at=captured_at)
    view = current.inventory["nodes"][2]
    assert view["known"] and view["reason"] is None and view["as_of"] == captured_at
    assert view["reported_actual_empty"] == 1
    assert prepared.nodes[2]["inventory_known"]
    assert prepared.nodes[2]["stock"] == 0.
    assert "B0" not in prepared.actual_by_tray
    evidence = [row for row in prepared.supply_events if row["physical_tray_id"] == "B0"]
    assert len(evidence) == 1 and evidence[0]["availability_kind"] == "accepted_inbound"
    assert evidence[0]["event_time_estimate"] == 60.
    assert not any(row.get("reason") == "commitment_already_covered_by_capture"
        for row in prepared.audit["deduplication_and_unknown"])
    # The claim is covered by this exact request's one supply credit, not by old stock.
    assert orders.outstanding_uncredited(state, prepared) == {}


@pytest.mark.parametrize("captured_at", [30., 35.])
def test_sender_capture_at_or_after_receipt_is_one_actual_not_inbound(captured_at):
    _, _, prepared, state = sender_context(captured_at=captured_at)
    assert prepared.actual_by_tray["B0"] == 2
    assert prepared.nodes[2]["stock"] == 1.
    assert prepared.nodes[2]["events"] == []
    evidence = [row for row in prepared.supply_events if row["physical_tray_id"] == "B0"]
    assert len(evidence) == 1 and evidence[0]["availability_kind"] == "actual_current"
    assert orders.outstanding_uncredited(state, prepared) == {}


@pytest.mark.parametrize("received_at", [None, -1.])
@pytest.mark.parametrize("captured_at", [2., 35.])
def test_sender_unknown_receipt_cannot_be_covered_by_peer_capture(received_at, captured_at):
    _, _, prepared, state = sender_context(captured_at=captured_at, received_at=received_at)
    assert orders.outstanding_uncredited(state, prepared) == {2: 1}
    assert not any(row["availability_kind"] == "accepted_inbound" for row in prepared.supply_events)
    assert not any(row.get("reason") == "commitment_already_covered_by_capture"
        for row in prepared.audit["deduplication_and_unknown"])
    assert prepared.nodes[2]["stock"] == float(captured_at >= 10.)


@pytest.mark.parametrize("captured_at,kind", [(2., "accepted_inbound"), (10., "actual_current")])
def test_accepted_request_capture_requires_issuance_dominance(captured_at, kind):
    _, _, prepared, state = sender_context(captured_at=captured_at, status="accepted", received_at=-1.)
    evidence = [row for row in prepared.supply_events if row["physical_tray_id"] == "B0"]
    assert len(evidence) == 1 and evidence[0]["availability_kind"] == kind
    assert orders.outstanding_uncredited(state, prepared) == {}


def history_context(*, later_status, reverse=False):
    current, _, _, state = sender_context(received_at=20.)
    observation = copy.deepcopy(current.observation)
    old_request = observation["client_transfer_ledger"][0]
    later = dict(old_request, request_id="r2", issued_at=40., earliest_departure=42.,
        status=later_status, received_at=50. if later_status == "received" else -1.)
    observation["client_transfer_ledger"].append(later)
    if reverse:
        observation["client_transfer_ledger"].reverse()
    observation["transfers"] = copy.deepcopy(observation["client_transfer_ledger"])
    orders.ledger(state)["orders"]["new"] = dict(orders.ledger(state)["orders"]["own"],
        status=later_status.upper(), request_id="r2", proposed_at=40., received_at=later["received_at"])
    return observation, state


@pytest.mark.parametrize("later_status", ["accepted", "departed", "received"])
@pytest.mark.parametrize("reverse", [False, True])
def test_later_confirmed_cycle_supersedes_historical_receipt_without_duplicate_supply(later_status, reverse):
    observation, state = history_context(later_status=later_status, reverse=reverse)
    current, _, prepared = policy_context(observation)
    assert current.inventory["nodes"][2]["known"]
    evidence = [row for row in prepared.supply_events if row["physical_tray_id"] == "B0"]
    assert len(evidence) == 1 and evidence[0]["commitment_id_or_dependency"] == "r2"
    assert prepared.nodes[2]["stock"] == 0.
    assert any(row.get("request_id") == "r1" and row.get("superseding_request_id") == "r2"
        and row["reason"] == "historical_receipt_superseded_by_newer_commitment"
        for row in prepared.audit["deduplication_and_unknown"])
    assert orders.outstanding_uncredited(state, prepared) == {}


@pytest.mark.parametrize("later_status", ["pending", "rejected"])
def test_unconfirmed_later_intent_never_supersedes_physical_receipt(later_status):
    observation, state = history_context(later_status=later_status)
    _, _, prepared = policy_context(observation)
    evidence = [row for row in prepared.supply_events if row["physical_tray_id"] == "B0"]
    assert len(evidence) == 1 and evidence[0]["commitment_id_or_dependency"] == "r1"
    assert not any(row.get("reason") == "historical_receipt_superseded_by_newer_commitment"
        for row in prepared.audit["deduplication_and_unknown"])
    assert orders.outstanding_uncredited(state, prepared) == ({2: 1} if later_status == "pending" else {})


def test_two_genuinely_live_commitments_still_fail_closed():
    observation, _ = history_context(later_status="accepted")
    observation["client_transfer_ledger"][0].update(status="accepted", received_at=-1.)
    observation["transfers"] = copy.deepcopy(observation["client_transfer_ledger"])
    with pytest.raises(ValueError, match="one_live_accepted_commitment_per_tray"):
        policy_context(observation)
