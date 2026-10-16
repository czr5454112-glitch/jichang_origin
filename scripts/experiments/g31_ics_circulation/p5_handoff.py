"""Finite handoff proposals: receiving entitlements and downstream service slack.

The ordinary service-aware comparator is deliberately strong. No proposal
owns physics, grants a receiving right, or certifies a conditional forecast.
"""
from __future__ import annotations

import itertools
import math
import time

from .analytic_control import PublicTravel, _min_cost_matching, conditional_service_windows, transfer_candidates
from .boundary_reference import ObligationWindow, capacity_violations
from .joint_window_repair import _footprint, digest
from .local_context import LocalContextToken, PROTOCOL_OBSERVATION, protocol_projection
from .native_host import prepare_input

HORIZON = 160.
FACTORS = [
    {"name": "storage_slack_alternative_supply", "storage_release": 10., "p_load": 2., "reserve_third": False},
    {"name": "no_storage_slack", "storage_release": 0., "p_load": 2., "reserve_third": False},
    {"name": "third_source_reserve", "storage_release": 10., "p_load": 2., "reserve_third": True},
    {"name": "no_simultaneous_receiving_window", "storage_release": 10., "p_load": 8., "reserve_third": False},
]


def scenario_input(spec: dict) -> dict:
    edges = [(9, 0, .4, 1.), (10, 1, .4, 1.), (11, 2, .4, 1.),
             (0, 3, 2., 1.), (0, 4, 100., 1.), (1, 3, .9, 1.), (1, 4, .1, 1.),
             (2, 3, 50., 1.), (2, 4, 2., 1.), (3, 5, .4, 1.),
             (4, 6, .4, 1.), (6, 13, .4, 1.), (7, 3, 2., 1.), (3, 8, .5, 1.)]
    owner = lambda n: "A" if n in (0, 1, 2, 3, 4, 6, 9, 10, 11) else "C"
    zone = lambda n: "receiving" if n in (3, 4, 6) else "supply" if owner(n) == "A" else "protected"
    jobs = [{"business_bag_id": name, "origin": source, "destination": target,
             "arrival": 0., "deadline": 150., "load_seconds": load,
             "unload_seconds": .1, "hold_seconds": .1,
             "protected_service": True, "allow_suffix_reroute": False}
            for name, source, target, load in [("U0", 9, 0, .1), ("U1", 10, 1, .1),
                ("U2", 11, 2, .1), ("D0", 3, 5, .1), ("D1", 4, 13, .1), ("P", 7, 8, spec["p_load"])]]
    jobs[4].update(storage_node=6, storage_release_at=spec["storage_release"], storage_min_dwell=.1)
    return prepare_input({"schema": "g31.circulation.input.v1",
        "model_scope": "independent synthetic handoff factor; common A owner across distinct supply/receiving zones; not original map",
        "node_records": [(n, 1, .05, n, 0, [v for u, v, _, _ in edges if u == n]) for n in range(14)],
        "edge_records": edges,
        "node_contracts": [{"node": n, "zone": zone(n), "resource_owner": owner(n), "capacity": 1,
                            "export_min_stock": 1 if n == 2 and spec["reserve_third"] else 0} for n in range(14)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": .2} for u, v, _, _ in edges],
        "trays": [{"tray_id": f"T{i}", "node": 9+i} for i in range(3)] + [{"tray_id": "TP", "node": 7}],
        "jobs": jobs, "transfers": [], "faults": [],
        "options": {"max_simulation_time": HORIZON+1., "max_events": 100000}})


def predicted_completion(job: dict, arrival: float, travel: PublicTravel) -> float:
    required = {"destination", "load_seconds", "unload_seconds", "storage_node",
                "storage_release_at", "storage_min_dwell"}
    if not required.issubset(job):
        raise ValueError("handoff:local_full_service_contract_required")
    ready, location = arrival + job["load_seconds"], int(job["origin"])
    if int(job["storage_node"]) >= 0:
        location = int(job["storage_node"])
        entered = ready + travel.complete(int(job["origin"]), location)
        ready = max(entered + job["storage_min_dwell"], job["storage_release_at"])
    return ready + travel.complete(location, int(job["destination"])) + job["unload_seconds"]


def _physical_key(action):
    return tuple(sorted((c["supply"], c["demand"], c["request"]["earliest_departure"]) for c in action["candidates"]))


def _cost(action, service=True):
    return (-len(action["candidates"]), action["completion_sum"] if service else action["arrival_sum"],
            action["arrival_sum"], _physical_key(action))


def build_domain(observation: dict, *, max_actions=64, message_delay=.1) -> dict:
    """Dispatch versioned protocol views; retain the historical v1 entry.

    New online code should call ``build_protocol_domain`` explicitly. Existing
    v1 experiments keep their original request/read-set encoding through
    ``build_legacy_domain`` and are not silently relabelled protocol evidence.
    """
    if observation.get("schema") == PROTOCOL_OBSERVATION:
        return build_protocol_domain(observation, max_actions=max_actions, message_delay=message_delay)
    return build_legacy_domain(observation, max_actions=max_actions, message_delay=message_delay)


def build_legacy_domain(observation: dict, *, max_actions=64, message_delay=.1) -> dict:
    """Historical finite-domain v1 compatibility; not an online protocol view."""
    if observation.get("schema") == PROTOCOL_OBSERVATION or "version" not in observation:
        raise ValueError("handoff:legacy_versioned_observation_required")
    return _build_domain(observation, max_actions=max_actions, message_delay=message_delay)


def build_protocol_domain(observation: dict, *, max_actions=64, message_delay=.1) -> dict:
    """Use only local sensors, client payloads and actually delivered messages."""
    view = protocol_projection(observation)
    context = LocalContextToken.from_observation(view)
    # The compact analytic view omits waiting service contracts. Do not turn
    # that optimization into access to private jobs or invented durations.
    if "control_projection" in view:
        return {"status": "unknown_full_service_projection_required", "actions": [],
                "schema": "g31.handoff_protocol_domain.v2", "local_context": context.to_dict(),
                "message_requirements": [{"kind": "local_full_observation", "owner_id": view["owner_id"]}]}
    result = _build_domain(view, max_actions=max_actions, message_delay=message_delay, context=context)
    result.update(schema="g31.handoff_protocol_domain.v2", local_context=context.to_dict(),
                  decision_identity=context.identity,
                  executable_status="unknown_until_native_owner_delivery_revalidation")
    return result


def submit_protocol_action(client, action: dict, observation: dict) -> dict:
    """Enqueue a proposal with distinct client IDs and saved decision evidence.

    This checks fresh *local* provenance once before the bundle. It provides
    no atomic commit: source and receiver validate each delivered request, and
    only a delivered ACK may resolve it. Retries use the saved client outbox.
    """
    context = LocalContextToken.from_observation(observation)
    if action.get("public_read_sha256") != context.identity:
        raise ValueError("handoff:action_context_mismatch")
    current = LocalContextToken.from_observation(client.view(context.owner_id, compact=False))
    if current != context:
        return {"status": "unknown_changed_local_context", "submissions": [], "atomic": False}
    # Validate the entire bundle before its first side effect.
    for candidate in action["candidates"]:
        request = candidate["request"]
        if "expected_version" in request or "request_id" in request:
            raise ValueError("handoff:protocol_requires_client_request_identity")
        if request.get("owner_id") != context.owner_id or request.get("decision_context") != context.to_dict():
            raise ValueError("handoff:candidate_context_mismatch")
    rows = []
    for candidate in action["candidates"]:
        identity, reply = client.submit(context.owner_id, "transfer", candidate["request"])
        rows.append({"candidate_id": candidate["candidate_id"], "request_id": identity, "reply": reply})
    return {"status": "submitted" if rows else "wait", "submissions": rows, "atomic": False,
            "decision_identity": context.identity, "physical_resolution": "unknown_until_delivered_ack"}


def _build_domain(observation: dict, *, max_actions=64, message_delay=.1, context=None) -> dict:
    """All injective partial assignments, earliest/first receiver-window exit.

    Every strategy receives the same lawful owner projection and this same
    finite domain. The only protected window is an actually delivered native
    service forecast. Candidate terminal leases start at predicted grant,
    unlike the old transit-only approximation. Their ends are conditional.
    """
    started = time.perf_counter()
    base = transfer_candidates(observation, predictive=True, message_delay=message_delay,
        terminal_clearing=False, respect_service_forecasts=True, request_prefix="handoff-base")
    if context is not None:
        # Analytic v1 defaults its old version metadata to zero. It is neither
        # a protocol version nor an execution precondition; omit it entirely.
        base.pop("version", None)
        for row in base["supplies"] + base["forecasts"]:
            row.pop("version", None)
        for request in base["intents"]:
            request.pop("expected_version", None)
            request.pop("request_id", None)
            request["decision_context"] = context.to_dict()
    if len(base["supplies"]) > 3 or len(base["demands"]) > 2:
        return {"status": "unknown_domain_budget", "actions": [], "base": base}
    local = {j["business_bag_id"]: j for j in observation["jobs"]}
    missing = [j for j in base["demands"] if j["business_bag_id"] not in local]
    if missing:
        contracts = {n["node"]: n for n in observation["node_contracts"]}
        return {"status": "unknown_private_service_contract", "actions": [], "base": base,
                "message_requirements": [{"kind": "conditional_service_contract",
                    "source_owner": contracts[j["origin"]].get("resource_owner", contracts[j["origin"]]["zone"]),
                    "target_owner": observation["owner_id"], "business_bag_id": j["business_bag_id"],
                    "required": ["service_completion_conditions", "route_applicability", "valid_until", "revocation_identity"],
                    "status": "required_message_not_available_in_current_native_protocol"} for j in missing]}
    travel = PublicTravel(observation)
    capacities = {f"node:{n['node']}": n["capacity"] for n in observation["node_contracts"]}
    capacities.update({f"edge:{e['from']}:{e['to']}": e["capacity"] for e in observation["edge_contracts"]})
    capacities.update({f"headway:{e['from']}:{e['to']}": 1 for e in observation["edge_contracts"]})
    messages = conditional_service_windows(observation)
    frozen = [{"task": "service:"+m["message_id"], "resource": f"node:{m['next']}",
               "start": m["entry_estimate"], "end": m["release_estimate"], "amount": 1} for m in messages]
    fixed_conflicts = capacity_violations([ObligationWindow(**w) for w in frozen], capacities)
    if fixed_conflicts:
        return {"status": "unknown_inconsistent_fixed_predictions", "actions": [], "base": base,
                "inconsistent_fixed_predictions": fixed_conflicts, "hard_infeasibility_certified": False}
    by_supply = {i: [] for i in range(len(base["supplies"]))}
    for pair in base["pool"]:
        supply, demand = base["supplies"][pair["supply"]], base["demands"][pair["demand"]]
        job = local[demand["business_bag_id"]]
        destination = int(job["origin"])
        ready = max(observation["now"] + message_delay, supply["estimate"])
        shifted = ready
        for _ in range(len(frozen)+1):
            arrival = shifted + travel.complete(supply["node"], destination)
            end = arrival + job["load_seconds"] + travel.service[destination]
            conflicts = [w for w in frozen if w["resource"] == f"node:{destination}"
                         and shifted < w["end"] and w["start"] < end]
            if not conflicts:
                break
            shifted = max(w["end"] for w in conflicts) + 1e-6
        for departure in sorted({ready, shifted}):
            arrival = departure + travel.complete(supply["node"], destination)
            identity = digest([pair["supply"], pair["demand"], departure])
            request = {"tray_id": supply["tray_id"],
                "source": supply["node"], "destination": destination, "issued_at": observation["now"],
                "message_delay": message_delay, "earliest_departure": departure,
                "expiry": arrival + 30., "owner_id": observation["owner_id"]}
            if context is None:
                request.update(request_id="live:handoff:"+digest(observation)[:20]+":"+identity,
                               expected_version=observation["version"])
            else:
                request["decision_context"] = context.to_dict()
            footprint = _footprint(observation, pair["path"], departure, identity, travel)
            terminal = {"task": identity, "resource": f"node:{destination}", "start": departure,
                        "end": arrival+job["load_seconds"]+travel.service[destination], "amount": 1}
            footprint.append(terminal)
            conflict = capacity_violations([ObligationWindow(**w) for w in frozen+footprint], capacities)
            by_supply[pair["supply"]].append({"candidate_id": identity, "supply": pair["supply"], "demand": pair["demand"],
                "request": request, "path": pair["path"], "footprint": footprint,
                "predicted_arrival": arrival, "predicted_completion": predicted_completion(job, arrival, travel),
                "individual_conflicts": conflict,
                "read_set": {"owner": observation["owner_id"],
                    **({"version": observation["version"]} if context is None else {"local_context": context.to_dict()}),
                    "supply": supply, "local_job_contract": job, "delivered_windows": messages,
                    "static_contract_sha256": (digest([observation["node_contracts"], observation["edge_contracts"]])
                                               if context is None else context.static_contract_sha256)}})
    actions = []
    for choice in itertools.product(*[[None]+v for v in by_supply.values()]):
        chosen = [c for c in choice if c is not None]
        if len({c["demand"] for c in chosen}) != len(chosen):
            continue
        if len(actions) >= max_actions:
            return {"status": "unknown_domain_budget", "actions": actions, "base": base}
        footprint = frozen + [w for c in chosen for w in c["footprint"]]
        actions.append({"action_id": digest([c["candidate_id"] for c in chosen]) if chosen else "WAIT",
            "candidates": chosen, "public_read_sha256": digest(observation) if context is None else context.identity,
            "arrival_sum": sum(c["predicted_arrival"] for c in chosen),
            "completion_sum": sum(c["predicted_completion"] for c in chosen),
            "conditional_conflicts": capacity_violations([ObligationWindow(**w) for w in footprint], capacities)})
    ordinary = min(actions, key=lambda a: _cost(a, False))
    assignment = {(c["supply"], c["demand"]) for c in ordinary["candidates"]}
    screened = [a for a in actions if all(not c["individual_conflicts"] for c in a["candidates"])]
    feedback = min((a for a in screened if {(c["supply"], c["demand"]) for c in a["candidates"]} == assignment),
                   key=_cost, default=None)
    # Independent service-aware min-cost matching is a separate ordinary
    # baseline, not the joint enumerator renamed. It screens each column
    # against the same protected public window but has no pairwise resource
    # constraints between distinct chosen empty moves.
    choices = {}
    matrix = []
    for supply_index in by_supply:
        costs = []
        for demand_index in range(len(base["demands"])):
            candidate = min((c for c in by_supply[supply_index] if c["demand"] == demand_index
                and not c["individual_conflicts"]), key=lambda c: (
                    c["predicted_completion"], c["predicted_arrival"], c["request"]["earliest_departure"]), default=None)
            if candidate is not None:
                choices[supply_index, demand_index] = candidate
            costs.append(candidate["predicted_completion"] if candidate else math.inf)
        matrix.append(costs)
    strong_ids = {choices[pair]["candidate_id"] for pair in _min_cost_matching(matrix)}
    strong = next(a for a in actions if {c["candidate_id"] for c in a["candidates"]} == strong_ids)
    joint = min((a for a in actions if not a["conditional_conflicts"]), key=_cost)
    if len({a["action_id"] for a in actions}) != len(actions):
        raise ValueError("handoff:duplicate_action")
    return {"status": "complete_finite_public_domain", "actions": actions, "base": base,
        "selected": {"ordinary_arrival_assignment": ordinary["action_id"],
            "one_round_receiving_retime": feedback["action_id"] if feedback else None,
            "strong_service_assignment": strong["action_id"], "joint_handoff": joint["action_id"], "WAIT": "WAIT"},
        "compute_ms": 1000*(time.perf_counter()-started), "hard_feasibility_certified": False,
        "unclosed_dependencies": ["all future/local congestion may extend receiving lease beyond point estimate",
            "ordinary path choice and transit footprints are not globally frozen",
            "no multi-owner atomic grant or universal all-business protection"],
        "domain_scope": "at most 3 lawful next-release sources, 2 current local demands, static paths and 2 derived departure choices; fixed no-further-control continuation"}
