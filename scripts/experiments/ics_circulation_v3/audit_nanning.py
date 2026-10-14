"""Read-only topology audit for the isolated ICS circulation V3 prototype.

This reports source fields and data gaps. It neither supplies missing operating
parameters nor turns a routing profile into a supplier-module integration.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE = Path(__file__).resolve().parent / "fixtures/nanning_airport_profile.json"
DOCUMENTED_TYPES = {
    1: "loader", 2: "unloader", 4: "divert",
    7: "empty_pallet_storage", 11: "recode_station",
}
# These are proposed V3 contract fields, not claims about the original schema.
STORAGE_CONTRACT_FIELDS = (
    "initial_empty_count", "max_empty_count", "min_empty_count",
    "target_empty_count", "served_loader_ids",
)
NODE_CONTRACT_FIELDS = ("logistics_region_id", "routing_control_region_id", "controller_id")
EDGE_CONTRACT_FIELDS = ("allowed_tray_modes", "handoff_rule", "reservation_owner")
PROFILE_CONTRACT_FIELDS = (
    "tray_states", "old_in_transit", "local_empty_module_interface",
    "demand_forecast", "forecast_issued_at", "timestamped_business_events",
)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}")
    return result


def _missing(row: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    return [field for field in fields if field not in row or row[field] is None]


def audit_profile(profile_path: str | Path) -> dict[str, Any]:
    """Derive evidence from the exact file bytes without changing the source."""
    path = Path(profile_path).resolve()
    raw_bytes = path.read_bytes()
    profile = json.loads(raw_bytes.decode("utf-8-sig"))
    if not isinstance(profile, dict):
        raise ValueError("profile root must be an object")
    raw_nodes, raw_edges = profile.get("nodes"), profile.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("nodes must be a nonempty list")
    if not isinstance(raw_edges, list):
        raise ValueError("edges must be a list")

    nodes: dict[int, dict[str, Any]] = {}
    for row in raw_nodes:
        if not isinstance(row, dict):
            raise ValueError("every node must be an object")
        node_id = _integer(row.get("location"), "node.location")
        _integer(row.get("node_type"), f"node {node_id}.node_type")
        if node_id in nodes:
            raise ValueError(f"duplicate node ID: {node_id}")
        if "service_time" in row:
            _number(row["service_time"], f"node {node_id}.service_time")
        nodes[node_id] = row

    edge_keys: set[tuple[int, int]] = set()
    outgoing: dict[int, set[int]] = {node: set() for node in nodes}
    cross_edges, zero_capacity, missing_edge_contract = [], [], []
    unknown_system_edges = []
    for row in raw_edges:
        if not isinstance(row, dict):
            raise ValueError("every edge must be an object")
        start = _integer(row.get("start"), "edge.start")
        end = _integer(row.get("end"), "edge.end")
        if start not in nodes or end not in nodes:
            raise ValueError(f"edge {start}->{end} references an unknown node")
        if (start, end) in edge_keys:
            raise ValueError(f"duplicate edge: {start}->{end}")
        edge_keys.add((start, end))
        outgoing[start].add(end)
        length = _number(row.get("length"), f"edge {start}->{end}.length", positive=True)
        speed = _number(row.get("speed"), f"edge {start}->{end}.speed", positive=True)
        if row.get("capacity") is not None:
            _number(row["capacity"], f"edge {start}->{end}.capacity")
        evidence = {
            "start": start, "end": end,
            "start_external_id": nodes[start].get("external_id"),
            "end_external_id": nodes[end].get("external_id"),
            "start_system": nodes[start].get("system_key"),
            "end_system": nodes[end].get("system_key"),
            "length": length, "speed": speed,
            "travel_time_seconds_derived": length / speed,
            "capacity_as_recorded": row.get("capacity"),
            "source": row.get("source"),
        }
        if row.get("capacity") == 0:
            zero_capacity.append(evidence)
        systems = (nodes[start].get("system_key"), nodes[end].get("system_key"))
        if not all(systems):
            unknown_system_edges.append([start, end])
        elif systems[0] != systems[1]:
            cross_edges.append(evidence)
        missing = _missing(row, EDGE_CONTRACT_FIELDS)
        if missing:
            missing_edge_contract.append({"start": start, "end": end, "missing_fields": missing})

    missing_adjacency = []
    for node_id, node in nodes.items():
        if "outgoing" not in node:
            missing_adjacency.append(node_id)
            continue
        declared = node["outgoing"]
        if not isinstance(declared, list):
            raise ValueError(f"node {node_id}.outgoing must be a list")
        declared = [_integer(value, f"node {node_id}.outgoing") for value in declared]
        if len(set(declared)) != len(declared) or set(declared) != outgoing[node_id]:
            raise ValueError(f"node {node_id} outgoing does not match directed edges")

    mappings = [
        {
            "location": node_id,
            "external_id": row.get("external_id"), "alias": row.get("alias"),
            "system_key": row.get("system_key"), "system_label": row.get("system"),
            "node_type": row["node_type"],
            "documented_role": DOCUMENTED_TYPES.get(row["node_type"]),
            "business_roles_as_recorded": row.get("business_roles"),
            "service_time_as_recorded": row.get("service_time"),
            "service_time_source": row.get("service_time_source"),
            "source": row.get("source"),
        }
        for node_id, row in sorted(nodes.items())
    ]
    storage = [
        {
            **mapping,
            "empty_pallet_storage_id": nodes[mapping["location"]].get("empty_pallet_storage_id"),
            "operating_values_as_recorded": {
                field: nodes[mapping["location"]][field]
                for field in STORAGE_CONTRACT_FIELDS
                if field in nodes[mapping["location"]]
            },
            "missing_fields": _missing(nodes[mapping["location"]], STORAGE_CONTRACT_FIELDS),
        }
        for mapping in mappings if mapping["node_type"] == 7
    ]
    external_ids: dict[str, list[int]] = {}
    for mapping in mappings:
        if mapping["external_id"] is not None:
            external_ids.setdefault(str(mapping["external_id"]), []).append(mapping["location"])

    return {
        "schema": "czr005.ics_circulation_v3.nanning_data_audit.v1",
        "scope": "SOURCE_TOPOLOGY_AND_DATA_GAPS_ONLY_NOT_SUPPLIER_INTEGRATION",
        "source": {
            "profile_path": str(path), "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "byte_count": len(raw_bytes), "map_id": profile.get("map_id"),
            "profile_schema": profile.get("schema"),
        },
        "derived_counts": {
            "nodes": len(nodes), "directed_edges": len(raw_edges),
            "systems": dict(sorted(Counter(str(row.get("system_key", "MISSING")) for row in nodes.values()).items())),
            "node_types": dict(sorted(Counter(str(row["node_type"]) for row in nodes.values()).items())),
            "cross_system_edges": len(cross_edges),
            "unknown_system_edges": len(unknown_system_edges),
            "empty_pallet_storage_nodes": len(storage),
        },
        "verified_mapping": {
            "node_ids_dense_zero_based": sorted(nodes) == list(range(len(nodes))),
            "all_edge_endpoints_exist": True,
            "declared_adjacency_matches_edges": not missing_adjacency,
            "nodes_without_declared_adjacency": missing_adjacency,
            "duplicate_external_ids": {
                key: ids for key, ids in sorted(external_ids.items()) if len(ids) > 1
            },
            "node_mapping": mappings,
        },
        "cross_system_edges": cross_edges,
        "empty_pallet_storage": storage,
        "source_caveats": {
            "undocumented_node_types": sorted({row["node_type"] for row in nodes.values()} - DOCUMENTED_TYPES.keys()),
            "imputed_service_nodes": [mapping for mapping in mappings if str(mapping["service_time_source"]).startswith("IMPUTED")],
            "zero_capacity_edges_as_recorded": zero_capacity,
            "assumptions_as_recorded": profile.get("assumptions"),
            "unknown_system_edges": unknown_system_edges,
            "type_7_is_empty_pallet_storage_not_real_ebs": True,
        },
        "missing_business_fields": {
            "field_names_are_proposed_v3_contract_not_original_schema": True,
            "profile": _missing(profile, PROFILE_CONTRACT_FIELDS),
            "nodes": [
                {"location": node_id, "missing_fields": _missing(row, NODE_CONTRACT_FIELDS)}
                for node_id, row in sorted(nodes.items()) if _missing(row, NODE_CONTRACT_FIELDS)
            ],
            "edges": missing_edge_contract,
            "storage": [{"location": row["location"], "missing_fields": row["missing_fields"]} for row in storage if row["missing_fields"]],
        },
        "interpretation_limits": [
            "System labels support a coarse domestic/international partition; logistics regions and routing authority are separate unconfirmed mappings.",
            "A shared directed topology does not establish permissions or resource semantics for empty and loaded trays.",
            "Edge capacity metadata is not storage inventory or a validated production safety rule; zero capacities are retained.",
            "Existing service-time assumptions are reported, never supplied or corrected by this audit.",
            "Topology alone provides no tray identity lifecycle, old in-transit commitments, forecast history, or executable local empty-tray module.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.profile.resolve() == args.output.resolve():
        parser.error("--output must differ from the read-only --profile")
    try:
        audit = audit_profile(args.profile)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    from .experiment_protocol import write_new_json
    try:
        write_new_json(args.output, audit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(args.output.resolve()), "counts": audit["derived_counts"], "sha256": audit["source"]["sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
