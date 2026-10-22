"""Tiny synthetic pure cases; no real TRAIN/DEV records or native imports."""
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import pytest

PATH = Path(__file__).with_name('pending_time_solver.py')
spec = importlib.util.spec_from_file_location('pending_time_solver_tested', PATH)
w = importlib.util.module_from_spec(spec); sys.modules[spec.name] = w; spec.loader.exec_module(w)


def config(**updates):
    values = dict(horizon_seconds=600., dispatch_slot_seconds=60., command_delay_seconds=2.,
        transport_penalty_weight=.01, delay_cost_model='none', delay_penalty_weight=0.,
        marginal_reference_available_offset_seconds=2., minimum_net_gain=0., use_forecast=False,
        max_expanded_nodes=30000, max_completed_plans=10000, max_wall_seconds=20.)
    values.update(updates)
    return w.Config(**values)


def scene(specs, *, stocks=None, waiting=None, curves=None, edges=None, caps=None):
    """Specs=(tray,source,destination,travel[,category]); legal-menu producer fixture."""
    owner, now = 'owner:synthetic', 0.
    nodes = sorted({node for row in specs for node in row[1:3]})
    source_nodes = {row[1] for row in specs}
    actions, trays, sources = [], {}, {}
    for row in specs:
        tray, source, destination, travel = row[:4]
        category = row[4] if len(row) > 4 else 'loader_optional'
        action = dict(action_type='transfer', action_id=f'{tray}:{source}:{destination}', tray_id=tray,
            source=source, destination=destination, owner_id=owner, source_category=category,
            earliest_departure=2., static_travel_time=travel, nominal_arrival_time=2.+travel)
        actions.append(action)
        offer = trays.setdefault(tray, dict(tray_id=tray, source=source, owner_id=owner,
            source_category=category, available_at=0., legal_actions=[]))
        offer['legal_actions'].append(copy.deepcopy(action))
        supply = sources.setdefault(source, dict(source=source, owner_id=owner, source_category=category, tray_ids=[]))
        if tray not in supply['tray_ids']: supply['tray_ids'].append(tray)
    for source, supply in sources.items(): supply['source_cap'] = (caps or {}).get(source, len(supply['tray_ids']))
    catalog = dict(catalog_id='synthetic-full-menu', public_state_digest='synthetic-public-state', owner_id=owner,
        pruning='none_full_legal_single_move_menu', catalog_uses_future_plan=False,
        candidates=[dict(action_type='noop', action_id='noop')]+actions)
    offers = dict(catalog_id=catalog['catalog_id'], public_state_digest=catalog['public_state_digest'],
        owner_id=owner, now=now, sources=sources, trays=trays)
    node_states = {node: dict(stock=(stocks or {}).get(node, 2. if node in source_nodes else 0.),
        waiting=(waiting or {}).get(node, 0. if node in source_nodes else 1.),
        inventory_known=True, waiting_known=True, service_rate=100., events=[]) for node in nodes}
    projection = dict(now=now, owner=owner, public_state_digest=catalog['public_state_digest'], horizon_seconds=600.,
        actual_by_tray={tray: row['source'] for tray, row in trays.items()}, nodes=node_states,
        forecast={} if curves is not None else None, forecast_edges=edges or [0., 600.],
        forecast_curves={node: (curves or {}).get(node, [0.] * (len(edges or [0., 600.])-1)) for node in nodes},
        forecast_missing={node: [False] * (len(edges or [0., 600.])-1) for node in nodes})
    return dict(catalog=catalog, offers=offers, projection=projection,
        receiver_contract={node: dict(known=True, available_slots=4) for node in nodes},
        uncredited_claims=[], known_assignment_coverage={}, next_eligible_tick=0., config=config(use_forecast=curves is not None))


def moves(result):
    return [row for row in result['dispatch_profile'] if row['kind'] == 'move']


def test_shared_slot_cannot_switch_real_source_or_legal_destination():
    case = scene([('A', 1, 10, .125), ('B', 2, 20, .125)])
    case['receiver_contract'][10]['available_slots'] = 0
    result = w.solve_pending(**case)
    chosen = moves(result)
    assert len(chosen) == 1 and (chosen[0]['tray_id'], chosen[0]['source'], chosen[0]['destination']) == ('B', 2, 20)
    assert result['whole_ICS_optimal_claimed'] is False


def test_owner_quota_fractional_eta_and_future_slots_are_not_collapsed():
    result = w.solve_pending(**scene([('A', 1, 10, .125), ('B', 2, 20, .375)]))
    chosen = moves(result)
    assert [row['submit_at'] for row in chosen] == [0., 60.]
    assert len({(row['owner_id'], row['submit_at']) for row in chosen}) == 2
    assert [row['estimated_arrival'] for row in chosen] == [2.125, 62.375]
    assert result['current_slot_action']['tray_id'] == 'A'


def test_same_tray_cannot_be_sent_twice_to_two_receivers():
    result = w.solve_pending(**scene([('A', 1, 10, 1.), ('A', 1, 20, 2.)]))
    assert len(moves(result)) == 1
    assert result['search']['repeated_partial_feasibility_rejections']['tray_already_selected'] > 0


def test_source_cap_and_shared_receiver_cap_are_hard_limits():
    case = scene([('A', 1, 10, 1.), ('B', 1, 20, 2.), ('C', 2, 10, 3.)], caps={1: 1, 2: 1})
    case['receiver_contract'][10]['available_slots'] = 1
    chosen = moves(w.solve_pending(**case))
    assert sum(row['source'] == 1 for row in chosen) <= 1
    assert sum(row['destination'] == 10 for row in chosen) <= 1
    assert len(chosen) == 2


def test_multisource_exact_eta_can_outweigh_positive_source_opportunity_cost():
    case = scene([('cheap_late', 1, 10, 500.125), ('valuable_early', 2, 10, 50.375)],
        waiting={1: 0., 2: 0., 10: 1.}, curves={1: [0., 0., 0.], 2: [0., 2., 0.], 10: [0., 0., 0.]},
        edges=[0., 400., 401., 600.])
    case['receiver_contract'][10]['available_slots'] = 1
    result = w.solve_pending(**case)
    assert result['current_slot_action']['tray_id'] == 'valuable_early'
    assert result['objective']['source_opportunity_cost'] > 0
    assert result['current_slot_action']['estimated_arrival'] == 52.375


def test_high_source_future_demand_can_make_hold_best():
    case = scene([('A', 1, 10, 400.)], waiting={1: 0., 10: 1.},
                 curves={1: [2., 0.], 10: [0., 0.]}, edges=[0., 1., 600.])
    result = w.solve_pending(**case)
    assert result['current_slot_action']['kind'] == 'HOLD'
    assert result['planned_quantity'] == 0 and result['objective']['net_proxy_gain'] == 0.


def test_two_individually_nonpositive_moves_can_have_positive_joint_value():
    case = scene([('A', 1, 2, 1.), ('B', 2, 10, 450.)], waiting={1: 0., 2: 0., 10: 0.},
        curves={1: [0., 0., 0.], 2: [0., 2., 0.], 10: [1., 0., 0.]}, edges=[0., 100., 101., 600.])
    simulate, _ = w.load_frozen_simulator()
    params = w.projection_inputs(case['projection'], case['config'])
    baseline = {node: simulate(**values) for node, values in params.items()}
    for action in case['catalog']['candidates'][1:]:
        planned = w.schedule_action(action, slot=0, submit=0., now=0.,
            offer=case['offers']['trays'][action['tray_id']], config=case['config'])
        single = w.evaluate_plan([planned], params, baseline, simulate, case['config'], 0.)
        assert single['net_proxy_gain'] <= 0
    result = w.solve_pending(**case)
    assert result['planned_quantity'] == 2 and result['objective']['net_proxy_gain'] > 0
    assert result['search']['negative_single_action_pruning'] is False
    assert result['current_slot_standalone_gain_positive'] is False


def test_ordinary_return_is_earliest_even_if_optional_would_score_higher():
    case = scene([('ordinary', 1, 10, 100., 'ordinary_return'), ('optional', 2, 20, .125)],
                 waiting={1: 0., 2: 0., 10: 0., 20: 5.})
    result = w.solve_pending(**case)
    assert result['current_slot_action']['source_category'] == 'ordinary_return'
    assert result['protected_planned_quantity'] == 1
    assert moves(result)[1]['submit_at'] == 60.


def test_unknown_ordinary_coverage_requests_baseline_never_silent_hold():
    case = scene([('ordinary', 1, 10, 1., 'ordinary_return'), ('optional', 2, 20, 1.)])
    case['receiver_contract'][10]['known'] = False
    result = w.solve_pending(**case)
    assert result['status'] == 'unsupported_protected_coverage'
    assert result['current_slot_action'] is None and result['baseline_fallback_required']


@pytest.mark.parametrize('covered,expected_remaining', [(False, 1), (True, 2)])
def test_untimed_claim_deducts_only_uncovered_capacity_and_requires_fallback(covered, expected_remaining):
    case = scene([('A', 1, 10, 1., 'ordinary_return')])
    case['receiver_contract'][10]['available_slots'] = 2
    case['uncredited_claims'] = [dict(request_id='accepted-or-pending', physical_tray_id='other-owner-tray', destination_terminal=10)]
    if covered: case['known_assignment_coverage'] = {10: [dict(tray_id='other-owner-tray')]}
    before = copy.deepcopy(case['projection'])
    result = w.solve_pending(**case)
    assert result['status'] == 'unsupported_claim_timing'
    assert result['receiver_caps_after_claims'][10] == expected_remaining
    assert result['baseline_fallback_required'] and result['current_slot_action'] is None
    assert result['pending_claims_added_as_inventory'] is False and case['projection'] == before


def test_current_tick_already_spent_preserves_future_slot_without_promotion():
    case = scene([('A', 1, 10, .125)]); case['next_eligible_tick'] = 60.
    result = w.solve_pending(**case)
    assert result['current_slot_action']['kind'] == 'HOLD'
    assert moves(result)[0]['submit_at'] == 60. and moves(result)[0]['estimated_arrival'] == 62.125
    assert json.loads(json.dumps(result))['dispatch_profile'][0]['submit_at'] == 60.


def test_cutoff_is_explicit_and_does_not_disable_ordinary_baseline():
    case = scene([('A', 1, 10, 1., 'ordinary_return')])
    case['config'] = replace(case['config'], max_expanded_nodes=1)
    result = w.solve_pending(**case)
    assert result['status'] == 'capped_approximate'
    assert result['search']['cutoff_reason'] == 'max_expanded_nodes' and result['search']['bound_or_gap'] is None
    assert result['baseline_fallback_required'] and result['current_slot_action'] is None


def test_complete_reference_search_has_no_claim_of_ICS_optimality_and_no_input_mutation():
    case = scene([('A', 1, 10, 1.)]); before = copy.deepcopy(case)
    result = w.solve_pending(**case)
    assert result['status'] == 'optimal_within_declared_proxy_and_slot_grid'
    assert result['search']['completed_plans'] == 11  # Ten immutable slots or all HOLD.
    assert result['search']['exhaustive_over_declared_supported_action_slot_grid']
    assert result['preparation_status'] == 'pending_not_enabled' and not result['native_execution_authority']
    assert case == before


def test_committed_supply_keeps_original_fractional_eta():
    case = scene([('A', 1, 10, 1.)])
    case['projection']['nodes'][10]['events'] = [(10.375, 1., 'accepted_inbound')]
    simulate, _ = w.load_frozen_simulator()
    params = w.projection_inputs(case['projection'], case['config'])
    assert params[10]['supply_events'] == [(10.375, 1.)]
    result = w.solve_pending(**case)
    assert result['known_committed_ETA_events_preserved']


def test_arrival_outside_600_seconds_is_not_credited_inside_horizon():
    result = w.solve_pending(**scene([('A', 1, 10, 600.125)]))
    assert result['planned_quantity'] == 0 and result['current_slot_action']['kind'] == 'HOLD'


def test_completed_plan_budget_is_reported_as_approximate_not_zero_gap():
    case = scene([('A', 1, 10, 1.)])
    case['config'] = replace(case['config'], max_completed_plans=1)
    result = w.solve_pending(**case)
    assert result['status'] == 'capped_approximate'
    assert result['search']['completed_plans'] == 1
    assert result['search']['cutoff_reason'] == 'max_completed_plans'
    assert result['search']['bound_or_gap'] is None


@pytest.mark.parametrize('alter,reason', [
    (lambda c: c['offers']['trays']['A']['legal_actions'].clear(), 'no_search_or_forecast_pruning'),
    (lambda c: c['offers']['trays']['A'].update(available_at=60.), 'no_future_event_as_current_supply'),
    (lambda c: c['projection']['actual_by_tray'].update(A=999), 'real_current_owned_tray'),
    (lambda c: c['offers']['trays']['A'].update(owner_id='owner:other'), 'real_current_owned_tray'),
])
def test_illegal_identity_or_hidden_menu_pruning_is_rejected(alter, reason):
    case = scene([('A', 1, 10, 1.)]); alter(case)
    with pytest.raises(ValueError, match=reason): w.solve_pending(**case)
