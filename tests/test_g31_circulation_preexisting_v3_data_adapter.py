"""Native-shaped v3 fixtures are explicitly supplied data, never native facts."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import preexisting_v3_data_adapter as adapter
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as v3
from scripts.experiments.g31_ics_circulation import public_preexisting_v3_model as model
from test_g31_circulation_public_preexisting_v3_model import fixture


def pair(owner="A", edge=(1,3), phase="first_return"):
    c,j,t,r,args=fixture(edge,phase)
    args["now"] += .05 if phase=="first_return" else .03
    now=args["now"]
    for index,record in enumerate(args["source_records"]):
        record.update(captured_at=now-.04+index*.005,delivered_at=now-.03+index*.005,valid_until=now+.1)
    floor=min(s["captured_at"] for s in args["source_records"])
    args["collection_contract"].update(physical_admissions_quiesced_from=floor,through=now)
    for job in j.values(): job["protected_service"]=True
    for tray in t.values(): tray.setdefault("load_complete_at",-1.)
    owners={n["node"]:n["resource_owner"] for n in c["node_contracts"]}
    envelopes={}
    for record in args["source_records"]:
        source=record["owner"]; capture=record["captured_at"]; peer="B" if source=="A" else "A"
        local={"schema":"g31.planning_capture.v1","message_id":"supplied-v3-"+source,"source_owner":source,
            "target_owner":peer,"publication_sequence":1,"captured_at":capture,"valid_until":now+.1,
            "static_contract_sha256":"a"*64,"semantics":copy.deepcopy(c["native_semantics"]),
            "jobs":[copy.deepcopy(j[key]) for key in record["job_ids"]],
            "trays":[copy.deepcopy(t[key]) for key in record["tray_ids"]],
            "nodes":[copy.deepcopy(r[node]) for node in record["node_ids"]],"known_faults":[],
            "coverage":{"scope":"source_waiting_or_locally_carried_released_jobs_and_local_trays",
                "complete_for_declared_local_scope":True,"local_node_ids":record["node_ids"],"tray_ids":record["tray_ids"],
                "business_bag_ids":record["job_ids"],"unrepresented_occupancy":record["unrepresented_occupancy"],"future_arrivals_included":False}}
        terminals=[row for row in args["terminal_receipts"] if row["source_owner"]==source]
        terminals.sort(key=lambda row:row["completed_at"])
        receipts=[{"receipt_id":f"completion:1:{source}:{index}","source_local_sequence":index,"source_owner":source,
            "event":"UNLOAD_COMPLETE","status":"completed","business_bag_id":row["business_bag_id"],
            "destination":j[row["business_bag_id"]]["destination"],"tray_id":"P" if row["business_bag_id"]=="blocker" else "L",
            "completed_at":row["completed_at"]} for index,row in enumerate(terminals,1)]
        extension={"schema":"g31.planning_extension.v2","source_owner":source,"captured_at":capture,"terminal_receipts":receipts,
            "submitted_physical_actions":[],"completion_coverage":{"scope":"all_source_owned_destination_unload_completions_through_capture",
                "complete_for_declared_scope":True,"through":capture,"source_owned_destination_nodes":record["node_ids"],
                "future_events_included":False,"completed_business_bag_ids":[row["business_bag_id"] for row in receipts]},
            "action_coverage":{"scope":"all_source_submitted_physical_operations_last_delivered_ack","through":capture,
                "complete_for_declared_scope":True,"includes_unsubmitted_python_plans":False,"uses_hidden_execution_truth":False,
                "submitted_request_ids":[],"unresolved_request_ids":[]}}
        entries=[row for row in args["entry_receipts"] if row["source_owner"]==source]
        body={"schema":v3.SCHEMA,"capture_v2":{"schema":"g31.planning_capture.v2","local_capture":local,"extension":extension},
            "extension":{"schema":v3.EXTENSION,"source_owner":source,"captured_at":capture,"source_observed_inflight":copy.deepcopy(entries),
                "coverage":{"scope":v3.SCOPE,"source_owned_inflight_tray_ids":[row["tray_id"] for row in entries],
                    "capture_cutoff":capture,"complete_for_declared_source_inflight":True,"unmatched_tray_ids":[],"uses_future_event_heap":False}}}
        envelopes[source]={"schema":"g31.planning_snapshot.v3","kind":"planning_snapshot_v3","digest_format":"g31.planning_capture_digest.v3",
            "capture":body,"payload_sha256":v3.capture_digest_v3(body),"delivered_at":capture+.01,"status":"conditional"}
    own=envelopes[owner];local=own["capture"]["capture_v2"]["local_capture"]
    view={**copy.deepcopy(c),"owner_id":owner,"now":now,"known_faults":[],"jobs":copy.deepcopy(local["jobs"]),"trays":copy.deepcopy(local["trays"])}
    for row in view["node_contracts"]:
        if row["resource_owner"]==owner: row.update({f:r[row["node"]][f] for f in ("occupancy","actual_available")})
    for entry in args["entry_receipts"]:
        if entry["source_owner"]==owner:
            next(row for row in view["trays"] if row["tray_id"]==entry["tray_id"])["edge_exit_at"]=entry["derived_edge_exit_at"]
    ack={"status":"delivered","executed_at":local["captured_at"],"completed_at":own["delivered_at"],
        "delivered_at":own["delivered_at"]+.02,"result_id":local["message_id"],"planning_snapshot_v3":own}
    retained={"owner":owner,"retained_at":.11,"static_contract_sha256":"a"*64,
        "contracts":{key:{f:row[f] for f in adapter.CONTRACT_FIELDS} for key,row in j.items()}}
    return view,ack,[envelopes["B" if owner=="A" else "A"]],{"retained":retained,"own_actions":[],"phase":phase,
        "collection_contract":args["collection_contract"]}


@pytest.mark.parametrize("owner",["A","B"])
@pytest.mark.parametrize("edge",[(1,3),(3,4)])
@pytest.mark.parametrize("phase",["first_return","first_reuse_route"])
def test_source_scoped_asynchronous_pair_validates_conditionally_only(owner,edge,phase):
    value=adapter.validate_later_pair(*pair(owner,edge,phase)[:3],**pair(owner,edge,phase)[3])
    assert value["status"]=="conditional_validated_later_v3_data", value
    assert not value["native_delivery_verified"] and not value["online_information_delivered"]
    bundle=value["bundle"]
    assert bundle["conditional_stability_only"] and not bundle["current_state_certified"]
    assert len({s["captured_at"] for s in bundle["source_records"]})==2
    assert set(model.predict(bundle,{"reuse_next":8,"return_delay":0.})["completion"])==model.JOBS


@pytest.mark.parametrize("defect",["digest","own_generation","own_exit","own_available","own_occupancy","own_job","self_ack_missing",
    "peer_missing","expired","missing_entry","unmatched","pending_action","missing_terminal","missing_coverage","wrong_message","bool_publication","wrong_scope"])
def test_model_never_fills_missing_delivery_coverage_or_current_own_change(defect):
    view,ack,received,kwargs=pair("A"); body=ack["planning_snapshot_v3"]["capture"]
    if defect=="digest": body["extension"]["source_observed_inflight"][0]["entered_at"]-=.001
    elif defect=="own_generation": view["trays"][0]["generation"]+=1
    elif defect=="own_exit": next(t for t in view["trays"] if t["tray_id"]=="E")["edge_exit_at"]+=.001
    elif defect=="own_available": view["trays"][0]["available_at"]+=.001
    elif defect=="own_occupancy": next(n for n in view["node_contracts"] if n["resource_owner"]=="A")["occupancy"]+=1
    elif defect=="own_job": view["jobs"][0]["loaded_at"]+=.001
    elif defect=="self_ack_missing": ack["status"]="pending"
    elif defect=="peer_missing": received=[]
    elif defect=="expired": received[0]["status"]="expired"
    elif defect=="missing_entry": body["extension"]["source_observed_inflight"]=[]
    elif defect=="unmatched": body["extension"]["coverage"].update(complete_for_declared_source_inflight=False,unmatched_tray_ids=["E"])
    elif defect=="pending_action":
        ext=body["capture_v2"]["extension"]
        ext["submitted_physical_actions"]=[{"request_id":"pending","kind":"route","source_owner":"A","last_delivered_ack":None}]
        ext["action_coverage"].update(submitted_request_ids=["pending"],unresolved_request_ids=["pending"]);kwargs["own_actions"]=[("pending","route")]
    elif defect=="missing_terminal":
        ext=body["capture_v2"]["extension"];ext["terminal_receipts"]=[];ext["completion_coverage"]["completed_business_bag_ids"]=[]
    elif defect=="missing_coverage": body["capture_v2"]["local_capture"]["coverage"]["complete_for_declared_local_scope"]=False
    elif defect=="wrong_message": ack["result_id"]="different"
    elif defect=="bool_publication": body["capture_v2"]["local_capture"]["publication_sequence"]=True
    elif defect=="wrong_scope": body["capture_v2"]["local_capture"]["coverage"]["scope"]="all_remote_truth"
    if defect!="digest": ack["planning_snapshot_v3"]["payload_sha256"]=v3.capture_digest_v3(body)
    value=adapter.validate_later_pair(view,ack,received,**kwargs)
    assert value["status"]=="unknown", (defect,value)
    assert not value["native_delivery_verified"] and not value["native_protection_certified"]


def test_both_owners_obtain_same_conditional_predictions_without_reading_peer_view():
    results=[]
    for owner in ("A","B"):
        view,ack,received,kwargs=pair(owner)
        info=adapter.validate_later_pair(view,ack,received,**kwargs)
        results.append([model.propose(info["bundle"],method=method) for method in model.METHODS])
    assert [r["selected_action"] for r in results[0]]==[r["selected_action"] for r in results[1]]
    assert [r["selected_prediction"]["completion"] for r in results[0]]==[r["selected_prediction"]["completion"] for r in results[1]]


@pytest.mark.parametrize("position",["before","same_epoch","inside_union","missing_time","omitted_action"])
def test_peer_terminal_route_ack_is_retained_and_bounded_by_earliest_capture(position):
    view,ack,inbox,kwargs=pair("A",phase="first_reuse_route")
    floor=kwargs["collection_contract"]["physical_admissions_quiesced_from"]
    body=inbox[0]["capture"];extension=body["capture_v2"]["extension"]
    row={"request_id":"live:1:B:route-prior","source_owner":"B","kind":"route",
        "last_delivered_ack":{"sequence":1,"status":"updated","delivered_at":floor-.1}}
    if position=="same_epoch":row["last_delivered_ack"]["delivered_at"]=floor
    elif position=="inside_union":row["last_delivered_ack"]["delivered_at"]=floor+.001
    elif position=="missing_time":del row["last_delivered_ack"]["delivered_at"]
    extension["submitted_physical_actions"]=[] if position=="omitted_action" else [row]
    extension["action_coverage"]["submitted_request_ids"]=[row["request_id"]]
    if position!="missing_time":inbox[0]["payload_sha256"]=v3.capture_digest_v3(body)
    else:
        # A missing typed field cannot even be re-encoded as a genuine native
        # digest; the adapter must reject it before any model admission.
        inbox[0]["payload_sha256"]="0"*64
    value=adapter.validate_later_pair(view,ack,inbox,**kwargs)
    if position=="before":
        assert value["status"]=="conditional_validated_later_v3_data",value
        source=next(s for s in value["bundle"]["source_records"] if s["owner"]=="B")
        assert source["submitted_physical_actions"]==[row]
    else:assert value["status"]=="unknown",(position,value)
