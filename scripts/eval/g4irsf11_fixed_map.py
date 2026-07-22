"""Fail-closed identity and loading for the only G4IRSF11 topology.

G4IRSF11 is deliberately a fixed-real-map programme.  Callers must not accept
an arbitrary, merely self-consistent graph.  The canonical digest normalises
text newlines so a Git LF checkout and a Windows CRLF checkout identify the
same protected JSON document; the raw byte digest is retained as provenance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_MAP_RELATIVE_PATH = Path("data/processed/maps/map2.json")
CANONICAL_MAP_PATH = (ROOT / CANONICAL_MAP_RELATIVE_PATH).resolve()
CANONICAL_MAP_SHA256 = "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
CANONICAL_MAP_HASH_SEMANTICS = "utf8_text_with_crlf_normalized_to_lf"
FIXED_REAL_MAP_ONLY = True


class FixedRealMapError(ValueError):
    """Raised when a caller attempts to use anything except canonical map2."""


def _normalised_text_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixedRealMapError(f"canonical map is not UTF-8: {path}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def normalised_text_sha256(path: Path) -> str:
    return hashlib.sha256(_normalised_text_bytes(path)).hexdigest()


def raw_bytes_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_schema(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise FixedRealMapError("canonical map JSON root must be an object")
    for field in ("nodes", "edges", "heuristic_time"):
        if not isinstance(data.get(field), list):
            raise FixedRealMapError(f"canonical map field {field!r} must be an array")

    nodes = data["nodes"]
    edges = data["edges"]
    heuristic = data["heuristic_time"]
    if len(nodes) != 54 or len(edges) != 69 or len(heuristic) != 54:
        raise FixedRealMapError(
            "canonical map dimensions changed: "
            f"nodes={len(nodes)}, edges={len(edges)}, heuristic_rows={len(heuristic)}"
        )
    locations = [int(node["location"]) for node in nodes]
    if locations != list(range(54)):
        raise FixedRealMapError("canonical map locations must be the exact contiguous range 0..53")
    if any(not isinstance(row, list) or len(row) != 54 for row in heuristic):
        raise FixedRealMapError("canonical map heuristic must be an exact 54x54 matrix")

    declared_edges = {
        (int(edge["start"]), int(edge["end"])) for edge in edges
    }
    outgoing_edges = {
        (int(node["location"]), int(next_node))
        for node in nodes
        for next_node in node.get("outgoing", [])
    }
    if declared_edges != outgoing_edges:
        raise FixedRealMapError("canonical map node outgoing lists and edge table disagree")
    if any(float(edge["speed"]) <= 0.0 for edge in edges):
        raise FixedRealMapError("canonical map contains a non-positive edge speed")
    return data


def assert_canonical_map(path: Path = CANONICAL_MAP_PATH) -> Path:
    resolved = path.resolve(strict=True)
    if resolved != CANONICAL_MAP_PATH:
        raise FixedRealMapError(
            "G4IRSF11 accepts only data/processed/maps/map2.json; "
            f"received {resolved}"
        )
    actual = normalised_text_sha256(resolved)
    if actual != CANONICAL_MAP_SHA256:
        raise FixedRealMapError(
            "canonical map content hash mismatch: "
            f"expected={CANONICAL_MAP_SHA256}, actual={actual}"
        )
    _validate_schema(json.loads(resolved.read_text(encoding="utf-8")))
    return resolved


def canonical_map_data(path: Path = CANONICAL_MAP_PATH) -> dict[str, Any]:
    resolved = assert_canonical_map(path)
    return _validate_schema(json.loads(resolved.read_text(encoding="utf-8")))


def canonical_graph_records(
    path: Path = CANONICAL_MAP_PATH,
) -> tuple[
    list[tuple[int, int, float, int, int, list[int]]],
    list[tuple[int, int, float, float]],
    list[list[float]],
]:
    data = canonical_map_data(path)
    nodes = [
        (
            int(node["location"]),
            int(node["node_type"]),
            float(node.get("service_time", 0.0)),
            int(node.get("x", 0)),
            int(node.get("y", 0)),
            [int(value) for value in node.get("outgoing", [])],
        )
        for node in data["nodes"]
    ]
    edges = [
        (
            int(edge["start"]),
            int(edge["end"]),
            float(edge["length"]),
            float(edge["speed"]),
        )
        for edge in data["edges"]
    ]
    heuristic = [[float(value) for value in row] for row in data["heuristic_time"]]
    return nodes, edges, heuristic


def canonical_map_identity() -> dict[str, Any]:
    path = assert_canonical_map()
    return {
        "fixed_real_map_only": True,
        "repo_relative_path": CANONICAL_MAP_RELATIVE_PATH.as_posix(),
        "resolved_path": str(path),
        "sha256": CANONICAL_MAP_SHA256,
        "sha256_semantics": CANONICAL_MAP_HASH_SEMANTICS,
        "raw_bytes_sha256": raw_bytes_sha256(path),
        "topology_mutation_allowed": False,
    }


def canonical_map_protocol_identity() -> dict[str, Any]:
    """Return the checkout-independent identity used in protocol digests.

    Absolute paths and raw-byte hashes remain useful execution provenance, but
    they differ across operating systems and Git newline policies.  Keeping
    them out of the protocol manifest makes the same protected map produce the
    same protocol digest on every conforming checkout.
    """

    assert_canonical_map()
    return {
        "fixed_real_map_only": True,
        "repo_relative_path": CANONICAL_MAP_RELATIVE_PATH.as_posix(),
        "sha256": CANONICAL_MAP_SHA256,
        "sha256_semantics": CANONICAL_MAP_HASH_SEMANTICS,
        "topology_mutation_allowed": False,
    }
