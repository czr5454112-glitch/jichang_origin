"""Prepared native feasibility of four actual local two-second route commands.

No performance comparison is authorized by this gate. It stops on a delivered
rejection, observed path divergence, successful four-edge chain, or fixed bound.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time
from . import research_original_interference as old
from . import original_tie_path_enumeration as enumeration
from .original_workload import digest, json_digest, write_json
from .protocol_control import ProtocolClient
from .event_protocol_control import run_event_protocol_control
from .native_host import load_native

TARGET = "projected:1x:0"
GATE_HORIZON = 10000.


class ChainIntent:
    def __init__(self, path, commands):
        self.path = list(path)
        self.commands = copy.deepcopy(commands)
        self.stage = 0
        self.request_id = None
        self.status = "waiting_for_current_local_node"
        self.decisions = []
        self.observed_edges = []
        self.actual_prefix = []

    def observe(self, view, client):
        if self.status in ("rejected_intent", "observed_path_divergence", "all_four_intents_and_edges_observed"):
            return
        if self.request_id:
            ack = client.state["outbox"][self.request_id].get("client_view", {}).get("last_delivered_ack", {})
            if ack.get("delivered_at", float("inf")) <= view["now"]:
                if ack.get("status") in ("rejected", "expired", "failed", "cancelled"):
                    self.decisions[-1]["delivered_ack"] = copy.deepcopy(ack)
                    self.status = "rejected_intent"
                    return
                if ack.get("status") == "updated":
                    self.decisions[-1]["delivered_ack"] = copy.deepcopy(ack)
                    self.stage += 1
                    self.request_id = None
                    self.status = "waiting_for_current_local_node"
        tray = next((t for t in view["trays"] if t["business_bag_id"] == TARGET and t["mode"] == "loaded"), None)
        if tray:
            prefix = list(tray["committed_prefix"])
            if tray["edge_to"] >= 0:
                prefix.append(tray["edge_to"])
                identity = [tray["generation"], tray["traversal_id"]]
                if not any(e["identity"] == identity for e in self.observed_edges):
                    self.observed_edges.append({"identity": identity, "from": tray["edge_from"], "to": tray["edge_to"],
                        "observed_at": view["now"], "owner": view["owner_id"], "local_tray": copy.deepcopy(tray)})
            if prefix != self.path[:len(prefix)]:
                self.status = "observed_path_divergence"
                self.actual_prefix = prefix
                return
            if len(prefix) > len(self.actual_prefix):
                self.actual_prefix = prefix
        required_edges = {(c["from"], c["next"]) for c in self.commands}
        observed_edges = {(c["from"], c["to"]) for c in self.observed_edges}
        if self.stage == len(self.commands) and required_edges <= observed_edges:
            self.status = "all_four_intents_and_edges_observed"
            return
        if self.request_id or self.stage == len(self.commands) or not tray or tray["edge_to"] >= 0:
            return
        command = self.commands[self.stage]
        if tray["node"] != command["from"]:
            return
        source = next(n for n in view["node_contracts"] if n["node"] == command["from"])
        if source["resource_owner"] != view["owner_id"]:
            return
        job = next((j for j in view["jobs"] if j["business_bag_id"] == TARGET), None)
        if not job or job["storage_node"] != 53 or job["storage_released_at"] >= 0:
            return
        owner = view["owner_id"]
        payload = {"business_bag_id": TARGET, "tray_id": tray["tray_id"], **command,
            "expected_generation": tray["generation"], "expected_traversal": tray["traversal_id"],
            "expiry": view["now"] + 120., "message_delay": 2.}
        identity = f"live:{len(owner.encode('utf-8'))}:{owner}:tie-chain-{self.stage}"
        self.request_id, reply = client.submit(owner, "route", payload, request_id=identity)
        self.decisions.append({"stage": self.stage, "owner": owner, "at": view["now"], "request_id": identity,
            "local_tray": copy.deepcopy(tray), "local_job": copy.deepcopy(job), "request": copy.deepcopy(payload),
            "submission_reply": copy.deepcopy(reply)})
        self.status = "awaiting_delivered_ack"


class GateResolved(Exception): pass


class OwnerBoundary:
    def __init__(self, native, path, commands):
        self.native = native
        self.client = ProtocolClient(native, retry_period=60.)
        self.intent = ChainIntent(path, commands)

    def __getattr__(self, name): return getattr(self.native, name)

    def observe_protocol_control_policy(self, owner): return self.native.observe_protocol_control_policy(owner)

    def advance_until_owner_notification(self, owners, after, horizon, *, max_events):
        response = self.native.advance_until_owner_notification(owners, after, horizon, max_events=max_events)
        if response.get("timestamp_complete"):
            for owner in sorted(response.get("notifications", {})):
                self.client.refresh(owner_id=owner)
                self.intent.observe(self.native.observe_protocol(owner), self.client)
            if self.intent.status in ("rejected_intent", "observed_path_divergence", "all_four_intents_and_edges_observed"):
                raise GateResolved(self.intent.status)
        return response


def prepare(output, input_file, paths):
    output.mkdir(parents=True, exist_ok=False)
    data = json.load(gzip.open(input_file, "rt"))
    prior = json.loads((paths / "preregistered_protocol.json").read_text())
    summary = json.loads((paths / "summary.json").read_text())
    selected = next(s for s in summary["selected_hypotheses"] if s["business_bag_id"] == TARGET)
    hypothesis = selected["selected_offline_hypothesis"]
    if digest(input_file) != prior["source_input_sha256"] or len(data["jobs"]) != 28506 or len(data["trays"]) != 22:
        raise ValueError("tie_gate:original_input_identity")
    expected = [(1, 2), (5, 33), (33, 51), (29, 146)]
    if [(c["from"], c["next"]) for c in hypothesis["commands"]] != expected:
        raise ValueError("tie_gate:predeclared_action_identity")
    sources = [Path(__file__), Path(enumeration.__file__), Path(old.__file__), *[Path(__file__).with_name(n + ".py")
        for n in ("original_workload", "protocol_control", "event_protocol_control", "analytic_control", "regional_control", "native_host", "run_original_protocol")]]
    archive = output / "source_archive"; archive.mkdir()
    for source in sources: (archive / source.name).write_bytes(source.read_bytes())
    protocol = {"schema": "g31.lt2.original_two_second_chain_gate.v1", "native_branch_budget": 1,
        "target": TARGET, "horizon": GATE_HORIZON, "input_business_count": 28506, "tray_count": 22,
        "source_input_file_sha256": digest(input_file), "input_sha256": json_digest(data),
        "offline_hypothesis": hypothesis, "offline_required_delay": selected["required_delay"],
        "source_path_census_sha256": digest(paths / "summary.json"),
        "source_sha256": {str(s.resolve()): digest(s) for s in sources},
        "current_local_contract": "Only actual notified source owner, current local node, actual generation and traversal; eachnewroute has original2sdelay. No future preissue, pause or fullsuffix grant.",
        "continuation": "unchanged event R2 predictive/prebalance+forecasts; routes=False except four explicit gate intents",
        "stop": "first delivered rejection or observed committed-prefix divergence; otherwise fourth updatedACK+actualselectededge; else H10000 or100000activations/hard60s unknown",
        "first_gate": "first1to2 exact2s command; continue remainingthree onlyifactualACKupdated and observedpathcontinues",
        "comparison_admitted": False, "business_metrics": None, "strict_protection_status": "not_assessed",
        "limits": "This gate onlytests actionexecutability. Originalbad0 unfinished vsunfinished hasundefinedcompletiondelta; nozero-regressionclaim. A matchedfullpopulationmechanismcomparison requiresseparateexecution."}
    old.gzip_json(output / "input.json.gz", data)
    write_json(output / "preregistered_protocol.json", protocol)
    write_json(output / "branch_ledger.json", {"chain_gate": {"status": "unknown_unexecuted"}})
    return protocol


def worker(args):
    protocol = json.loads((args.output / "preregistered_protocol.json").read_text())
    data = json.load(gzip.open(args.output / "input.json.gz", "rt"))
    if json_digest(data) != protocol["input_sha256"] or digest(args.binary) != args.expected_binary_sha256:
        raise ValueError("tie_gate:input_or_binary_changed")
    if any(digest(Path(s)) != h for s, h in protocol["source_sha256"].items()):
        raise ValueError("tie_gate:source_changed")
    native = load_native(args.binary); session = native.NativeSession(data)
    chosen = protocol["offline_hypothesis"]
    gate = OwnerBoundary(session, chosen["path"], chosen["commands"])
    owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    started = time.perf_counter(); status = "unknown_horizon_or_compute_bound"
    try:
        run_event_protocol_control(gate, owners, horizon=GATE_HORIZON, control_period=60., command_delay=2.,
            publication_delay=.5, retry_period=60., lease_seconds=120., routes=False, forecasts=True,
            predictive=True, prebalance=True, event_budget=100000, max_activations=100000)
    except GateResolved as stop: status = str(stop)
    changed = [s for s, h in protocol["source_sha256"].items() if digest(Path(s)) != h]
    report = {"schema": protocol["schema"], "status": status if not changed else "unknown_source_changed",
        "input_sha256": protocol["input_sha256"], "input_business_count": len(data["jobs"]), "tray_count": len(data["trays"]),
        "actual_native_clock": session.physical_time, "intent": vars(gate.intent), "route_calls": gate.client.calls,
        "route_outbox": gate.client.state, "binary_sha256": args.expected_binary_sha256,
        "native_branches_executed": 1, "wall_seconds": time.perf_counter() - started,
        "source_changed": changed, "business_metrics": None, "gain": None,
        "strict_protection_status": "not_assessed", "comparison_admitted": False}
    write_json(args.output / "receipt.json", report)
    write_json(args.output / "branch_ledger.json", {"chain_gate": {"status": report["status"]}})
    print(json.dumps({k: report[k] for k in ("status", "actual_native_clock", "wall_seconds", "source_changed")}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--input", type=Path); p.add_argument("--paths", type=Path)
    p.add_argument("--binary", type=Path); p.add_argument("--expected-binary-sha256")
    p.add_argument("--execute", action="store_true"); p.add_argument("--worker", action="store_true")
    p.add_argument("--timeout-seconds", type=float, default=60.)
    a = p.parse_args()
    if a.worker: worker(a); return
    prepare(a.output, a.input, a.paths)
    if not a.execute: print("prepared_no_native_calls:one_four_stage_gate"); return
    if not a.binary or not a.expected_binary_sha256: p.error("exact_native_binary_identity_required")
    command = [sys.executable, "-m", __spec__.name, "--worker", "--output", str(a.output),
        "--binary", str(a.binary), "--expected-binary-sha256", a.expected_binary_sha256]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=a.timeout_seconds)
        (a.output / "worker.stdout.log").write_text(done.stdout, encoding="utf-8")
        (a.output / "worker.stderr.log").write_text(done.stderr, encoding="utf-8")
        if done.returncode: write_json(a.output / "worker_failure.json", {"status": "unknown_failed", "returncode": done.returncode})
    except subprocess.TimeoutExpired:
        write_json(a.output / "worker_failure.json", {"status": "unknown_hard_timeout", "branch_ledger_retained": True})


if __name__ == "__main__": main()
