"""Find which proposed departures must be admitted together.

For unit-capacity idle nodes, a route requiring another proposed tray's node
induces a dependency. A directed cycle has no sequential admission order;
its strongly connected component needs a joint reservation transaction.
This constructs bundles for supplied witnesses, not optimal routes. The final
physical owner still checks all edge, reception, deadline and source rules.
The proposal layer below is centralized and is explicitly not a private-view
distributed planner; relaxing idle occupancy never grants admission authority.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .joint_transactions import commit_joint, commit_joint_actions
from .routing import RegionalCandidateGenerator
from .runtime import candidate_reservations


def state_key(snapshot):
    return sha256(json.dumps(asdict(snapshot), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class DependencyPlan:
    source_fingerprint: str
    bundles: tuple
    diagnostics: dict


def _components(graph):
    serial, stack, active, index, low, result = 0, [], set(), {}, {}, []

    def visit(node):
        nonlocal serial
        index[node] = low[node] = serial
        serial += 1
        stack.append(node)
        active.add(node)
        for target in sorted(graph[node]):
            if target not in index:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], index[target])
        if low[node] == index[node]:
            component = []
            while True:
                target = stack.pop()
                active.remove(target)
                component.append(target)
                if target == node:
                    break
            result.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    # Tarjan finishes prerequisites before their dependents for edges i -> j.
    return tuple(result)


def plan_dependencies(snapshot, proposals):
    proposals = tuple(proposals)
    by_tray = {p.tray_id: p for p in proposals}
    if len(by_tray) != len(proposals) or any(p.dependency_version != snapshot.version for p in proposals):
        raise ValueError('dependency proposals require unique trays and the same current source version')
    graph = {tray_id: set() for tray_id in by_tray}
    unresolved = {tray_id: set() for tray_id in by_tray}
    evidence = []
    for proposal in proposals:
        for slot in candidate_reservations(snapshot, proposal):
            kind, _, node = slot.resource.partition(':')
            if kind != 'node' or slot.end <= slot.start:
                continue
            blockers = {tray.tray_id for tray in snapshot.trays.values()
                        if tray.tray_id != proposal.tray_id and tray.node == node and tray.tray_id not in snapshot.plans}
            # A free slot needs no coordinated release. At larger capacities
            # all blockers are conservative dependencies, not a minimal set.
            if len(blockers) < snapshot.network.nodes[node].capacity:
                continue
            for blocker in sorted(blockers):
                (graph[proposal.tray_id] if blocker in by_tray else unresolved[proposal.tray_id]).add(blocker)
                evidence.append({'dependent': proposal.tray_id, 'required_departure': blocker,
                                 'resource': slot.resource, 'requested_start': slot.start,
                                 'proposed_release_available': blocker in by_tray})
    components = _components(graph)
    planned = snapshot.clone()
    accepted, rejected, successful = [], [], set()
    for component in components:
        missing = set().union(*(unresolved[t] for t in component))
        failed_dependencies = {d for t in component for d in graph[t] if d not in component and d not in successful}
        if missing or failed_dependencies:
            rejected.append({'trays': component, 'reason': 'unavailable_departure_dependency',
                             'unresolved': sorted(missing), 'failed_dependencies': sorted(failed_dependencies)})
            continue
        bundle = tuple(replace(by_tray[t], dependency_version=planned.version) for t in component)
        verdict = commit_joint(planned, bundle)
        if verdict.accepted:
            successful.update(component)
            accepted.append(bundle)
        else:
            rejected.append({'trays': component, 'reason': verdict.reason})
    return DependencyPlan(state_key(snapshot), tuple(accepted),
        {'method': 'departure_dependency_components_then_physical_batch_validation',
         'dependency_edges': evidence, 'components': components, 'rejected_components': rejected,
         'accepted_tray_count': len(successful), 'proposal_count': len(proposals),
         'joint_component_count': sum(len(b) > 1 for b in accepted),
         'uncommitted_trays': sorted(set(by_tray) - successful),
         'claim': 'feasible admission for supplied witnesses; no route-domain completeness or objective optimality',
         'minimality_scope': 'unit-capacity idle-node dependency graph only; larger capacities use conservative all-blocker dependencies'})


def execute_dependencies(engine, plan):
    if state_key(engine.observe()) != plan.source_fingerprint:
        raise ValueError('stale_dependency_plan')
    for bundle in plan.bundles:
        verdict = commit_joint_actions(engine, bundle)
        if not verdict.accepted:
            raise AssertionError('prevalidated_dependency_bundle_rejected:' + verdict.reason)


def propose_loaded_departures(snapshot, *, horizon=24, expansion_limit=2000):
    """Counterfactual witnesses assume other eligible loads will depart.

    Only eligible uncommitted loaded peers are removed from proposal views.
    Empty/held/in-transit or already committed trays and their calendars stay.
    No removed identity is ever removed from the physical state or ledger.
    """
    eligible = {tray.tray_id for tray in snapshot.trays.values()
                if tray.mode == 'loaded' and tray.node is not None and tray.available_at <= snapshot.now
                and tray.tray_id not in snapshot.plans
                and all(f.tray_id != tray.tray_id for f in snapshot.old_in_transit)}
    proposals, logs = [], []
    for tray_id in sorted(eligible):
        view = snapshot.clone()
        peers = eligible - {tray_id}
        view.trays = {t: tray for t, tray in view.trays.items() if t not in peers}
        view.reservations = tuple(s for s in view.reservations if s.tray_id not in peers)
        view.conditional_forecasts = {t: f for t, f in view.conditional_forecasts.items() if t not in peers}
        generator = RegionalCandidateGenerator(horizon=horizon, expansion_limit=expansion_limit,
                                               deadline_ms=None, dynamic_local=True)
        candidates = generator.generate(view, view.trays[tray_id].bag_id, tray_id, k=1)
        proposals.extend(candidates)
        logs.append({'tray_id': tray_id, 'relaxed_idle_peer_ids': sorted(peers),
                     'search_status': generator.last_search_status, 'expansions': generator.last_expansions,
                     'proposals': [asdict(p) for p in candidates]})
    return tuple(proposals), logs
