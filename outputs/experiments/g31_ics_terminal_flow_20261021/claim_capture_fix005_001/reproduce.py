"""Pure prepared-observation riskcases; no native construction or execution."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent/'scripts').is_dir())
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from test_g31_terminal_transport_claims import three_owner_capture_context, received_other_owner
from test_g31_terminal_projection_capture import sender_context, history_context
from test_g31_terminal_transport_claims import policy_context
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_control as control

FROZEN = ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_004'
PACKAGE = 'scripts/experiments/g31_ics_circulation'


def old_module(stem):
    name = 'scripts.experiments.g31_ics_circulation._before005_'+stem
    spec = importlib.util.spec_from_file_location(name, FROZEN/PACKAGE/(stem+'.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def allocation_with(function, current, catalog, prepared, state):
    previous = orders.outstanding_uncredited
    try:
        orders.outstanding_uncredited = function
        plan = control.TransportPolicy()._solve(current, catalog, prepared, state)
    finally:
        orders.outstanding_uncredited = previous
    return dict(claims=plan['receiver_claims_deducted'], chosen=plan['chosen'])


def describe(prepared, state, order_module):
    return dict(actual_by_tray=prepared.actual_by_tray,
        destination_stock=prepared.nodes[2]['stock'],
        destination_inventory_known=prepared.nodes[2]['inventory_known'],
        tray_supply=[row for row in prepared.supply_events if row['physical_tray_id']=='B0'],
        deduplication=prepared.audit['deduplication_and_unknown'],
        claims=order_module.outstanding_uncredited(state, prepared))


def main():
    before_orders = old_module('foundation_airport_transport_orders')
    before_projection = old_module('foundation_airport_inventory_projection')
    current, catalog, prepared = three_owner_capture_context()
    state = {}
    received_other_owner(state)
    cross = dict(observation=current.observation, policy_state=state,
        accepted_remote_views={node: current.inventory['nodes'][node] for node in (1,2)},
        before_claims=before_orders.outstanding_uncredited(state, prepared),
        after_claims=orders.outstanding_uncredited(state, prepared),
        before_allocation=allocation_with(before_orders.outstanding_uncredited,current,catalog,prepared,state),
        after_allocation=allocation_with(orders.outstanding_uncredited,current,catalog,prepared,state))
    current, _, prepared, state = sender_context()
    old_prepared = before_projection.prepare_inventory_projection(current.observation, prepared_current=current)
    sender = dict(observation=current.observation, policy_state=state,
        before=describe(old_prepared,state,before_orders), after=describe(prepared,state,orders))
    history = {}
    for status in ('pending', 'accepted', 'received'):
        observation, state = history_context(later_status=status)
        current, _, prepared = policy_context(observation)
        try:
            old_prepared = before_projection.prepare_inventory_projection(observation, prepared_current=current)
            before = describe(old_prepared, state, before_orders)
        except ValueError as error:
            before = dict(error_type=type(error).__name__, error=str(error))
        history[status] = dict(observation=observation, before=before, after=describe(prepared,state,orders))
    files = ['foundation_airport_transport_orders.py', 'foundation_airport_inventory_projection.py']
    hashes = {stem: dict(before004=hashlib.sha256((FROZEN/PACKAGE/stem).read_bytes()).hexdigest(),
        working005=hashlib.sha256((ROOT/PACKAGE/stem).read_bytes()).hexdigest()) for stem in files}
    return dict(schema='g31.terminal_flow.claim_capture_riskcase.v1', native_started=False,
        native003_occurrence_claimed=False, scope='pure_reachable_legal_observation_riskcase',
        cross_owner_missing_sender_ledger=cross, own_sender_ledger=sender,
        retained_request_history=history, source_hashes=hashes)


if __name__ == '__main__':
    print(json.dumps(main(), ensure_ascii=False, indent=2, allow_nan=False))
