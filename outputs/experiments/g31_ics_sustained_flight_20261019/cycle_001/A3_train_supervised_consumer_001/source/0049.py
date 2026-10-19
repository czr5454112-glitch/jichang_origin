"""New closed three-case native-data gate for the unchanged fixed96 domain.
Copied digest/owner/ACK/current-view checks stay explicit; no old module globals
are changed. This module accepts supplied data only, never native authority or
predicted protection. Full capture-union stability is conditional on the declared
finite population and common no-new-physical-admissions collection policy.
"""
from __future__ import annotations
import copy, hashlib, json, math, struct
from . import public_preexisting_model as model
from . import public_live_obligation_projection as construction
from .native_preexisting_initial_adapter import capture_digest, coverage_matches_rows
from .native_preexisting_rolling_adapter import CONTRACT_FIELDS
from .planning_capture_v2_contract import validate_extension, PHYSICAL_KINDS, TERMINAL_BY_KIND
from .planning_capture_v3_contract import capture_digest_v3, validate_inflight
from .public_preexisting_v3_model import latest_possible_start
from .public_owned_action_state import current_actions

def unknown(reason, **extra):
    return {"status":"unknown", "reasons":reason if isinstance(reason,list) else [reason],
        "native_delivery_verified":False,"online_information_delivered":False,
        "native_protection_certified":False,"current_state_certified":False,**extra}
def finite(v): return type(v) in (int,float) and math.isfinite(v)
def require(v,why):
    if not v: raise ValueError(why)
def canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)
def public_input(case="mechanism"):
    require(case in construction.construction.CASE_IDS,"unsupported_public_case")
    return construction.inputs()[case]
def supported_contract(*,later=False,case="mechanism"):
    contract=model.public_contract(public_input(case))
    if later:contract["native_semantics"]=copy.deepcopy(model.SUPPORTED_NATIVE_SEMANTICS)
    return contract

def identify_public_case(contract,jobs,*,later=False):
    matches=[]
    for case in construction.construction.CASE_IDS:
        expected=construction.initial_facts(public_input(case))[0]
        if (canonical(contract)==canonical(supported_contract(later=later,case=case)) and set(jobs)==set(expected)
                and all(all(jobs[k][f]==expected[k][f] for f in CONTRACT_FIELDS) for k in jobs)):
            matches.append(case)
    require(len(matches)==1,"unsupported_or_ambiguous_public_graph_and_jobs")
    return matches[0]

def initial_bundle(contract, projected, now):
    try:
        require(type(now) is float and now==.11,"unsupported_initial_epoch")
        jobs={r["business_bag_id"]:r for p in projected.values() for r in p["jobs"]}
        trays={r["tray_id"]:r for p in projected.values() for r in p["trays"]}
        resources={r["node"]:r for p in projected.values() for r in p["resources"]}
        case=identify_public_case(contract,jobs)
        expected_jobs,expected_trays,expected_resources=construction.initial_facts(public_input(case))
        require(set(jobs)==set(expected_jobs) and set(trays)==set(expected_trays) and set(resources)==set(expected_resources),"initial_population")
        fields=(*CONTRACT_FIELDS,"status","loaded_at","storage_entered_at","storage_released_at")
        for k,row in jobs.items():require(all(row[f]==expected_jobs[k][f] for f in fields),"initial_job_contract_or_lifecycle")
        for k,row in trays.items():
            require(all(type(row[f]) is int and row[f]>=0 for f in ("generation","traversal_id")),"initial_public_tray_identity")
            require(all(row[f]==expected_trays[k][f] for f in ("node","mode","edge_from","edge_to","reception_node","generation","traversal_id","business_bag_id","committed_prefix")),"initial_tray_state")
        require(resources==expected_resources,"initial_occupancy_or_available_stock")
        return {"status":"conditional_model_input","now":now,"jobs":jobs,"trays":trays,"resources":resources,
            "contract":copy.deepcopy(contract),"online_information_delivered":False,"native_protection_certified":False}
    except (KeyError,TypeError,ValueError) as e:return unknown(str(e))

def later_bundle(contract,jobs,trays,resources,*,now,phase,source_records,terminal_receipts,
                 owner_pending_tray_requests,entry_receipts,collection_contract):
    try:
        case=identify_public_case(contract,jobs,later=True)
        require(phase in ("first_return","first_reuse_route") and finite(now),"unsupported_phase_or_time")
        require(set(jobs)==model.JOBS and set(trays)=={"L","E","P"},"population")
        # Native's documented default protected_service is True when omitted
        # from the fixed input; the initial public contract ledger records it.
        expected=construction.initial_facts(public_input(case))[0]
        require(all(all(jobs[k][f]==expected[k][f] for f in CONTRACT_FIELDS) for k in jobs),"changed_job_contract")
        require(len(source_records)==2 and {r["owner"] for r in source_records}=={"A","B"},"source_domain")
        floor=min(r["captured_at"] for r in source_records)
        require(finite(floor) and 0<=floor<=now and all(j["arrival"]<=floor for j in jobs.values()),"future_uncaptured_population")
        require(all(finite(j[f]) and (j[f]==-1 or 0<=j[f]<=floor) for j in jobs.values()
            for f in ("loaded_at","storage_entered_at","storage_released_at")),"future_observed_job_epoch")
        require(collection_contract=={"schema":"g31.conditional_collection_quiescence.v1","physical_admissions_quiesced_from":floor,"through":now,"future_python_actions_certified_by_native":False},"quiet_contract")
        require(owner_pending_tray_requests==[],"current_owned_pending_action")
        owners={n["node"]:n["resource_owner"] for n in contract["node_contracts"]}; records={r["owner"]:r for r in source_records}
        require(set(resources)==set(owners),"full_resource_coverage")
        for r in source_records:
            require(r["known_faults"]==[] and r["unresolved_tray_request_ids"]==[],"unresolved_source_action_or_fault")
            actions=r["submitted_physical_actions"];ids=r["submitted_physical_request_ids"]
            require(ids==[a["request_id"] for a in actions] and len(ids)==len(set(ids)) and all(isinstance(i,str) and i for i in ids),"complete_action_ids")
            require([(a["request_id"],a["kind"]) for a in actions]==sorted((a["request_id"],a["kind"]) for a in actions),"action_order")
            for action in actions:
                ack=action.get("last_delivered_ack",{})
                require(action["source_owner"]==r["owner"] and action["kind"] in PHYSICAL_KINDS and type(ack.get("sequence")) is int and ack["sequence"]>0
                    and ack.get("status") in TERMINAL_BY_KIND[action["kind"]] and finite(ack.get("delivered_at")) and 0<=ack["delivered_at"]<floor,"physical_action_not_delivered_terminal_before_capture_union")
            require(set(r["node_ids"])=={n for n,o in owners.items() if o==r["owner"]},"owner_node_coverage")
        completed={r["business_bag_id"]:r["completed_at"] for r in terminal_receipts}
        require(set(completed)=={"loaded"} and len(terminal_receipts)==1 and all(finite(t) and 0<=t<=floor for t in completed.values()),"complete_delivered_prefix")
        require(jobs["loaded"]["status"]=="completed" and jobs["reuse2"]["status"]=="waiting_for_tray","lifecycle_scope")
        lt=trays["L"]
        require((lt["node"],lt["mode"],lt["business_bag_id"])==((6,"empty","") if phase=="first_return" else (7,"loaded","reuse1")),"current_L_phase")
        require(jobs["reuse1"]["status"]==("waiting_for_tray" if phase=="first_return" else "in_transit"),"reuse_job_phase")
        require(all(type(t[f]) is int and t[f]>=0 for t in trays.values() for f in ("generation","traversal_id")),"public_tray_identity")
        require(all(t["reception_node"]==-1 for t in trays.values()),"unsupported_additional_lease")
        moving={k:t for k,t in trays.items() if t["edge_to"]>=0};entries={e["tray_id"]:e for e in entry_receipts}
        require(set(entries)==set(moving) and len(entries)==len(entry_receipts),"observed_entry_coverage")
        travel={(u,v):max(.001,length/speed) for u,v,length,speed in contract["edge_records"]};service={n[0]:max(.001,n[2]) for n in contract["node_records"]}
        stability=[]
        for name,t in trays.items():
            source=owners[t["node"]];bound=None
            require(finite(t["available_at"]) and 0<=t["available_at"],"unsupported_tray_available_epoch")
            if name=="E" and name not in moving and t["mode"]=="loading":
                # Accepted027 capture sets loading.available_at to the
                # observed LOAD_START + public load duration, not a past
                # availability event. Only this already-supported typed
                # loading phase may carry that future completion bound.
                require(t["available_at"]==t["load_complete_at"]==t["service_ready_at"]>now,
                        "E_loading_available_bound")
            else:
                require(t["available_at"]<=floor,"unsupported_tray_available_epoch")
            if name in moving:
                e=entries[name];edge=t["edge_from"],t["edge_to"];job={"E":"receiver","P":"blocker"}.get(name)
                require(job and edge in ({(1,3),(3,4)} if name=="E" else {(9,3),(3,10)}) and t["node"]==edge[0] and t["mode"]=="loaded" and t["business_bag_id"]==job and jobs[job]["status"]=="in_transit","unsupported_moving_state")
                require(e["source_owner"]==source and e["receipt_event"]=="EDGE_ENTER" and all(e[f]==t[f] for f in ("tray_id","business_bag_id","generation","traversal_id","edge_from","edge_to")),"entry_identity")
                require(all(finite(e[f]) for f in ("entered_at","derived_edge_exit_at","static_edge_travel_seconds")) and 0<=jobs[job]["loaded_at"]<=e["entered_at"]<=floor and e["static_edge_travel_seconds"]==travel[edge] and e["derived_edge_exit_at"]==e["entered_at"]+travel[edge] and now<e["derived_edge_exit_at"],"entry_interval")
                require(t["committed_prefix"]==(([1] if edge==(1,3) else [1,3]) if name=="E" else ([9] if edge==(9,3) else [9,3])),"current_leg_prefix")
                if name=="P":require(0<=jobs[job]["storage_entered_at"]<=jobs[job]["storage_released_at"]<=e["entered_at"],"P_storage_release_history")
                bound=e["derived_edge_exit_at"]
            else:
                require(t["edge_from"]==-1 and t["service_ready_known"] is True,"stationary_known_epoch")
                mode=t["mode"]
                if name=="P":
                    j=jobs["blocker"];bound=max(j["storage_release_at"],j["storage_entered_at"]+j["storage_min_dwell"])
                    require(mode=="storage" and t["node"]==9 and t["business_bag_id"]=="blocker" and j["status"]=="storage" and 0<=j["storage_entered_at"]<=floor and j["storage_released_at"]==-1 and t["ready_kind"]=="observed_storage_release_bound" and t["service_ready_at"]==bound>now,"P_stable_storage")
                elif name=="E":
                    j=jobs["receiver"];bound=t["load_complete_at"]
                    require(mode=="loading" and t["node"]==1 and t["business_bag_id"]=="receiver" and j["status"]=="loading" and t["ready_kind"]=="observed_load_completion" and finite(bound) and t["service_ready_at"]==bound>now and latest_possible_start(bound,j["load_seconds"])<=floor,"E_stable_loading")
                elif phase=="first_return":
                    require(t["ready_kind"]=="empty_available_at" and finite(t["available_at"]) and completed["loaded"]<=t["available_at"]==t["service_ready_at"]<=floor,"L_available_release")
                else:
                    bound=t["service_ready_at"]
                    require(t["ready_kind"]=="committed_local_service_end" and finite(bound) and bound>now and latest_possible_start(bound,service[7])<=floor and 0<=jobs["reuse1"]["loaded_at"]<=floor,"L_stable_local_service")
            stability.append({"tray_id":name,"source_owner":source,"floor":floor,"now":now,"next_bound":bound})
        for node,r in resources.items():
            occupants=[k for k,t in trays.items() if (t["edge_to"] if t["edge_to"]>=0 else t["node"])==node]
            local=sum(owners[trays[k]["node"]]==owners[node] for k in occupants)
            available=sum(t["node"]==node and t["edge_to"]<0 and t["mode"]=="empty" and t["available_at"]<=now for t in trays.values())
            require(all(type(r[f]) is int for f in ("occupancy","actual_available","unrepresented_occupancy")) and r["occupancy"]==len(occupants) and r["actual_available"]==available and r["unrepresented_occupancy"]==len(occupants)-local,"OR_receiving_occupancy")
        for owner,r in records.items():require(r["unrepresented_occupancy"]==sum(resources[n]["unrepresented_occupancy"] for n,o in owners.items() if o==owner),"source_occupancy_coverage")
        return {"status":"conditional_model_input","phase":phase,"now":now,"jobs":copy.deepcopy(jobs),"trays":copy.deepcopy(trays),"resources":copy.deepcopy(resources),"source_records":copy.deepcopy(source_records),"terminal_receipts":copy.deepcopy(terminal_receipts),"stability":stability,"conditional_stability_only":True,"current_state_certified":False,"online_information_delivered":False,"native_protection_certified":False}
    except (KeyError,TypeError,ValueError,OverflowError) as e:return unknown(str(e))


def validate_pair(view: dict, own_ack: dict, received: list[dict]) -> dict:
    """Validate an owner-local evidence bundle, without authenticating its origin.

    This is intentionally restricted to the published three-tray/five-obligation
    experiment. Its known population and absence of later arrivals are public
    experiment contracts, not inferred from an empty remote observation.
    """
    try:
        now, owner = view["now"], view["owner_id"]
        peer = {"A": "B", "B": "A"}[owner]
        if now != model.START or not math.isfinite(now):
            return unknown("unsupported_decision_epoch")
        if own_ack.get("status") != "delivered" or not (0 <= own_ack["delivered_at"] <= now):
            return unknown("missing_or_undelivered_self_copy")
        own = own_ack["planning_snapshot"]
        peers = [m for m in received if m["capture"]["source_owner"] == peer]
        if len(peers) != 1 or len(received) != 1:
            return unknown("missing_duplicate_or_unexpected_peer_snapshot")
        envelopes = {owner: own, peer: peers[0]}
        contract = model.public_contract(view)
        node_owner = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        all_trays, all_jobs, all_nodes = {}, {}, {}
        projected, transitions = {}, []
        digests, capture_times = set(), set()
        for source, envelope in envelopes.items():
            body = envelope["capture"]
            if (envelope["schema"] != "g31.planning_snapshot.v1" or envelope["kind"] != "planning_snapshot"
                    or envelope["digest_format"] != "g31.planning_capture_digest.v1"
                    or body["schema"] != "g31.planning_capture.v1"):
                return unknown("invalid_snapshot_schema")
            if body["source_owner"] != source or body["target_owner"] != ({"A", "B"} - {source}).pop():
                return unknown("capture_channel_mismatch")
            capture, delivery, expiry = body["captured_at"], envelope["delivered_at"], body["valid_until"]
            if not (math.isfinite(capture) and math.isfinite(delivery) and math.isfinite(expiry)
                    and .05 <= capture <= delivery <= now < expiry and now - capture <= .06):
                return unknown("invalid_causal_time_or_unsupported_capture_age")
            if envelope["status"] != "conditional":
                return unknown("latest_snapshot_expired_or_unusable")
            if source == owner and (not (capture == own_ack["executed_at"] <= own_ack["completed_at"]
                    == delivery <= own_ack["delivered_at"] <= now) or own_ack["result_id"] != body["message_id"]):
                return unknown("self_ack_capture_order_or_identity_mismatch")
            if type(body["publication_sequence"]) is not int or body["publication_sequence"] <= 0:
                return unknown("invalid_publication_sequence")
            if len(body["static_contract_sha256"]) != 64:
                return unknown("invalid_static_digest")
            if capture_digest(body) != envelope["payload_sha256"]:
                return unknown("capture_digest_mismatch")
            digests.add(body["static_contract_sha256"])
            capture_times.add(capture)
            semantics = body["semantics"]
            if (semantics["queue_discipline"] != "fifo" or semantics["resource_semantics"] != contract["resource_semantics"]
                    or semantics["event_semantics"] != contract["event_semantics"]
                    or semantics["scorer_mode"] != "S4_queue_aware_rule_only"
                    or semantics["merge_grant_rule"] != "M3"
                    or semantics["merge_grant_timing_mode"] != "jit_fair_aging_deadline"
                    or semantics["minimum_service_seconds"] != .001):
                return unknown("unsupported_native_resource_semantics")
            coverage = body["coverage"]
            local_nodes = sorted(n for n, o in node_owner.items() if o == source)
            if (not coverage["complete_for_declared_local_scope"] or coverage["future_arrivals_included"]
                    or coverage["unrepresented_occupancy"] != 0 or coverage["local_node_ids"] != local_nodes
                    or not coverage_matches_rows(coverage["tray_ids"], body["trays"], "tray_id")
                    or not coverage_matches_rows(coverage["business_bag_ids"], body["jobs"], "business_bag_id")):
                return unknown("missing_or_unrepresented_coverage")
            if sorted(n["node"] for n in body["nodes"]) != local_nodes:
                return unknown("local_resource_coverage_mismatch")
            if body["known_faults"]:
                return unknown("unsupported_known_fault")
            jobs, trays = copy.deepcopy(body["jobs"]), copy.deepcopy(body["trays"])
            for row in jobs:
                if row["business_bag_id"] in all_jobs or node_owner[row["origin"]] != source:
                    return unknown("duplicate_job_or_source_authority")
                if any(row[k] > capture for k in ("arrival", "loaded_at", "storage_entered_at", "storage_released_at")):
                    return unknown("future_observed_job_epoch")
                all_jobs[row["business_bag_id"]] = row
            for tray in trays:
                if tray["tray_id"] in all_trays or node_owner[tray["node"]] != source:
                    return unknown("duplicate_tray_or_source_authority")
                if tray["edge_to"] != -1 or tray["edge_from"] != -1 or tray["reception_node"] != -1:
                    return unknown("unsupported_inflight_or_receiving_state")
                if tray["committed_prefix"] != [tray["node"]]:
                    return unknown("unsupported_committed_history")
                all_trays[tray["tray_id"]] = tray
                if tray["tray_id"] == "L":
                    job = next(j for j in jobs if j["business_bag_id"] == "loaded")
                    if (tray["node"] != 0 or tray["business_bag_id"] != "loaded" or tray["mode"] != "loading"
                            or not tray["service_ready_known"] or tray["ready_kind"] != "observed_load_completion"
                            or not capture < tray["service_ready_at"] == tray["load_complete_at"] <= now
                            or job["loaded_at"] != -1 or job["status"] != "loading"):
                        return unknown("unsupported_loading_projection")
                    finish = tray["load_complete_at"]
                    service = next(n[2] for n in contract["node_records"] if n[0] == 0)
                    if finish + service <= now:
                        return unknown("source_dispatch_may_have_occurred")
                    transitions.append({"source": source, "tray_id": "L", "from_mode": "loading", "to_mode": "loaded",
                        "source_captured_at": capture, "source_known_load_complete_at": finish,
                        "projected_at": now, "first_possible_source_service_end": finish + service,
                        "scope": "conditional native-observed committed load completion; not a fresh remote observation"})
                    tray["mode"], tray["available_at"] = "loaded", 0.
                    job["status"], job["loaded_at"] = "in_transit", finish
                elif tray["tray_id"] == "E":
                    if (tray["node"] != 5 or tray["mode"] != "empty" or tray["business_bag_id"]
                            or not tray["service_ready_known"] or tray["ready_kind"] != "empty_available_at"
                            or tray["available_at"] > capture):
                        return unknown("unsupported_empty_projection")
                elif tray["tray_id"] == "P":
                    job = next(j for j in jobs if j["business_bag_id"] == "blocker")
                    if (tray["node"] != 1 or tray["mode"] != "loading" or tray["business_bag_id"] != "blocker"
                            or not tray["service_ready_known"] or tray["ready_kind"] != "observed_load_completion"
                            or not capture <= now < tray["service_ready_at"] == tray["load_complete_at"] == job["load_seconds"]
                            or job["status"] != "loading" or job["loaded_at"] != -1):
                        return unknown("unsupported_blocker_loading_state")
                    tray["load_end"] = tray["load_complete_at"]
                else:
                    return unknown("unsupported_tray_population")
            for node in body["nodes"]:
                if node["node"] in all_nodes or node["unrepresented_occupancy"] != 0:
                    return unknown("unrepresented_or_duplicate_resource")
                all_nodes[node["node"]] = node
            projected[source] = {"owner": source, "identity": "projection:" + body["message_id"], "captured_at": now,
                "delivered_at": None, "expires_at": expiry, "provenance": "conditional_aged_native_capture_projection",
                "jobs": jobs, "trays": trays, "resources": [{k: n[k] for k in ("node", "occupancy", "actual_available")} for n in body["nodes"]],
                # Native capture order was validated above. The separate pure
                # model contract uses canonical sorted coverage identities;
                # normalize only this derived projection, never the raw body
                # or its digest/ACK self-copy.
                "coverage": {"jobs": sorted(coverage["business_bag_ids"]),
                    "trays": sorted(coverage["tray_ids"]), "resources": local_nodes},
                "known_faults": [], "source_identity": body["message_id"],
                "model_epoch_field_semantics": "legacy model captured_at denotes projected state epoch here, never native capture time",
                "projected_at": now, "source_captured_at": capture, "source_delivered_at": delivery,
                "age_seconds": now - capture}
        if len(digests) != 1 or len(capture_times) != 1:
            return unknown("mismatched_static_contract_or_capture_epoch")
        if set(all_jobs) != model.JOBS or set(all_trays) != {"L", "E", "P"}:
            return unknown("incomplete_declared_population")
        # Check this owner's fresh facts only. No peer observation is read.
        own_projected = projected[owner]
        local_tray_fields = ("tray_id", "node", "mode", "edge_from", "edge_to", "reception_node",
                             "generation", "traversal_id", "business_bag_id", "committed_prefix")
        canonical = lambda rows, fields: sorted([{k: r[k] for k in fields} for r in rows], key=lambda r: json.dumps(r, sort_keys=True))
        if canonical(view["trays"], local_tray_fields) != canonical(own_projected["trays"], local_tray_fields):
            return unknown("local_tray_changed_since_capture")
        job_fields = tuple(own_projected["jobs"][0])
        if canonical(view["jobs"], job_fields) != canonical(own_projected["jobs"], job_fields):
            return unknown("local_obligation_changed_since_capture")
        local_nodes = [n for n in view["node_contracts"] if n["resource_owner"] == owner]
        if canonical(local_nodes, ("node", "occupancy", "actual_available")) != canonical(own_projected["resources"], ("node", "occupancy", "actual_available")):
            return unknown("local_resource_changed_since_capture")
        if view["known_faults"]:
            return unknown("local_fault_changed_since_capture")
        bundle = initial_bundle(contract, projected, now)
        if bundle["status"] != "conditional_model_input":
            return unknown("unsupported_projected_model_input", model_reasons=bundle["reasons"])
        identity = hashlib.sha256(json.dumps([envelopes[o]["capture"] for o in ("A", "B")], sort_keys=True).encode()).hexdigest()
        return {"status": "conditional_validated_data", "native_delivery_verified": False,
            "owner": owner, "peer": peer, "source_capture_pair_sha256": identity, "bundle": bundle,
            "native_protection_certified": False, "conditional_projection": transitions,
            "capture_age_seconds": {o: now - envelopes[o]["capture"]["captured_at"] for o in ("A", "B")},
            "envelopes": copy.deepcopy(envelopes), "own_delivered_ack": copy.deepcopy(own_ack),
            "agreement_certified": False, "assumptions": ["published fixture has exactly three trays and five obligations, all released by .05",
                "no intervening physical commands before .11; initial planning and demand messages only",
                "peer committed load completion is projected conditionally; only own current state revalidated",
                "one owner cannot infer peer readiness or atomic action agreement from snapshots alone"]}
    except (KeyError, TypeError, ValueError, StopIteration, OverflowError, struct.error) as exc:
        return unknown("invalid_snapshot_or_view_shape", error=type(exc).__name__ + ":" + str(exc))

def validate_later_pair(view, own_ack, received, *, retained, own_actions, phase, collection_contract):
    """Validate supplied data only; no native collector or trust mint exists here."""
    try:
        owner, now = view["owner_id"], view["now"]
        peer = {"A": "B", "B": "A"}[owner]
        if (not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now)
                or retained["owner"] != owner or not 0 <= retained["retained_at"] <= now
                or set(retained["contracts"]) != model.JOBS):
            return unknown("missing_retained_public_contract_ledger")
        if own_ack.get("status") != "delivered" or not 0 <= own_ack.get("delivered_at", math.inf) <= now:
            return unknown("missing_delivered_v3_self_copy")
        if len(received) != 1:
            return unknown("missing_duplicate_or_unexpected_v3_peer_capture")
        envelopes = {owner: own_ack["planning_snapshot_v3"], peer: received[0]}
        contract = model.public_contract(view)
        contract["native_semantics"] = copy.deepcopy(model.SUPPORTED_NATIVE_SEMANTICS)
        owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        jobs = {key: {**copy.deepcopy(row), "status": "unknown", "loaded_at": -1.,
            "storage_entered_at": -1., "storage_released_at": -1.} for key, row in retained["contracts"].items()}
        trays, resources, source_records, terminals, own_local = {}, {}, [], [], None
        entries = []
        seen_jobs = set()
        for source, envelope in envelopes.items():
            body = envelope["capture"]
            if (envelope.get("schema") != "g31.planning_snapshot.v3" or envelope.get("kind") != "planning_snapshot_v3"
                    or envelope.get("digest_format") != "g31.planning_capture_digest.v3"
                    or body.get("schema") != "g31.planning_capture.v3"
                    or capture_digest_v3(body) != envelope["payload_sha256"]):
                return unknown("invalid_v3_schema_or_digest")
            local, extension = body["capture_v2"]["local_capture"], body["capture_v2"]["extension"]
            capture, delivery, expiry = local["captured_at"], envelope["delivered_at"], local["valid_until"]
            if (local.get("schema") != "g31.planning_capture.v1" or local["source_owner"] != source
                    or local["target_owner"] != ({"A", "B"} - {source}).pop()
                    or not isinstance(local["message_id"], str) or not local["message_id"]
                    or type(local["publication_sequence"]) is not int or local["publication_sequence"] <= 0
                    or local["static_contract_sha256"] != retained["static_contract_sha256"]
                    or envelope.get("status") != "conditional"
                    or not all(math.isfinite(v) for v in (capture, delivery, expiry))
                    or not 0 <= capture <= delivery <= now < expiry or now - capture > .05):
                return unknown("invalid_v3_channel_contract_or_causal_age")
            inflight = validate_inflight(body, contract, now=now, delivered_at=delivery)
            if inflight["status"] != "conditional_inflight_extension_data":
                return unknown("invalid_v3_observed_entry_extension", extension_check=inflight)
            entries.extend(copy.deepcopy(inflight["entries"]))
            available = delivery
            if source == owner:
                if (not (capture == own_ack["executed_at"] <= own_ack["completed_at"] == delivery
                        <= own_ack["delivered_at"] <= now) or own_ack["result_id"] != local["message_id"]):
                    return unknown("v3_self_ack_identity_or_time_mismatch")
                available = own_ack["delivered_at"]
                own_local = local
            checked = validate_extension(extension, source_owner=source, captured_at=capture,
                node_owners=owners, retained_job_contracts=retained["contracts"],
                local_action_ledger=own_actions if source == owner else None)
            if checked["status"] != "conditional_extension_data":
                return unknown("unsupported_v3_extension", extension_check=checked)
            coverage = local["coverage"]
            if (coverage["scope"] != "source_waiting_or_locally_carried_released_jobs_and_local_trays"
                    or coverage["complete_for_declared_local_scope"] is not True or coverage["future_arrivals_included"] is not False
                    or type(coverage["unrepresented_occupancy"]) is not int or coverage["unrepresented_occupancy"] < 0 or local["known_faults"]
                    or coverage["local_node_ids"] != [n["node"] for n in local["nodes"]]
                    or coverage["tray_ids"] != [t["tray_id"] for t in local["trays"]]
                    or coverage["business_bag_ids"] != [j["business_bag_id"] for j in local["jobs"]]):
                return unknown("incomplete_v3_local_scope")
            for row in local["jobs"]:
                key = row["business_bag_id"]
                if key in seen_jobs or key not in jobs or {k: row[k] for k in CONTRACT_FIELDS} != retained["contracts"][key]:
                    return unknown("changed_duplicate_or_unknown_job_contract")
                seen_jobs.add(key); jobs[key] = copy.deepcopy(row)
            for row in local["trays"]:
                key = row["tray_id"]
                if key in trays or owners.get(row["node"]) != source:
                    return unknown("duplicate_or_foreign_tray_capture")
                trays[key] = copy.deepcopy(row)
            for row in local["nodes"]:
                key = row["node"]
                if key in resources or owners.get(key) != source:
                    return unknown("duplicate_or_foreign_node_capture")
                resources[key] = copy.deepcopy(row)
            for key, row in checked["completed_receipts"].items():
                if jobs[key]["status"] not in ("unknown", "completed"):
                    return unknown("completion_conflicts_with_observed_lifecycle")
                jobs[key]["status"] = "completed"
                terminals.append({"business_bag_id": key, "status": "completed", "source_owner": source,
                    "completed_at": row["completed_at"], "captured_at": capture, "delivered_at": available,
                    "identity": row["receipt_id"], "capture_message_id": local["message_id"]})
            source_records.append({"owner": source, "identity": local["message_id"], "captured_at": capture,
                "delivered_at": available, "valid_until": expiry, "known_faults": copy.deepcopy(local["known_faults"]),
                "unrepresented_occupancy": coverage["unrepresented_occupancy"],
                "unresolved_tray_request_ids": checked["unresolved_request_ids"], "semantics": copy.deepcopy(local["semantics"]),
                "submitted_physical_request_ids": copy.deepcopy(extension["action_coverage"]["submitted_request_ids"]),
                "submitted_physical_actions": copy.deepcopy(extension["submitted_physical_actions"]),
                "node_ids": coverage["local_node_ids"], "tray_ids": coverage["tray_ids"], "job_ids": coverage["business_bag_ids"]})
        canonical = lambda rows, fields: sorted(({key: row[key] for key in fields} for row in rows), key=lambda row: json.dumps(row, sort_keys=True))
        tray_fields = ("tray_id", "node", "mode", "edge_from", "edge_to", "reception_node", "generation", "traversal_id", "business_bag_id", "committed_prefix", "available_at")
        if canonical(view["trays"], tray_fields) != canonical(own_local["trays"], tray_fields):
            return unknown("owned_tray_changed_after_v3_capture")
        current_trays = {t["tray_id"]: t for t in view["trays"]}
        for entry in entries:
            if entry["source_owner"] != owner: continue
            current = current_trays.get(entry["tray_id"], {})
            actual_exit = current.get("edge_exit_at")
            if (type(actual_exit) not in (int, float) or not math.isfinite(actual_exit)
                    or actual_exit != entry["derived_edge_exit_at"] or not now < actual_exit):
                return unknown("owned_observed_entry_changed_after_v3_capture")
        job_fields = (*CONTRACT_FIELDS, "status", "loaded_at", "storage_entered_at", "storage_released_at")
        # Full owner observations retain source jobs after their trays leave.
        # The capture's explicit scope is waiting or locally carried jobs. Use
        # that exact scope for freshness, then require an actual receipt for
        # every completed job excluded from this owner's active capture.
        carried = {t["business_bag_id"] for t in view["trays"] if t["business_bag_id"]}
        if any(j["business_bag_id"] not in retained["contracts"] or
            {k: j[k] for k in CONTRACT_FIELDS} != retained["contracts"][j["business_bag_id"]] for j in view["jobs"]):
            return unknown("owned_observation_contract_differs_from_retained_ledger")
        scoped_jobs = [j for j in view["jobs"] if j["status"] != "unreleased" and
            (j["business_bag_id"] in carried or j["status"] == "waiting_for_tray" and owners.get(j["origin"]) == owner)]
        completed_ids = {r["business_bag_id"] for r in terminals}
        if any(j["status"] == "completed" and j["business_bag_id"] not in completed_ids for j in view["jobs"]):
            return unknown("owned_completed_job_without_delivered_terminal_receipt")
        if canonical(scoped_jobs, job_fields) != canonical(own_local["jobs"], job_fields):
            return unknown("owned_job_changed_after_v3_capture")
        own_nodes = [n for n in view["node_contracts"] if n["resource_owner"] == owner]
        if canonical(own_nodes, ("node", "occupancy", "actual_available")) != canonical(own_local["nodes"], ("node", "occupancy", "actual_available")) or view["known_faults"]:
            return unknown("owned_resource_or_fault_changed_after_v3_capture")
        bundle = later_bundle(contract, jobs, trays, resources, now=now, phase=phase,
            source_records=source_records, terminal_receipts=terminals, owner_pending_tray_requests=[], entry_receipts=entries, collection_contract=collection_contract)
        if bundle["status"] != "conditional_model_input":
            return unknown("unsupported_later_model_state", bundle=bundle)
        return {"status": "conditional_validated_later_v3_data", "bundle": bundle, "native_delivery_verified": False,
            "online_information_delivered": False, "native_protection_certified": False,
            "agreement_certified": False, "envelopes": copy.deepcopy(envelopes), "own_delivered_ack": copy.deepcopy(own_ack),
            "assumptions": ["published three-tray five-job domain and no unannounced exogenous actions",
                "common controller quiesces physical admissions while collecting this pair; native does not certify future Python plans",
                "only this owner's current view is revalidated; peer age remains conditional"]}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return unknown("malformed_later_capture_pair", error=type(error).__name__ + ":" + str(error))

def validate_collected_endpoints(view, command, returned, *, retained, own_actions, phase,
                                 own_request_id, peer_message_id, collection_started_at,
                                 policy_quiet_since, own_request):
    """Validate supplied endpoint data only; all existing downstream guards run."""
    raw = {"view": copy.deepcopy(view), "command": copy.deepcopy(command),
           "received": copy.deepcopy(returned)}
    try:
        now, owner = view["now"], view["owner_id"]
        if (not all(finite(v) for v in (now, collection_started_at, policy_quiet_since))
                or not 0 <= policy_quiet_since <= collection_started_at <= now
                or owner not in {"A", "B"}
                or not isinstance(peer_message_id, str) or not peer_message_id
                or not isinstance(own_request_id, str) or not own_request_id):
            return unknown("missing_explicit_collection_or_quiet_policy_binding", raw_endpoints=raw)
        peer = {"A": "B", "B": "A"}[owner]
        if (own_request.get("request_id") != own_request_id
                or own_request.get("owner_id") != owner
                or own_request.get("target_owner") != peer
                or own_request.get("kind") != "planning_snapshot_v3"):
            return unknown("own_immutable_publication_payload_binding_mismatch", raw_endpoints=raw)
        if (command.get("request_id") != own_request_id
                or command.get("kind") != "planning_snapshot_v3"
                or command.get("status") != "acknowledged"
                or type(command.get("attempt")) is not int or command["attempt"] < 1):
            return unknown("own_command_request_binding_mismatch", raw_endpoints=raw)
        ack = command.get("last_delivered_ack", {})
        own = ack.get("planning_snapshot_v3", {}).get("capture", {}).get("capture_v2", {}).get("local_capture", {})
        if (ack.get("status") != "delivered"
                or not isinstance(ack.get("result_id"), str) or not ack["result_id"]
                or ack["result_id"] != own.get("message_id")
                or own.get("source_owner") != owner or own.get("target_owner") != peer):
            return unknown("own_ack_generated_message_binding_mismatch", raw_endpoints=raw)
        selected = [row for row in returned if row.get("capture", {}).get("capture_v2", {})
                    .get("local_capture", {}).get("message_id") == peer_message_id]
        if len(selected) != 1:
            return unknown("selected_peer_message_missing_or_duplicate", raw_endpoints=raw)
        peer_local = selected[0]["capture"]["capture_v2"]["local_capture"]
        if (not finite(own.get("captured_at")) or not finite(peer_local.get("captured_at"))
                or not collection_started_at <= own["captured_at"] <= now
                or not collection_started_at <= peer_local["captured_at"] <= now):
            return unknown("selected_capture_precedes_collection_or_is_future", raw_endpoints=raw)
        floor = min(own["captured_at"], peer_local["captured_at"])
        quiet = {"schema": "g31.conditional_collection_quiescence.v1",
                 "physical_admissions_quiesced_from": floor, "through": now,
                 "future_python_actions_certified_by_native": False}
        result = validate_later_pair(view, ack, selected, retained=retained,
            own_actions=own_actions, phase=phase, collection_contract=quiet)
        if result["status"] == "conditional_validated_later_v3_data":
            current=current_actions(view)
            source=next(r for r in result["bundle"]["source_records"] if r["owner"]==owner)
            if current["pending_request_ids"] or [(r["request_id"],r["kind"]) for r in current["actions"]] != [(r["request_id"],r["kind"]) for r in source["submitted_physical_actions"]]:
                return unknown("current_owned_action_scope_changed",raw_endpoints=raw)
            if any(r["last_delivered_ack"] is None or not r["last_delivered_ack"]["delivered_at"] < floor for r in current["actions"]):
                return unknown("current_owned_ACK_crosses_union",raw_endpoints=raw)
            result["bundle"]["owner_current_action_facts"]=current
        result.update(raw_endpoints=raw, policy_quiet_since=policy_quiet_since,
            collection_started_at=collection_started_at, selected_peer_message_id=peer_message_id,
            endpoint_identity_binding={"own_request_id": own_request_id,
                "native_generated_message_id": own["message_id"],
                "native_ack_result_id": ack["result_id"], "own_command_kind": command["kind"],
                "own_immutable_request": copy.deepcopy(own_request)})
        return result
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return unknown("malformed_native_endpoint_replay", raw_endpoints=raw,
                       error=type(error).__name__ + ":" + str(error))
