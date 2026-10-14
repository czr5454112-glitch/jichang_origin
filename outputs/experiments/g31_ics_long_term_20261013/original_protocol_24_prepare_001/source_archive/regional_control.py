"""Owner-local on-demand routing and a versioned system A* intent codec.

Only public observations are consumed. The packet is a replaceable preference,
never a reservation, inventory record or permission to undo an entered edge.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import heapq
import json
import math
import time
from typing import Any


@dataclass(frozen=True)
class RoutePacket:
    schema: str
    business_bag_id: str
    tray_id: str
    owner_id: str
    generation: int
    traversal_id: int
    stage: str
    stage_goal: int
    committed_prefix: tuple[int, ...]
    replaceable_suffix: tuple[int, ...]
    observed_at: float


def encode_route(packet: RoutePacket) -> str:
    if packet.schema != "g31.route_intent.v1" or not packet.replaceable_suffix or not packet.committed_prefix:
        raise ValueError("route_codec:invalid_packet")
    if packet.committed_prefix[-1] != packet.replaceable_suffix[0] or packet.replaceable_suffix[-1] != packet.stage_goal:
        raise ValueError("route_codec:prefix_or_stage_mismatch")
    return json.dumps(asdict(packet),sort_keys=True,separators=(",",":"),allow_nan=False)


def decode_route(payload: str) -> RoutePacket:
    data=json.loads(payload)
    data["committed_prefix"]=tuple(data["committed_prefix"])
    data["replaceable_suffix"]=tuple(data["replaceable_suffix"])
    packet=RoutePacket(**data)
    encode_route(packet)
    return packet


def public_astar(observation: dict[str, Any], source: int, goal: int) -> tuple[int, ...]:
    """A* with exact static lower bound and declared local berth penalty.

    Dynamic penalties use local occupancy only. Remote live queues do not exist
    in this projection. This is a deterministic strong baseline, not novelty.
    """
    contracts={n["node"]:n for n in observation["node_contracts"]}
    service={n[0]:max(n[2],.001) for n in observation["node_records"]}
    closed={(e["from"],e["to"]) for e in observation["edge_contracts"] if e["capacity"]==0}
    closed.update((f["from"],f["to"]) for f in observation.get("known_faults",[]) if f["active"])
    outgoing={n:[] for n in contracts}; incoming={n:[] for n in contracts}
    for u,v,length,speed in observation["edge_records"]:
        if (u,v) in closed: continue
        cost=service[u]+max(length/speed,.001)
        outgoing[u].append((v,cost));incoming[v].append((u,cost))
    h={goal:0.};queue=[(0.,goal)]
    while queue:
        cost,node=heapq.heappop(queue)
        if cost!=h[node]:continue
        for predecessor,weight in incoming[node]:
            new=cost+weight
            if new<h.get(predecessor,math.inf):
                h[predecessor]=new;heapq.heappush(queue,(new,predecessor))
    if source not in h:return ()
    queue=[(h[source],0.,(source,),source)];best={source:0.}
    while queue:
        _,cost,path,node=heapq.heappop(queue)
        if cost!=best[node]:continue
        if node==goal:return path
        for successor,weight in outgoing[node]:
            if successor not in h:continue
            local=contracts[successor]
            penalty=max(0,local.get("occupancy",0))*service[successor]
            new=cost+weight+penalty
            if new<best.get(successor,math.inf):
                best[successor]=new
                heapq.heappush(queue,(new+h[successor],new,path+(successor,),successor))
    return ()


def make_route_packet(observation: dict[str, Any], tray_id: str) -> RoutePacket:
    tray=next((t for t in observation["trays"] if t["tray_id"]==tray_id),None)
    if tray is None:raise ValueError("route:tray_not_visible")
    if tray["edge_to"]>=0:raise ValueError("route:committed_edge_cannot_be_replaced")
    job=next((j for j in observation["jobs"] if j["business_bag_id"]==tray["business_bag_id"]),None)
    if job is None or not job["allow_suffix_reroute"]:raise ValueError("route:service_obligation_disallows_reroute")
    if tray["mode"]!="loaded":raise ValueError("route:no_active_route_stage")
    storage=job.get("storage_node",-1)
    before_storage=storage>=0 and job.get("storage_released_at",-1)<0
    goal=storage if before_storage else job["destination"]
    path=public_astar(observation,tray["node"],goal)
    if len(path)<2:raise ValueError("route:no_safe_public_continuation")
    return RoutePacket("g31.route_intent.v1",job["business_bag_id"],tray_id,observation["owner_id"],
                       tray["generation"],tray["traversal_id"],"storage_in" if before_storage else "storage_out_or_direct",
                       goal,tuple(tray.get("committed_prefix",[tray["node"]])),path,observation["now"])


def submit_on_demand(session, owner_id: str, tray_id: str, request_id: str, *,
                     message_delay: float=0., logical_compute_delay: float=0., lease_seconds: float=5.) -> dict[str, Any]:
    """Queue completion at a native event time; delayed state can invalidate it.

    Measured CPU/wall compute is distinct from declared deterministic processing
    delay. Owner delivery/revalidation must be measured separately for a full
    100ms claim; this routine deliberately does not make that claim.
    """
    if not all(math.isfinite(x) and x>=0 for x in (message_delay,logical_compute_delay,lease_seconds)):
        raise ValueError("route:invalid_delay")
    start=time.perf_counter();cpu=time.process_time()
    observation=session.observe(owner_id)
    try:
        packet=make_route_packet(observation,tray_id)
        decoded=decode_route(encode_route(packet))
        request={"request_id":request_id,"owner_id":owner_id,"business_bag_id":decoded.business_bag_id,
                 "tray_id":tray_id,"from":decoded.replaceable_suffix[0],"next":decoded.replaceable_suffix[1],
                 "expected_generation":decoded.generation,"expected_traversal":decoded.traversal_id,
                 "expiry":observation["now"]+lease_seconds,"message_delay":message_delay+logical_compute_delay}
        response=session.submit_route_intent(request)
        payload=encode_route(packet)
    except ValueError as exc:
        response={"status":"rejected","reason":str(exc)};request=None;payload=None
    return {"response":response,"request":request,"encoded_route":payload,
            "submission_compute_ms":(time.perf_counter()-start)*1000,
            "submission_cpu_ms":(time.process_time()-cpu)*1000,
            "logical_compute_delay":logical_compute_delay,"message_delay":message_delay,
            "timing_scope":"observe+conversion+candidate A*+codec+submit; delivery owner compute excluded",
            "complete_100ms_requirement_certified":False}


def complete_on_demand(session, owner_id: str, tray_id: str, request_id: str, *,
                       message_delay: float=0., logical_compute_delay: float=0.,
                       lease_seconds: float=5., event_budget: int=100000) -> dict[str, Any]:
    """Measure one complete synchronous *simulation experiment* request chain.

    This drives the existing native session only to the declared completion
    message time, then reads the actual owner response. All simulated physical
    event work in that interval is charged too: measured wall/CPU is therefore
    a conservative compute scope, not a pure policy timing or deployment SLA.
    It must not be nested in an external controller without preserving that
    controller's intervening ticks. Network delay is logical and separately
    recorded; no claim is made that wall-clock physical equipment was running.
    """
    start=time.perf_counter();cpu=time.process_time();physical_start=session.physical_time
    submitted=submit_on_demand(session,owner_id,tray_id,request_id,
        message_delay=message_delay,logical_compute_delay=logical_compute_delay,lease_seconds=lease_seconds)
    progress=None
    if submitted["response"]["status"]=="pending":
        progress=session.advance_to(physical_start+logical_compute_delay+message_delay,max_events=event_budget)
        actual=next((r for r in session.observe(owner_id)["route_requests"] if r["request_id"]==request_id),None)
        if actual is None or actual["status"]=="pending":
            final={"status":"timeout_unknown","reason":"owner_completion_not_observed"}
        else:
            final=actual
    else:
        final=submitted["response"]
    # Include response serialization/deserialization in the measured path.
    final=json.loads(json.dumps(final,allow_nan=False))
    wall_ms=(time.perf_counter()-start)*1000;cpu_ms=(time.process_time()-cpu)*1000
    return {"submission":submitted,"final_response":final,"advance":progress,
            "compute_wall_ms":wall_ms,"compute_cpu_ms":cpu_ms,
            "meets_measured_100ms":wall_ms<=100.,"overrun_is_failure":wall_ms>100.,
            "physical_started_at":physical_start,"physical_finished_at":session.physical_time,
            "logical_network_delay_seconds":message_delay,
            "logical_processing_delay_seconds":logical_compute_delay,
            "timing_scope":"observe+conversion+A*+codec+submit+all intervening native events including owner revalidation+confirmation+response codec",
            "hard_realtime_guarantee":False,"complete_100ms_requirement_certified":False,
            "limits":"single-process synthetic/request sample; modeled network wait; external controller ticks not automatically replayed"}
