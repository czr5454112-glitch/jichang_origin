"""Versioned whole-flight research projection; no runtime or simulation imports.

The output deliberately is not BusinessWorkload. Original tasks are retained in
full and an explicit future adapter is required before any physical experiment.
Static necessary domains are not a certificate of joint capacity feasibility.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from heapq import heappop, heappush
import json
from pathlib import Path
from typing import Any, Mapping

from .business_inputs import (BusinessInputError, BusinessTask, BusinessWorkload,
    OperationContract, business_workload_sha256, ceil_tick, seconds)


class BusinessProjectionError(BusinessInputError):
    """An incomplete or unsupported research projection fails closed."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise BusinessProjectionError(message)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False, default=str)


def _sha(value: Any) -> str:
    return sha256(_json(value).encode()).hexdigest()


POLICIES = {
    "schema": "ics_business_destination_projection_v1",
    "evidence_status": "proxy_research",
    "grouping_policy": "whole_parent_flight_family_with_all_derived_copies",
    "selection_policy": "retain_legal_original_else_min_sha256_rank",
    "node_order": "unicode_lexical_string_id",
    "candidate_policy": "original_role_unloaders_with_return_to_any_original_loader",
    "edge_policy": "both_modes_positive_original_directed_edges_proxy",
    "deadline_policy": "original_protected_deadline_exact_seconds_and_per_edge_ceil_ticks",
    "preservation_policy": "all_original_task_fields_and_full_denominator",
    "result_dependency": "none_source_and_declared_contract_only",
}


@dataclass(frozen=True)
class DestinationProjectionContract:
    projection_id: str
    title: str
    evidence_status: str
    source_workload_sha256: str
    graph_sha256: str
    salt: str
    unload_seconds: Decimal
    assumption_id: str
    source_ref: str
    canonical_json: str
    canonical_sha256: str


@dataclass(frozen=True)
class CandidateNecessaryCondition:
    final_destination: str
    return_loader_ids: tuple[str, ...]
    structural_necessary: bool
    deadline_necessary: bool
    minimum_protected_seconds_slack: str | None
    minimum_protected_tick_slack: int | None
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class FlightDestinationProjection:
    group_id: str
    # parent timetable SHA, rational original STD, original end, original Unloader
    parent_flight_key: tuple[str, str, str, str]
    business_bag_ids: tuple[str, ...]
    flight_instance_count: int
    original_destination: str
    projected_destination: str
    structural_domain: tuple[str, ...]
    necessary_domain: tuple[str, ...]
    candidates: tuple[CandidateNecessaryCondition, ...]
    decision: str
    selection_sha256: str | None


@dataclass(frozen=True)
class ProjectedBusinessTask:
    original: BusinessTask
    group_id: str
    original_destination: str
    projected_destination: str


@dataclass(frozen=True)
class BusinessProjection:
    contract: DestinationProjectionContract
    source_operation_contract: OperationContract
    source_input_sha256: tuple[tuple[str, str], ...]
    records: tuple[ProjectedBusinessTask, ...]
    groups: tuple[FlightDestinationProjection, ...]
    source_business_count: int
    source_segment_count: int
    original_count: int
    derived_count: int
    source_timetable_count: int
    independent_observed_operating_days: int
    information_scope: str
    runtime_adaptation_required: bool = True
    qualification: str = "Static necessary-domain research proxy; no joint capacity or real assignment claim"
    content_sha256: str = ""


def projection_sha256(projection: BusinessProjection) -> str:
    payload = asdict(projection)
    payload.pop("content_sha256")
    return _sha(payload)


def parse_projection_contract(value: Mapping[str, Any], workload: BusinessWorkload) -> DestinationProjectionContract:
    fields = set(POLICIES) | {"projection_id", "title", "source_workload_sha256", "graph_sha256",
                             "salt", "unload_seconds", "assumption_id", "source_ref"}
    _check(isinstance(value, dict) and set(value) == fields, "exact projection contract fields required")
    for name, expected in POLICIES.items():
        _check(value[name] == expected, f"unsupported projection {name}")
    for field in ("projection_id", "title", "salt", "assumption_id", "source_ref"):
        _check(isinstance(value[field], str) and bool(value[field].strip()), f"explicit {field} required")
    _check("proxy" in value["title"].lower(), "projection title must identify proxy")
    _check(workload.contract.evidence_status == "proxy_research", "only explicit proxy input supported")
    _check(value["source_workload_sha256"] == workload.content_sha256, "projection source workload binding mismatch")
    _check(value["graph_sha256"] == workload.contract.graph_sha256, "projection graph binding mismatch")
    unload = seconds(value["unload_seconds"], "projection unload seconds")
    _check(unload >= 0, "nonnegative explicit final unload service required")
    canonical = _json(value)
    return DestinationProjectionContract(value["projection_id"], value["title"], value["evidence_status"],
        value["source_workload_sha256"], value["graph_sha256"], value["salt"], unload,
        value["assumption_id"], value["source_ref"], canonical, sha256(canonical.encode()).hexdigest())


def _validate_source(workload: BusinessWorkload) -> None:
    _check(isinstance(workload, BusinessWorkload), "audited original BusinessWorkload required")
    _check(workload.content_sha256 == business_workload_sha256(workload), "source workload content binding mismatch")
    _check(len(workload.tasks) == workload.raw_business_count == workload.original_count + workload.derived_count,
           "complete source business denominator required")
    _check(sum(len(t.old_segment_ids) for t in workload.tasks) == workload.old_segment_count,
           "complete source segment denominator required")
    _check(len({t.business_bag_id for t in workload.tasks}) == len(workload.tasks) and
           len({t.source_identity for t in workload.tasks}) == len(workload.tasks), "duplicate source identity")
    _check(sum(t.source.synthetic_inserted for t in workload.tasks) == workload.derived_count,
           "source derived denominator mismatch")


def _parent_key(task: BusinessTask) -> tuple[str, str, str, str]:
    std, end, unloader = task.source.flight_surrogate
    return task.source.parent_timetable_sha256, str(Fraction(std)), str(end), unloader


def _graph(profile: Mapping[str, Any], workload: BusinessWorkload):
    nodes = {str(row["location"]) for row in profile["nodes"]}
    _check(len(nodes) == len(profile["nodes"]), "duplicate graph node")
    _check(nodes == {n.node_id for n in workload.contract.nodes}, "source graph node binding mismatch")
    roles = profile["business_roles"]
    loaders = tuple(sorted(map(str, roles["source_candidate_ids"])))
    finals = tuple(sorted(map(str, roles["sink_candidate_ids"])))
    _check(bool(loaders) and bool(finals) and len(loaders) == len(set(loaders)) and
           len(finals) == len(set(finals)) and set(loaders + finals) <= nodes, "invalid original business roles")
    adjacency = defaultdict(list)
    tick = Fraction(workload.contract.tick_seconds)
    edges = set()
    for row in profile["edges"]:
        start, end = str(row["start"]), str(row["end"])
        _check(start in nodes and end in nodes, "source edge endpoint absent")
        _check((start, end) not in edges, "parallel source edge identity unsupported")
        edges.add((start, end))
        capacity = row["capacity"]
        _check(type(capacity) is int and capacity >= 0, "nonnegative integer source edge capacity required")
        length, speed = seconds(row["length"]), seconds(row["speed"])
        _check(length > 0 and speed > 0, "positive source length/speed required")
        duration = Fraction(length) / Fraction(speed)
        travel = duration / tick
        edge_ticks = -(-travel.numerator // travel.denominator)
        if capacity > 0:
            adjacency[start].append((end, duration, edge_ticks))
    needed = set(loaders + finals) | {t.storage_node for t in workload.tasks if t.storage_node is not None}
    _check(needed <= nodes, "storage node absent from original graph")
    distances = {}
    for origin in sorted(needed):
        for unit in (1, 2):
            reached, queue = {origin: Fraction(0) if unit == 1 else 0}, [(0, origin)]
            while queue:
                distance, current = heappop(queue)
                if reached[current] != distance:
                    continue
                for edge in adjacency[current]:
                    candidate = distance + edge[unit]
                    if edge[0] not in reached or candidate < reached[edge[0]]:
                        reached[edge[0]] = candidate
                        heappush(queue, (candidate, edge[0]))
            distances[origin, unit] = reached
    return loaders, finals, distances


def _build(workload: BusinessWorkload, profile: Mapping[str, Any], contract: DestinationProjectionContract) -> BusinessProjection:
    loaders, finals, distance = _graph(profile, workload)
    unload_seconds = Fraction(contract.unload_seconds)
    unload_ticks = ceil_tick(contract.unload_seconds, workload.contract.tick_seconds)
    grouped = defaultdict(list)
    for task in workload.tasks:
        _check(task.origin in loaders and task.final_destination in finals, "task must retain original business roles")
        _check(task.lifecycle in ("direct", "early_storage"), "unsupported original lifecycle")
        if task.lifecycle == "early_storage":
            _check(task.storage_node == workload.contract.storage.node_id and task.release_at is not None and
                   task.scheduled_release_seconds is not None, "complete original storage contract required")
        grouped[_parent_key(task)].append(task)
    groups = []
    for key, tasks in sorted(grouped.items()):
        original_destinations = {t.final_destination for t in tasks}
        _check(len(original_destinations) == 1, "original whole flight family has inconsistent final destinations")
        original = next(iter(original_destinations))
        group_id = "parent-flight:" + _sha(key)
        conditions = []
        for final in finals:
            returns = tuple(loader for loader in loaders if loader in distance[final, 1])
            reasons = set()
            if not returns:
                reasons.add("no_empty_return_to_any_legal_loader")
            min_seconds, min_ticks = None, None
            for task in tasks:
                origin = task.origin
                if task.lifecycle == "early_storage":
                    storage = task.storage_node
                    if storage == final:
                        reasons.add("storage_is_not_a_final_unload")
                    if storage not in distance[origin, 1]:
                        reasons.add("early_origin_to_storage_unreachable")
                        continue
                    if final not in distance[storage, 1]:
                        reasons.add("early_storage_to_final_unreachable")
                        continue
                    earliest_seconds = max(Fraction(task.arrival_seconds) + distance[origin, 1][storage],
                        Fraction(task.scheduled_release_seconds)) + distance[storage, 1][final]
                    earliest_ticks = max(task.arrival + distance[origin, 2][storage], task.release_at) + distance[storage, 2][final]
                else:
                    if final not in distance[origin, 1]:
                        reasons.add("direct_origin_to_final_unreachable")
                        continue
                    earliest_seconds = Fraction(task.arrival_seconds) + distance[origin, 1][final]
                    earliest_ticks = task.arrival + distance[origin, 2][final]
                if task.protected:
                    slack = Fraction(task.deadline_seconds) - earliest_seconds - unload_seconds
                    tick_slack = task.deadline - earliest_ticks - unload_ticks
                    min_seconds = slack if min_seconds is None else min(min_seconds, slack)
                    min_ticks = tick_slack if min_ticks is None else min(min_ticks, tick_slack)
            structural = not reasons
            if min_seconds is not None and min_seconds < 0:
                reasons.add("protected_exact_seconds_deadline_lower_bound")
            if min_ticks is not None and min_ticks < 0:
                reasons.add("protected_per_edge_tick_deadline_lower_bound")
            conditions.append(CandidateNecessaryCondition(final, returns, structural, not reasons,
                str(min_seconds) if min_seconds is not None else None, min_ticks, tuple(sorted(reasons))))
        structural_domain = tuple(c.final_destination for c in conditions if c.structural_necessary)
        domain = tuple(c.final_destination for c in conditions if c.deadline_necessary)
        _check(bool(domain), f"empty whole-flight necessary domain: {group_id}; no bags removed")
        if original in domain:
            selected, decision, selected_hash = original, "retained_legal_original", None
        else:
            def rank(final):
                return _sha([POLICIES["schema"], contract.salt, key, final]), final
            selected_hash, selected = min(rank(final) for final in domain)
            decision = "projected_illegal_original_by_declared_sha256_rank"
        groups.append(FlightDestinationProjection(group_id, key,
            tuple(sorted(t.business_bag_id for t in tasks)),
            len({(t.source.synthetic_inserted, Fraction(t.source.time_shift_seconds)) for t in tasks}),
            original, selected, structural_domain, domain, tuple(conditions), decision, selected_hash))
    by_key = {g.parent_flight_key: g for g in groups}
    records = tuple(ProjectedBusinessTask(t, by_key[_parent_key(t)].group_id, t.final_destination,
                    by_key[_parent_key(t)].projected_destination) for t in workload.tasks)
    result = BusinessProjection(contract, workload.contract, workload.input_sha256, records, tuple(groups),
        workload.raw_business_count, workload.old_segment_count, workload.original_count, workload.derived_count,
        workload.source_timetable_count, workload.independent_observed_operating_days, workload.information_scope)
    return replace(result, content_sha256=projection_sha256(result))


def project_business_destinations(workload: BusinessWorkload, profile_path: str | Path,
                                  contract: Mapping[str, Any]) -> BusinessProjection:
    _validate_source(workload)
    parsed = parse_projection_contract(contract, workload)
    path = Path(profile_path)
    raw = path.read_bytes()
    _check(sha256(raw).hexdigest() == parsed.graph_sha256, "profile bytes differ from bound graph")
    result = _build(workload, json.loads(raw, parse_float=Decimal), parsed)
    _check(sha256(path.read_bytes()).hexdigest() == parsed.graph_sha256, "profile changed during projection")
    return result


def validate_business_projection(projection: BusinessProjection, original: BusinessWorkload,
                                 profile_path: str | Path) -> None:
    _check(isinstance(projection, BusinessProjection), "explicit BusinessProjection required")
    _check(projection.content_sha256 == projection_sha256(projection), "projection content binding mismatch")
    expected = project_business_destinations(original, profile_path, json.loads(projection.contract.canonical_json))
    _check(projection == expected, "projection differs from complete bound source, whole-group domain or declared rule")
