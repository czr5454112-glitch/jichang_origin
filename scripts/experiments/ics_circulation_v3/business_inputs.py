"""Immutable business input, provenance and fixed-storage proxy contracts.

This is a pure input boundary: it neither imports a simulator nor allocates a
tray for a bag. Passing this boundary does not establish a complete operational
scenario. Supplier modules, mode permissions, service and headway contracts
must additionally be supplied by a runtime adapter. The complete future task
tuple is an ENVIRONMENT tape, never an initial controller observation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


class BusinessInputError(ValueError):
    """A missing, unsupported or inconsistent input contract fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BusinessInputError(message)


def seconds(value: Any, field: str = "seconds") -> Decimal:
    """Parse finite decimal source seconds without binary-float arithmetic."""
    _require(not isinstance(value, bool) and value is not None, f"{field}: finite seconds required")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BusinessInputError(f"{field}: finite seconds required") from None
    _require(result.is_finite(), f"{field}: finite seconds required")
    return result


def ceil_tick(value: Any, tick_seconds: Any) -> int:
    tick = seconds(tick_seconds, "tick_seconds")
    _require(tick > 0, "tick_seconds must be positive")
    ratio = Fraction(seconds(value)) / Fraction(tick)
    return -(-ratio.numerator // ratio.denominator)


def floor_tick(value: Any, tick_seconds: Any) -> int:
    tick = seconds(tick_seconds, "tick_seconds")
    _require(tick > 0, "tick_seconds must be positive")
    ratio = Fraction(seconds(value)) / Fraction(tick)
    return ratio.numerator // ratio.denominator


def _subtract_seconds(first: Decimal, second: Decimal) -> Decimal:
    # Decimal's process-wide default precision must not turn an exact source
    # deadline into a later rounded value before the final conservative floor.
    a, b = first.as_tuple(), second.as_tuple()
    with localcontext() as context:
        context.prec = max(len(a.digits), len(b.digits)) + abs(a.exponent - b.exponent) + 2
        return first - second


def _integer(value: Any, field: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{field}: integer >= {minimum} required")
    return value


def _text(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field}: nonempty string required")
    return value


def _keys(value: Any, names: set[str], field: str) -> Mapping[str, Any]:
    _require(isinstance(value, dict), f"{field}: object required")
    _require(set(value) == names, f"{field}: missing or unsupported fields {sorted(set(value) ^ names)}")
    return value


def _digest(value: Any, field: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             f"{field}: lowercase SHA256 required")
    return value


@dataclass(frozen=True)
class EvidenceReference:
    field: str
    source_ref: str
    assumption_id: str | None


@dataclass(frozen=True)
class InitialTray:
    tray_id: str
    node_id: str
    available_seconds: Decimal
    available_at: int


@dataclass(frozen=True)
class NodeInputContract:
    node_id: str
    capacity: int
    loaded_wait_allowed: bool


@dataclass(frozen=True)
class FixedStorageInputContract:
    node_id: str
    capacity: int
    carrier_policy: str
    publication_policy: str
    release_policy: str


@dataclass(frozen=True)
class OperationContract:
    contract_id: str
    title: str
    evidence_status: str
    graph_sha256: str
    tick_seconds: Decimal
    deadline_lead_seconds: Decimal
    protection_policy: str
    protected_business_ids: tuple[str, ...]
    initial_trays: tuple[InitialTray, ...]
    nodes: tuple[NodeInputContract, ...]
    storage: FixedStorageInputContract
    evidence: tuple[EvidenceReference, ...]
    canonical_sha256: str
    # Deliberate boundary: an input-only contract cannot certify operation.
    runtime_adaptation_required: bool = True


@dataclass(frozen=True)
class SourceReference:
    raw_sha256: str
    raw_task_id: int
    source_line: int
    parent_timetable_sha256: str
    parent_task_id: int
    parent_source_line: int
    flight_surrogate: tuple[Decimal, int, str]
    synthetic_inserted: bool
    time_shift_seconds: Decimal


@dataclass(frozen=True)
class BusinessTask:
    business_bag_id: str
    source: SourceReference
    arrival_seconds: Decimal
    std_seconds: Decimal
    deadline_seconds: Decimal
    origin: str
    final_destination: str
    lifecycle: str
    old_segment_ids: tuple[str, ...]
    arrival: int
    deadline: int
    protected: bool
    storage_node: str | None
    scheduled_release_seconds: Decimal | None
    release_at: int | None
    published_at: int | None

    @property
    def source_identity(self) -> tuple[str, int]:
        """Immutable identity remains tied to the projected raw artifact."""
        return self.source.raw_sha256, self.source.raw_task_id


@dataclass(frozen=True)
class BusinessWorkload:
    tasks: tuple[BusinessTask, ...]
    contract: OperationContract
    input_sha256: tuple[tuple[str, str], ...]
    raw_business_count: int
    old_segment_count: int
    original_count: int
    derived_count: int
    source_timetable_count: int = 1
    independent_observed_operating_days: int = 0
    information_scope: str = "private_environment_tape_reveal_only_on_observation"
    content_sha256: str = ""


def business_workload_sha256(workload: BusinessWorkload) -> str:
    """Bind the audited values, not merely the mutable caller's type/contract ID.

    This is a reproducible integrity seal, not a signature or trust mechanism
    against a caller deliberately replacing both the payload and its seal.
    """
    payload = asdict(workload)
    payload.pop("content_sha256")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         default=str, allow_nan=False).encode()
    return sha256(encoded).hexdigest()


def parse_operation_contract(value: Mapping[str, Any], profile: Mapping[str, Any],
                             graph_sha256: str) -> OperationContract:
    """Validate only the declared, narrow input contract; no hidden defaults."""
    obj = _keys(value, {"schema", "scope", "contract_id", "title", "evidence_status",
        "graph_sha256", "tick_seconds", "deadline", "protection", "initial_trays",
        "initial_storage", "nodes", "storage", "evidence"}, "operation_contract")
    _require(obj["schema"] == "ics_business_inputs_v1", "unsupported operation contract schema")
    _require(obj["scope"] == "input_only_fixed_storage_proxy", "unsupported operation contract scope")
    mode = obj["evidence_status"]
    _require(mode == "proxy_research", "this input-only proxy schema cannot certify confirmed operation")
    title = _text(obj["title"], "title")
    _require(mode != "proxy_research" or "proxy" in title.lower(), "proxy title must identify proxy")
    _require(_digest(obj["graph_sha256"], "graph_sha256") == graph_sha256, "graph SHA mismatch")
    tick = seconds(obj["tick_seconds"], "tick_seconds")
    _require(tick > 0, "tick_seconds must be positive")
    deadline = _keys(obj["deadline"], {"policy", "lead_seconds"}, "deadline")
    _require(deadline["policy"] == "std_minus_lead", "explicit supported deadline policy required")
    lead = seconds(deadline["lead_seconds"], "deadline.lead_seconds")
    _require(lead >= 0, "deadline lead must be nonnegative")
    protection = _keys(obj["protection"], {"policy", "business_ids"}, "protection")
    _require(protection["policy"] in ("all", "explicit_ids"), "explicit supported protection policy required")
    _require(isinstance(protection["business_ids"], list), "protection.business_ids list required")
    ids = tuple(_text(x, "protected business ID") for x in protection["business_ids"])
    _require(len(ids) == len(set(ids)), "duplicate protected business ID")
    _require((protection["policy"] == "all" and not ids) or
             (protection["policy"] == "explicit_ids" and bool(ids)), "ambiguous or empty protection policy")
    node_ids = {str(n["location"]) for n in profile["nodes"]}
    _require(isinstance(obj["nodes"], list), "nodes list required")
    nodes = []
    for row in obj["nodes"]:
        row = _keys(row, {"node_id", "capacity", "loaded_wait_allowed"}, "node")
        _require(type(row["loaded_wait_allowed"]) is bool, "loaded_wait_allowed boolean required")
        nodes.append(NodeInputContract(_text(row["node_id"], "node_id"),
            _integer(row["capacity"], "node capacity"), row["loaded_wait_allowed"]))
    _require(len(nodes) == len(node_ids) and {n.node_id for n in nodes} == node_ids,
             "exactly one explicit node contract per graph node required")
    node_map = {n.node_id: n for n in nodes}
    _require(obj["initial_storage"] == [], "only explicitly empty initial storage is supported")
    _require(isinstance(obj["initial_trays"], list),
             "explicit finite initial tray inventory required")
    trays = []
    for row in obj["initial_trays"]:
        row = _keys(row, {"tray_id", "node_id", "available_seconds"}, "initial tray")
        at = seconds(row["available_seconds"], "initial tray available_seconds")
        _require(at >= 0, "initial tray availability before epoch unsupported")
        node_id = _text(row["node_id"], "initial tray node")
        _require(node_id in node_map, "initial tray node absent from graph")
        trays.append(InitialTray(_text(row["tray_id"], "tray_id"), node_id, at, ceil_tick(at, tick)))
    _require(len({t.tray_id for t in trays}) == len(trays), "duplicate initial tray identity")
    for node_id, count in Counter(t.node_id for t in trays).items():
        _require(count <= node_map[node_id].capacity, "initial inventory exceeds node capacity")
    storage = _keys(obj["storage"], {"node_id", "capacity", "carrier_policy", "publication_policy",
        "release_policy", "uses_node_wait_capacity", "dedicated_retrieval"}, "storage")
    _require(storage["carrier_policy"] == "on_carrier", "only on_carrier storage supported")
    _require(storage["publication_policy"] == "irrevocable_at_bag_arrival", "dynamic or future publication unsupported")
    _require(storage["release_policy"] == "normalized_scheduled_release", "unknown release policy")
    _require(storage["uses_node_wait_capacity"] is True and storage["dedicated_retrieval"] is False,
             "only node-wait proxy storage supported")
    storage_node = _text(storage["node_id"], "storage node")
    _require(storage_node in node_map, "storage node absent from graph")
    capacity = _integer(storage["capacity"], "storage capacity")
    _require(node_map[storage_node].loaded_wait_allowed, "storage loaded waiting permission required")
    _require(capacity == node_map[storage_node].capacity, "storage capacity must equal its shared node capacity")
    _require(isinstance(obj["evidence"], list), "evidence list required")
    evidence = []
    required = {"clock", "deadline", "protection", "initial_trays", "nodes", "storage"}
    for row in obj["evidence"]:
        row = _keys(row, {"field", "source_ref", "assumption_id"}, "evidence reference")
        field = _text(row["field"], "evidence field")
        ref = _text(row["source_ref"], "evidence source_ref")
        assumption = row["assumption_id"]
        assumption = _text(assumption, "proxy assumption_id")
        evidence.append(EvidenceReference(field, ref, assumption))
    _require(len(evidence) == len(required) and {e.field for e in evidence} == required,
             "exact evidence coverage required")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return OperationContract(_text(obj["contract_id"], "contract_id"), title, mode, graph_sha256,
        tick, lead, protection["policy"], tuple(sorted(ids)), tuple(trays), tuple(nodes),
        FixedStorageInputContract(storage_node, capacity, "on_carrier",
                                  storage["publication_policy"], storage["release_policy"]),
        tuple(evidence), sha256(canonical.encode()).hexdigest())


@dataclass(frozen=True)
class _Raw:
    task_id: int
    arrival: Decimal
    std: Decimal
    origin: int
    destination: int
    unloader: str
    loader: str
    line: int


def _raw_rows(data: bytes) -> dict[int, _Raw]:
    lines = data.decode("utf-8-sig").splitlines()
    _require(bool(lines) and lines[0].split() ==
        ["ID", "EntryTime(s)", "STD(s)", "star", "end", "Unloader", "Loader"], "raw header mismatch")
    result = {}
    for n, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        fields = line.split()
        _require(len(fields) == 7, f"raw line {n}: seven fields required")
        try:
            ident, origin, destination = int(fields[0]), int(fields[3]), int(fields[4])
        except ValueError:
            raise BusinessInputError(f"raw line {n}: integer ID/endpoints required") from None
        _require(ident >= 0 and ident not in result, "invalid or duplicate raw task ID")
        arrival, std = seconds(fields[1]), seconds(fields[2])
        _require(0 <= arrival <= std, "raw task time order invalid")
        result[ident] = _Raw(ident, arrival, std, origin, destination, fields[5], fields[6], n)
    _require(bool(result), "empty raw business source")
    return result


def load_business_workload(*, normalized: str | Path, normalization_manifest: str | Path,
                          raw: str | Path, canonical: str | Path, source_timetable: str | Path,
                          source_manifest: str | Path, graph_profile: str | Path,
                          contract: Mapping[str, Any]) -> BusinessWorkload:
    """Load the complete normalized denominator with raw/parent/segment checks.

    No graph reachability test filters tasks. The normalized artifact is bound
    to its Round8 audit manifest, and all source bytes are rehashed. Source
    seconds are parsed from raw text; normalized binary-float representations
    are checked but never used for final clock rounding.
    """
    paths = {key: Path(value) for key, value in dict(normalized=normalized,
        normalization_manifest=normalization_manifest, raw=raw, canonical=canonical,
        source_timetable=source_timetable, source_manifest=source_manifest,
        graph_profile=graph_profile).items()}
    data = {key: path.read_bytes() for key, path in paths.items()}
    digests = {key: sha256(value).hexdigest() for key, value in data.items()}
    audit = json.loads(data["normalization_manifest"])
    _require(audit["outputs"].get(paths["normalized"].name) == digests["normalized"],
             "normalized SHA mismatch")
    for key in ("raw", "canonical", "source_timetable", "source_manifest", "graph_profile"):
        expected = audit["input_sha256"].get(str(paths[key].resolve()))
        _require(expected == digests[key], f"{key}: source SHA mismatch")
    profile = json.loads(data["graph_profile"])
    operation = parse_operation_contract(contract, profile, digests["graph_profile"])
    projected, parent_rows = _raw_rows(data["raw"]), _raw_rows(data["source_timetable"])
    manifest = json.loads(data["source_manifest"])
    _require(len(projected) in (len(parent_rows), 2 * len(parent_rows)),
             "only complete original or once-densified source manifests supported")
    scale = len(projected) // len(parent_rows)
    lifecycle = manifest["lifecycle"]
    _require(seconds(lifecycle["early_bag_threshold_seconds"]) == 4800 and
             seconds(lifecycle["storage_out_lead_seconds"]) == 2700, "unsupported source lifecycle rules")
    _require(str(lifecycle["storage_in_goal"]) == operation.storage.node_id ==
             str(lifecycle["storage_out_start"]), "storage proxy differs from declared source lifecycle")
    nodes = {str(n["location"]): n for n in profile["nodes"]}
    loaders = {str(x) for x in profile["business_roles"]["source_candidate_ids"]}
    unloaders = {str(x) for x in profile["business_roles"]["sink_candidate_ids"]}
    segments: dict[int, list[dict[str, Any]]] = defaultdict(list)
    segment_ids = set()
    for line in data["canonical"].decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        task_id = _integer(row["task_id"], "canonical task ID")
        _require(task_id in projected, "orphan canonical segment")
        _require(row["segment_id"] not in segment_ids, "duplicate canonical segment")
        segment_ids.add(row["segment_id"])
        segments[task_id].append(row)
    rows = [json.loads(line) for line in gzip.decompress(data["normalized"]).splitlines() if line.strip()]
    seen_raw, seen_bags, parent_original, parent_inserted = set(), set(), set(), set()
    observed_flight_destinations: dict[tuple[Any, ...], str] = {}
    observed_inserted_shifts: dict[tuple[Any, ...], Decimal] = {}
    parent_order = tuple(parent_rows)
    inserted_offset = max(parent_rows) + 1
    tasks = []
    protection_ids = set(operation.protected_business_ids)
    for row in rows:
        ref = row["source"]
        task_id = _integer(ref["raw_task_id"], "raw task ID")
        _require(task_id in projected and task_id not in seen_raw, "missing or duplicate normalized raw identity")
        seen_raw.add(task_id)
        original = projected[task_id]
        parent_id = _integer(ref["parent_task_id"], "parent task ID")
        _require(parent_id in parent_rows, "parent task missing from source timetable")
        parent = parent_rows[parent_id]
        _require(ref["raw_sha256"] == digests["raw"] and ref["parent_timetable_sha256"] == digests["source_timetable"],
                 "normalized source digest mismatch")
        _require(ref["source_line"] == original.line and ref["parent_source_line"] == parent.line,
                 "source line mismatch")
        inserted = ref["synthetic_inserted"]
        _require(type(inserted) is bool, "synthetic_inserted boolean required")
        _require(inserted == (task_id not in parent_rows), "derived/source identity conflict")
        if not inserted:
            _require(parent_id == task_id, "original bag parent identity changed")
        else:
            rank = task_id - inserted_offset
            _require(0 <= rank < len(parent_order) and parent_order[rank] == parent_id,
                     "derived bag ID does not preserve source parent rank")
        parent_set = parent_inserted if inserted else parent_original
        _require(parent_id not in parent_set, "source parent duplicated within original/derived class")
        parent_set.add(parent_id)
        shift = seconds(ref["time_shift_seconds"])
        _require((inserted and shift > 0) or (not inserted and shift == 0), "invalid source time shift")
        _require(Fraction(original.arrival) == Fraction(parent.arrival) + Fraction(shift) and
                 Fraction(original.std) == Fraction(parent.std) + Fraction(shift),
                 "parent source exact seconds mismatch")
        _require(len(ref["flight_surrogate"]) == 3, "flight surrogate must preserve three source fields")
        flight = (seconds(ref["flight_surrogate"][0]), ref["flight_surrogate"][1], ref["flight_surrogate"][2])
        _require(flight == (parent.std, parent.destination, parent.unloader), "source flight surrogate mismatch")
        if inserted:
            prior_shift = observed_inserted_shifts.setdefault(flight, shift)
            _require(prior_shift == shift, "derived flight manifest split across time shifts")
        bag_id = _text(row["business_bag_id"], "business_bag_id")
        _require(bag_id == f"projected:{scale}x:{task_id}", "business bag ID does not preserve source namespace")
        _require(bag_id not in seen_bags, "duplicate business bag ID")
        seen_bags.add(bag_id)
        _require(seconds(row["arrival_seconds"]) == original.arrival and seconds(row["std_seconds"]) == original.std,
                 "normalized source seconds mismatch")
        origin, destination = str(original.origin), str(original.destination)
        _require(row["origin"] == origin and row["final_destination"] == destination,
                 "normalized OD mismatch")
        _require(origin in loaders and destination in unloaders, "business OD role mismatch")
        _require(original.loader == nodes[origin]["alias"] and original.unloader == nodes[destination]["alias"],
                 "projected raw alias mismatch")
        prior_destination = observed_flight_destinations.setdefault(flight, destination)
        _require(prior_destination == destination, "source flight group split across projected destinations")
        early = _subtract_seconds(original.std, original.arrival) >= Decimal(4800)
        release = _subtract_seconds(original.std, Decimal(2700)) if early else None
        _require(row["lifecycle"] == ("early_storage" if early else "direct"), "business lifecycle mismatch")
        _require(row["storage_node_proxy"] == (operation.storage.node_id if early else None), "normalized storage node mismatch")
        _require((release is None and row["scheduled_release_seconds"] is None) or
                 (release is not None and seconds(row["scheduled_release_seconds"]) == release), "scheduled release mismatch")
        for unset in ("physical_tray_id", "deadline_contract", "protected_contract", "storage_carrier_policy"):
            _require(row[unset] is None, f"normalized {unset} must remain unresolved; use explicit contract")
        expected_legs = {"storage_in": (origin, operation.storage.node_id, original.arrival),
                         "storage_out": (operation.storage.node_id, destination, release)} if early else {
                             "direct": (origin, destination, original.arrival)}
        by_leg = {s["leg"]: s for s in segments[task_id]}
        _require(set(by_leg) == set(expected_legs) and len(by_leg) == len(segments[task_id]),
                 "business bag does not have its exact complete old segment set")
        expected_ids = tuple(sorted(f"{task_id}:{leg}" for leg in expected_legs))
        _require(tuple(sorted(row["old_segment_ids"])) == expected_ids, "normalized old segment identity mismatch")
        for leg, (start, goal, entry) in expected_legs.items():
            s = by_leg[leg]
            _require(s["segment_id"] == f"{task_id}:{leg}" and s["pallet_id"] == task_id,
                     "old segment identity mismatch")
            _require((str(s["start"]), str(s["goal"]), seconds(s["pass_time"])) == (start, goal, entry),
                     "old segment stage mismatch")
            _require((str(s["original_start"]), str(s["original_goal"]), seconds(s["original_entry_time"]),
                seconds(s["std"]), s["source_line"], s["early_bag_split"]) ==
                (origin, destination, original.arrival, original.std, original.line, early),
                "old segment source attributes mismatch")
        hard_deadline = _subtract_seconds(original.std, operation.deadline_lead_seconds)
        # An impossible arrival/deadline pair is retained, never removed or softened.
        tasks.append(BusinessTask(bag_id, SourceReference(digests["raw"], task_id, original.line,
            digests["source_timetable"], parent_id, parent.line, flight, inserted, shift),
            original.arrival, original.std, hard_deadline, origin, destination, row["lifecycle"],
            expected_ids, ceil_tick(original.arrival, operation.tick_seconds),
            floor_tick(hard_deadline, operation.tick_seconds),
            operation.protection_policy == "all" or bag_id in protection_ids,
            operation.storage.node_id if early else None, release,
            ceil_tick(release, operation.tick_seconds) if release is not None else None,
            ceil_tick(original.arrival, operation.tick_seconds) if early else None))
    _require(seen_raw == set(projected), "normalized artifact omits raw business bags")
    _require(parent_original == set(parent_rows), "original business denominator incomplete")
    _require(not parent_inserted or parent_inserted == set(parent_rows), "derived complete-manifest denominator incomplete")
    _require(protection_ids <= seen_bags, "protected IDs absent from workload")
    counts = Counter(t.lifecycle for t in tasks)
    _require((len(tasks), len(segment_ids), counts["direct"], counts["early_storage"]) ==
        (manifest["raw_task_count"], manifest["expanded_segment_count"], manifest["direct_raw_task_count"],
         manifest["early_split_raw_task_count"]), "source manifest full denominator mismatch")
    _require(dict(Counter(t.origin for t in tasks)) == manifest["raw_by_start"] and
             dict(Counter(t.final_destination for t in tasks)) == manifest["raw_by_goal"],
             "source manifest OD marginal mismatch")
    # Bind the data actually consumed, then reject concurrent modification.
    for key, path in paths.items():
        _require(sha256(path.read_bytes()).hexdigest() == digests[key], f"{key}: changed during read")
    result = BusinessWorkload(tuple(sorted(tasks, key=lambda t: (t.arrival_seconds, t.business_bag_id))),
        operation, tuple(sorted((str(paths[k].resolve()), v) for k, v in digests.items())),
        len(tasks), len(segment_ids), len(parent_original), len(parent_inserted))
    return replace(result, content_sha256=business_workload_sha256(result))
