"""Conditional later-state finite joint model, independent of native outcomes.

Supported checkpoints are the first L return opportunity at6 or its first
loaded reuse service at7, with E still loading at1 or finished at4. This is a
new model version; the earlier .11 model/evidence is not changed. Input data
alone never certifies native delivery or physical individual protection.
"""
from __future__ import annotations
import copy
import hashlib
import heapq
import json
import math
from . import public_reuse_model as initial
from . import research_preexisting_occupancy_domain as domain

VERSION = "public-preexisting-3tray-5job-v1"
JOBS = domain.JOBS
START, HORIZON, PERIOD = initial.START, initial.HORIZON, initial.PERIOD
Capture = initial.Capture
SUPPORTED_NATIVE_SEMANTICS = {"queue_discipline": "fifo", "resource_semantics": "R3_java_node_window_compatible",
    "event_semantics": "E4_batch_plus_destination_merge_request", "scorer_mode": "S4_queue_aware_rule_only",
    "merge_grant_rule": "M3", "merge_grant_timing_mode": "jit_fair_aging_deadline", "minimum_service_seconds": .001}


def public_contract(view):
    value = initial.public_contract(view)
    value["scope"] = "SYNTHETIC_3TRAY_5OBLIGATION_ONLY"
    value["protocol"]["receiver_load_public"] = "delivered_job_contract"
    return value


def supported_contract():
    data = domain.make_bundle(domain.cases()[0])["contract"]
    value = public_contract(data)
    value["native_semantics"] = copy.deepcopy(SUPPORTED_NATIVE_SEMANTICS)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unknown_input(reasons):
    return {"status": "unknown", "reasons": sorted(set(reasons)), "online_information_delivered": False,
        "capture_pair_sha256": None, "model_version": VERSION}


CONTRACT_FIELDS = ("business_bag_id", "origin", "destination", "arrival", "deadline", "storage_node",
    "storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds", "allow_suffix_reroute")


def infer_case(jobs):
    """Case parameters come only from the supplied complete job contracts."""
    if set(jobs) != JOBS: return None
    for case in domain.cases():
        expected = domain.make_bundle(case)["jobs"]
        if all(all(jobs[key].get(field) == row[field] for field in CONTRACT_FIELDS)
               and jobs[key].get("protected_service", True) is True for key, row in expected.items()):
            return copy.deepcopy(case)
    return None


def assemble(contract, captures, now):
    """Restricted initial projection data; native authentication is external."""
    try:
        expected = supported_contract(); expected.pop("native_semantics")
        if _canonical(contract) != _canonical(expected) or now != START:
            return _unknown_input(["unsupported_initial_static_or_protocol_contract"])
        sources = [c.read() for c in captures]
        if len(sources) != 2 or {s["owner"] for s in sources} != {"A", "B"}:
            return _unknown_input(["missing_initial_sources"])
        jobs, trays, resources = {}, {}, {}
        owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        for source in sources:
            if (source["captured_at"] != now or not now < source["expires_at"] or source["known_faults"]
                    or source.get("source_captured_at", now + 1) > now):
                return _unknown_input(["unsupported_initial_capture_epoch"])
            for name, field, target in (("jobs", "business_bag_id", jobs), ("trays", "tray_id", trays), ("resources", "node", resources)):
                rows = source[name]; ids = [row[field] for row in rows]
                if len(ids) != len(set(ids)) or sorted(ids) != source["coverage"][name] or set(ids) & set(target):
                    return _unknown_input(["missing_duplicate_initial_coverage"])
                for row in rows:
                    node = row["origin"] if name == "jobs" else row["node"]
                    if owners.get(node) != source["owner"]: return _unknown_input(["foreign_initial_source_fact"])
                    target[row[field]] = copy.deepcopy(row)
        case = infer_case(jobs)
        if case is None or set(trays) != {"L", "E", "P"} or set(resources) != set(owners):
            return _unknown_input(["unsupported_initial_population_or_obligations"])
        if any(t["edge_to"] != -1 or t["edge_from"] != -1 or t["reception_node"] != -1 for t in trays.values()):
            return _unknown_input(["unsupported_initial_inflight"])
        if ((trays["L"]["node"], trays["L"]["mode"], trays["L"]["business_bag_id"]) != (0, "loaded", "loaded")
                or jobs["loaded"]["loaded_at"] != .1
                or (trays["E"]["node"], trays["E"]["mode"], trays["E"]["business_bag_id"]) != (5, "empty", "")
                or trays["E"]["available_at"] > now
                or (trays["P"]["node"], trays["P"]["mode"], trays["P"]["business_bag_id"]) != (1, "loading", "blocker")
                or not trays["P"].get("service_ready_known")
                or trays["P"].get("ready_kind") != "observed_load_completion"
                or not now < trays["P"]["service_ready_at"] == trays["P"]["load_complete_at"] == case["blocker_load"]):
            return _unknown_input(["unsupported_initial_lifecycle"])
        if any(jobs[j]["status"] != "waiting_for_tray" for j in ("receiver", "reuse1", "reuse2")) or jobs["blocker"]["status"] != "loading":
            return _unknown_input(["unsupported_initial_job_status"])
        for node, resource in resources.items():
            if (resource["occupancy"] != sum(t["node"] == node for t in trays.values())
                    or resource["actual_available"] != sum(t["node"] == node and t["mode"] == "empty" and t["available_at"] <= now for t in trays.values())):
                return _unknown_input(["unrepresented_initial_occupancy_or_stock"])
        trays["P"]["load_end"] = trays["P"]["load_complete_at"]
        value = {"status": "conditional_model_input", "reasons": [], "model_version": VERSION,
            "contract": copy.deepcopy(contract), "jobs": jobs, "trays": trays, "resources": resources, "now": now,
            "case_from_delivered_contracts": case, "online_information_delivered": False,
            "assumptions": ["three-tray/five-job fixed public fixture; no future arrivals or undisclosed actions",
                "initial L load completion projected within source service window; P still loading",
                "conditional approximate resource model, no native prediction-error bound"]}
        value["capture_pair_sha256"] = hashlib.sha256(_canonical(sources).encode()).hexdigest()
        return value
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return _unknown_input(["malformed_initial_three_tray_data"])


def initial_predict(bundle, action):
    if bundle.get("status") != "conditional_model_input": return {"status": "unknown_input", "completion": {}}
    case = infer_case(bundle["jobs"])
    if case is None or action not in domain.domain(case)["actions"]: return {"status": "unknown_action_or_case", "completion": {}}
    return domain.Projection(bundle, action).run()


def propose_initial(bundle, method, fixed_window=None, budget=32):
    if bundle.get("status") != "conditional_model_input": return {"status": "unknown_input", "selected_action": None}
    if method not in domain.METHODS or type(budget) is not int or budget < 1: raise ValueError("unsupported_initial_search")
    case = infer_case(bundle["jobs"]); declared = domain.domain(case)
    actions = declared["actions"]; incumbent = declared["incumbent"]
    if fixed_window is not None:
        times = declared["public_derivation"]["supply_windows"]
        if type(fixed_window) is not int or not 0 <= fixed_window < len(times): raise ValueError("unsupported_fixed_window")
        actions = [a for a in actions if a["initial_next"] == 1 and a["departure"] == times[fixed_window]]
        incumbent = {**incumbent, "departure": times[fixed_window]}
    values = {domain.prior.key(a): a for a in actions}; base = domain.prior.key(incumbent); cache = {}; hit = False
    def evaluate(candidate):
        nonlocal hit
        if candidate in cache: return cache[candidate]
        if len(cache) >= budget: hit = True; return None
        prediction = initial_predict(bundle, values[candidate]); reference = cache[base]["prediction"] if base in cache else prediction
        cache[candidate] = {"action": values[candidate], "prediction": prediction, "model_protected": domain.protected(prediction, reference)}
        return cache[candidate]
    evaluate(base); score = lambda candidate: (sum(cache[candidate]["prediction"]["completion"].values()), candidate)
    if cache[base]["model_protected"] is True:
        if method == "finite_horizon_enumeration":
            for candidate in sorted(values):
                if evaluate(candidate) is None: break
        else:
            frontier, expanded = [base], set()
            while frontier and not hit:
                current = min(frontier, key=score); frontier.remove(current)
                if current in expanded: continue
                expanded.add(current); eligible = []
                for candidate in sorted(values):
                    distance = sum(a != b for a, b in zip(candidate, current))
                    if not 1 <= distance <= (2 if method == "resource_pair_repair" else 1): continue
                    row = evaluate(candidate)
                    if row is None: break
                    if row["model_protected"] is not True: continue
                    improves = score(candidate)[0] < score(current)[0] if method == "coordinate_strict" else score(candidate)[0] <= score(current)[0]
                    if improves and candidate not in expanded: eligible.append(candidate)
                if method == "coordinate_strict": frontier = [min(eligible, key=score)] if eligible else []
                else: frontier.extend(x for x in eligible if x not in frontier)
    eligible = [k for k, value in cache.items() if value["model_protected"] is True]; best = min(eligible, key=score) if eligible else None
    return {"status": "conditional_initial_model_proposal" if best else "unknown_initial_projection", "method": method,
        "selected_action": values[best] if best else None, "selected_prediction": cache[best]["prediction"] if best else None,
        "evaluations": len(cache), "budget": budget, "candidate_denominator": len(values), "fixed_window": fixed_window,
        "model_gain": score(base)[0] - score(best)[0] if best else None,
        "rows": [{**cache[k], "evaluation_status": "evaluated"} if k in cache else {"action": values[k], "evaluation_status": "unknown_unexecuted"} for k in sorted(values)],
        "online_information_delivered": False, "native_protection_certified": False, "future_components_nonbinding": True}


def assemble_later(contract, jobs, trays, resources, *, now, phase, source_records,
                   terminal_receipts, owner_pending_tray_requests):
    """Pure validation of declared public facts; native authentication is separate.

Terminal completion receipts are a required source-authorized extension to the
current planning capture, which omits completed obligations. No absence-based
completion inference or hidden native outcome lookup is allowed.
"""
    try:
        expected = supported_contract()
        # Normalize JSON tuple/list representation, but do not normalize edge
        # order, outgoing priority, unknown semantic fields or protocol values.
        reasons = ["unsupported_fixed_contract:" + key for key in expected
                   if _canonical(contract.get(key)) != _canonical(expected[key])]
        if set(contract) != set(expected): reasons.append("unsupported_contract_fields")
        if reasons: return _unknown_input(reasons)
        _canonical((jobs, trays, resources, now, source_records, terminal_receipts))
        return _assemble_supported(contract, jobs, trays, resources, now=now, phase=phase,
            source_records=source_records, terminal_receipts=terminal_receipts,
            owner_pending_tray_requests=owner_pending_tray_requests)
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return _unknown_input(["malformed_or_nonfinite_supported_input"])


def _assemble_supported(contract, jobs, trays, resources, *, now, phase, source_records,
                        terminal_receipts, owner_pending_tray_requests):
    reasons = []
    c, jobs, trays, resources = copy.deepcopy((contract, jobs, trays, resources))
    if phase not in ("first_return", "first_reuse_route") or isinstance(now, bool) or not math.isfinite(now) or not initial.START < now < 39.:
        reasons.append("unsupported_later_epoch_or_phase")
    if set(jobs) != JOBS or set(trays) != {"L", "E", "P"}:
        reasons.append("missing_full_obligation_or_tray_coverage")
        return _unknown_input(reasons)
    for key, origin, destination, arrival, load in (("loaded", 0, 6, 0., .1),
            ("receiver", 1, 4, .05, jobs["receiver"]["load_seconds"]), ("reuse1", 7, 6, .02, .1), ("reuse2", 7, 6, .03, .1), ("blocker", 1, 9, 0., jobs["blocker"]["load_seconds"])):
        expected_job = {"business_bag_id": key, "origin": origin, "destination": destination,
            "arrival": arrival, "deadline": 40., "storage_node": 4 if key == "loaded" else -1,
            "storage_min_dwell": 0., "load_seconds": load, "unload_seconds": .1,
            "hold_seconds": .1, "allow_suffix_reroute": True}
        if any(jobs[key].get(field) != value for field, value in expected_job.items()):
            reasons.append("unsupported_obligation_contract:" + key)
        if jobs[key].get("storage_release_at") not in (0.,):
            reasons.append("unsupported_obligation_storage_gate:" + key)
    if set(resources) != {n[0] for n in c["node_records"]}:
        reasons.append("missing_resource_coverage")
    if owner_pending_tray_requests != []:
        reasons.append("unresolved_owned_tray_request")
    if len(source_records) != 2 or {r["owner"] for r in source_records} != {"A", "B"}:
        reasons.append("missing_source_capture")
    for r in source_records:
        if not (r.get("identity") and 0 <= r["captured_at"] <= r["delivered_at"] <= now < r["valid_until"] and now - r["captured_at"] <= .05):
            reasons.append("invalid_or_stale_declared_source_capture")
        if r.get("known_faults") or r.get("unrepresented_occupancy", 0):
            reasons.append("unsupported_fault_or_reservation_uncertainty")
        if r.get("semantics") != SUPPORTED_NATIVE_SEMANTICS:
            reasons.append("missing_or_unsupported_source_semantics")
        if r.get("unresolved_tray_request_ids") != []:
            reasons.append("missing_or_unresolved_source_tray_requests")
    completed = {}
    owners = {n["node"]: n["resource_owner"] for n in c["node_contracts"]}
    declared_trays, declared_nodes, declared_jobs = set(), set(), set()
    for record in source_records:
        source = record["owner"]
        expected_trays = {key for key, tray in trays.items() if owners.get(tray["node"]) == source}
        expected_nodes = {node for node, owner in owners.items() if owner == source}
        expected_jobs = {tray["business_bag_id"] for key, tray in trays.items() if key in expected_trays and tray["business_bag_id"]}
        expected_jobs.update(key for key, job in jobs.items() if job["status"] == "waiting_for_tray" and owners.get(job["origin"]) == source)
        if (set(record.get("tray_ids", [])) != expected_trays or set(record.get("node_ids", [])) != expected_nodes
                or set(record.get("job_ids", [])) != expected_jobs):
            reasons.append("declared_source_authority_or_coverage_mismatch")
        if any(len(record.get(field, [])) != len(set(record.get(field, []))) for field in ("tray_ids", "node_ids", "job_ids")):
            reasons.append("duplicate_declared_coverage_identity")
        if declared_trays & expected_trays or declared_nodes & expected_nodes or declared_jobs & expected_jobs:
            reasons.append("duplicate_declared_source_identity")
        declared_trays.update(expected_trays); declared_nodes.update(expected_nodes); declared_jobs.update(expected_jobs)
        for key in expected_trays:
            tray = trays[key]
            # A small age bound alone does not imply unchanged lifecycle. No
            # autonomous load/service/hold completion may cross this interval.
            capture = record["captured_at"]
            if tray["mode"] == "empty":
                stable = (tray.get("ready_kind") == "empty_available_at" and tray.get("service_ready_known")
                    and tray["available_at"] == tray["service_ready_at"] <= capture and not tray["business_bag_id"])
            elif tray["mode"] == "loading":
                stable = (tray.get("ready_kind") == "observed_load_completion" and tray.get("service_ready_known")
                    and capture <= now < tray["service_ready_at"] == tray.get("load_complete_at"))
            elif tray["mode"] == "loaded":
                stable = (tray.get("ready_kind") == "committed_local_service_end" and tray.get("service_ready_known")
                    and 0 <= jobs[tray["business_bag_id"]].get("loaded_at", -1) <= capture <= now < tray["service_ready_at"])
            elif tray["mode"] == "hold":
                stable = (tray.get("ready_kind") == "observed_hold_completion" and tray.get("service_ready_known")
                    and capture <= now < tray["available_at"] == tray["service_ready_at"])
            else: stable = False
            if not stable: reasons.append("autonomous_transition_or_unknown_capture_state:" + key)
        for key in expected_jobs:
            if any(jobs[key].get(field, -1) > record["captured_at"]
                   for field in ("arrival", "loaded_at", "storage_entered_at", "storage_released_at")):
                reasons.append("future_observed_job_epoch:" + key)
    for r in terminal_receipts:
        job = jobs.get(r["business_bag_id"])
        if not job or r["business_bag_id"] in completed or r.get("status") != "completed" or job.get("status") != "completed":
            reasons.append("invalid_or_duplicate_terminal_receipt"); continue
        if not (r["source_owner"] == owners[job["destination"]] and 0 <= r["completed_at"] <= r["captured_at"] <= r["delivered_at"] <= now and r.get("identity")):
            reasons.append("invalid_terminal_receipt_authority_or_time"); continue
        completed[r["business_bag_id"]] = r["completed_at"]
    if "blocker" not in completed or (trays["P"].get("node"), trays["P"].get("mode"), trays["P"].get("business_bag_id")) != (9, "empty", ""):
        reasons.append("missing_completed_parked_blocker_receipt")
    if infer_case(jobs) is None:
        reasons.append("unsupported_full_five_job_contract")
    if "loaded" not in completed:
        reasons.append("missing_finished_prefix_receipt")
    if declared_jobs | set(completed) != JOBS:
        reasons.append("unrepresented_obligation_state")
    if jobs.get("reuse2", {}).get("status") != "waiting_for_tray":
        reasons.append("unsupported_later_reuse2_state")
    l, e = trays.get("L", {}), trays.get("E", {})
    if any(t.get("edge_to", 0) >= 0 or t.get("reception_node", 0) >= 0 for t in trays.values()):
        reasons.append("unknown_inflight_or_receiving_clearance")
    if phase == "first_return":
        if (l.get("node"), l.get("mode"), l.get("business_bag_id")) != (6, "empty", "") or l.get("available_at", math.inf) > now:
            reasons.append("unsupported_first_return_tray_state")
        if jobs.get("reuse1", {}).get("status") != "waiting_for_tray": reasons.append("unsupported_reuse1_state")
    elif phase == "first_reuse_route":
        if (l.get("node"), l.get("mode"), l.get("business_bag_id")) != (7, "loaded", "reuse1"):
            reasons.append("unsupported_first_reuse_tray_state")
        if not l.get("service_ready_known") or l.get("service_ready_at", -1) < now + c["protocol"]["message_delay"]:
            reasons.append("route_window_commits_before_message_or_unknown")
    if (e.get("node"), e.get("mode"), e.get("business_bag_id")) == (1, "loading", "receiver"):
        if not e.get("service_ready_known") or e.get("service_ready_at", -1) <= now:
            reasons.append("unknown_receiver_load_completion")
        if "receiver" in completed: reasons.append("terminal_receipt_conflicts_with_loading")
    elif e.get("node") == 4 and e.get("mode") in ("hold", "empty"):
        if "receiver" not in completed: reasons.append("missing_receiver_finished_receipt")
        if e["mode"] == "hold" and e.get("available_at", -1) <= now:
            reasons.append("aged_hold_transition_not_supported")
    else: reasons.append("unsupported_receiver_state")
    for node in c["node_contracts"]:
        if node["allow_export"] != (node["node"] not in (4, 9)) or not node["allow_receive"] or node["export_min_stock"] != 0:
            reasons.append("unsupported_port_or_min_stock_contract")
    for node, row in resources.items():
        if row["occupancy"] != sum(t["node"] == node for t in trays.values()):
            reasons.append("unexplained_occupancy")
        if row["actual_available"] != sum(t["node"] == node and t["mode"] == "empty" and t["available_at"] <= now for t in trays.values()):
            reasons.append("unexplained_available_stock")
    # With all trays stationary and no receiving leases, no in-flight future
    # service reservation exists. The only possibly reused shared edge3→4 was
    # last used by the completed original L job; even its minimum remaining
    # path to completion must exceed that edge's headway. A larger headway
    # invalidates the inference instead of being silently reset.
    travel = {(u, v): max(.001, length / speed) for u, v, length, speed in c["edge_records"]}
    service = {n[0]: max(.001, n[2]) for n in c["node_records"]}
    try:
        clearance_lower_bound = travel[3, 4] + service[4] + travel[4, 6] + service[6] + jobs["loaded"]["unload_seconds"]
        if any(edge["entry_headway"] > clearance_lower_bound for edge in c["edge_contracts"] if (edge["from"], edge["to"]) == (3, 4)):
            reasons.append("unbounded_prior_shared_edge_headway")
        if phase == "first_reuse_route" and any(edge["entry_headway"] > travel[6, 7] for edge in c["edge_contracts"] if (edge["from"], edge["to"]) == (6, 7)):
            reasons.append("unbounded_prior_return_edge_headway")
    except KeyError:
        reasons.append("unsupported_topology")
    for job in completed: jobs[job]["status"] = "completed"
    value = {"model_version": VERSION, "contract": c, "jobs": jobs, "trays": trays, "resources": resources, "now": now,
        "phase": phase, "completed_prefix": completed, "source_records": copy.deepcopy(source_records),
        "terminal_receipts": copy.deepcopy(terminal_receipts), "online_information_delivered": False,
        "status": "unknown" if reasons else "conditional_model_input", "reasons": sorted(set(reasons)),
        "assumptions": ["complete declared three-tray/five-obligation population, no unknown future jobs or faults",
            "stationary supported lifecycle phases and current source-authored terminal facts",
            "no unresolved source-owned tray action; known service epochs bound autonomous transitions",
            "remaining-resource projection approximates native R3/E4; no certified model error bound"]}
    value["capture_pair_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return value


class LaterProjection(initial.DiscreteProjection):
    def __init__(self, bundle, action):
        super().__init__(bundle, {"initial_next": 1, "departure": bundle["now"], "later_mode": "native_keep"})
        self.action = copy.deepcopy(action)
        self.completed = copy.deepcopy(bundle["completed_prefix"])
        self.returns = 0 if bundle["phase"] == "first_return" else 1
        self.next_return_number = self.returns + 1
        self.planned_return = False

    def tick(self):
        for request in self.requests[:]:
            if not request["terminal"] and self.time >= request["next_retry"]:
                request["next_retry"] = self.time + .5
                self.schedule(self.time + .01, "request_delivery", request)
        tray = self.trays["L"]
        if tray["mode"] == "empty" and tray["node"] == 6 and self.returns < 2 and not self.return_pending:
            self.returns += 1
            delay = self.action["return_delay"] if self.returns == self.next_return_number else 0.
            self.request("L", 7, self.time + delay)
        if tray["node"] == 7 and tray["mode"] == "loaded" and tray["edge_to"] < 0 and tray["job"] not in self.choice_jobs:
            self.choice_jobs.add(tray["job"])
            chosen = self.action["reuse_next"] if tray["job"] == "reuse1" else 3
            self.choices.append({"at": self.time, "job": tray["job"], "next": chosen, "source": "finite_model_action"})
            self.schedule(self.time + .01, "route", "L", chosen)

    def seed(self):
        l, e = self.trays["L"], self.trays["E"]
        if self.b["phase"] == "first_reuse_route":
            self.begin_leg("L", 6, ready=l["service_ready_at"])
        if e["mode"] == "loading":
            e["load_end"] = e["service_ready_at"]
            self.schedule(e["load_end"], "load_end", "E")
        elif e["mode"] == "hold":
            self.schedule(e["available_at"], "hold", "E")
        # A fixed public activation grid anchored to this actual new request,
        # shared across all candidates/methods; no native future event peeking.
        for i in range(int((initial.HORIZON - self.time) / initial.PERIOD) + 1):
            self.schedule(self.time + i * initial.PERIOD, "tick")

    def run(self):
        self.seed(); count = 0
        while self.events:
            self.time, _, _, kind, args = heapq.heappop(self.events)
            if self.time > initial.HORIZON: break
            count += 1
            if count > 20000: return {"status": "unknown_event_budget", "completion": self.completed}
            if kind == "tick": self.tick()
            elif kind == "ready": self.try_depart(args[0])
            elif kind == "route": self.trays[args[0]]["forced"] = args[1]
            elif kind == "arrive":
                key, target = args; tray = self.trays[key]
                tray["node"], tray["edge_from"], tray["edge_to"] = target, -1, -1
                tray["ready"] = self.time + self.service[target]
                self.schedule(tray["ready"], "ready", key); self.wake_waiters()
            elif kind == "load_end":
                tray = self.trays[args[0]]; tray["mode"] = "loaded"
                self.begin_leg(args[0], self.jobs[tray["job"]]["destination"])
            elif kind == "unload":
                tray = self.trays[args[0]]; self.completed[tray["job"]] = self.time; tray["mode"] = "hold"
                self.schedule(self.time + self.jobs[tray["job"]]["hold_seconds"], "hold", args[0])
            elif kind == "hold":
                tray = self.trays[args[0]]; tray["mode"], tray["job"] = "empty", None
            elif kind == "request_delivery":
                request = args[0]
                if request["physical_status"] == "enqueued":
                    request["physical_status"] = "pending"
                    if request["earliest"] <= self.time: self.grant(request)
                    else: self.schedule(request["earliest"], "grant", request)
                self.schedule(self.time + .02, "ack", request, request["physical_status"])
            elif kind == "grant": self.grant(args[0])
            elif kind == "ack":
                request, status = args
                if not request["terminal"]:
                    request["ack"], request["ack_at"] = status, self.time
                    request["terminal"] = status in ("received", "rejected")
                    if request["tray"] == "L" and request["terminal"]: self.return_pending = False
            else: raise ValueError("rolling_model:undeclared_lifecycle_event:" + kind)
        complete = set(self.completed) == JOBS
        return {"status": "conditional_prediction" if complete else "unknown_unfinished_projection",
            "completion": self.completed, "completion_sum": sum(self.completed.values()) if complete else None,
            "physical_projection": self.receipts, "resource_waits": self.waits, "later_choices": self.choices,
            "projected_rejections": sum(r["physical_status"] == "rejected" for r in self.requests),
            "event_count": count, "native_feasibility_certified": False, "online_information_delivered": False}


def predict(bundle, action):
    if bundle["status"] != "conditional_model_input":
        return {"status": "unknown_missing_input", "completion": {}, "reasons": bundle["reasons"]}
    if set(action) != {"reuse_next", "return_delay"} or action["reuse_next"] not in (3, 8) or not math.isfinite(action["return_delay"]) or not 0 <= action["return_delay"] <= 6.:
        return {"status": "unknown_unsupported_action", "completion": {}}
    return LaterProjection(bundle, action).run()


def candidates(bundle):
    return [{"reuse_next": route, "return_delay": delay} for route in (3, 8) for delay in (0., .5)], {"reuse_next": 3, "return_delay": 0.}


def propose(bundle, *, method="resource_pair_repair", evaluation_budget=32):
    if method not in ("coordinate_strict", "coordinate_plateau", "resource_pair_repair", "finite_horizon_enumeration"):
        raise ValueError("rolling_model:undeclared_method")
    if bundle["status"] != "conditional_model_input": return {"status": "unknown_input", "selected_action": None, "reasons": bundle["reasons"]}
    if type(evaluation_budget) is not int or evaluation_budget < 1: raise ValueError("rolling_model:invalid_budget")
    actions, incumbent = candidates(bundle)
    domain = {(a["reuse_next"], a["return_delay"]): a for a in actions}; base = (3, 0.)
    cache = {}; budget_hit = False
    def evaluate(key):
        nonlocal budget_hit
        if key in cache: return cache[key]
        if len(cache) >= evaluation_budget: budget_hit = True; return None
        projection = predict(bundle, domain[key]); baseline = cache[base]["prediction"] if base in cache else projection
        known = projection["status"] == baseline["status"] == "conditional_prediction" and set(projection["completion"]) == set(baseline["completion"]) == JOBS
        protected = all(projection["completion"][j] <= baseline["completion"][j] for j in JOBS) if known else None
        cache[key] = {"action": domain[key], "prediction": projection, "model_protected": protected}; return cache[key]
    baseline = evaluate(base)
    if baseline["model_protected"] is not True: return {"status": "unknown_incumbent_projection", "selected_action": None, "rows": list(cache.values())}
    score = lambda k: (cache[k]["prediction"]["completion_sum"], k)
    neighbors = lambda k: [x for x in sorted(domain) if sum(a != b for a, b in zip(x, k)) == 1]
    if method in ("resource_pair_repair", "finite_horizon_enumeration"):
        for key in sorted(domain):
            if evaluate(key) is None: break
    else:
        frontier, expanded = [base], set()
        while frontier and not budget_hit:
            current = min(frontier, key=score); frontier.remove(current)
            if current in expanded: continue
            expanded.add(current); eligible = []
            for key in neighbors(current):
                row = evaluate(key)
                if row is None: break
                if row["model_protected"] is not True: continue
                better = score(key)[0] < score(current)[0] if method == "coordinate_strict" else score(key)[0] <= score(current)[0]
                if better and key not in expanded: eligible.append(key)
            if method == "coordinate_strict": frontier = [min(eligible, key=score)] if eligible else []
            else: frontier.extend(k for k in eligible if k not in frontier)
    best = min((k for k, v in cache.items() if v["model_protected"] is True), key=score)
    return {"schema": "g31.lt2.public_rolling_proposal.v1", "version": VERSION, "status": "conditional_model_proposal",
        "method": method, "evaluations": len(cache), "evaluation_budget": evaluation_budget,
        "candidate_denominator": len(domain), "selected_action": copy.deepcopy(domain[best]),
        "selected_prediction": cache[best]["prediction"], "model_gain": score(base)[0] - score(best)[0],
        "rows": [{**cache[k], "evaluation_status": "evaluated"} if k in cache else {"action": domain[k], "evaluation_status": "unknown_unexecuted", "model_protected": None} for k in sorted(domain)],
        "capture_pair_sha256": bundle["capture_pair_sha256"], "first_action_owner": "A" if bundle["phase"] == "first_return" else "B",
        "first_action": "transfer_L6to7" if bundle["phase"] == "first_return" else "route_L7",
        "future_action_is_nonbinding_prediction": True, "native_protection_certified": False,
        "online_information_delivered": False, "model_error_bound_certified": False,
        "stop_reason": "evaluation_budget_exhausted" if budget_hit else "declared_neighborhood_exhausted"}
