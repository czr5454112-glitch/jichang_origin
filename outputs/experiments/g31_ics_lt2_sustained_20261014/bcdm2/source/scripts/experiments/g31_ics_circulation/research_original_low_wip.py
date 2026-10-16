"""Finite original-permission R2 feasibility experiment; no native run by prepare.

Keep all original jobs/trays/FIFO/physical contracts. Serialize opposite-zone
empty parking through real source ACKs and recipient-authored typed snapshots;
then admit exactly one currently observed reachable FIFO head with one tray.
This is a feasibility probe, not a protection or 100ms certificate.
"""
from __future__ import annotations
import argparse
import ast
from collections import defaultdict
from copy import deepcopy
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from .native_host import load_native, audit_result
from .protocol_control import ProtocolClient
from .planning_capture_v2_digest import capture_digest_v2

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
SCHEMA = "g31.original_low_wip_feasibility.v1"
INPUT_SHA = "d37118333de2aa60fb5e9b9d41bab53cccb7ddbab5842862b88a2818e08709a1"
BINARY_SHA = "c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"
ACCEPTANCE_SHA = "ec0bf85b9a4be4030ed13209c75656ee2b83910235f76bec652943ae98ba99df"
HORIZON = 22200.
WIRE = 2.
PERIOD = 10.
VALIDITY = 120.
MAX_TICKS = 2222
MAX_PHYSICAL = 23
REPLACE_RETRY_DELAYS = (.01, .02, .04, .08, .16, .25)
ENDPOINTS = frozenset(("observe_protocol_control_policy_recent", "protocol_planning_snapshots_v2",
    "submit_protocol_transfer", "submit_protocol_command", "protocol_request", "protocol_command", "advance_to"))


def require(value, reason):
    if not value: raise ValueError("original_low_wip:" + reason)


def owner_request_id(owner, suffix):
    """Match native owner.size() (UTF-8 bytes), including owners containing ':'."""
    require(type(owner) is str and bool(owner) and type(suffix) is str and bool(suffix), "request_identity_parts")
    return f"live:{len(owner.encode('utf-8'))}:{owner}:low-wip:{suffix}"


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def gzread(path):
    with gzip.open(path, "rt", encoding="utf-8") as f: return json.load(f)
def canonical(value): return json.loads(json.dumps(value, allow_nan=False))


def replace_with_retry(source, target):
    """Bound PermissionError retries; never omit a required atomic write."""
    for attempt in range(len(REPLACE_RETRY_DELAYS)+1):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == len(REPLACE_RETRY_DELAYS): raise
            time.sleep(REPLACE_RETRY_DELAYS[attempt])


def write(path, value):
    path = Path(path); tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"); replace_with_retry(tmp, path)
def gzwrite(path, value):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as f: json.dump(value, f, ensure_ascii=False, allow_nan=False)


def public_graph(contract):
    nodes = {r["node"]: r for r in contract["node_contracts"]}
    records = {r[0]: r for r in contract["node_records"]}
    capacity = {(r["from"], r["to"]): r["capacity"] for r in contract["edge_contracts"]}
    graph = defaultdict(list)
    for u, v, length, speed in contract["edge_records"]:
        require(math.isfinite(length) and math.isfinite(speed) and length > 0 and speed > 0, "invalid_edge")
        if capacity[u, v] > 0 and nodes[u]["capacity"] > 0 and nodes[v]["capacity"] > 0:
            graph[u].append((v, length/speed + max(.001, records[v][2])))
    return graph


def paths_from(graph, source):
    queue = [(0., source, ())]; result = {}
    while queue:
        distance, node, prefix = heapq.heappop(queue)
        if node in result: continue
        result[node] = (distance, [*prefix, node])
        for target, cost in sorted(graph[node]):
            if target not in result: heapq.heappush(queue, (distance+cost, target, (*prefix, node)))
    return result


def parking_plan(contract, declared_inventory):
    """Uses public node role1=loader and role7=Storage, never future job origins."""
    nodes = {r["node"]: r for r in contract["node_contracts"]}
    roles = {r[0]: r[1] for r in contract["node_records"]}
    owners = sorted({n["resource_owner"] for n in nodes.values()})
    require(len(owners) == 2, "requires_declared_two_owner_domain")
    require(len({t["tray_id"] for t in declared_inventory}) == len(declared_inventory), "duplicate_inventory")
    graph = public_graph(contract); paths = {n: paths_from(graph, n) for n in nodes}
    used = set(); rows = []
    for owner in owners:
        local = sorted((t for t in declared_inventory if nodes[t["node"]]["resource_owner"] == owner), key=lambda t: (t["node"], t["tray_id"]))
        for tray in local:
            source = tray["node"]; require(nodes[source]["allow_export"] and nodes[source]["export_min_stock"] == 0, "initial_export_contract")
            choices = []
            for target, node in nodes.items():
                if (target in used or roles[target] in (1, 7) or node["zone"] == nodes[source]["zone"]
                        or node["capacity"] < 3 or not node["allow_receive"] or target not in paths[source]): continue
                reverse = paths[target].get(source)
                choices.append((0 if reverse else 1, paths[source][target][0]+(reverse[0] if reverse else 0.), target))
            require(choices, "no_distinct_opposite_zone_nonloader_parking")
            target = min(choices)[2]; used.add(target)
            rows.append({"owner": owner, "tray_id": tray["tray_id"], "source": source, "destination": target,
                "request_id": owner_request_id(owner, f"park:{tray['tray_id']}"), "positive_path": paths[source][target][1],
                "free_flow_seconds": paths[source][target][0], "return_to_original_source_path": paths[target].get(source),
                "stationary_spare_berths": nodes[target]["capacity"]-1})
    require(rows, "empty_inventory")
    # The first tray of the last exporting owner ends in the first owner's
    # jurisdiction, so the eventual token owner can inspect it locally.
    token = next(r for r in rows if r["owner"] == owners[-1])
    return {"owners": owners, "parking": rows, "token_tray_id": token["tray_id"],
        "token_owner": nodes[token["destination"]]["resource_owner"], "token_parking_node": token["destination"],
        "serial_free_flow_seconds": sum(r["free_flow_seconds"] for r in rows),
        "role_authority": "public native node_records type1 loader/type7 Storage; no future-job origin filtering",
        "bound_scope": "free-flow screening only; actual native routing, FIFO, reservations, 2s wire and ACKs remain required"}


def validate_initial_local(view, plan, owner):
    require(view["owner_id"] == owner and view["now"] == 0., "initial_observation_scope")
    expected = {r["tray_id"]: r["source"] for r in plan["parking"] if r["owner"] == owner}
    trays = view["trays"]
    require(len(trays) == len(expected) and {t["tray_id"] for t in trays} == set(expected), "initial_local_inventory")
    require(all(t["node"] == expected[t["tray_id"]] and t["mode"] == "empty" and not t["business_bag_id"]
        and t["edge_to"] < 0 and t["reception_node"] < 0 and t["available_at"] <= 0 for t in trays), "initial_local_empty_required")


def coverage_matches_rows(identities, rows, field, *, node_ids=False):
    """Native renders coverage and body rows together, in their original order."""
    if type(identities) is not list or type(rows) is not list or any(type(r) is not dict for r in rows): return False
    values = [r.get(field) for r in rows]
    valid = (lambda v: type(v) is int and v >= 0) if node_ids else (lambda v: type(v) is str and bool(v))
    return all(valid(v) for v in [*identities, *values]) and identities == values and len(set(values)) == len(values)


def action_resolved(action):
    # Same operation-specific delivered-ACK contract as native v2 capture.
    status = (action["last_delivered_ack"] or {}).get("status")
    return status in {"rejected", "failed", "expired"} or status in {
        "transfer": {"received", "cancelled"}, "route": {"updated"}, "cancel_transfer": {"cancelled"}
    }.get(action["kind"], set())


def delivered_peer(envelopes, owner, peer, now, nodes):
    if not envelopes: return None
    require(len(envelopes) == 1, "unexpected_or_duplicate_peer_envelope")
    envelope = envelopes[0]; body = envelope["capture"]; local = body["local_capture"]
    require(envelope["schema"] == "g31.planning_snapshot.v2" and envelope["kind"] == "planning_snapshot_v2"
        and body["schema"] == "g31.planning_capture.v2" and envelope["digest_format"] == "g31.planning_capture_digest.v2", "message_schema")
    require(local["source_owner"] == peer and local["target_owner"] == owner, "message_owner")
    require(capture_digest_v2(body) == envelope["payload_sha256"], "message_digest")
    require(all(math.isfinite(t) for t in (local["captured_at"], envelope["delivered_at"], local["valid_until"])), "message_nonfinite_time")
    require(0 <= local["captured_at"] <= envelope["delivered_at"] <= now, "message_causality")
    if envelope["status"] != "conditional" or now >= local["valid_until"]: return None
    owned = {n for n, row in nodes.items() if row["resource_owner"] == peer}
    coverage = local["coverage"]
    require(coverage["complete_for_declared_local_scope"] and not coverage["future_arrivals_included"]
        and coverage_matches_rows(coverage["local_node_ids"], local["nodes"], "node", node_ids=True)
        and set(coverage["local_node_ids"]) == owned, "message_coverage")
    # A receiver may legitimately have a reserved berth before the remote tray
    # appears in its local capture. Wait for an actual complete parked snapshot.
    if coverage["unrepresented_occupancy"] != 0: return None
    require(coverage_matches_rows(coverage["tray_ids"], local["trays"], "tray_id")
        and coverage_matches_rows(coverage["business_bag_ids"], local["jobs"], "business_bag_id"), "message_membership")
    require(all(nodes[j["origin"]]["resource_owner"] == peer or any(t["business_bag_id"] == j["business_bag_id"] for t in local["trays"])
        for j in local["jobs"]), "message_job_authority")
    extension = body["extension"]; actions = extension["submitted_physical_actions"]; ac = extension["action_coverage"]
    completions = extension["terminal_receipts"]; cc = extension["completion_coverage"]
    require(cc["scope"] == "all_source_owned_destination_unload_completions_through_capture"
        and cc["complete_for_declared_scope"] and cc["through"] == local["captured_at"] and not cc["future_events_included"]
        and cc["source_owned_destination_nodes"] == coverage["local_node_ids"]
        and coverage_matches_rows(cc["completed_business_bag_ids"], completions, "business_bag_id")
        and coverage_matches_rows([r.get("receipt_id") for r in completions], completions, "receipt_id"), "completion_coverage")
    require(all(r["source_owner"] == peer and r["destination"] in owned for r in completions), "completion_owner")
    require(ac["scope"] == "all_source_submitted_physical_operations_last_delivered_ack" and ac["complete_for_declared_scope"]
        and ac["through"] == local["captured_at"] and not ac["uses_hidden_execution_truth"]
        and not ac["includes_unsubmitted_python_plans"]
        and coverage_matches_rows(ac["submitted_request_ids"], actions, "request_id")
        and coverage_matches_rows(ac["unresolved_request_ids"], [r for r in actions if not action_resolved(r)], "request_id"), "action_coverage")
    require(all(r["source_owner"] == peer for r in actions), "action_owner")
    return envelope


def parked_tray(local, row):
    matches = [t for t in local["trays"] if t["tray_id"] == row["tray_id"]]
    return len(matches) == 1 and matches[0]["node"] == row["destination"] and matches[0]["mode"] == "empty" and not matches[0]["business_bag_id"] and matches[0]["edge_to"] < 0 and matches[0]["reception_node"] < 0 and matches[0]["available_at"] <= local.get("captured_at", local.get("now"))


def peer_finished(envelope, peer_rows, own_view):
    if envelope is None: return False
    body = envelope["capture"]; actions = {r["request_id"]: r for r in body["extension"]["submitted_physical_actions"]}
    for row in peer_rows:
        action = actions.get(row["request_id"], {}); ack = action.get("last_delivered_ack") or {}
        if (action.get("kind") != "transfer" or ack.get("status") != "received"
                or not 0 <= ack.get("delivered_at", -1) <= body["local_capture"]["captured_at"] or not parked_tray(own_view, row)): return False
    return True


def eligible_head(envelope, own_view, token_id):
    """Only the earliest waiting job at each source; never skip an unreachable head."""
    if envelope is None: return None
    nodes = {r["node"]: r for r in own_view["node_contracts"]}; graph = public_graph(own_view)
    local = envelope["capture"]["local_capture"]
    tokens = [t for t in own_view["trays"] if t["tray_id"] == token_id and t["mode"] == "empty"
        and not t["business_bag_id"] and t["edge_to"] < 0 and t["reception_node"] < 0 and t["available_at"] <= own_view["now"]]
    if len(tokens) != 1: return None
    token = tokens[0]; destinations = paths_from(graph, token["node"])
    heads = {}
    for job in sorted(local["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"])):
        if job["status"] == "waiting_for_tray" and nodes[job["origin"]]["resource_owner"] == local["source_owner"]:
            require(0 <= job["arrival"] <= local["captured_at"], "future_head")
            heads.setdefault(job["origin"], job)
    for job in sorted(heads.values(), key=lambda j: (j["arrival"], j["business_bag_id"])):
        source, origin = token["node"], job["origin"]
        if (nodes[source]["zone"] == nodes[origin]["zone"] or not nodes[source]["allow_export"]
                or not nodes[origin]["allow_receive"] or origin not in destinations): continue
        stages = [origin] + ([job["storage_node"]] if job["storage_node"] >= 0 else []) + [job["destination"]]
        witnesses = [paths_from(graph, a).get(b) for a, b in zip(stages, stages[1:])]
        if all(witnesses): return {"job": deepcopy(job), "tray": deepcopy(token), "delivered_message": deepcopy(envelope),
            "positive_supply_path": destinations[origin][1], "positive_mandatory_paths": [w[1] for w in witnesses]}
    return None


class Tape:
    def __init__(self, session, directory):
        self.session, self.directory, self.rows = session, directory, []
        directory.mkdir(); (directory / "manifest.jsonl").write_text("", encoding="utf-8")
    @property
    def physical_time(self): return self.session.physical_time
    def __getattr__(self, name):
        require(name in ENDPOINTS, "unclassified_endpoint:" + name)
        def call(*args, **kwargs):
            row = {"ordinal": len(self.rows), "endpoint": name, "args": canonical(args), "kwargs": canonical(kwargs), "before": self.physical_time}
            try: result = getattr(self.session, name)(*args, **kwargs); row["result"] = canonical(result); return result
            except BaseException as error: row["error"] = repr(error); raise
            finally:
                row["after"] = self.physical_time; path = self.directory / f"{len(self.rows):06d}.json.gz"; gzwrite(path, row)
                item = {"path": path.name, "sha256": sha(path), "endpoint": name}; self.rows.append(item)
                with (self.directory / "manifest.jsonl").open("a", encoding="utf-8") as f: f.write(json.dumps(item) + "\n")
        return call


class Owner:
    def __init__(self, session, owner, plan):
        self.session, self.owner, self.plan = session, owner, plan
        self.peer = next(o for o in plan["owners"] if o != owner)
        self.rows = [r for r in plan["parking"] if r["owner"] == owner]
        self.peer_rows = [r for r in plan["parking"] if r["owner"] == self.peer]
        self.client = ProtocolClient(session, retry_period=60.)
        self.index = 0; self.pending = None; self.failure = None; self.completed = []
        self.next_publication = 0.; self.publications = 0; self.supply = None; self.decisions = []; self.quiet = False
    def activate(self):
        self.client.refresh(owner_id=self.owner)
        if self.quiet: return
        view = self.session.observe_protocol_control_policy_recent(self.owner, VALIDITY)
        now = view["now"]; nodes = {r["node"]: r for r in view["node_contracts"]}
        require(view["owner_id"] == self.owner and now == self.session.physical_time, "view_owner_or_clock")
        peer = delivered_peer(self.session.protocol_planning_snapshots_v2(self.owner), self.owner, self.peer, now, nodes)
        if now == 0.: validate_initial_local(view, self.plan, self.owner)
        if self.failure: return
        if self.index == len(self.rows) and peer and any(r["request_id"] == owner_request_id(self.peer, "single-supply")
                for r in peer["capture"]["extension"]["submitted_physical_actions"]):
            self.quiet = True; return
        # A fixed publication period conveys native facts, not arbitrary tokens.
        if now >= self.next_publication and self.supply is None:
            self.client.submit(self.owner, "planning_snapshot_v2", {"target_owner": self.peer, "message_delay": WIRE,
                "publication_delay": WIRE, "expiry": now + VALIDITY}, request_id=owner_request_id(self.owner, f"snapshot:{self.publications}"))
            self.publications += 1; self.next_publication = now + PERIOD
        if self.pending:
            row = self.client.state["outbox"][self.pending["request_id"]]; ack = row.get("client_view", {}).get("last_delivered_ack", {})
            if row.get("submission_reply", {}).get("status") == "rejected" or (row["terminal"] and ack.get("status") != "received"):
                self.failure = {"reason": "parking_rejected_or_failed", "row": deepcopy(row)}; return
            if ack.get("status") == "received" and peer and parked_tray(peer["capture"]["local_capture"], self.pending):
                self.completed.append({"row": deepcopy(self.pending), "ack": deepcopy(ack), "recipient_snapshot": deepcopy(peer)})
                self.index += 1; self.pending = None
            else: return
        if self.index < len(self.rows):
            if self.owner != self.plan["owners"][0] and not peer_finished(peer, self.peer_rows, view): return
            row = self.rows[self.index]
            found = [t for t in view["trays"] if t["tray_id"] == row["tray_id"] and t["node"] == row["source"] and t["mode"] == "empty"
                and not t["business_bag_id"] and t["edge_to"] < 0 and t["reception_node"] < 0 and t["available_at"] <= now]
            if len(found) != 1:
                self.failure = {"reason": "predeclared_startup_source_no_longer_empty", "row": deepcopy(row), "view": deepcopy(view)}; return
            self.pending = deepcopy(row)
            self.client.submit(self.owner, "transfer", {"tray_id": row["tray_id"], "source": row["source"], "destination": row["destination"],
                "message_delay": WIRE, "earliest_departure": now, "expiry": min(HORIZON, now+2000.)}, request_id=row["request_id"])
            return
        if self.owner != self.plan["token_owner"] or self.supply is not None or not peer_finished(peer, self.peer_rows, view): return
        choice = eligible_head(peer, view, self.plan["token_tray_id"])
        if choice:
            request = {"tray_id": self.plan["token_tray_id"], "source": choice["tray"]["node"], "destination": choice["job"]["origin"],
                "message_delay": WIRE, "earliest_departure": now, "expiry": min(HORIZON, now+2000.)}
            self.supply = {"request_id": owner_request_id(self.owner, "single-supply"), "request": deepcopy(request), "at": now, "choice": choice}
            self.decisions.append(deepcopy(self.supply)); self.client.submit(self.owner, "transfer", request, request_id=self.supply["request_id"])
            self.quiet = True
    def summary(self):
        return {"owner": self.owner, "index": self.index, "pending": self.pending, "failure": self.failure, "completed": self.completed,
            "supply": self.supply, "outbox": self.client.state, "calls": self.client.calls, "publications": self.publications, "quiet": self.quiet}


def source_paths():
    pending = [Path(__file__)]; found = set()
    def enqueue(target):
        for p in (target.with_suffix(".py"), target / "__init__.py"):
            if p.is_file() and p.resolve().is_relative_to(ROOT):
                pending.append(p)
                for parent in p.parents:
                    if parent == ROOT: break
                    if (parent / "__init__.py").is_file(): pending.append(parent / "__init__.py")
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        found.add(path)
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(n, ast.ImportFrom):
                for base in ([path.parent] if n.level else [ROOT, ROOT / "src"]):
                    for _ in range(max(0, n.level-1)): base = base.parent
                    if n.module: base = base.joinpath(*n.module.split(".")); enqueue(base)
                    for alias in n.names:
                        if alias.name != "*": enqueue(base / alias.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    for base in (ROOT, ROOT / "src"): enqueue(base.joinpath(*a.name.split(".")))
    return sorted(found)


def prepare(output, source, binary):
    require(sha(source) == INPUT_SHA and sha(binary) == BINARY_SHA, "input_or_binary_identity")
    data = gzread(source)
    require(len(data["jobs"]) == 28506 and len(data["trays"]) == 22 and all(not j.get("allow_suffix_reroute", False) for j in data["jobs"]), "original_population_permission")
    require(not data["transfers"] and not data["faults"] and data["owner_protocol"]["ack_delay"] == .2, "original_initial_contract")
    public = {k: deepcopy(data[k]) for k in ("node_records", "edge_records", "node_contracts", "edge_contracts")}
    parking = parking_plan(public, data["trays"])
    require(len(parking["parking"]) == 22 and parking["serial_free_flow_seconds"] < min(j["arrival"] for j in data["jobs"]), "static_startup_screen_failed")
    build_path, accepted_path = OUT / "native026_build_001/receipt.json", OUT / "native026_acceptance_001/receipt.json"
    build, accepted = read(build_path), read(accepted_path)
    require(build["status"] == "build_passed_tests_held" and build["source_changed"] == [] and all(c["exit_code"] == 0 for c in build["commands"]), "build_status")
    require(build["binary_sha256"].get(str(binary.resolve())) == BINARY_SHA and sha(accepted_path) == ACCEPTANCE_SHA
        and accepted["status"] == "passed" and accepted["source_changed"] == [] and accepted["input_changed"] == [], "native_authority")
    output.mkdir(parents=True, exist_ok=False); shutil.copyfile(source, output / "input.json.gz")
    sources = {str(p): sha(p) for p in source_paths()}
    for p in sources:
        target = output / "source_archive" / Path(p).relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, target)
    for rel, digest in build["source_before"].items():
        src = build_path.parent / "source" / rel; require(sha(src) == digest, "compiled_archive")
        dest = output / "compiled_source_archive" / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dest)
    plan = {"schema": SCHEMA, "status": "prepared_native_unexecuted", "input_sha256": INPUT_SHA, "binary": str(binary.resolve()), "binary_sha256": BINARY_SHA,
        "source_before": sources, "authority_pins": {str(p): sha(p) for p in (build_path, accepted_path)}, "compiled_source_sha256": build["source_before"],
        "public_contract": public, "parking_plan": parking, "inventory": data["trays"], "horizon": HORIZON, "parent_timeout_seconds": 600.,
        "max_physical_requests": MAX_PHYSICAL, "max_ticks": MAX_TICKS, "tick_seconds": PERIOD, "event_budget_per_advance": 100000,
        "offered": 28506, "trays": 22, "native_branch_budget": 1, "original_r1_permission": False,
        "execution_amendment": "Preserve002 namespace rejection,003 coverage-order exception and004 heartbeat atomic-replace PermissionError interruption. IDs use the native owner namespace and coverage follows unique body-row order. Atomic replace alone retries PermissionError at most6 times after10/20/40/80/160/250ms; exhaustion still raises and no heartbeat is skipped. Exclusive parent/worker claims prohibit repeat execution or overwrite. No physical-policy, input, permission or budget change.",
        "policy_contract": "Static public startup inventory is checked against each owner's exact time0 local empty observation. First owner parks its trays sequentially; each source needs receivedACK and actual recipient native snapshot empty occupancy. Second owner starts only after delivered peer ACK coverage plus its own current recipient empties prove first segment finished. One designated tray may then supply one currently captured peer FIFO head with all positive-capacity mandatory paths; no same-zone fallback, no other parked-tray use, no alternate parking or head skipping.",
        "conditional_quiescence": "Only this predeclared controller submits physical operations. After parking,21 trays stay at nonloaders and never move; newly arriving jobs append to waiting FIFO. Native snapshots do not certify absence of future Python plans.",
        "assessment": "All28506 remain denominator. Require physical audit, actual original job UNLOAD_COMPLETE then HOLD_COMPLETE and same tray empty. No claim of second reuse, per-job protection, deadline success or complete-request100ms.",
        "failures": "Any rejection/changed startup source/open ACK/censored horizon retained; never replace a failed target or skip a waiting head."}
    write(output / "preregistered_protocol.json", plan); write(output / "branch_ledger.json", {"single_candidate": {"status": "unknown_unexecuted"}})
    return plan


def verify_pins(output, plan, runtime=False):
    require(sha(output / "input.json.gz") == plan["input_sha256"] == INPUT_SHA and sha(plan["binary"]) == BINARY_SHA, "input_binary_changed")
    for p, digest in plan["source_before"].items():
        require(sha(p) == digest and sha(output / "source_archive" / Path(p).relative_to(ROOT)) == digest, "source_changed")
    for p, digest in plan["authority_pins"].items(): require(sha(p) == digest, "authority_changed")
    for p, digest in plan["compiled_source_sha256"].items(): require(sha(output / "compiled_source_archive" / p) == digest, "compiled_source_changed")
    if runtime:
        actual = {str(Path(m.__file__).resolve()) for m in list(sys.modules.values()) if getattr(m, "__file__", None)
            and Path(m.__file__).suffix == ".py" and Path(m.__file__).resolve().is_relative_to(ROOT)}
        require(actual <= set(plan["source_before"]), "unarchived_loaded_dependency")


def run_policy(session, plan, progress=None):
    owners = [Owner(session, o, plan["parking_plan"]) for o in plan["parking_plan"]["owners"]]
    status = "unknown_incomplete"; tick = 0
    for tick in range(MAX_TICKS):
        for owner in owners: owner.activate()
        calls = [r for owner in owners for r in owner.client.calls]
        require(sum(r["kind"] == "transfer" and not r["retry"] for r in calls) <= MAX_PHYSICAL, "action_budget")
        if progress: progress(tick, owners)
        if any(o.failure for o in owners): status = "unknown_startup_failure"; break
        if session.physical_time >= HORIZON: status = "horizon_complete"; break
        target = min(HORIZON, session.physical_time+PERIOD)
        response = session.advance_to(target, max_events=100000)
        if response.get("status") != "reached" or response.get("horizon_complete") is not True or session.physical_time != target:
            status = "unknown_native_budget"; break
    return owners, status, tick


EXECUTION_ARTIFACTS = ("execution_claim.json", "worker_claim.json", "worker.log", "api", "heartbeat.json",
    "raw_final.json.gz", "error_prefix.json.gz", "assessment.json", "independent_verification.json", "receipt.json")


def claim_execution(output, plan):
    """One irreversible attempt per prepared package, including crashes/timeouts."""
    require(read(output / "branch_ledger.json") == {"single_candidate": {"status": "unknown_unexecuted"}}, "execution_already_attempted")
    require(not any((output / name).exists() for name in EXECUTION_ARTIFACTS), "execution_artifacts_already_exist")
    require(read(output / "preregistered_protocol.json") == plan, "execution_plan_changed")
    claim = {"schema": SCHEMA, "plan_sha256": sha(output / "preregistered_protocol.json"),
        "attempt_budget": 1, "status": "claimed_never_reuse_even_if_interrupted"}
    try:
        with (output / "execution_claim.json").open("x", encoding="utf-8") as f:
            json.dump(claim, f, ensure_ascii=False, allow_nan=False)
    except FileExistsError as error:
        raise ValueError("original_low_wip:execution_already_claimed") from error


def claim_worker(output):
    require(read(output / "execution_claim.json")["plan_sha256"] == sha(output / "preregistered_protocol.json"), "worker_parent_claim")
    require(not any((output / name).exists() for name in
        ("api", "heartbeat.json", "raw_final.json.gz", "error_prefix.json.gz", "assessment.json", "independent_verification.json", "receipt.json")), "worker_artifacts_already_exist")
    try:
        with (output / "worker_claim.json").open("x", encoding="utf-8") as f:
            json.dump({"schema": SCHEMA, "plan_sha256": sha(output / "preregistered_protocol.json")}, f)
    except FileExistsError as error:
        raise ValueError("original_low_wip:worker_already_claimed") from error


def worker(output):
    plan = read(output / "preregistered_protocol.json"); verify_pins(output, plan); claim_worker(output)
    data = gzread(output / "input.json.gz"); native = load_native(plan["binary"]); raw = native.NativeSession(data)
    tape = Tape(raw, output / "api"); owners = []; current_owners = []
    started = time.perf_counter()
    try:
        def progress(tick, current):
            current_owners[:] = current
            write(output / "heartbeat.json", {"tick": tick, "physical_time": raw.physical_time,
                "owners": [{"owner": o.owner, "parked": o.index, "failure": o.failure is not None, "supply": o.supply is not None} for o in current],
                "wall_seconds": time.perf_counter()-started, "offered": 28506})
        owners, status, tick = run_policy(tape, plan, progress)
        verify_pins(output, plan, runtime=True)
        result = raw.result_at(raw.physical_time)
        replay = deepcopy(data); replay["transfers"] += [{**r["request"], "issued_at": r["at"]} for o in owners for r in o.client.calls if r["kind"] == "transfer" and not r["retry"]]
        audit = audit_result(replay, result)
        final = {"schema": SCHEMA, "status": status, "physical_time": raw.physical_time, "tick": tick,
            "owners": [o.summary() for o in owners], "result": result, "physical_audit": audit,
            "native_state_sha256": raw.offline_state_sha256(), "offered": 28506, "wall_seconds": time.perf_counter()-started,
            "source_changed": [], "input_sha256": INPUT_SHA, "binary_sha256": BINARY_SHA,
            "plan_sha256": sha(output / "preregistered_protocol.json"), "strict_protection": "not_assessed", "complete_100ms_certified": False}
        gzwrite(output / "raw_final.json.gz", final); write(output / "assessment.json", assess(final, plan))
    except BaseException as error:
        gzwrite(output / "error_prefix.json.gz", {"status": "unknown_exception", "error": repr(error), "traceback": traceback.format_exc(),
            "physical_time": raw.physical_time, "owners": [o.summary() for o in (owners or current_owners)], "offered": 28506})
        raise


def assess(raw, plan):
    # Exact event names/identities are independently read from actual native receipts.
    rows = raw["result"].get("receipts", []); token = plan["parking_plan"]["token_tray_id"]
    completions = [r for r in rows if r.get("event") == "UNLOAD_COMPLETE" and r.get("tray_id") == token]
    holds = [r for r in rows if r.get("event") == "HOLD_COMPLETE" and r.get("tray_id") == token]
    supplies = [o["supply"] for o in raw["owners"] if o["supply"] is not None]
    witness = None
    if len(supplies) == 1:
        job = supplies[0]["choice"]["job"]["business_bag_id"]
        for c in completions:
            for h in holds:
                if c.get("business_bag_id") == job and h.get("business_bag_id") == job and c["time"] <= h["time"]:
                    witness = {"job": job, "tray_id": token, "unload": c, "hold_complete": h}
    physical_rows = [r for o in raw["owners"] for r in o["outbox"]["outbox"].values() if r["kind"] == "transfer"]
    closed_requests = len(physical_rows) == MAX_PHYSICAL and all(r.get("client_view", {}).get("last_delivered_ack", {}).get("status") == "received" for r in physical_rows)
    final_empty = [t for t in raw["result"]["trays"] if t["tray_id"] == token and t["mode"] == "empty" and t["job"] == -1 and t["edge_to"] < 0]
    closed = raw["status"] == "horizon_complete" and raw["physical_time"] == HORIZON and raw["result"]["advance"]["horizon_complete"] is True
    loaded_jobs = [(r["business_bag_id"], r["tray_id"]) for r in rows if r["event"] == "LOAD_START"]
    only_declared_load = bool(witness) and loaded_jobs == [(witness["job"], token)]
    complete = closed and witness and len(final_empty) == 1 and closed_requests and only_declared_load and sum(o["index"] for o in raw["owners"]) == 22 and raw["physical_audit"]["status"] == "passed"
    return {"schema": SCHEMA, "status": "observed_complete_and_empty" if complete else "unknown_or_no_complete_witness",
        "offered": 28506, "observed_horizon_complete": closed, "completion_witness": witness,
        "completed_parking": sum(o["index"] for o in raw["owners"]), "actual_supply_count": len(supplies),
        "all_physical_received_acks": closed_requests, "final_token_empty": bool(final_empty), "only_declared_job_loaded": only_declared_load,
        "second_reuse_proved": False, "strict_protection": "not_assessed", "complete_100ms_certified": False}


class ReplayTape:
    def __init__(self, directory):
        self.directory = directory; self.manifest = [json.loads(line) for line in (directory / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        self.index = 0; self.now = 0.
        require(len(list(directory.glob("*.json.gz"))) == len(self.manifest), "omitted_tape_file")
        for i, row in enumerate(self.manifest):
            require(row["path"] == f"{i:06d}.json.gz" and sha(directory / row["path"]) == row["sha256"], "tape_identity_or_hash")
    @property
    def physical_time(self): return self.now
    def __getattr__(self, name):
        require(name in ENDPOINTS, "unclassified_replay_endpoint")
        def call(*args, **kwargs):
            require(self.index < len(self.manifest), "missing_tape_call")
            row = gzread(self.directory / self.manifest[self.index]["path"])
            require(row["ordinal"] == self.index and row["endpoint"] == name and row["args"] == canonical(args)
                and row["kwargs"] == canonical(kwargs) and row["before"] == self.now and "error" not in row, "tape_call_order_or_payload")
            require(row["after"] >= self.now and (name == "advance_to" or row["after"] == self.now), "tape_clock")
            self.index += 1; self.now = row["after"]; return deepcopy(row["result"])
        return call


def normalized_owners(rows):
    rows = canonical(rows)
    for row in rows:
        for call in row["calls"]: call.pop("submit_compute_ms", None)
    return rows


def verify_saved(output):
    plan = read(output / "preregistered_protocol.json"); verify_pins(output, plan)
    data = gzread(output / "input.json.gz"); raw = gzread(output / "raw_final.json.gz")
    require(raw["input_sha256"] == INPUT_SHA and raw["binary_sha256"] == BINARY_SHA
        and raw["plan_sha256"] == sha(output / "preregistered_protocol.json"), "raw_source_identity")
    receipt_path = output / "receipt.json"
    if receipt_path.is_file():
        for name, digest in read(receipt_path)["artifact_sha256"].items(): require(sha(output / name) == digest, "completed_artifact_changed")
    require(plan["public_contract"] == {k: data[k] for k in plan["public_contract"]}
        and plan["inventory"] == data["trays"] and plan["parking_plan"] == canonical(parking_plan(data, data["trays"])), "predeclared_plan_changed")
    replay = ReplayTape(output / "api"); owners, status, tick = run_policy(replay, plan)
    require(replay.index == len(replay.manifest) and status == raw["status"] and tick == raw["tick"]
        and replay.physical_time == raw["physical_time"] and normalized_owners([o.summary() for o in owners]) == normalized_owners(raw["owners"]), "policy_replay_mismatch")
    require(len(raw["result"]["jobs"]) == raw["offered"] == 28506 and len(raw["native_state_sha256"]) == 64
        and raw["source_changed"] == [], "raw_scope_or_identity")
    replay_input = deepcopy(data); replay_input["transfers"] += [{**r["request"], "issued_at": r["at"]} for o in owners for r in o.client.calls if r["kind"] == "transfer" and not r["retry"]]
    require(audit_result(replay_input, raw["result"]) == raw["physical_audit"], "physical_audit_mismatch")
    assessment = assess(raw, plan); require(assessment == read(output / "assessment.json"), "assessment_changed")
    return {"status": "passed_saved_raw_replay", "api_rows": replay.index, "assessment": assessment,
        "scope": "Exact owner-local policy/ACK/recipient-capture reconstruction and independent complete physical receipt audit; no protection or timing claim."}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source", type=Path, default=OUT / "full_stream_native024_001/full1x/input.json.gz")
    p.add_argument("--binary", type=Path, default=ROOT / "build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd")
    p.add_argument("--worker", action="store_true"); p.add_argument("--execute", action="store_true"); p.add_argument("--verify", action="store_true"); args = p.parse_args()
    if args.worker: worker(args.output); return
    if args.verify: print(json.dumps(verify_saved(args.output), ensure_ascii=False)); return
    plan = read(args.output / "preregistered_protocol.json") if args.output.exists() else prepare(args.output, args.source, args.binary)
    verify_pins(args.output, plan)
    if not args.execute:
        print(json.dumps({"status": "prepared_native_unexecuted", "parking": len(plan["parking_plan"]["parking"]), "free_flow_seconds": plan["parking_plan"]["serial_free_flow_seconds"]})); return
    claim_execution(args.output, plan)
    write(args.output / "branch_ledger.json", {"single_candidate": {"status": "unknown_in_progress"}})
    started = time.perf_counter(); command = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.research_original_low_wip", "--worker", "--output", str(args.output)]
    with (args.output / "worker.log").open("wb") as log:
        try:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600., cwd=ROOT)
            code = process.returncode; status = "worker_finished" if code == 0 else "unknown_worker_nonzero"
        except subprocess.TimeoutExpired: code = None; status = "unknown_hard_timeout"
    changed = [s for s, digest in plan["source_before"].items() if sha(s) != digest]
    assessment = read(args.output / "assessment.json") if (args.output / "assessment.json").is_file() else None
    verification = None
    if code == 0 and not changed:
        try: verification = verify_saved(args.output); write(args.output / "independent_verification.json", verification)
        except BaseException as error: status = "unknown_verification_failed"; verification = {"error": repr(error)}
    if changed: status = "unknown_source_changed"
    receipt = {"schema": SCHEMA, "status": status, "exit_code": code, "command": command, "wall_seconds": time.perf_counter()-started,
        "source_changed": changed, "assessment": assessment, "verification": verification, "offered": 28506, "strict_protection": "not_assessed", "complete_100ms_certified": False}
    receipt["artifact_sha256"] = {name: sha(args.output / name) for name in
        ("preregistered_protocol.json", "raw_final.json.gz", "assessment.json", "api/manifest.jsonl", "worker.log", "independent_verification.json", "error_prefix.json.gz") if (args.output / name).is_file()}
    write(args.output / "receipt.json", receipt); write(args.output / "branch_ledger.json", {"single_candidate": receipt})
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__": main()
