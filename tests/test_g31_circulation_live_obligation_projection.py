import copy
import json
import pytest
from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as p


@pytest.fixture(scope="module")
def prepared():
    data=p.inputs()["mechanism"];captures=p.declared_captures(data)
    bundle=p.assemble(data,captures)
    assert bundle["status"]=="conditional_model_input"
    return data,captures,bundle


def engine(prepared):
    return p.Projection(prepared[2],p.actions()[0])


def test_three_cases_same_32_and_no_authority(prepared):
    assert len(p.inputs())==3 and len(p.actions())==32
    assert len({p.action_key(a) for a in p.actions()})==32
    assert not prepared[2]["online_information_delivered"]
    assert p.revalidate(prepared[2])["status"]=="conditional_model_input"


@pytest.mark.parametrize("mutation",["expired","future_capture","future_delivery","pending","foreign_owner",
    "missing_job","duplicate_tray","unrepresented_occupancy","changed_ready","changed_status","changed_completed_prefix"])
def test_source_and_lifecycle_negative(prepared,mutation):
    data,captures,_=copy.deepcopy(prepared);a=next(c for c in captures if c["owner"]=="A")
    if mutation=="expired":a["expires_at"]=p.START
    elif mutation=="future_capture":a["captured_at"]=p.START+.01
    elif mutation=="future_delivery":a["declared_delivered_at"]=p.START+.01
    elif mutation=="pending":a["pending_action_ids"]=["route-pending"]
    elif mutation=="foreign_owner":a["owner"]="B"
    elif mutation=="missing_job":a["jobs"].pop();a["coverage"]["jobs"].pop()
    elif mutation=="duplicate_tray":a["trays"].append(copy.deepcopy(a["trays"][0]));a["coverage"]["trays"].append(a["trays"][0]["tray_id"])
    elif mutation=="unrepresented_occupancy":a["resources"][0]["occupancy"]=999
    elif mutation=="changed_ready":next(t for t in a["trays"] if t["tray_id"]=="P")["service_ready_at"]=2.
    elif mutation=="changed_status":next(j for j in a["jobs"] if j["business_bag_id"]=="blocker")["status"]="completed"
    elif mutation=="changed_completed_prefix":next(t for t in a["trays"] if t["tray_id"]=="L")["committed_prefix"]=[0,2]
    assert p.assemble(data,captures)["status"].startswith("unknown")


@pytest.mark.parametrize("field,value",[("message_delay",1.),("transfer_expiry",.1),("period",.1)])
def test_protocol_mismatch_rejected(prepared,field,value):
    protocol=copy.deepcopy(p.PROTOCOL);protocol[field]=value
    assert p.assemble(prepared[0],prepared[1],protocol=protocol)["status"].startswith("unknown")


def test_current_actions_and_forged_bundle_revalidated(prepared):
    bundle=copy.deepcopy(prepared[2]);bundle["owner_pending_tray_requests"]=["new_action_after_capture"]
    assert p.revalidate(bundle)["status"].startswith("unknown")
    bundle=copy.deepcopy(prepared[2]);bundle["resources"][0]["occupancy"]=99
    assert p.revalidate(bundle)["status"].startswith("unknown")
    bundle=copy.deepcopy(prepared[2]);bundle["online_information_delivered"]=True
    assert p.revalidate(bundle)["online_information_delivered"] is False


def test_generic_storage_preserves_carrier_job_and_public_release(prepared):
    e=engine(prepared);t=e.trays["P"];t.update(node=9,mode="loaded",goal=9)
    e.time=4.2;e.complete_leg("P")
    assert t["mode"]=="storage" and t["job"]=="blocker" and e.completed=={}
    assert len(e.events)==2  # storage receipt owner notification plus actual public release
    release=next(row for row in e.events if row[3]=="storage_release")
    assert release[0]==8.95
    e.time=release[0];t["mode"]="loaded"
    e.begin_leg("P",e.jobs["loaded"]["destination"])
    assert t["goal"]==10 and t["ready"]==8.95+.1 and "blocker" in e.storage_passed


def test_new_load_cannot_skip_mandatory_storage(prepared):
    e=engine(prepared);e.time=3.;e.trays["P"]["mode"]="loaded"
    e.begin_leg("P",10)
    assert e.trays["P"]["goal"]==9


def test_default_waits_best_ranked_instead_of_allowed_alternative(prepared):
    e=engine(prepared);e.time=8.;e.trays["L"].update(node=7,job="reuse1",mode="loaded",goal=6)
    e.trays["P"].update(node=3,mode="storage",goal=10)
    rows=e.candidate_rows("L")
    assert rows[0]["next"]==3 and rows[0]["reason"]=="receiving_full"
    assert next(r for r in rows if r["next"]==8)["allowed"]
    assert e.choose_next("L")==3


def test_resource_reservation_counts_before_arrival_and_deduplicates_lease(prepared):
    e=engine(prepared);t=e.trays["P"]
    t.update(node=9,edge_from=9,edge_to=3,lease=3)
    assert e.occupancy(3)==1 and e.occupancy(9)==0


def test_absolute_return_window_and_immediate_have_same_native_wire(prepared):
    e=engine(prepared);e.time=6.34;e.returns=1;e.trays["L"].update(node=6,mode="empty",job=None)
    e.action["return_delay"]=.5;e.request("L",7,e.time+.5)
    assert e.requests[-1]["earliest"]==7.84
    assert next(r[0] for r in e.events if r[3]=="request_delivery")==6.34+.01


def test_expired_or_nonlocal_action_fails_closed(prepared):
    e=engine(prepared);e.time=39.;e.returns=1;e.trays["L"].update(node=6,mode="empty",job=None)
    with pytest.raises(ValueError,match="expiry"):e.request("L",7,e.time)
    e.time=6.;e.trays["L"]["node"]=5
    with pytest.raises(ValueError,match="source"):e.request("L",7,e.time)
    e.trays["L"].update(node=7,mode="loaded",job="reuse1")
    with pytest.raises(ValueError,match="expired_route"):e.submit_preference("L",8,expiry=e.time)


def test_snapshot_or_output_mutation_does_not_change_fresh_state(prepared):
    a=engine(prepared);b=engine(prepared)
    a.trays["P"]["node"]=10;a.jobs["blocker"]["destination"]=0;a.calendars[3].append((0.,9.))
    assert b.trays["P"]["node"]==1 and b.jobs["blocker"]["destination"]==10 and b.calendars[3]==[]


def test_bad_new_action_unknown_without_running(prepared):
    action=p.actions()[0];action["return_delay"]=True
    assert p.predict(prepared[2],action)["status"]=="unknown_undeclared_action"


def test_json_roundtrip_and_resource_key_aliases(prepared):
    value=json.loads(json.dumps(prepared[2]))
    assert p.revalidate(value)["status"]=="conditional_model_input"
    value["resources"][0]=copy.deepcopy(value["resources"]["0"])
    assert p.revalidate(value)["status"]=="unknown_duplicate_resource_key"
    value=json.loads(json.dumps(prepared[2]));value["resources"]["00"]=value["resources"].pop("0")
    assert p.revalidate(value)["status"]=="unknown_invalid_resource_key"


@pytest.mark.parametrize("at,expected",[(39.,"conditional_prediction"),(39.001,"unknown_projection_empty_departure_expiry"),(True,"unknown_projection_empty_departure_expiry")])
def test_wrapper_rejects_post_grant_departure_expiry_without_erasing_events(prepared,monkeypatch,at,expected):
    class FakeProjection:
        def __init__(self,*args):self.operation_guards=[];self.requests=[]
        def run(self):return {"status":"conditional_prediction","completion":{j:20. for j in p.JOBS},
            "completion_sum":100.,"limits":[],"physical_projection":[{"event":"EDGE_ENTER","tray":"E","job":None,"source":5,"target":1,"at":at}]}
    monkeypatch.setattr(p,"Projection",FakeProjection)
    result=p.predict(prepared[2],p.actions()[0])
    assert result["status"]==expected and len(result["physical_projection"])==1
    assert result["completion"]["blocker"]==20. and result["native_protection_certified"] is False
