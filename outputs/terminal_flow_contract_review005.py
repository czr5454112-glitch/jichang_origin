"""Independent, finite public/fake-client contract checks; never creates native."""
from pathlib import Path
import copy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as joint
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_control as adapter
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as rules
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_control as control
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_allocation as allocation
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from scripts.experiments.g31_ics_circulation import protocol_control as protocol
from test_g31_airport_inventory_rule import observation, PublicSession
from test_g31_foundation_airport_joint_projection import fixture, forecast

MANIFEST = ROOT / 'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005/source_manifest.json'
EXPECTED_MANIFEST_SHA = '22201c59569d2c2a67460ebff7be249432e25fc6a3f42941d4d15ddac8113bef'
OUTPUT = ROOT / 'outputs/experiments/g31_ics_terminal_flow_20261021/contract_review005_001.json'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(obs, demand=None):
    obs['observation_scope'] = 'controller_policy'
    obs.pop('control_projection', None)
    current = joint.prepare_current(obs, rules.r0_priority_planner(obs), message_delay=2.)
    catalog = joint.build_joint_catalog(current)
    projected = projection.prepare_inventory_projection(obs, forecast=demand, prepared_current=current)
    return current, catalog, projected

def main():
    assert not OUTPUT.exists(), 'immutable output already exists'
    assert sha(MANIFEST) == EXPECTED_MANIFEST_SHA
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    reviewed = [campaign, joint, adapter, rules, projection, control, allocation, orders, protocol]
    source_hashes = {}
    for module in reviewed:
        path = Path(module.__file__).resolve()
        name = path.relative_to(ROOT).as_posix()
        assert sha(path) == manifest['files'][name]
        source_hashes[name] = sha(path)
    results = []

    # Full RecordingPolicy call: a usable provider exists but must never be read.
    calls = []
    def forbidden_forecast(**kwargs):
        calls.append(kwargs)
        raise AssertionError('TF-current called forecast provider')
    plan = dict(method='TF-current', task_id='independent-contract-review',
                policy_version='terminal_flow_v1', transport_config=allocation.DEFAULT_CONFIG,
                recompute_period_seconds=60., projection_horizon_seconds=600.,
                transport_penalty=.01, minimum_gain=0.)
    decisions, observations = [], []
    policy = campaign.RecordingPolicy(plan, forbidden_forecast, decisions, observations)
    obs = observation(source=0, stock=1, remote=True)
    obs['static_role_contract']['loader_nodes'] = [2]
    current, catalog, projected = prepare(obs)
    choice = policy(current, catalog, policy_state={}, decision_context={'tick': 1})
    assert not calls and decisions[0]['forecast_binding'] is None
    assert choice['empty_transport_order']['reason'] == 'ORDINARY_RETURN'
    assert choice['fallback_reason'] == 'flow_no_covered_ordinary_solution_C00'
    assert choice['empty_transport_order']['forecast_guided'] is False
    assert projected.nodes[2]['inventory_known'] is False
    results.append(dict(case='TF-current_no_forecast_and_unknown_ordinary_fallback', passed=True,
                        forecast_calls=0, action=choice['action_id'], fallback=choice['fallback_reason']))

    # The post-priority entry refuses even a newly visible real demand intent.
    session = PublicSession()
    session.current['jobs'] = [dict(business_bag_id='fresh', origin=1, arrival=1., status='waiting_for_tray')]
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    blocked = protocol._post_inventory_return(client, 'A', {'next_tick': 1}, compact=True,
        command_delay=2., priority_error=False)
    assert blocked['reason'] == 'fresh_priority_intents_remain' and not session.transfer_calls
    results.append(dict(case='fresh_real_demand_blocks_post_priority', passed=True))

    # One FIFO-reserved tray and one hard minimum remain, exact real tray survives.
    obs = observation(source=1, stock=3)
    obs['node_contracts'][1]['export_min_stock'] = 1
    obs['jobs'] = [dict(business_bag_id='local', origin=1, arrival=1., status='waiting_for_tray')]
    current, catalog, _ = prepare(obs)
    offers = allocation.build_supply_offers(current, catalog)
    assert set(offers['trays']) == {'E2'}
    assert offers['sources'][1]['fifo_reserved'] == 1
    assert offers['sources'][1]['hard_minimum_reserve'] == 1
    assert offers['sources'][1]['source_cap'] == 1
    results.append(dict(case='real_tray_fifo_and_source_ceiling', passed=True, source_cap=1,
                        eligible_trays=['E2']))

    # An actual soft target is created but does not alter the canonical intent.
    obs = fixture((0, 2, 0))
    current, catalog, projected = prepare(obs, forecast(obs, {2: [10.]+[0.]*29}))
    choice = control.TransportPolicy().select(current, catalog, projected, policy_state={},
                                              decision_context={'tick': 1})
    selected = next(row for row in catalog['candidates'] if row['action_id'] == choice['action_id'])
    decision = adapter.apply_selected_action(current, catalog, choice)
    order = choice['empty_transport_order']
    assert order['target_by'] is not None
    assert decision['intents'][0] == selected['intent']
    assert order['native_expiry'] == selected['intent']['expiry']
    assert not {'target_by', 'useful_until', 'latest_issue_estimate', 'native_business_deadline'} & set(decision['intents'][0])
    results.append(dict(case='soft_target_cannot_change_native_departure_lease', passed=True,
                        target_by=order['target_by'], native_expiry=order['native_expiry']))

    # Lost reply -> JSON restore -> same-tick block -> native immutable-ID retry.
    session = PublicSession()
    session.current['observation_scope'] = 'controller_policy'
    def lose_first(payload):
        session.transfer_calls.append(copy.deepcopy(payload))
        if len(session.transfer_calls) == 1:
            raise RuntimeError('lost_reply')
        return {'status': 'pending'}
    session.submit_protocol_transfer = lose_first
    client = protocol.ProtocolClient(session, inventory_snapshots=True, retry_period=1.)
    class FakeAdapter:
        def __call__(self, current, catalog, *, policy_state, decision_context):
            projected = projection.prepare_inventory_projection(current.observation, prepared_current=current)
            return control.TransportPolicy().select(current, catalog, projected,
                policy_state=policy_state, decision_context=decision_context)
        def on_submission(self, **kwargs):
            orders.record_submission(**kwargs)
    state = {'next_tick': 1}
    options = dict(compact=True, command_delay=2., priority_error=False,
                   stock_return_selector=adapter.JointPostPrioritySelector(FakeAdapter()),
                   stock_return_selector_identity='TF-review')
    try:
        protocol._post_inventory_return(client, 'A', state, **options)
        raise AssertionError('expected lost reply')
    except RuntimeError as error:
        assert str(error) == 'lost_reply'
    state = json.loads(json.dumps(state))
    client = protocol.ProtocolClient(session, state=json.loads(json.dumps(client.state)),
                                    inventory_snapshots=True, retry_period=1.)
    assert protocol._post_inventory_return(client, 'A', state, **options)['reason'] == 'owner_tick_return_quota_spent'
    assert len(session.transfer_calls) == 1
    session.physical_time = 12.
    client.refresh(retry=True)
    assert len(session.transfer_calls) == 2
    assert session.transfer_calls[0] == session.transfer_calls[1]
    order = next(iter(orders.ledger(state['joint_post_priority']['policy_state'])['orders'].values()))
    assert order['request_id'] == session.transfer_calls[0]['request_id']
    assert order['status'] == 'SUBMITTED'
    results.append(dict(case='lost_reply_quota_restore_and_original_id_retry', passed=True,
                        new_attempts=1, physical_send_calls_including_retry=2, immutable_retry=True))

    for name, expected in source_hashes.items():
        assert sha(ROOT / name) == expected
    report = dict(schema='g31.terminal_flow.independent_contract_review.v1',
        source_manifest_sha256=EXPECTED_MANIFEST_SHA, reviewed_source_sha256=source_hashes,
        producer_sha256=sha(Path(__file__)), native_starts=0, full_native_ack_opened=False,
        observations_opened=False, confirmed_defects=[], cases=results,
        result='no_confirmed_defect_in_scoped_review',
        limitations=['Finite pure/fake-client contracts, not native admission or service nonharm certification.',
                     'Existing receipt/capture repair is excluded from this independent scope.'])
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(OUTPUT), 'cases_passed': len(results), 'confirmed_defects': 0,
                      'report_sha256': sha(OUTPUT)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
