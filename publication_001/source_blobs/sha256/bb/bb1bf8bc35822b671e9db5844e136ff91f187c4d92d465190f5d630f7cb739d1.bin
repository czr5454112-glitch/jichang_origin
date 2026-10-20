"""Pure, conditional two-tray public model; never a native execution oracle.

This small B3-style joint enumeration predicts complete reuse obligations under
one declared continuation. It is deliberately restricted to the synthetic
stationary checkpoint. Captures do not establish a delivered online contract.
No native object, checkpoint, result table or gate label enters this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import heapq
import json
import math

VERSION = "public-reuse-discrete-v2-native-r3-e4"
START, HORIZON, PERIOD = .11, 40., .05


@dataclass(frozen=True)
class Capture:
    """Canonical immutable source-authorized snapshot, not proof of delivery."""
    payload_json: str

    @classmethod
    def from_view(cls, view: dict, *, identity: str, provenance: str,
                  delivered_at: float | None = None, expires_at: float = .21):
        fields = ("business_bag_id", "origin", "destination", "arrival", "deadline", "storage_node",
                  "storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds",
                  "hold_seconds", "status", "loaded_at", "storage_entered_at", "storage_released_at")
        owner = view["owner_id"]
        payload = {"owner": owner, "identity": identity, "captured_at": view["now"],
            "delivered_at": delivered_at, "expires_at": expires_at, "provenance": provenance,
            "jobs": [{k: j[k] for k in fields} for j in view["jobs"]],
            "trays": copy.deepcopy(view["trays"]),
            "resources": [{k: n[k] for k in ("node", "occupancy", "actual_available")}
                          for n in view["node_contracts"] if n["resource_owner"] == owner],
            "coverage": {"jobs": sorted(j["business_bag_id"] for j in view["jobs"]),
                         "trays": sorted(t["tray_id"] for t in view["trays"]),
                         "resources": sorted(n["node"] for n in view["node_contracts"] if n["resource_owner"] == owner)},
            "known_faults": copy.deepcopy(view["known_faults"])}
        return cls(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))

    def read(self):
        return json.loads(self.payload_json)


def public_contract(view: dict) -> dict:
    """Project only common topology/operation contracts, never remote sensors."""
    keys = ("node", "zone", "resource_owner", "capacity", "allow_export", "allow_receive", "export_min_stock")
    return {"node_records": copy.deepcopy(view["node_records"]), "edge_records": copy.deepcopy(view["edge_records"]),
        "node_contracts": [{k: n[k] for k in keys} for n in view["node_contracts"]],
        "edge_contracts": copy.deepcopy(view["edge_contracts"]), "protocol": {"message_delay": .01,
            "publication_delay": .01, "ack_delay": .02, "retry": .5, "rejection_cooldown": .5,
            "period": PERIOD, "horizon": HORIZON, "expiry": 39., "attempt_limit": 16,
            "receiver_load_public": 3., "native_dispatch_quantum": .001},
        "continuation": "v2.1_initial_native_keep", "scope": "SYNTHETIC_2TRAY_4OBLIGATION_ONLY",
        "resource_semantics": "R3_java_node_window_compatible", "event_semantics": "E4_batch_plus_destination_merge_request"}


def assemble(contract: dict, captures: tuple[Capture, ...], now: float) -> dict:
    """Fail closed for omissions, overlap, stale captures and unsupported states."""
    reasons, jobs, trays, resources = [], {}, {}, {}
    payloads = [c.read() for c in captures]
    if len(payloads) != 2 or {p["owner"] for p in payloads} != {"A", "B"}:
        reasons.append("missing_or_duplicate_counterpart")
    for p in payloads:
        if not (p["captured_at"] == now == START and now <= p["expires_at"]):
            reasons.append("unsupported_capture_age_or_checkpoint")
        if p["delivered_at"] is not None and not (p["captured_at"] <= p["delivered_at"] <= now):
            reasons.append("invalid_declared_delivery_order")
        if p["known_faults"]:
            reasons.append("fault_model_not_implemented")
        for name, key, target in [("jobs", "business_bag_id", jobs), ("trays", "tray_id", trays), ("resources", "node", resources)]:
            ids = [item[key] for item in p[name]]
            if sorted(ids) != p["coverage"][name] or len(ids) != len(set(ids)):
                reasons.append("invalid_coverage:" + name)
            for item in p[name]:
                if item[key] in target:
                    reasons.append("duplicate_identity:" + name)
                target[item[key]] = item
        for resource in p["resources"]:
            owner = next(n["resource_owner"] for n in contract["node_contracts"] if n["node"] == resource["node"])
            if owner != p["owner"]:
                reasons.append("resource_authority_mismatch")
        for job in p["jobs"]:
            zone = next(n["zone"] for n in contract["node_contracts"] if n["node"] == job["origin"])
            if zone != p["owner"]:
                reasons.append("job_source_authority_mismatch")
            observed_times = [job[k] for k in ("arrival", "loaded_at", "storage_entered_at", "storage_released_at")]
            if any(t > p["captured_at"] for t in observed_times):
                reasons.append("future_observed_job_epoch")
            if any(not math.isfinite(value) for value in job.values() if isinstance(value, (int, float))):
                reasons.append("nonfinite_job_field")
        for tray in p["trays"]:
            node = next((n for n in contract["node_contracts"] if n["node"] == tray["node"]), None)
            if node is None or node["resource_owner"] != p["owner"]:
                reasons.append("tray_source_authority_mismatch")
    if set(jobs) != {"loaded", "receiver", "reuse1", "reuse2"} or set(trays) != {"L", "E"}:
        reasons.append("unsupported_population_or_missing_obligation")
    if set(resources) != {n[0] for n in contract["node_records"]}:
        reasons.append("missing_resource_coverage")
    if any(t["edge_to"] >= 0 or t["reception_node"] >= 0 for t in trays.values()):
        reasons.append("unbounded_inflight_or_receiving_clearance")
    if "L" in trays and (trays["L"]["node"], trays["L"]["mode"], trays["L"]["business_bag_id"]) != (0, "loaded", "loaded"):
        reasons.append("unsupported_loaded_state")
    if "E" in trays and (trays["E"]["node"], trays["E"]["mode"]) != (5, "empty"):
        reasons.append("unsupported_empty_state")
    for n, resource in resources.items():
        if resource["occupancy"] != sum(t["node"] == n for t in trays.values()):
            reasons.append("unexplained_reserved_occupancy")
        available = sum(t["node"] == n and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= now
                        for t in trays.values())
        if resource["actual_available"] != available:
            reasons.append("unexplained_available_stock")
    if "E" in trays and trays["E"]["available_at"] > now:
        reasons.append("unsupported_initial_empty_readiness")
    for node in contract["node_contracts"]:
        # The predictor implements this declared fixture, not arbitrary module
        # policies. In particular a denial/min-stock constraint must not be
        # ignored merely because the public timing projection completes.
        if node["allow_export"] != (node["node"] != 4) or not node["allow_receive"]:
            reasons.append("unsupported_port_permission_contract")
        if node["export_min_stock"] != 0:
            reasons.append("unsupported_export_min_stock")
    if "loaded" in jobs and jobs["loaded"]["loaded_at"] < 0:
        reasons.append("missing_local_service_epoch")
    declared_delivery = all(p["provenance"] == "native_delivered_planning_contract" and
                 p["delivered_at"] is not None and p["delivered_at"] <= now for p in payloads)
    identity = hashlib.sha256(json.dumps({"contract": contract, "captures": payloads}, sort_keys=True).encode()).hexdigest()
    return {"status": "unknown" if reasons else "conditional_model_input", "reasons": sorted(set(reasons)),
        "jobs": jobs, "trays": trays, "resources": resources, "now": now, "contract": copy.deepcopy(contract),
        # Caller-controlled metadata is never a native delivery credential.
        # A future trusted adapter must validate envelope, self-copy, digest,
        # causal times and actual native capture identity before online use.
        "capture_pair_sha256": identity, "online_information_delivered": False,
        "declared_delivery_metadata_present": declared_delivery,
        "assumptions": ["source service starts at loaded_at at this restricted initial checkpoint",
            "no undisclosed incoming tray or service reservation beyond complete two-tray coverage",
            "model FIFO/merge event tie order approximates native; validation is separate"]}


class DiscreteProjection:
    """Explicit node berths, FIFO, edge occupancy/headway and receiving leases.

    This projects operations, not physical execution. Model errors never turn
    into feasibility proofs. Future controller messages are generated from
    projected source states with the declared delays, never from native rows.
    """
    def __init__(self, bundle: dict, action: dict):
        self.b = copy.deepcopy(bundle)
        self.a = copy.deepcopy(action)
        c = self.b["contract"]
        self.service = {n[0]: max(.001, n[2]) for n in c["node_records"]}
        self.travel = {(u, v): max(.001, length / speed) for u, v, length, speed in c["edge_records"]}
        self.nodes = {n["node"]: n for n in c["node_contracts"]}
        self.edges = {(e["from"], e["to"]): e for e in c["edge_contracts"]}
        self.outgoing = {n[0]: n[5] for n in c["node_records"]}
        self.jobs = self.b["jobs"]
        self.jstatus = {j: value["status"] for j, value in self.jobs.items()}
        self.trays = {key: {**copy.deepcopy(value), "job": value["business_bag_id"] or None,
                           "goal": None, "ready": math.inf, "lease": None, "forced": None}
                      for key, value in self.b["trays"].items()}
        self.events, self.sequence, self.time = [], 0, self.b["now"]
        self.completed, self.receipts, self.waits, self.choices = {}, [], [], []
        self.next_entry = {e: -math.inf for e in self.edges}
        self.calendars = {n: [] for n in self.nodes}
        self.waiting, self.fifo = {}, 0
        self.requests, self.last_supply, self.returns = [], None, 0
        self.forecasts, self.forecast_keys, self.choice_jobs = [], set(), set()
        self.return_pending = False
        self.last_arbitration = {}
        self.minimum = .001

    def schedule(self, when, kind, *args):
        self.sequence += 1
        # Native E4: exits/service completion precede circulation lifecycle;
        # circulation grants precede junction dispatch; external owner ticks
        # happen after advance_to has drained that exact physical timestamp.
        rank = 99 if kind == "tick" else 5 if kind == "ready" else 1 if kind == "arrive" else 2
        heapq.heappush(self.events, (when, rank, self.sequence, kind, args))

    def record(self, event, tray, **extra):
        self.receipts.append({"at": self.time, "event": event, "tray": tray, **extra})

    def occupancy(self, node, exclude=None):
        return sum((t["node"] == node if t["edge_to"] < 0 else t["edge_to"] == node) or t["lease"] == node
                   for key, t in self.trays.items() if key != exclude)

    def blocked(self, key, to):
        t, now = self.trays[key], self.time
        edge = (t["node"], to)
        if self.edges[edge]["capacity"] == 0: return "edge_closed"
        if self.next_entry[edge] > now + 1e-9: return "headway"
        if sum((x["edge_from"], x["edge_to"]) == edge for x in self.trays.values()) >= self.edges[edge]["capacity"]: return "edge_capacity"
        if self.occupancy(to, key) >= self.nodes[to]["capacity"]: return "receiving_full"
        start, end = now + self.travel[edge], now + self.travel[edge] + self.service[to]
        # Native R3 excludes goal service from the shared destination calendar.
        # Physical receiving berth capacity still applies at a goal.
        if to != t["goal"] and any(start < b - 1e-9 and end > a + 1e-9 for a, b in self.calendars[to]): return "service_calendar"
        return None

    def begin_leg(self, key, goal, *, ready=None):
        t = self.trays[key]
        t["goal"] = goal
        t["ready"] = self.time + self.service[t["node"]] if ready is None else ready
        self.calendars[t["node"]].append((self.time, t["ready"]))
        self.schedule(t["ready"], "ready", key)

    def choose_next(self, key):
        t = self.trays[key]
        if t["forced"] is not None:
            return t["forced"]
        if t["node"] == 0: return self.a["initial_next"]
        if t["node"] == 7:
            # Native keep is modelled with local immediate-resource avoidance;
            # native scorer/calendar differences remain a validation residual.
            return 8 if self.blocked(key, 3) else 3
        return self.outgoing[t["node"]][0]

    def try_depart(self, key):
        t = self.trays[key]
        if t["edge_to"] >= 0 or t["goal"] is None or t["ready"] > self.time + 1e-9: return
        if t["node"] == t["goal"]:
            self.waiting.pop(key, None)
            self.complete_leg(key)
            return
        to = self.choose_next(key)
        reason = self.blocked(key, to)
        self.last_arbitration[t["node"]] = self.time
        if reason:
            if key not in self.waiting:
                self.fifo += 1
                self.waiting[key] = self.fifo
                self.waits.append({"at": self.time, "tray": key, "node": t["node"], "to": to, "reason": reason})
            if reason == "headway": self.schedule(self.next_entry[t["node"], to], "ready", key)
            if reason == "service_calendar":
                times = [b - self.travel[t["node"], to] for a, b in self.calendars[to] if b - self.travel[t["node"], to] > self.time + 1e-9]
                if times: self.schedule(min(times), "ready", key)
            return
        self.waiting.pop(key, None)
        source, edge = t["node"], (t["node"], to)
        self.next_entry[edge] = self.time + self.edges[edge]["entry_headway"]
        t["edge_from"], t["edge_to"], t["forced"] = source, to, None
        arrival = self.time + self.travel[edge]
        if to != t["goal"]:
            self.calendars[to].append((arrival, arrival + self.service[to]))
        self.record("EDGE_ENTER", key, job=t["job"], source=source, target=to)
        self.schedule(arrival, "arrive", key, to)
        self.wake_waiters()

    def wake_waiters(self):
        for key in sorted(self.waiting, key=self.waiting.get):
            t = self.trays[key]
            delay = self.minimum if self.last_arbitration.get(t["node"]) == self.time else 0.
            self.schedule(self.time + delay, "ready", key)

    def load_waiting(self, key):
        t = self.trays[key]
        waiting = sorted((j for j, s in self.jstatus.items() if s == "waiting_for_tray" and self.jobs[j]["origin"] == t["node"]),
                         key=lambda j: (self.jobs[j]["arrival"], j))
        if not waiting: return
        job = waiting[0]
        t["job"], t["mode"] = job, "loading"
        self.jstatus[job] = "loading"
        t["load_end"] = self.time + self.jobs[job]["load_seconds"]
        self.record("LOAD_START", key, job=job)
        self.schedule(t["load_end"], "load_end", key)

    def complete_leg(self, key):
        t = self.trays[key]
        t["goal"] = None
        if t["mode"] == "empty_transit":
            t["mode"], t["lease"] = "empty", None
            t["request"]["physical_status"] = "received"
            self.record("EMPTY_RECEIVED", key, node=t["node"])
            self.load_waiting(key)
        elif t["job"] == "loaded" and t["node"] == self.jobs["loaded"]["storage_node"]:
            t["mode"] = "storage"
            self.record("STORAGE_ENTER", key)
            self.schedule(max(self.time + self.jobs["loaded"]["storage_min_dwell"], self.jobs["loaded"]["storage_release_at"]), "storage_release", key)
        else:
            t["mode"] = "unloading"
            self.schedule(self.time + self.jobs[t["job"]]["unload_seconds"], "unload", key)

    def request(self, key, destination, earliest):
        r = {"tray": key, "destination": destination, "earliest": earliest, "physical_status": "enqueued",
            "terminal": False, "ack": None, "next_retry": self.time + .5}
        self.requests.append(r)
        self.schedule(self.time + .01, "request_delivery", r)
        if key == "E": self.last_supply = r
        else: self.return_pending = True

    def grant(self, r):
        if r["physical_status"] != "pending": return
        t, key = self.trays[r["tray"]], r["tray"]
        if self.occupancy(r["destination"], key) >= self.nodes[r["destination"]]["capacity"]:
            r["physical_status"] = "rejected"
            self.record("TRANSFER_REJECTED", key, reason="receiving_full")
            return
        t["lease"], t["mode"], t["request"] = r["destination"], "empty_transit", r
        r["physical_status"] = "dispatching"
        self.begin_leg(key, r["destination"])

    def tick(self):
        for r in self.requests[:]:
            if not r["terminal"] and self.time >= r["next_retry"]:
                r["next_retry"] = self.time + .5
                self.schedule(self.time + .01, "request_delivery", r)
        e, l = self.trays["E"], self.trays["L"]
        if e["node"] == 1 and e["edge_to"] < 0 and e["mode"] in ("loading", "loaded"):
            key = (e["mode"], e["job"])
            if key not in self.forecast_keys:
                self.forecast_keys.add(key)
                self.schedule(self.time + .01, "forecast_capture", key)
        for f in self.forecasts:
            if not f.get("withdrawal") and not(e["node"] == 1 and e["edge_to"] < 0 and e["mode"] == f["mode"]):
                f["withdrawal"] = self.time + .02
        if l["mode"] == "empty" and l["node"] == 6 and self.returns < 2 and not self.return_pending:
            self.returns += 1
            self.request("L", 7, self.time)
        r = self.last_supply
        if r and r["terminal"] and r["ack"] == "rejected" and self.time >= r["ack_at"] + .5 and len([x for x in self.requests if x["tray"] == "E"]) < 16:
            if e["mode"] == "empty" and e["node"] == 5: self.request("E", 1, self.time)
        if l["node"] == 7 and l["mode"] == "loaded" and l["edge_to"] < 0 and l["job"] not in self.choice_jobs:
            self.choice_jobs.add(l["job"])
            mode, next_node = self.a["later_mode"], 3
            if mode == "native_keep": next_node = None
            else:
                active = [f for f in self.forecasts if f["delivered"] <= self.time and (not f.get("withdrawal") or f["withdrawal"] > self.time)]
                f = max(active, key=lambda x: x["captured"], default=None)
                eta = self.time + self.service[7] + self.travel[7, 3]
                if mode == "adaptive" and f and f["release"] >= eta and f["entry"] <= eta + 3.: next_node = 8
                if next_node == 3 and self.occupancy(3) >= self.nodes[3]["capacity"]: next_node = 8
            self.choices.append({"at": self.time, "job": l["job"], "next": next_node})
            if next_node is not None: self.schedule(self.time + .01, "route", "L", next_node)

    def run(self):
        l = self.trays["L"]
        self.begin_leg("L", self.jobs["loaded"]["storage_node"], ready=self.jobs["loaded"]["loaded_at"] + self.service[0])
        self.request("E", 1, self.a["departure"])
        for i in range(int((HORIZON - START) / PERIOD) + 1): self.schedule(START + i * PERIOD, "tick")
        count = 0
        while self.events:
            self.time, _, _, kind, args = heapq.heappop(self.events)
            if self.time > HORIZON: break
            count += 1
            if count > 20000: return {"status": "unknown_event_budget", "completion": self.completed}
            if kind == "tick": self.tick()
            elif kind == "ready": self.try_depart(args[0])
            elif kind == "route": self.trays[args[0]]["forced"] = args[1]
            elif kind == "arrive":
                key, to = args
                t = self.trays[key]
                t["node"], t["edge_from"], t["edge_to"] = to, -1, -1
                t["ready"] = self.time + self.service[to]
                self.schedule(t["ready"], "ready", key)
                self.wake_waiters()
            elif kind == "load_end":
                t = self.trays[args[0]]
                t["mode"] = "loaded"
                self.begin_leg(args[0], self.jobs[t["job"]]["destination"])
            elif kind == "storage_release":
                self.trays[args[0]]["mode"] = "loaded"
                self.begin_leg(args[0], self.jobs["loaded"]["destination"])
            elif kind == "unload":
                t = self.trays[args[0]]
                self.completed[t["job"]] = self.time
                t["mode"] = "hold"
                self.schedule(self.time + self.jobs[t["job"]]["hold_seconds"], "hold", args[0])
            elif kind == "hold":
                t = self.trays[args[0]]
                t["mode"], t["job"] = "empty", None
            elif kind == "request_delivery":
                r = args[0]
                if r["physical_status"] == "enqueued":
                    r["physical_status"] = "pending"
                    if r["earliest"] <= self.time: self.grant(r)
                    else: self.schedule(r["earliest"], "grant", r)
                self.schedule(self.time + .02, "ack", r, r["physical_status"])
            elif kind == "grant": self.grant(args[0])
            elif kind == "ack":
                r, status = args
                if not r["terminal"]:
                    r["ack"], r["ack_at"] = status, self.time
                    r["terminal"] = status in ("received", "rejected")
                    if r["tray"] == "L" and r["terminal"]: self.return_pending = False
            elif kind == "forecast_capture":
                e = self.trays["E"]
                if e["node"] == 1 and e["edge_to"] < 0 and e["mode"] in ("loading", "loaded"):
                    entry = e["load_end"] + self.service[1] if e["mode"] == "loading" else max(self.time, e["ready"])
                    self.forecasts.append({"mode": e["mode"], "captured": self.time, "delivered": self.time + .01,
                        "entry": entry, "release": entry + self.travel[1, 3] + self.service[3]})
        status = "conditional_prediction" if set(self.completed) == set(self.jobs) else "unknown_unfinished_projection"
        return {"status": status, "completion": self.completed, "completion_sum": sum(self.completed.values()) if status == "conditional_prediction" else None,
            "resource_waits": self.waits, "later_choices": self.choices, "physical_projection": self.receipts,
            "projected_rejections": sum(r["physical_status"] == "rejected" for r in self.requests),
            "event_count": count, "assumptions": self.b["assumptions"], "native_feasibility_certified": False,
            "online_information_delivered": self.b["online_information_delivered"]}


def predict(bundle: dict, action: dict) -> dict:
    if bundle["status"] == "unknown":
        return {"status": "unknown_missing_input", "reasons": bundle["reasons"], "completion": {}, "native_feasibility_certified": False}
    if action["initial_next"] not in (1, 2) or action["later_mode"] not in ("adaptive", "occupancy_only", "native_keep") or not START <= action["departure"] < 39.:
        return {"status": "unknown_unsupported_action", "completion": {}, "native_feasibility_certified": False}
    return DiscreteProjection(bundle, action).run()


def propose(bundle: dict, candidates: list[dict], incumbent: dict) -> dict:
    """Conditional finite B3-style first action, all obligations strictly checked.

    Reinvocation after a fresh supported capture is the rolling interface. Only
    the initial stationary checkpoint is implemented; later captures return
    unknown. No prediction alone certifies physical individual protection.
    """
    base = predict(bundle, incumbent)
    rows = [{"action": copy.deepcopy(a), "prediction": predict(bundle, a)} for a in candidates]
    for row in rows:
        pred = row["prediction"]
        row["model_protected"] = (base["status"] == pred["status"] == "conditional_prediction"
            and all(pred["completion"][j] <= t for j, t in base["completion"].items()))
    eligible = [row for row in rows if row["model_protected"]]
    best = min(eligible, key=lambda row: (row["prediction"]["completion_sum"], row["action"]["initial_next"], row["action"]["departure"]), default=None)
    return {"schema": "g31.lt2.public_joint_proposal.v1", "model_version": VERSION,
        "status": "conditional_offline_model_proposal" if best else "unknown_no_model_protected_candidate",
        "capture_pair_sha256": bundle["capture_pair_sha256"], "selected_action": best["action"] if best else None,
        "incumbent_prediction": base, "candidates": rows, "online_executable": False,
        "native_protection_certified": False, "reason": "typed delivery and model-error bounds not established"}


def candidates_from_durations(bundle: dict) -> tuple[list[dict], dict]:
    """31 fixed-route times and four route2 times, no fitted outcome inputs."""
    c = bundle["contract"]
    s = {n[0]: n[2] for n in c["node_records"]}
    d = {(u, v): length / speed for u, v, length, speed in c["edge_records"]}
    old = [START, START + s[0] + d[0, 1] + s[1], START + 3., START + 6.]
    commit = max(START, bundle["jobs"]["loaded"]["loaded_at"] + s[0])
    arrival, lead = commit + d[0, 1], s[5] + d[5, 1]
    clear = arrival + s[1]
    headway = next(e["entry_headway"] for e in c["edge_contracts"] if (e["from"], e["to"]) == (3, 4))
    centers = [commit, arrival, clear, commit - lead, clear - lead, clear + headway - lead]
    times = set(old)
    for center in centers:
        times.update(t for t in (center - PERIOD / 50, center, center + PERIOD / 50) if old[0] <= t <= old[-1])
    while len(times) < 31:
        values = sorted(times)
        a, b = min(zip(values, values[1:]), key=lambda pair: (-(pair[1] - pair[0]), pair[0]))
        times.add(a + (b - a) / 2)
    if len(times) != 31: raise ValueError("public_model:unsupported_candidate_budget")
    actions = [{"initial_next": route, "departure": t, "later_mode": "adaptive"}
               for route, departures in [(1, sorted(times)), (2, old)] for t in departures]
    return actions, {"initial_next": 1, "departure": old[1], "later_mode": "adaptive"}
