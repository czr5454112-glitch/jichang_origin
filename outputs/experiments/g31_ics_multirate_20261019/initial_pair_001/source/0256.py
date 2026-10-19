"""Decision provenance from a delivered-ACK owner view, never an authority.

Request IDs are allocated by the client's durable outbox. This token only
identifies what that client could read when deciding. The native source and
receiver still validate actual executability when the request is delivered.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json


PROTOCOL_OBSERVATION = "g31.owner_protocol_observation.v1"
CONTEXT_SCHEMA = "g31.local_context_token.v1"
_STATIC_NODE_FIELDS = ("node", "zone", "logistics_zone", "control_partition",
                       "resource_owner", "capacity", "export_min_stock",
                       "allow_export", "allow_receive")
_VIEW_FIELDS = ("schema", "owner_id", "now", "node_records", "edge_records",
                "node_contracts", "edge_contracts", "trays", "jobs", "known_faults",
                "delivered_messages", "client_transfer_ledger", "client_requests",
                "client_commands", "delivered_transfer_acks", "delivered_command_acks",
                "control_projection")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def protocol_projection(observation: dict) -> dict:
    """Copy the explicit online view and derive transfers from delivered ACKs.

    A legacy observation is deliberately rejected. In particular neither an
    extra ``version`` nor an injected truth transfer ledger can enter this
    projection. Node dynamic fields are accepted only for the observing owner.
    Native ``observe_protocol`` supplies the remaining local sensor boundary.
    """
    if observation.get("schema") != PROTOCOL_OBSERVATION:
        raise ValueError("local_context:protocol_observation_required")
    result = {k: deepcopy(observation[k]) for k in _VIEW_FIELDS if k in observation}
    owner = result["owner_id"]
    nodes = []
    for node in result["node_contracts"]:
        row = {k: node[k] for k in _STATIC_NODE_FIELDS if k in node}
        if node.get("resource_owner", node.get("zone")) == owner:
            row.update({k: node[k] for k in ("occupancy", "actual_available") if k in node})
        nodes.append(row)
    result["node_contracts"] = nodes
    for message in result.get("delivered_messages", []):
        if message.get("target_owner") != owner or not 0 <= message["delivered_at"] <= result["now"]:
            raise ValueError("local_context:undelivered_or_wrong_owner_message")
    for key in ("delivered_transfer_acks", "delivered_command_acks"):
        for ack in result.get(key, []):
            if not 0 <= ack["delivered_at"] <= result["now"]:
                raise ValueError("local_context:undelivered_ack")
    result["transfers"] = deepcopy(result.get("client_transfer_ledger", []))
    return result


@dataclass(frozen=True)
class LocalContextToken:
    schema: str
    owner_id: str
    observed_at: float
    static_contract_sha256: str
    local_read_sha256: str
    delivered_read_sha256: str
    # Sequence numbers are scoped by channel/request. Taking their global max
    # would silently miss a new ACK on a different request.
    delivered_sequences: tuple[tuple[str, str, str, int], ...]

    @classmethod
    def from_observation(cls, observation: dict) -> "LocalContextToken":
        view = protocol_projection(observation)
        static = {k: view[k] for k in ("node_records", "edge_records", "edge_contracts")}
        static["node_contracts"] = [{k: n[k] for k in _STATIC_NODE_FIELDS if k in n}
                                    for n in view["node_contracts"]]
        local = {k: view.get(k, []) for k in ("trays", "jobs", "known_faults",
                 "client_transfer_ledger", "client_requests", "client_commands")}
        local["node_sensors"] = [{k: n[k] for k in ("node", "occupancy", "actual_available") if k in n}
                                 for n in view["node_contracts"]
                                 if n.get("resource_owner", n.get("zone")) == view["owner_id"]]
        if "control_projection" in view:
            local["control_projection"] = view["control_projection"]
        delivered = {k: view.get(k, []) for k in ("delivered_messages",
                     "delivered_transfer_acks", "delivered_command_acks")}
        sequences = [("publication", m.get("source_owner", ""), m["message_id"],
                      int(m.get("publication_sequence", 0)))
                     for m in delivered["delivered_messages"]]
        for key in ("delivered_transfer_acks", "delivered_command_acks"):
            sequences.extend((key, view["owner_id"], a["request_id"], int(a["sequence"]))
                             for a in delivered[key])
        return cls(CONTEXT_SCHEMA, view["owner_id"], float(view["now"]), _digest(static),
                   _digest(local), _digest(delivered), tuple(sorted(sequences)))

    @property
    def identity(self) -> str:
        return _digest(asdict(self))

    def to_dict(self) -> dict:
        # JSON round trip also turns immutable tuples into serializable lists.
        return json.loads(json.dumps(asdict(self)))
