"""Independent typed encoder for the opt-in native planning capture v2."""
import hashlib
import struct

def _write_local_capture(body, data):
    """Independent encoding of the documented native typed capture digest."""
    def text(value):
        encoded = value.encode("utf-8")
        data.extend(struct.pack(">Q", len(encoded)))
        data.extend(encoded)
    def integer(value):
        data.extend(struct.pack(">Q", value & ((1 << 64) - 1)))
    def floating(value):
        data.extend(struct.pack(">d", value))
    def boolean(value):
        data.append(1 if value else 0)
    text(body["schema"])
    for key in ("message_id", "source_owner", "target_owner"):
        text(body[key])
    integer(body["publication_sequence"])
    floating(body["captured_at"])
    floating(body["valid_until"])
    text(body["static_contract_sha256"])
    for key in ("queue_discipline", "resource_semantics", "event_semantics", "scorer_mode", "merge_grant_rule", "merge_grant_timing_mode"):
        text(body["semantics"][key])
    floating(body["semantics"]["minimum_service_seconds"])
    integer(len(body["jobs"]))
    for job in body["jobs"]:
        text(job["business_bag_id"])
        integer(job["origin"])
        integer(job["destination"])
        floating(job["arrival"])
        floating(job["deadline"])
        integer(job["storage_node"])
        for key in ("storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds"):
            floating(job[key])
        boolean(job["protected_service"])
        boolean(job["allow_suffix_reroute"])
        text(job["status"])
        for key in ("loaded_at", "storage_entered_at", "storage_released_at"):
            floating(job[key])
    integer(len(body["trays"]))
    for tray in body["trays"]:
        for key in ("tray_id", "business_bag_id", "mode", "ready_kind"):
            text(tray[key])
        for key in ("node", "edge_from", "edge_to", "reception_node", "generation", "traversal_id"):
            integer(tray[key])
        for key in ("available_at", "service_ready_at", "load_complete_at"):
            floating(tray[key])
        boolean(tray["service_ready_known"])
        integer(len(tray["committed_prefix"]))
        for node in tray["committed_prefix"]:
            integer(node)
    integer(len(body["nodes"]))
    for node in body["nodes"]:
        for key in ("node", "occupancy", "actual_available", "unrepresented_occupancy"):
            integer(node[key])
    integer(len(body["known_faults"]))
    for fault in body["known_faults"]:
        integer(fault["from"])
        integer(fault["to"])
        boolean(fault["active"])
        floating(fault["received_at"])
    coverage = body["coverage"]
    text(coverage["scope"])
    boolean(coverage["complete_for_declared_local_scope"])
    integer(len(coverage["local_node_ids"]))
    for node in coverage["local_node_ids"]:
        integer(node)
    for field in ("tray_ids", "business_bag_ids"):
        integer(len(coverage[field]))
        for identity in coverage[field]:
            text(identity)
    integer(coverage["unrepresented_occupancy"])
    boolean(coverage["future_arrivals_included"])



def capture_digest_v2(body):
    data = bytearray()
    def text(value):
        encoded = value.encode("utf-8")
        data.extend(struct.pack(">Q", len(encoded))); data.extend(encoded)
    def integer(value): data.extend(struct.pack(">Q", value & ((1 << 64) - 1)))
    def floating(value): data.extend(struct.pack(">d", value))
    def boolean(value): data.append(1 if value else 0)
    text("czr005.g4irsf14.runtime-state-component.v2")
    text("g31.planning_capture_digest.v2")
    text(body["schema"])
    _write_local_capture(body["local_capture"], data)
    e = body["extension"]
    text(e["schema"]); text(e["source_owner"]); floating(e["captured_at"])
    integer(len(e["terminal_receipts"]))
    for r in e["terminal_receipts"]:
        text(r["receipt_id"]); integer(r["source_local_sequence"]); text(r["source_owner"])
        text(r["event"]); text(r["status"]); text(r["business_bag_id"])
        integer(r["destination"]); text(r["tray_id"]); floating(r["completed_at"])
    c = e["completion_coverage"]
    text(c["scope"]); boolean(c["complete_for_declared_scope"]); floating(c["through"])
    integer(len(c["source_owned_destination_nodes"]))
    for n in c["source_owned_destination_nodes"]: integer(n)
    boolean(c["future_events_included"]); integer(len(c["completed_business_bag_ids"]))
    for j in c["completed_business_bag_ids"]: text(j)
    integer(len(e["submitted_physical_actions"]))
    for a in e["submitted_physical_actions"]:
        text(a["request_id"]); text(a["kind"]); text(a["source_owner"])
        ack = a["last_delivered_ack"]; boolean(ack is not None)
        if ack is not None:
            integer(ack["sequence"]); floating(ack["delivered_at"]); text(ack["status"])
    c = e["action_coverage"]
    text(c["scope"]); floating(c["through"]); boolean(c["complete_for_declared_scope"])
    boolean(c["includes_unsubmitted_python_plans"]); boolean(c["uses_hidden_execution_truth"])
    for key in ("submitted_request_ids", "unresolved_request_ids"):
        integer(len(c[key]))
        for r in c[key]: text(r)
    return hashlib.sha256(data).hexdigest()
