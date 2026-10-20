"""Read-only physical audit of fixed 1d895da0 artifacts; no native or model calls."""
from __future__ import annotations
from pathlib import Path
import argparse
import collections
import gzip
import hashlib
import json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root",type=Path,required=True,help="Fixed-commit repository/export root")
parser.add_argument("--output",type=Path,required=True,help="New diagnostic JSON destination")
args=parser.parse_args()
ROOT=args.root.resolve()
OUTPUT=args.output.resolve()
CYCLE=ROOT/"outputs/experiments/g31_ics_action_value_20261020/cycle_001"
RUNS=("G_N26_C00_P902_001","G_N26_C10_P902_001","G_N26_C11_S29_P902_001")

def load(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)

def bind(path):
    b=path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))

def path_bfs(edges,source,target):
    q=collections.deque([source]); parent={source:None}
    while q:
        u=q.popleft()
        if u==target:
            found=[u]
            while parent[found[-1]] is not None:
                found.append(parent[found[-1]])
            return found[::-1]
        for v in edges[u]:
            if v not in parent:
                parent[v]=u
                q.append(v)
    return None

def occupancy(trays):
    holders=collections.defaultdict(list)
    for t in trays:
        claims=collections.defaultdict(list)
        if t["edge_to"]<0: claims[t["node"]].append("physical_at_node")
        else: claims[t["edge_to"]].append("physical_incoming")
        if t["reception_node"]>=0: claims[t["reception_node"]].append("remote_reception_lease")
        for n,kinds in claims.items():
            holders[n].append(dict(tray_id=t["tray_id"],kinds=kinds,mode=t.get("mode")))
    return holders

def spatial_at(data,receipts,t):
    state={r["tray_id"]:dict(tray_id=r["tray_id"],node=r["node"],edge_to=-1,reception_node=-1)
           for r in data["trays"]}
    for r in receipts:
        if r["time"]>t: break
        tid=r.get("tray_id")
        if tid not in state: continue
        s=state[tid]; e=r["event"]
        if e=="EDGE_ENTER": s["edge_to"]=r["to"]
        elif e=="EDGE_EXIT": s.update(node=r["to"],edge_to=-1)
        elif e=="EXPORT_GRANTED": s["reception_node"]=r["to"]
        elif e in ("EMPTY_RECEIVED","UNUSED_RECEIVING_RELEASED"): s["reception_node"]=-1
    return list(state.values())

results=[]
for name in RUNS:
    d=CYCLE/name
    x=load(d/"input.json"); r=load(d/"final_result.json.gz"); calls=load(d/"client_calls.json.gz")
    receipts=r["receipts"]
    if not isinstance(calls,list):
        calls=calls.get("calls",calls.get("client_calls",[]))
    contracts={z["node"]:z for z in x["node_contracts"]}
    edges=collections.defaultdict(list)
    for e in x["edge_contracts"]:
        if e["capacity"]>0: edges[e["from"]].append(e["to"])
    occ=occupancy(r["trays"])
    reconstructed={z["tray_id"]:z for z in spatial_at(x,receipts,r["physical_clock"])}
    for tray in r["trays"]:
        assert all(reconstructed[tray["tray_id"]][key]==tray[key]
                   for key in ("node","edge_to","reception_node")), "final spatial reconstruction mismatch"
    leg_by_id={z["runtime_id"]:z for z in r["leg_identities"]}
    failure_rows=[]
    for f in receipts:
        if f["event"]!="LEG_FAILED": continue
        tr=next(z for z in r["trays"] if z["tray_id"]==f["tray_id"])
        leg=leg_by_id[tr["active_leg"]]
        transfer_id=f["transport_leg_id"].split(":empty_return:")[0]
        transfer=next(z for z in r["transfers"] if z["request_id"]==transfer_id)
        submitted=[z for z in calls if z.get("kind")=="transfer" and
            not z.get("retry") and z["request"]["request_id"]==transfer_id]
        node=tr["node"]
        after=[z for z in receipts if z["time"]>f["time"] and z["node"]==node
            and z["event"] in ("RESOURCE_WAIT","RESOURCE_WAKE","EDGE_ENTER")]
        physical_snapshot=spatial_at(x,receipts,f["time"]+1e-8)
        at_failure=occupancy(physical_snapshot)
        following=[z for z in r["trays"] if z["node"]==node and z["mode"]=="loaded"]
        following_ids={z["tray_id"] for z in following}
        followers_last_entry=[z for z in receipts if z["event"]=="EDGE_EXIT" and
            z["to"]==node and z["tray_id"] in following_ids]
        failure_rows.append(dict(failure=f,final_tray=tr,native_transfer=transfer,
            actual_submissions=submitted,
            unused_receiving_releases=[z for z in receipts if z["event"]=="UNUSED_RECEIVING_RELEASED"
                and z["transport_leg_id"]==f["transport_leg_id"]],
            physical_first_edges=[z for z in receipts if z["event"]=="EDGE_ENTER"
                and z["transport_leg_id"]==f["transport_leg_id"]],
            recovery_receipts=[z for z in receipts if z["tray_id"]==f["tray_id"]
                and "RECOVERY" in z["event"]],
            final_same_node_loaded_trays=following,
            final_followers_last_arrivals=followers_last_entry,
            same_node_service_or_resource_events_after_failure=after,
            downstream_first_departures_after_failure={str(n):next((z for z in receipts
                if z["time"]>f["time"] and z["event"]=="EDGE_ENTER" and z["from"]==n),None)
                for n in edges[node]},
            receiver_holder_snapshot_at_failure={str(k):v for k,v in at_failure.items()
                if k==node or k in edges[node]},
            final_outgoing=[dict(to=v,capacity=contracts[v]["capacity"],holders=occ[v],
                static_positive_capacity_path_to_53=path_bfs(edges,v,53)) for v in edges[node]]))
    physical=[]
    for n,holders in sorted(occ.items()):
        if holders:
            physical.append(dict(node=n,capacity=contracts[n]["capacity"],occupancy=len(holders),
                holders=holders,outgoing=[dict(to=v,edge_capacity=next(e["capacity"] for e in x["edge_contracts"]
                    if e["from"]==n and e["to"]==v),receiver_capacity=contracts[v]["capacity"],
                    receiver_occupancy=len(occ[v]),
                    static_positive_capacity_path_to_53=path_bfs(edges,v,53)) for v in edges[n]]))
    def last(event):
        a=[z["time"] for z in receipts if z["event"]==event]
        return max(a) if a else None
    results.append(dict(name=name,inputs=[bind(d/f) for f in
        ("input.json","final_result.json.gz","client_calls.json.gz")],
        physical_clock=r["physical_clock"],advance=r["advance"],
        spatial_receipt_reconstruction_matches_all_final_trays=True,
        job_status_counts=dict(collections.Counter(z["status"] for z in r["jobs"])),
        tray_mode_counts=dict(collections.Counter(z["mode"] for z in r["trays"])),
        physical_inflight_trays=sum(z["edge_to"]>=0 for z in r["trays"]),
        last_completed=last("UNLOAD_COMPLETE"),last_edge_exit=last("EDGE_EXIT"),
        node_occupancy=physical,failures=failure_rows,
        interpretation_scope="Recorded evidence plus static reachability only; no queue snapshot or native rerun"))
report=dict(schema="independent.physical_stall_audit.1d895da0.v1",
    fixed_commit="1d895da00644c9486568fe74b835e057aa93f8c8",
    scope="Read raw input/final receipts/client submissions; independently reconstruct spatial occupancy and failures",
    native_starts=0,training_calls=0,fit_calls=0,source_edits=0,
    evidence_quality="Confirmed artifact facts; lost-wakeup mechanism requires minimal native reproducer",
    rows=results)
OUTPUT.parent.mkdir(exist_ok=True,parents=True)
OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
for r in results:
    print(r["name"],r["job_status_counts"],r["tray_mode_counts"],r["last_edge_exit"])
    for f in r["failures"]:
        print("failure",f["failure"]["tray_id"],f["failure"]["time"],
          "post-node-wake/dispatch-events",len(f["same_node_service_or_resource_events_after_failure"]),
          "loaded-followers",len(f["final_same_node_loaded_trays"]),
          "recoveries",len(f["recovery_receipts"]))
print(OUTPUT)

