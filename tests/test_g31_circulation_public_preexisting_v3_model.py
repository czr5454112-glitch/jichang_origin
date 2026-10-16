"""Restricted supplied-data tests; no native execution or delivery claim."""
import copy
import math
import pytest
from scripts.experiments.g31_ics_circulation import public_preexisting_v3_model as model
from test_g31_circulation_preexisting_online_model import later_state


def fixture(edge=(1, 3), phase="first_return"):
    c, j, t, r, args = later_state()
    if phase == "first_reuse_route":
        args.update(now=9.26, phase=phase)
        j["reuse1"].update(status="in_transit", loaded_at=9.22)
        t["L"].update(node=7, mode="loaded", business_bag_id="reuse1", committed_prefix=[7],
            service_ready_at=9.32, ready_kind="committed_local_service_end")
    now = args["now"]
    j["receiver"].update(status="in_transit", loaded_at=now-2.)
    t["E"].update(node=edge[0], mode="loaded", edge_from=edge[0], edge_to=edge[1],
        committed_prefix=[1] if edge==(1,3) else [1,3], service_ready_known=False,
        ready_kind="unknown_inflight", service_ready_at=-1., load_complete_at=-1., available_at=0., traversal_id=3)
    owners = {n["node"]: n["resource_owner"] for n in c["node_contracts"]}
    travel = next(length/speed for u,v,length,speed in c["edge_records"] if (u,v)==edge)
    entry = now-.1
    row = {"source_owner": owners[edge[0]], "receipt_event": "EDGE_ENTER", **{k:t["E"][k] for k in
        ("tray_id","business_bag_id","generation","traversal_id","edge_from","edge_to")},
        "entered_at": entry, "static_edge_travel_seconds": travel, "derived_edge_exit_at": entry+travel}
    for index, source in enumerate(args["source_records"]):
        source.update(captured_at=now-.005+index*.001, delivered_at=now-.001, valid_until=now+.1)
        source.update(submitted_physical_request_ids=[], submitted_physical_actions=[])
        owner = source["owner"]
        source["tray_ids"] = [key for key,tray in t.items() if owners[tray["node"]]==owner]
        source["job_ids"] = sorted({tray["business_bag_id"] for tray in t.values() if owners[tray["node"]]==owner and tray["business_bag_id"]}
            | {key for key,job in j.items() if job["status"]=="waiting_for_tray" and owners[job["origin"]]==owner})
    for node, resource in r.items():
        selected = [tray for tray in t.values() if (tray["edge_to"] if tray["edge_to"]>=0 else tray["node"])==node]
        resource.update(occupancy=len(selected), actual_available=sum(tray["mode"]=="empty" and tray["edge_to"]<0 and tray["available_at"]<=now for tray in selected),
            unrepresented_occupancy=sum(owners[tray["node"]]!=owners[node] for tray in selected))
    for source in args["source_records"]:
        source["unrepresented_occupancy"] = sum(row["unrepresented_occupancy"] for node,row in r.items() if owners[node]==source["owner"])
    args["entry_receipts"] = [row]
    args["collection_contract"] = {"schema":"g31.conditional_collection_quiescence.v1",
        "physical_admissions_quiesced_from":min(s["captured_at"] for s in args["source_records"]),
        "through":now,"future_python_actions_certified_by_native":False}
    return c,j,t,r,args


@pytest.mark.parametrize("edge",[(1,3),(3,4)])
@pytest.mark.parametrize("phase",["first_return","first_reuse_route"])
def test_moving_extension_keeps_full_five_jobs_and_all_old_contracts(edge,phase):
    c,j,t,r,args=fixture(edge,phase); before=copy.deepcopy((c,j,t,r,args))
    b=model.assemble_later(c,j,t,r,**args)
    assert b["status"]=="conditional_model_input", b
    assert (c,j,t,r,args)==before
    assert not b["current_state_certified"] and not b["online_information_delivered"]
    assert len(b["stability"])==3 and b["source_records"][0]["captured_at"]!=b["source_records"][1]["captured_at"]
    p=model.predict(b,{"reuse_next":8,"return_delay":0.})
    assert p["status"]=="conditional_prediction" and set(p["completion"])==model.JOBS
    assert p["completion"]["blocker"]==4.3 and p["completion"]["loaded"]==6.8


@pytest.mark.parametrize("defect",["no_entry","bool_generation","entry_after_first_capture","exit_now","zero_travel","wrong_traversal",
    "pending","future_job","ready_now","bool_calendar","zero_calendar","terminal_in_interval","missing_tray","unrepresented","foreign_source","quiescence_missing",
    "bad_protocol","changed_headway","new_lease","extra_entry"])
def test_unsupported_transition_resource_and_authority_fail_closed(defect):
    c,j,t,r,args=fixture(); entry=args["entry_receipts"][0]; now=args["now"]
    if defect=="no_entry": args["entry_receipts"]=[]
    elif defect=="bool_generation": entry["generation"]=True
    elif defect=="entry_after_first_capture": entry["entered_at"]=now-.0045; entry["derived_edge_exit_at"]=entry["entered_at"]+entry["static_edge_travel_seconds"]
    elif defect=="exit_now": entry["entered_at"]=now-entry["static_edge_travel_seconds"]; entry["derived_edge_exit_at"]=now
    elif defect=="zero_travel": entry["static_edge_travel_seconds"]=0.
    elif defect=="wrong_traversal": entry["traversal_id"]+=1
    elif defect=="pending": args["source_records"][0]["unresolved_tray_request_ids"]=["pending"]
    elif defect=="future_job": j["reuse2"]["arrival"]=now+.001
    elif defect=="ready_now": t["L"]["available_at"]=t["L"]["service_ready_at"]=now
    elif defect=="bool_calendar": t["L"]["available_at"]=t["L"]["service_ready_at"]=True
    elif defect=="zero_calendar": t["L"]["available_at"]=t["L"]["service_ready_at"]=0.
    elif defect=="terminal_in_interval": args["terminal_receipts"][0]["completed_at"]=now-.001
    elif defect=="missing_tray": del t["P"]
    elif defect=="unrepresented": r[3]["unrepresented_occupancy"]=0
    elif defect=="foreign_source": entry["source_owner"]="B"
    elif defect=="quiescence_missing": args["collection_contract"]={}
    elif defect=="bad_protocol": c["protocol"]["message_delay"]=1.
    elif defect=="changed_headway": c["edge_contracts"][0]["entry_headway"]+=.001
    elif defect=="new_lease": t["E"]["reception_node"]=4
    else: args["entry_receipts"].append(copy.deepcopy(entry))
    b=model.assemble_later(c,j,t,r,**args)
    assert b["status"]=="unknown", (defect,b)
    assert model.propose(b)["selected_action"] is None


def test_existing_target_service_calendar_and_headway_seeded_from_entry():
    c,j,t,r,args=fixture(); b=model.assemble_later(c,j,t,r,**args)
    projection=model.LaterProjection(b,{"reuse_next":3,"return_delay":0.}); projection.seed()
    entry=args["entry_receipts"][0]; end=entry["derived_edge_exit_at"]
    assert projection.calendars[3]==[(end,end+projection.service[3])]
    assert projection.next_entry[1,3]==entry["entered_at"]+projection.edges[1,3]["entry_headway"]
    assert projection.occupancy(3)==1 and projection.occupancy(1)==0
    assert sum(event[3]=="arrive" and event[4]==("E",3) for event in projection.events)==1
    c,j,t,r,args=fixture((3,4)); b=model.assemble_later(c,j,t,r,**args)
    projection=model.LaterProjection(b,{"reuse_next":3,"return_delay":0.}); projection.seed()
    assert projection.calendars[4]==[]  # R3 excludes destination goal service; berth still reserved.
    assert projection.occupancy(4)==1


def test_stationary_loaded_service_start_must_precede_every_capture():
    c,j,t,r,args=fixture(phase="first_reuse_route")
    t["L"]["service_ready_at"] = args["now"]+.099
    assert model.assemble_later(c,j,t,r,**args)["status"]=="unknown"


def test_entry_equal_earliest_capture_is_conditional_but_equal_exit_is_unknown():
    c,j,t,r,args=fixture(); entry=args["entry_receipts"][0]
    entry["entered_at"]=args["collection_contract"]["physical_admissions_quiesced_from"]
    entry["derived_edge_exit_at"]=entry["entered_at"]+entry["static_edge_travel_seconds"]
    value=model.assemble_later(c,j,t,r,**args)
    assert value["status"]=="conditional_model_input" and not value["current_state_certified"]


def test_same_four_action_budget_retains_unknowns_and_all_methods_use_same_facts():
    c,j,t,r,args=fixture(); b=model.assemble_later(c,j,t,r,**args)
    results=[model.propose(b,method=m,evaluation_budget=1) for m in model.METHODS]
    for result in results:
        assert result["evaluations"]==1 and result["candidate_denominator"]==4
        assert len(result["rows"])==4 and sum(row["evaluation_status"]=="unknown_unexecuted" for row in result["rows"])==3
        assert not result["native_protection_certified"] and not result["online_information_delivered"]
    assert len({result["capture_pair_sha256"] for result in results})==1


def stationary_fixture(mode="loading",node=1):
    c,j,t,r,args=fixture();e=t["E"]
    e.update(node=node,edge_from=-1,edge_to=-1,committed_prefix=[node],mode=mode,service_ready_known=True)
    if mode=="loading":
        e.update(service_ready_at=9.5,load_complete_at=9.5,ready_kind="observed_load_completion",available_at=9.5)
        j["receiver"].update(status="loading",loaded_at=-1.)
    else: e.update(service_ready_at=args["now"]+.08,ready_kind="committed_local_service_end")
    args["entry_receipts"]=[]
    owners={row["node"]:row["resource_owner"] for row in c["node_contracts"]}
    for n,row in r.items():
        row.update(occupancy=sum(x["node"]==n for x in t.values()),actual_available=sum(x["node"]==n and x["mode"]=="empty"
            and x["available_at"]<=args["now"] for x in t.values()),unrepresented_occupancy=0)
    for record in args["source_records"]:
        owner=record["owner"];record["unrepresented_occupancy"]=0
        record["tray_ids"]=[k for k,x in t.items() if owners[x["node"]]==owner]
        record["job_ids"]=sorted({x["business_bag_id"] for x in t.values() if owners[x["node"]]==owner and x["business_bag_id"]}
            |{k for k,x in j.items() if x["status"]=="waiting_for_tray" and owners[x["origin"]]==owner})
    return c,j,t,r,args


@pytest.mark.parametrize("mode,node",[("loading",2),("loaded",1)])
def test_moving_extension_does_not_relax_unsupported_stationary_receiver_with_valid_coverage(mode,node):
    c,j,t,r,args=stationary_fixture(mode,node)
    value=model.assemble_later(c,j,t,r,**args)
    assert value["status"]=="unknown" and "unsupported_receiver_state" in value["reasons"]


def test_supported_stationary_receiver_domain_remains_conditional():
    c,j,t,r,args=stationary_fixture()
    assert model.assemble_later(c,j,t,r,**args)["status"]=="conditional_model_input"


def test_naive_inverse_can_hide_one_ulp_later_native_start():
    finish,duration,floor=.2,.1,.1
    actual=math.nextafter(floor,math.inf)
    assert finish-duration==floor and actual>floor and actual+duration==finish
    assert model.latest_possible_start(finish,duration)>=actual>floor


@pytest.mark.parametrize("phase",["loading","loaded"])
def test_rounded_start_at_capture_boundary_remains_unknown_without_direct_start(phase):
    if phase=="loading":
        c,j,t,r,args=stationary_fixture();tray=t["E"];duration=j["receiver"]["load_seconds"]
    else:
        c,j,t,r,args=fixture(phase="first_reuse_route");tray=t["L"];duration=.1
    floor=args["collection_contract"]["physical_admissions_quiesced_from"]
    tray["service_ready_at"]=floor+duration
    if phase=="loading": tray["available_at"]=tray["load_complete_at"]=tray["service_ready_at"]
    assert model.latest_possible_start(tray["service_ready_at"],duration)>floor
    value=model.assemble_later(c,j,t,r,**args)
    assert value["status"]=="unknown"


def add_action(args, kind="route", status="updated", delivered_at=None):
    record=next(r for r in args["source_records"] if r["owner"]=="B")
    floor=args["collection_contract"]["physical_admissions_quiesced_from"]
    row={"request_id":"old-B-action","source_owner":"B","kind":kind,
        "last_delivered_ack":{"sequence":1,"status":status,"delivered_at":floor-.1 if delivered_at is None else delivered_at}}
    record["submitted_physical_actions"]=[row];record["submitted_physical_request_ids"]=[row["request_id"]]
    return record,row


@pytest.mark.parametrize("kind,status",[("route","updated"),("transfer","received"),("cancel_transfer","cancelled")])
def test_previously_delivered_terminal_actions_remain_conditional(kind,status):
    c,j,t,r,args=fixture(); record,row=add_action(args,kind,status)
    value=model.assemble_later(c,j,t,r,**args)
    assert value["status"]=="conditional_model_input",value
    assert next(s for s in value["source_records"] if s["owner"]=="B")["submitted_physical_actions"]==[row]


@pytest.mark.parametrize("defect",["inside_union","same_epoch","missing_ack_time","missing_action_set",
    "missing_coverage_set","missing_action_row","omitted_action_identity","unresolved","bool_ack_time"])
def test_complete_actions_must_finish_delivery_strictly_before_entire_capture_union(defect):
    c,j,t,r,args=fixture();record,row=add_action(args);floor=args["collection_contract"]["physical_admissions_quiesced_from"]
    if defect=="inside_union":row["last_delivered_ack"]["delivered_at"]=floor+.0005
    elif defect=="same_epoch":row["last_delivered_ack"]["delivered_at"]=floor
    elif defect=="missing_ack_time":del row["last_delivered_ack"]["delivered_at"]
    elif defect=="missing_action_set":del record["submitted_physical_actions"]
    elif defect=="missing_coverage_set":del record["submitted_physical_request_ids"]
    elif defect=="missing_action_row":record["submitted_physical_actions"]=[]
    elif defect=="omitted_action_identity":record["submitted_physical_request_ids"]=[]
    elif defect=="unresolved":row["last_delivered_ack"]["status"]="pending_execution"
    else:row["last_delivered_ack"]["delivered_at"]=True
    value=model.assemble_later(c,j,t,r,**args)
    assert value["status"]=="unknown",(defect,value)
    assert model.propose(value)["selected_action"] is None
