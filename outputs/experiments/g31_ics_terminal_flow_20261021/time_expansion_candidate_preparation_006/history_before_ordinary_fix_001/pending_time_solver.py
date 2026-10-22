"""PENDING pure time-plan reference. No native/control/campaign integration.

Complete supplied legal menu, immutable action identities, bounded exhaustive
search, and the frozen005 single-use event simulator. Selected source stock is
reserved from now in this proxy only. Untimed claims require caller fallback.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/sources/terminal_flow_runtime_005'
PROJECTION = SOURCE / 'scripts/experiments/g31_ics_circulation/foundation_airport_inventory_projection.py'
PROJECTION_SHA = '54a149ac946a6ba4a319bb348088dc1f217c6920dbb1fa6ef5f74389421baf2e'
SCHEMA = 'g31.pending_identity_time_plan_reference.v1'


def need(ok, reason):
    if not ok:
        raise ValueError('pending_time_solver:' + reason)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def get(obj, field):
    return obj[field] if isinstance(obj, dict) else getattr(obj, field)


def identity(action):
    return action['tray_id'], action['source'], action['destination'], action['owner_id']


@dataclass(frozen=True)
class Config:
    # All values are explicit call inputs; there are no production defaults.
    horizon_seconds: float
    dispatch_slot_seconds: float
    command_delay_seconds: float
    transport_penalty_weight: float
    delay_cost_model: str
    delay_penalty_weight: float
    marginal_reference_available_offset_seconds: float
    minimum_net_gain: float
    use_forecast: bool
    max_expanded_nodes: int
    max_completed_plans: int
    max_wall_seconds: float

    def validate(self):
        need(self.horizon_seconds == 600. and self.dispatch_slot_seconds == 60., 'fixed_600_horizon_60_slots')
        for name in ('command_delay_seconds', 'transport_penalty_weight', 'delay_penalty_weight',
                     'marginal_reference_available_offset_seconds', 'minimum_net_gain'):
            value = getattr(self, name)
            need(finite(value) and value >= 0, 'finite_nonnegative_' + name)
        need(self.delay_cost_model in ('none', 'linear_excess_over_reference'), 'explicit_delay_cost_model')
        need(type(self.use_forecast) is bool, 'explicit_forecast_mode')
        need(type(self.max_expanded_nodes) is int and self.max_expanded_nodes > 0
             and type(self.max_completed_plans) is int and self.max_completed_plans > 0
             and finite(self.max_wall_seconds) and self.max_wall_seconds > 0, 'explicit_positive_search_limits')


def load_frozen_simulator():
    """Load only the exact two original function ASTs, not actor module imports."""
    raw = PROJECTION.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PROJECTION_SHA, 'frozen005_projection_sha')
    parsed = ast.parse(raw.decode('utf-8'), filename=str(PROJECTION))
    names = ('require', 'simulate_node')
    definitions = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    need({node.name for node in definitions} == set(names) and len(definitions) == 2, 'exact_frozen_function_roster')
    namespace = {'defaultdict': defaultdict}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(PROJECTION), 'exec'), namespace)
    return namespace['simulate_node'], dict(path=str(PROJECTION), sha256=PROJECTION_SHA,
        functions=list(names), loading='verified_original_AST_functions_only_stdlib_defaultdict')


def receiver_caps(receiver_contract, uncredited_claims, known_assignment_coverage):
    """Apply only physical-space deductions; claims are never supply events."""
    claims, requests, trays = Counter(), set(), set()
    extra = Counter()
    for claim in uncredited_claims:
        request, tray, destination = claim['request_id'], claim['physical_tray_id'], claim['destination_terminal']
        need(request and request not in requests and tray not in trays, 'unique_uncredited_claim_identity')
        need(destination in receiver_contract, 'claim_known_receiver_contract')
        requests.add(request); trays.add(tray); claims[destination] += 1
        covered = {row['tray_id'] for row in known_assignment_coverage.get(destination, [])}
        if tray not in covered:
            extra[destination] += 1
    remaining = {}
    for node, contract in receiver_contract.items():
        need(type(contract['known']) is bool and type(contract['available_slots']) is int
             and contract['available_slots'] >= 0, 'receiver_capacity_contract')
        remaining[node] = max(0, contract['available_slots'] - extra[node]) if contract['known'] else 0
    return remaining, dict(claims), dict(extra)


def projection_inputs(projection, config):
    nodes = get(projection, 'nodes')
    result = {}
    if config.use_forecast:
        need(get(projection, 'forecast') is not None, 'forecast_required')
        edges = get(projection, 'forecast_edges')
        need(edges and edges[0] == 0 and edges[-1] >= 600.
             and all(finite(x) for x in edges) and all(a < b for a, b in zip(edges, edges[1:])), 'complete_forecast_horizon')
    else:
        edges = [0., 600.]
    for node, state in nodes.items():
        known = state['inventory_known'] and state['waiting_known']
        means = get(projection, 'forecast_curves')[node] if config.use_forecast else [0.]
        if config.use_forecast:
            missing = get(projection, 'forecast_missing')[node]
            need(len(means) == len(missing) == len(edges) - 1, 'forecast_shape')
            known = known and not any(absent for a, b, absent in zip(edges, edges[1:], missing) if a < 600 and b > 0)
        if not known:
            result[node] = None
            continue
        need(finite(state['stock']) and state['stock'] >= 0 and finite(state['waiting']) and state['waiting'] >= 0
             and finite(state['service_rate']) and state['service_rate'] > 0, 'finite_known_node_state')
        need(all(finite(value) and value >= 0 for a, value in zip(edges, means) if a < 600), 'known_nonnegative_demand')
        events = [(row[0], row[1]) for row in state['events']]
        need(all(finite(at) and at >= 0 and finite(mass) and mass >= 0 for at, mass in events), 'legal_supply_events')
        result[node] = dict(stock=state['stock'], waiting=state['waiting'], supply_events=events,
                            demand_edges=edges, demand_means=means, horizon_seconds=600., service_rate=state['service_rate'])
    return result


def validate_menu(catalog, offers, projection):
    need(catalog['pruning'] == 'none_full_legal_single_move_menu'
         and catalog['catalog_uses_future_plan'] is False, 'complete_supplied_legal_menu_required')
    state = get(projection, 'public_state_digest')
    need(catalog['public_state_digest'] == offers['public_state_digest'] == state
         and offers['catalog_id'] == catalog['catalog_id'], 'same_public_state_and_catalog')
    owner, now = get(projection, 'owner'), get(projection, 'now')
    need(owner == offers['owner_id'] == catalog['owner_id'] and now == offers['now'], 'current_owner_scope')
    need(get(projection, 'horizon_seconds') == 600., 'same_projection_horizon')
    transfers = [row for row in catalog['candidates'] if row['action_type'] == 'transfer']
    need(len({row['action_id'] for row in transfers}) == len(transfers)
         and len({identity(row) for row in transfers}) == len(transfers), 'unique_menu_actions')
    indexed = {identity(row): row for row in transfers}
    offered = [row for tray in offers['trays'].values() for row in tray['legal_actions']]
    need(len(offered) == len(transfers) and {identity(row): row for row in offered} == indexed,
         'no_search_or_forecast_pruning_of_supplied_menu')
    need(set(offers['trays']) == {row['tray_id'] for row in transfers}, 'exact_menu_tray_roster')
    for source, supply in offers['sources'].items():
        need(type(supply['source_cap']) is int and 0 <= supply['source_cap'] <= len(supply['tray_ids'])
             and len(set(supply['tray_ids'])) == len(supply['tray_ids']), 'real_source_cap')
        need(set(supply['tray_ids']) == {tray for tray, offer in offers['trays'].items() if offer['source'] == source},
             'source_exact_tray_roster')
    for tray, offer in offers['trays'].items():
        source = offer['source']
        need(offer['owner_id'] == owner and get(projection, 'actual_by_tray').get(tray) == source,
             'real_current_owned_tray_only')
        need(finite(offer['available_at']) and offer['available_at'] <= now, 'no_future_event_as_current_supply')
        need(source in offers['sources'] and offers['sources'][source]['owner_id'] == owner, 'source_owner')
        for action in offer['legal_actions']:
            need(action['tray_id'] == tray and action['source'] == source and action['owner_id'] == owner
                 and action['source_category'] == offer['source_category'] == offers['sources'][source]['source_category']
                 and action['source_category'] in ('ordinary_return', 'loader_optional')
                 and source != action['destination'], 'immutable_tray_source_owner_category')
            need(finite(action['earliest_departure']) and action['earliest_departure'] >= now
                 and finite(action['static_travel_time']) and action['static_travel_time'] >= 0, 'finite_public_exact_timing')
    return transfers


def schedule_action(action, *, slot, submit, now, offer, config):
    departure = max(offer['available_at'], action['earliest_departure'], submit + config.command_delay_seconds)
    return dict(kind='move', action=copy.deepcopy(action), action_id=action['action_id'],
        tray_id=action['tray_id'], source=action['source'], destination=action['destination'],
        owner_id=action['owner_id'], source_category=action['source_category'], slot_index=slot,
        clock_slot_index=int(round((submit-now)/60.)), submit_at=submit,
        earliest_departure=departure, estimated_arrival=departure+action['static_travel_time'],
        optimistic_advisory_only=True)


def evaluate_plan(plan, node_inputs, baseline, simulate, config, now):
    """One joint evaluation per affected node; no independent-action sum."""
    outgoing, incoming = Counter(), defaultdict(list)
    transport = delay = minimum = 0.
    for row in plan:
        if row['kind'] == 'HOLD':
            continue
        outgoing[row['source']] += 1
        incoming[row['destination']].append((row['estimated_arrival'] - now, 1.))
        travel = row['action']['static_travel_time']
        transport += config.transport_penalty_weight * travel
        if config.delay_cost_model == 'linear_excess_over_reference':
            # An explicitly retained regularizer, not an additional inventory event.
            delay += config.delay_penalty_weight * max(0., row['estimated_arrival'] - now
                - config.marginal_reference_available_offset_seconds)
        if row['source_category'] != 'ordinary_return':
            minimum += config.minimum_net_gain
    details, physical_delta, source_cost = {}, 0., 0.
    for node in sorted(set(outgoing) | set(incoming)):
        params = node_inputs[node]
        need(params is not None, 'cannot_score_unknown_inventory_or_demand')
        stock = params['stock'] - outgoing[node]
        need(stock >= 0, 'source_reserve_cannot_make_negative_stock')
        reserved = simulate(**dict(params, stock=stock))
        combined = simulate(**dict(params, stock=stock, supply_events=params['supply_events'] + incoming[node]))
        delta = combined['backlog_area'] - baseline[node]['backlog_area']
        source_delta = reserved['backlog_area'] - baseline[node]['backlog_area']
        source_cost += source_delta; physical_delta += delta
        details[node] = dict(baseline=baseline[node], after_now_source_reserve=reserved, with_plan_arrivals=combined,
                             source_reserved_quantity=outgoing[node], added_arrival_events=incoming[node],
                             backlog_area_delta=delta, source_opportunity_cost=source_delta)
    objective = physical_delta + transport + delay + minimum
    return dict(objective_cost=objective, net_proxy_gain=-objective, physical_backlog_area_delta=physical_delta,
                source_opportunity_cost=source_cost, transport_cost=transport, delay_regularizer=delay,
                minimum_gain_penalty=minimum, nodes=details,
                source_reserve_assumption='selected_real_source_trays_reserved_from_now_in_proxy_only')


def solve_pending(*, catalog, offers, receiver_contract, projection, uncredited_claims,
                  known_assignment_coverage, next_eligible_tick, config):
    """Return a pending plan, or explicit unsupported requiring baseline fallback.

    The caller supplies a fresh complete menu; this reference does not construct
    permissions, reconcile orders, consume quotas, submit requests or retry.
    """
    config.validate()
    transfers = validate_menu(catalog, offers, projection)
    owner, now = get(projection, 'owner'), get(projection, 'now')
    need(finite(next_eligible_tick) and next_eligible_tick >= now
         and math.isclose((next_eligible_tick-now)/60., round((next_eligible_tick-now)/60.), abs_tol=1e-10),
         'explicit_next_eligible_60_second_tick')
    caps, claim_counts, extra_claims = receiver_caps(receiver_contract, uncredited_claims, known_assignment_coverage)
    protected = [row for row in transfers if row['source_category'] == 'ordinary_return']
    result = dict(schema=SCHEMA, preparation_status='pending_not_enabled', native_execution_authority=False,
        information_asof=now, owner_scope=owner, public_state_digest=get(projection, 'public_state_digest'),
        catalog_id=catalog['catalog_id'], config=asdict(config),
        full_supplied_menu_digest=digest(catalog), full_legal_transfer_count=len(transfers),
        full_legal_tray_count=len(offers['trays']), source_caps={s: row['source_cap'] for s, row in offers['sources'].items()},
        receiver_caps_after_claims=caps, logical_claim_counts=claim_counts, additional_capacity_claim_deductions=extra_claims,
        current_slot_action=None, dispatch_profile=[], baseline_fallback_required=False,
        ordinary_return_present=bool(protected), independent_native_service_gain_claimed=False,
        whole_ICS_optimal_claimed=False, cannot_pass_to_legacy_reranking_adapter=True,
        menu_completeness_scope='exact_supplied_common_catalog_checked; original_menu_builder_not_reexecuted',
        execution_contract='caller must keep priority, quota consumption, same-ID retry, current-menu revalidation and baseline fallback')
    if uncredited_claims:
        result.update(status='unsupported_claim_timing', baseline_fallback_required=True,
            fallback_contract='caller must retain protected ordinary/current baseline; unsupported is not a HOLD command',
            search=dict(applicable=False, expanded_nodes=0, completed_plans=0, candidate_pruning=False),
            pending_claims_added_as_inventory=False)
        return result
    node_inputs = projection_inputs(projection, config)
    for source_node, supply in offers['sources'].items():
        params = node_inputs.get(source_node)
        if params is not None:
            need(supply['source_cap'] <= params['stock'], 'source_cap_exceeds_known_usable_stock')
    static_exclusions, eligible = [], []
    for row in transfers:
        reason = None
        if row['destination'] not in receiver_contract:
            raise ValueError('pending_time_solver:menu_destination_without_receiver_contract')
        if not receiver_contract[row['destination']]['known']:
            reason = 'unknown_receiver_coverage'
        elif node_inputs.get(row['source']) is None or node_inputs.get(row['destination']) is None:
            reason = 'unknown_proxy_state_or_forecast'
        if reason:
            static_exclusions.append(dict(action_id=row['action_id'], identity=list(identity(row)), reason=reason))
        else:
            eligible.append(row)
    result['menu_coverage_exclusions'] = static_exclusions
    protected_ids = {row['action_id'] for row in protected}
    if any(row['action_id'] in protected_ids for row in static_exclusions):
        result.update(status='unsupported_protected_coverage', baseline_fallback_required=True,
            fallback_contract='current protected ordinary return must use original baseline fallback; no guessed receiver slots',
            search=dict(applicable=False, expanded_nodes=0, completed_plans=0, candidate_pruning=False))
        return result
    simulate, source = load_frozen_simulator()
    result['simulator_source'] = source
    baseline = {node: simulate(**params) for node, params in node_inputs.items() if params is not None}
    slots = []
    at = next_eligible_tick
    while at < now + 600.:
        slots.append(at); at += 60.
    def hold(slot):
        return dict(kind='HOLD', owner_id=owner, slot_index=slot, submit_at=slots[slot],
                    clock_slot_index=int(round((slots[slot]-now)/60.)), optimistic_advisory_only=True)
    all_hold = [hold(slot) for slot in range(len(slots))]
    best_plan, best_score = all_hold, evaluate_plan(all_hold, node_inputs, baseline, simulate, config, now)
    def rank(plan, score):
        ordinary_bits = tuple(int(row['kind'] == 'move' and row['source_category'] == 'ordinary_return') for row in plan)
        optional_count = sum(row['kind'] == 'move' and row['source_category'] != 'ordinary_return' for row in plan)
        stable = tuple('~HOLD' if row['kind'] == 'HOLD' else row['action_id'] for row in plan)
        return (-sum(ordinary_bits), tuple(-bit for bit in ordinary_bits), score['objective_cost'], optional_count, stable)
    best_rank = rank(best_plan, best_score)
    eligible.sort(key=lambda row: (row['source_category'] != 'ordinary_return', row['action_id']))
    used_trays, source_used, receiver_used = set(), Counter(), Counter()
    expanded = completed = 0
    rejected = Counter()
    halted = None
    began = time.perf_counter()
    def visit(slot, plan):
        nonlocal expanded, completed, halted, best_plan, best_score, best_rank
        if halted is not None:
            return
        if expanded >= config.max_expanded_nodes:
            halted = 'max_expanded_nodes'; return
        if completed >= config.max_completed_plans:
            halted = 'max_completed_plans'; return
        if time.perf_counter() - began >= config.max_wall_seconds:
            halted = 'max_wall_seconds'; return
        expanded += 1
        if slot == len(slots):
            completed += 1
            score = evaluate_plan(plan, node_inputs, baseline, simulate, config, now)
            value = rank(plan, score)
            if value < best_rank:
                best_plan, best_score, best_rank = copy.deepcopy(plan), score, value
            return
        for action in eligible:
            tray, source_node, destination = action['tray_id'], action['source'], action['destination']
            if tray in used_trays:
                rejected['tray_already_selected'] += 1; continue
            if source_used[source_node] >= offers['sources'][source_node]['source_cap']:
                rejected['source_cap'] += 1; continue
            if receiver_used[destination] >= caps[destination]:
                rejected['receiver_cap'] += 1; continue
            row = schedule_action(action, slot=slot, submit=slots[slot], now=now, offer=offers['trays'][tray], config=config)
            used_trays.add(tray); source_used[source_node] += 1; receiver_used[destination] += 1
            visit(slot+1, plan+[row])
            used_trays.remove(tray); source_used[source_node] -= 1; receiver_used[destination] -= 1
            if halted is not None:
                return
        visit(slot+1, plan+[hold(slot)])
    visit(0, [])
    chosen = [row for row in best_plan if row['kind'] == 'move']
    current = next((copy.deepcopy(row) for row in best_plan if row['submit_at'] == now), None)
    if current is None:
        current = dict(kind='HOLD', owner_id=owner, submit_at=now, reason='no_eligible_owner_tick_now')
    # If search did not establish a protected current action, never silently
    # turn the caller's ordinary obligation into HOLD because of our limitation.
    fallback = bool(protected) and current['kind'] == 'HOLD' and next_eligible_tick == now
    standalone = (evaluate_plan([current], node_inputs, baseline, simulate, config, now)
                  if current['kind'] == 'move' else None)
    result.update(status='capped_approximate' if halted else 'optimal_within_declared_proxy_and_slot_grid',
        current_slot_action=None if fallback else current, dispatch_profile=best_plan, chosen=chosen,
        objective=best_score, baseline_fallback_required=fallback,
        current_slot_standalone_score=standalone,
        current_slot_standalone_gain_positive=None if standalone is None else standalone['net_proxy_gain'] > 0,
        fallback_contract=('current ordinary obligation remains with original baseline; reference HOLD is not a command'
                           if fallback else None),
        search=dict(applicable=True, method='explicit_identity_preserving_enumeration',
            expanded_nodes=expanded, completed_plans=completed, initial_all_HOLD_incumbent=True,
            all_HOLD_incumbent_counted_as_completed_plan=False, cutoff_reason=halted,
            supplied_legal_actions=len(transfers), coverage_supported_actions=len(eligible),
            owner_slots=len(slots), slot_times=slots, forecast_score_pruning=False,
            negative_single_action_pruning=False, beam_used=False,
            exhaustive_over_declared_supported_action_slot_grid=halted is None,
            bound_or_gap=None, wall_seconds=time.perf_counter()-began,
            repeated_partial_feasibility_rejections=dict(rejected)),
        planned_quantity=len(chosen), protected_planned_quantity=sum(row['source_category']=='ordinary_return' for row in chosen),
        HOLD_tray_quantity=len(offers['trays'])-len(chosen),
        pending_claims_added_as_inventory=False,
        future_qualification_and_priority_revalidation_required=True,
        known_committed_ETA_events_preserved=True)
    # Persisted output uses explicit original slot times. No submitter or legacy
    # adapter is called, and no future move is promoted into the current slot.
    need(hashlib.sha256(PROJECTION.read_bytes()).hexdigest() == PROJECTION_SHA, 'frozen_simulator_changed_during_search')
    return result
