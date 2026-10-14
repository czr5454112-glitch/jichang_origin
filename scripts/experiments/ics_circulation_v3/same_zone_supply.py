"""Opt-in central same-zone empty service, with the old cross-zone arm intact.

Both arms enter the same per-demand ranking before any commitment. This expands
the old candidate domain and adds a separately counted search allowance; it is
not equal-compute control. A public temporal-reachability matching guard protects
other source-zone demand, and an exact-node guard also protects firm supply.
Static shortest travel times are optimistic service capabilities, not executable
multi-tray schedules. ExecutionValidator remains the physical authority.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from heapq import heappop, heappush
import json
from time import perf_counter

from .prebalance import (PrebalancePlan, PredictivePrebalancer,
                         known_supply)


@dataclass(frozen=True)
class SameZoneDemand:
    key: str
    node: str
    at: int
    source: str
    unit_id: str | None = None


class _GuardExhausted(Exception):
    pass


@dataclass
class GuardWorkBudget:
    limit: int = 200000
    used: int = 0

    def spend(self):
        if self.used >= self.limit:
            raise _GuardExhausted
        self.used += 1


def _shortest(network, source, budget, cache):
    if source in cache:
        return cache[source]
    adjacency = defaultdict(list)
    for edge in network.edges.values():
        budget.spend()
        if edge.capacity > 0:
            adjacency[edge.source].append((edge.target, edge.travel_time))
    distances, heap = {source: 0}, [(0, source)]
    while heap:
        budget.spend()
        cost, node = heappop(heap)
        if distances[node] != cost:
            continue
        for target, length in adjacency[node]:
            budget.spend()
            new = cost + length
            if new < distances.get(target, float('inf')):
                distances[target] = new
                heappush(heap, (new, target))
    cache[source] = distances
    return distances


def _matching(units, supplies, earliest, cutoff, removed, budget, *, exact=False):
    """Each first release matches at most one demand; iterative augmenting paths."""
    adjacent = {}
    for unit in units:
        adjacent[unit.key] = []
        for supply in supplies:
            budget.spend()
            if supply.tray_id == removed:
                continue
            eligible = (supply.node == unit.node and supply.at <= cutoff) if exact else (
                earliest.get((supply.tray_id, unit.node), float('inf')) <= cutoff)
            if eligible:
                adjacent[unit.key].append(supply.tray_id)
    assigned, matched = {}, {}
    for unit in units:
        stack, seen_units, seen_trays, parent = [unit.key], {unit.key}, set(), {}
        free = None
        while stack and free is None:
            key = stack.pop()
            budget.spend()
            for tray_id in adjacent[key]:
                budget.spend()
                if tray_id in seen_trays:
                    continue
                seen_trays.add(tray_id)
                parent[tray_id] = key
                if tray_id not in assigned:
                    free = tray_id
                    break
                other = assigned[tray_id]
                if other not in seen_units:
                    seen_units.add(other)
                    stack.append(other)
        while free is not None:
            key = parent[free]
            previous = matched.get(key)
            assigned[free], matched[key] = key, free
            free = previous
    return len(matched)


def same_zone_service_guard(snapshot, candidate, units, target_key, *,
                            work_budget=None, horizon_end=None, _distance_cache=None):
    """Protect public source-zone prefixes; no future tape or physical mutation.

    Candidate physical validation is the caller's separate responsibility. The
    guard also checks its full empty path, release timing and source availability.
    All other demands retain their release times. Only the named target may wait
    until the actual candidate usable tick. Remote reachability is optimistic;
    preserving its matching rank does not certify joint capacity feasibility.
    """
    budget = work_budget if work_budget is not None else GuardWorkBudget()
    if horizon_end is not None and (type(horizon_end) is not int or horizon_end < snapshot.now):
        raise ValueError('guard horizon_end must be an integer at or after now')
    start_work = budget.used
    details = {'target_key': target_key, 'tray_id': candidate.tray_id,
               'usable_at': candidate.usable_at, 'prefixes': [],
               'scope': 'source_zone_temporal_reachability_and_firm_node_supply'}

    def finish(reason):
        details['work'] = budget.used - start_work
        details['reason'] = reason
        return reason, details

    tray = snapshot.trays.get(candidate.tray_id)
    if (tray is None or tray.node is None or tray.mode != 'empty' or tray.bag_id is not None
            or tray.available_at > snapshot.now or tray.tray_id in snapshot.plans
            or tray.tray_id in snapshot.empty_targets
            or any(f.tray_id == tray.tray_id for f in snapshot.old_in_transit)):
        return finish('same_zone_source_not_available')
    targets = [u for u in units if u.key == target_key]
    if len({u.key for u in units}) != len(units) or len(targets) != 1:
        return finish('same_zone_target_identity_not_unique')
    target = targets[0]
    network = snapshot.network
    zone = network.nodes[tray.node].logistics_zone
    if (target.node not in network.nodes or target.node != candidate.destination_node
            or target.node == tray.node or network.nodes[target.node].logistics_zone != zone):
        return finish('same_zone_target_mismatch')
    if candidate.bag_id is not None or candidate.prefix_only or not candidate.legs:
        return finish('same_zone_requires_full_empty_path')
    node, tick = tray.node, snapshot.now
    for leg in candidate.legs:
        edge = network.edges.get(leg.edge_id)
        if (edge is None or edge.source != node or edge.capacity <= 0 or leg.depart < tick
                or leg.arrive != leg.depart + edge.travel_time
                or (leg.depart > tick and not network.nodes[node].can_wait)):
            return finish('same_zone_invalid_witness')
        node, tick = edge.target, leg.arrive
    if (node != target.node or candidate.unload_complete != tick
            or candidate.usable_at != tick + snapshot.module.hold_ticks(node)):
        return finish('same_zone_invalid_release_time')
    regional = tuple(u for u in units if network.nodes[u.node].logistics_zone == zone)
    supplies = tuple(s for s in known_supply(snapshot) if network.nodes[s.node].logistics_zone == zone)
    service_at = max(target.at, candidate.usable_at)
    details.update({'source_zone': zone, 'source_owner': network.nodes[tray.node].control_partition,
                    'target_owner': network.nodes[target.node].control_partition,
                    'need_at': target.at, 'service_at': service_at,
                    'supplies': [asdict(s) for s in supplies]})
    try:
        earliest, cutoffs = {}, {snapshot.now, candidate.usable_at, service_at}
        cache = {} if _distance_cache is None else _distance_cache
        for unit in regional:
            cutoffs.add(unit.at)
        for supply in supplies:
            distances = _shortest(network, supply.node, budget, cache)
            for destination in sorted({u.node for u in regional}):
                budget.spend()
                if destination not in distances:
                    continue
                # known_supply already includes its current release-node hold.
                ready = supply.at if destination == supply.node else (
                    supply.at + distances[destination] + snapshot.module.hold_ticks(destination))
                earliest[supply.tray_id, destination] = ready
                cutoffs.add(ready)
        details['earliest_service'] = [dict(tray_id=t, node=n, at=a) for (t, n), a in sorted(earliest.items())]
        if horizon_end is not None:
            cutoffs = {t for t in cutoffs if snapshot.now <= t <= horizon_end} | {horizon_end}
        details['horizon_end'] = horizon_end
        for cutoff in sorted(cutoffs):
            others = tuple(u for u in regional if u.key != target_key and u.at <= cutoff)
            credited = int(service_at <= cutoff)
            # No target credit before its actual usable tick, including backlog.
            prefix = others + ((target,) if credited else ())
            before = _matching(prefix, supplies, earliest, cutoff, None, budget)
            other_before = _matching(others, supplies, earliest, cutoff, None, budget)
            other_after = _matching(others, supplies, earliest, cutoff, tray.tray_id, budget)
            firm_before = _matching(others, supplies, earliest, cutoff, None, budget, exact=True)
            firm_after = _matching(others, supplies, earliest, cutoff, tray.tray_id, budget, exact=True)
            after = other_after + credited
            details['prefixes'].append({'tick': cutoff, 'before': before, 'after': after,
                'other_before': other_before, 'other_after': other_after,
                'firm_other_before': firm_before, 'firm_other_after': firm_after,
                'target_credit': credited})
            if other_after < other_before or firm_after < firm_before or after < before:
                return finish('same_zone_would_degrade_other_prefix')
    except _GuardExhausted:
        return finish('same_zone_guard_work_budget')
    return finish(None)


def _units_from_filtered(snapshot, diagnostics, max_units, budget):
    """Attach stable business IDs or explicit anonymous slots to old filtering."""
    units = {}
    carried = {t.bag_id for t in snapshot.trays.values() if t.bag_id is not None}
    observed = set(snapshot.bags) | set(snapshot.completed) | carried
    duplicate_ids = []

    def add(unit):
        budget.spend()
        previous = units.get(unit.key)
        if previous is not None:
            if (previous.node, previous.at) != (unit.node, unit.at):
                raise ValueError('conflicting published unit identity across forecasts')
            duplicate_ids.append(unit.unit_id)
        else:
            if len(units) >= max_units:
                return False
            units[unit.key] = unit
        return True

    for bag in sorted(snapshot.bags.values(), key=lambda b: b.bag_id):
        if bag.bag_id not in snapshot.completed and bag.bag_id not in carried:
            if not add(SameZoneDemand('identity:' + bag.bag_id, bag.origin, snapshot.now,
                                     'visible_queue:' + bag.bag_id, bag.bag_id)):
                return (), 'same_zone_demand_ledger_limit'
    rows = sorted(diagnostics['accepted_forecasts'], key=lambda row: json.dumps(row, sort_keys=True))
    for row_index, row in enumerate(rows):
        source = 'overdue_identified_forecast' if row['overdue_pending'] else 'published_forecast'
        if 'unit_ids' in row:
            for unit_id in sorted(row['unit_ids']):
                if unit_id in observed:
                    continue
                if not add(SameZoneDemand('identity:' + unit_id, row['node'], row['effective_at'], source, unit_id)):
                    return (), 'same_zone_demand_ledger_limit'
        else:
            for ordinal in range(row['count']):
                if not add(SameZoneDemand(f'anonymous:{row_index}:{ordinal}', row['node'],
                                         row['effective_at'], source)):
                    return (), 'same_zone_demand_ledger_limit'
    diagnostics['duplicate_published_unit_ids_removed'] = duplicate_ids
    return tuple(sorted(units.values(), key=lambda u: (u.at, u.node, u.source, u.key))), None


class SameZoneSupplyPrebalancer(PredictivePrebalancer):
    """Extra same-zone allowance; original cross-zone order and guard preserved.

    max_candidates bounds cross-zone generator calls. max_same_zone_candidates
    bounds additional same-zone calls. max_guard_work bounds graph/adjacency/
    augmenting operations; exceeding it rejects new same-zone candidates only.
    max_guard_demand_units bounds the complete guard ledger; an incomplete ledger
    disables the additional arm, never truncates protection. Wall budgets retain
    the inherited between-search interpretation and are disabled in comparisons.
    """
    def __init__(self, forecasts=(), *, max_same_zone_candidates=32,
                 max_guard_work=200000, max_guard_demand_units=4096, **kwargs):
        for name, value in [('max_same_zone_candidates', max_same_zone_candidates),
                            ('max_guard_work', max_guard_work),
                            ('max_guard_demand_units', max_guard_demand_units)]:
            if type(value) is not int or value < (1 if name == 'max_guard_demand_units' else 0):
                raise ValueError(name + ' must be a nonnegative integer (positive for demand units)')
        super().__init__(forecasts, **kwargs)
        self.max_same_zone_candidates = max_same_zone_candidates
        self.max_guard_work = max_guard_work
        self.max_guard_demand_units = max_guard_demand_units

    def plan(self, snapshot, forecasts):
        if not self.max_same_zone_candidates:
            return super().plan(snapshot, forecasts)
        started = perf_counter()
        scratch = snapshot.clone()
        diagnostics = {'method': 'central_greedy_with_same_zone_supply',
            'snapshot_time': snapshot.now, 'snapshot_version': snapshot.version,
            'horizon_end': snapshot.now + self.planning_horizon,
            'accepted_forecasts': [], 'ignored_forecasts': [], 'donor_rejections': [],
            'candidate_rejections': [], 'proposal_details': [], 'candidate_comparisons': [],
            'pending_empty_obligations': [], 'demand_covered_by_pending_empty_obligation': [],
            'search_calls': 0, 'search_expansions': 0, 'bounded_stop': None,
            'search_calls_by_domain': {'cross_zone': 0, 'same_zone': 0},
            'search_expansions_by_domain': {'cross_zone': 0, 'same_zone': 0},
            'candidate_budget_omissions': {'cross_zone': 0, 'same_zone': 0},
            'same_zone_guards': [], 'irrevocable_existing_plans': len(snapshot.plans),
            'old_in_transit_count': len(snapshot.old_in_transit),
            'limits': {'max_candidates': self.max_candidates,
                'max_same_zone_candidates': self.max_same_zone_candidates,
                'max_total_generator_calls': self.max_candidates + self.max_same_zone_candidates,
                'max_proposals': self.max_proposals, 'max_demand_units': self.max_demand_units,
                'max_guard_work': self.max_guard_work, 'max_guard_demand_units': self.max_guard_demand_units,
                'planning_budget_ms': self.planning_budget_ms},
            'assumptions': ['Extra same-zone action and compute domain, not an equal-budget comparator.',
                'Old cross-zone source-prefix guard and within-domain tray ordering remain unchanged.',
                'Named target units deduplicate exact cross-forecast identities; conflicting locations/releases fail closed. The old cross-zone guard still uses its original aggregated demand.',
                'Only first known releases count; each matches at most one unit per prefix.',
                'Static positive-capacity full-graph travel plus hold gives optimistic temporal reachability, not joint physical feasibility.',
                'Other temporal matching and firm-node matching ranks may not drop; only the target can wait until actual usable_at.',
                'Existing empty obligations remain irrevocable; no unknown ETA is invented.',
                'All complete empty witnesses pass the unchanged execution validator before commitment.']}
        old_demand = self._demand(snapshot, forecasts, diagnostics)
        guard_budget, distance_cache = GuardWorkBudget(self.max_guard_work), {}
        try:
            units, ledger_stop = _units_from_filtered(snapshot, diagnostics, self.max_guard_demand_units, guard_budget)
        except _GuardExhausted:
            units, ledger_stop = (), 'same_zone_guard_work_budget'
        diagnostics['demand_expansion_work'] = guard_budget.used
        protected = sorted(b.bag_id for b in snapshot.bags.values() if b.protected
            and b.bag_id not in snapshot.completed and not any(p.bag_id == b.bag_id for p in snapshot.plans.values()))
        diagnostics['same_zone_enhancement_blocked'] = ledger_stop or ('unadmitted_protected_obligation' if protected else None)
        diagnostics['unadmitted_protected_bag_ids'] = protected
        diagnostics['demand_units'] = [asdict(u) for u in units]
        diagnostics['demand'] = [asdict(e) for e in old_demand]
        initial = known_supply(snapshot)
        diagnostics['initial_supply'] = [asdict(s) for s in initial]
        known_ids = {s.tray_id for s in initial}
        diagnostics['pending_empty_obligations'] = [dict(tray_id=t, destination=n, final_available_at=None)
            for t, n in sorted(snapshot.empty_targets.items()) if t not in known_ids]
        # A guard ledger overflow disables enhancement but retains old bounded
        # target planning and its complete aggregated cross-zone protection.
        if ledger_stop:
            slots = []
            for index, event in enumerate(old_demand):
                slots.extend(SameZoneDemand(f'fallback:{index}:{j}', event.node, event.at, event.source)
                             for j in range(min(event.count, self.max_demand_units - len(slots))))
        else:
            slots = list(units[:self.max_demand_units])
        diagnostics['demand_units_truncated'] = sum(e.count for e in old_demand) > len(slots)
        proposals, node_ordinals = [], defaultdict(int)
        quotas = {'cross_zone': self.max_candidates, 'same_zone': self.max_same_zone_candidates}

        def global_stop():
            if len(proposals) >= self.max_proposals:
                diagnostics['bounded_stop'] = 'max_proposals'
            elif self.planning_budget_ms is not None and (perf_counter() - started) * 1000 >= self.planning_budget_ms:
                diagnostics['bounded_stop'] = 'planning_budget_between_searches'
            return diagnostics['bounded_stop'] is not None

        for target in slots:
            ordinal = node_ordinals[target.node]
            node_ordinals[target.node] += 1
            if global_stop():
                break
            supplies = known_supply(scratch)
            known_ids = {s.tray_id for s in supplies}
            pending = sum(n == target.node and t not in known_ids for t, n in scratch.empty_targets.items())
            if ordinal < pending:
                diagnostics['demand_covered_by_pending_empty_obligation'].append(
                    dict(target_key=target.key, node=target.node, need_at=target.at, ordinal=ordinal,
                         reason='accepted_empty_continuation_final_eta_unknown'))
                continue
            ordinal -= pending
            at_target = sorted((s.at, s.tray_id) for s in supplies if s.node == target.node)
            promised_at = at_target[ordinal][0] if ordinal < len(at_target) else None
            if promised_at is not None and promised_at <= target.at:
                continue
            pools = {'cross_zone': [], 'same_zone': []}
            for tray_id, tray in sorted(scratch.trays.items()):
                if (tray.mode != 'empty' or tray.node is None or tray.available_at > scratch.now
                        or tray.bag_id is not None or tray_id in scratch.plans or tray_id in scratch.empty_targets
                        or any(f.tray_id == tray_id for f in scratch.old_in_transit)):
                    continue
                domain = ('same_zone' if scratch.network.nodes[tray.node].logistics_zone ==
                          scratch.network.nodes[target.node].logistics_zone else 'cross_zone')
                if domain == 'same_zone':
                    if tray.node == target.node or diagnostics['same_zone_enhancement_blocked']:
                        continue
                else:
                    reason = self._donor_protection(scratch, tray_id, supplies, old_demand)
                    if reason:
                        diagnostics['donor_rejections'].append(dict(tray_id=tray_id, node=target.node, reason=reason))
                        continue
                pools[domain].append(tray_id)
            order = [(domain, pool[index]) for index in range(max(map(len, pools.values()), default=0))
                     for domain, pool in pools.items() if index < len(pool)]
            choices = []
            for domain, tray_id in order:
                if global_stop():
                    break
                if diagnostics['search_calls_by_domain'][domain] >= quotas[domain]:
                    diagnostics['candidate_budget_omissions'][domain] += 1
                    continue
                generator = self.generator_factory()
                diagnostics['search_calls_by_domain'][domain] += 1
                diagnostics['search_calls'] += 1
                generated = generator.generate_empty(scratch, tray_id, target.node, k=1)
                expansions = getattr(generator, 'last_expansions', 0)
                diagnostics['search_expansions_by_domain'][domain] += expansions
                diagnostics['search_expansions'] += expansions
                reason = None
                if not generated:
                    reason = 'no_feasible_candidate'
                    if domain == 'same_zone':
                        status = getattr(generator, 'last_search_status', 'unknown')
                        reason = ('same_zone_search_budget_unknown' if status in (
                            'exhausted', 'expansion_budget_exhausted', 'deadline_exhausted') else
                            'same_zone_static_unreachable' if status == 'static_unreachable' else
                            'same_zone_search_no_candidate')
                else:
                    candidate = generated[0]
                    if candidate.tray_id != tray_id or candidate.bag_id is not None or candidate.destination_node != target.node:
                        reason = 'candidate_identity_or_destination_mismatch'
                    else:
                        result = self.validator.validate(scratch, candidate)
                        if not result.accepted:
                            reason = result.reason
                        elif promised_at is not None and candidate.usable_at >= promised_at:
                            reason = 'existing_supply_arrives_no_later'
                if reason:
                    diagnostics['candidate_rejections'].append(dict(tray_id=tray_id, target_key=target.key,
                        domain=domain, reason=reason, search_status=getattr(generator, 'last_search_status', 'unknown')))
                    continue
                shift = max(0, target.at - candidate.usable_at)
                if shift:
                    delayed = replace(candidate, legs=tuple(replace(leg, depart=leg.depart + shift,
                        arrive=leg.arrive + shift) for leg in candidate.legs),
                        unload_complete=candidate.unload_complete + shift, usable_at=candidate.usable_at + shift)
                    if self.validator.validate(scratch, delayed).accepted:
                        candidate = delayed
                if domain == 'same_zone':
                    reason, guard = same_zone_service_guard(scratch, candidate, units, target.key,
                        work_budget=guard_budget, horizon_end=snapshot.now + self.planning_horizon,
                        _distance_cache=distance_cache)
                    diagnostics['same_zone_guards'].append(guard)
                    if reason:
                        diagnostics['candidate_rejections'].append(dict(tray_id=tray_id, target_key=target.key,
                            domain=domain, reason=reason))
                        continue
                choices.append((candidate, domain))
            def rank(item):
                candidate = item[0]
                return (max(0, candidate.usable_at - target.at),
                        sum(scratch.network.edges[leg.edge_id].travel_time for leg in candidate.legs), candidate.tray_id)
            ranked = sorted(choices, key=rank)
            diagnostics['candidate_comparisons'].append(dict(target_key=target.key, node=target.node,
                need_at=target.at, candidates=[dict(tray_id=c.tray_id, domain=d, usable_at=c.usable_at,
                    first_depart=c.legs[0].depart if c.legs else scratch.now, rank=list(rank((c, d)))) for c, d in ranked]))
            if not ranked:
                continue
            choice, domain = ranked[0]
            result = self.validator.commit(scratch, choice)
            if not result.accepted:
                diagnostics['candidate_rejections'].append(dict(tray_id=choice.tray_id, reason=result.reason))
                continue
            proposals.append(choice)
            diagnostics['proposal_details'].append(dict(tray_id=choice.tray_id, destination=target.node,
                target_key=target.key, unit_id=target.unit_id, domain=domain, need_at=target.at,
                usable_at=choice.usable_at, first_depart=choice.legs[0].depart if choice.legs else scratch.now,
                previous_supply_at=promised_at, dependency_version=choice.dependency_version))
        diagnostics['guard_work'] = guard_budget.used
        diagnostics['guard_distance_source_count'] = len(distance_cache)
        diagnostics['proposal_count'] = len(proposals)
        diagnostics['elapsed_ms'] = (perf_counter() - started) * 1000
        return PrebalancePlan(tuple(proposals), diagnostics)
