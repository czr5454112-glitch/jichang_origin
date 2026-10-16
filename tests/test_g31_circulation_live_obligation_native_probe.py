"""Pure supplied-fact guards, not simulated or delivered native snapshots."""
import copy
import math
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_native_guard as guard
from scripts.experiments.g31_ics_circulation import research_live_obligation_native_probe as runner


def supplied(phase="first_reuse_route", p_moving=False):
    data=guard.public_input();jobs,trays,_=guard.construction.initial_facts(data)
    now=9.69 if p_moving else 8.69 if phase=="first_reuse_route" else 6.34
    floor=now-.03;owners={n["node"]:n["resource_owner"] for n in data["node_contracts"]}
    jobs["loaded"].update(status="completed",loaded_at=.1,storage_entered_at=5.4,storage_released_at=5.4)
    jobs["blocker"].update(status="storage",loaded_at=3.,storage_entered_at=4.2,storage_released_at=-1.)
    trays["P"].update(node=9,mode="storage",committed_prefix=[1,9],service_ready_at=8.95,
        load_complete_at=-1.,ready_kind="observed_storage_release_bound")
    trays["L"].update(node=6,mode="empty",business_bag_id="",available_at=6.3,
        service_ready_at=6.3,load_complete_at=-1.,ready_kind="empty_available_at",committed_prefix=[4,6])
    jobs["receiver"].update(status="loading")
    trays["E"].update(node=1,mode="loading",business_bag_id="receiver",generation=1,
        available_at=6.501,service_ready_at=6.501,load_complete_at=6.501,ready_kind="observed_load_completion",committed_prefix=[5,1])
    entries=[]
    if phase=="first_reuse_route":
        jobs["reuse1"].update(status="in_transit",loaded_at=now-.04)
        trays["L"].update(node=7,mode="loaded",business_bag_id="reuse1",service_ready_at=now+.06,
            ready_kind="committed_local_service_end",committed_prefix=[7],generation=5,traversal_id=5)
        jobs["receiver"].update(status="in_transit",loaded_at=6.501 if not p_moving else 7.601)
        trays["E"].update(node=3,mode="loaded",edge_from=3,edge_to=4,committed_prefix=[1,3],traversal_id=2)
        exit_at=9.801 if p_moving else 8.701
        entries.append(dict(source_owner=owners[3],receipt_event="EDGE_ENTER",entered_at=exit_at-1.,derived_edge_exit_at=exit_at,
            static_edge_travel_seconds=1.,**{f:trays["E"][f] for f in ("tray_id","business_bag_id","generation","traversal_id","edge_from","edge_to")}))
    if p_moving:
        jobs["blocker"].update(status="in_transit",storage_released_at=8.95)
        trays["P"].update(mode="loaded",edge_from=9,edge_to=3,committed_prefix=[9],traversal_id=2)
        entries.append(dict(source_owner=owners[9],receipt_event="EDGE_ENTER",entered_at=9.05,derived_edge_exit_at=10.05,
            static_edge_travel_seconds=1.,**{f:trays["P"][f] for f in ("tray_id","business_bag_id","generation","traversal_id","edge_from","edge_to")}))
    resources={}
    for node in owners:
        occupants=[t for t in trays.values() if (t["edge_to"] if t["edge_to"]>=0 else t["node"])==node]
        resources[node]={"node":node,"occupancy":len(occupants),"actual_available":sum(t["mode"]=="empty" and t["node"]==node and t["edge_to"]<0 for t in trays.values()),
            "unrepresented_occupancy":sum(owners[t["node"]]!=owners[node] for t in occupants)}
    records=[]
    for owner in ("A","B"):
        action={"source_owner":owner,"request_id":"test:"+owner,"kind":"transfer","last_delivered_ack":{"sequence":1,"status":"received","delivered_at":floor-.05}}
        records.append({"owner":owner,"captured_at":floor if owner=="B" else now-.01,"known_faults":[],"unresolved_tray_request_ids":[],
            "node_ids":[n for n,o in owners.items() if o==owner],"unrepresented_occupancy":sum(r["unrepresented_occupancy"] for n,r in resources.items() if owners[n]==owner),
            "submitted_physical_request_ids":[action["request_id"]],"submitted_physical_actions":[action]})
    return dict(contract=guard.supported_contract(later=True),jobs=jobs,trays=trays,resources=resources,now=now,phase=phase,
        source_records=records,terminal_receipts=[{"business_bag_id":"loaded","completed_at":6.2}],owner_pending_tray_requests=[],entry_receipts=entries,
        collection_contract={"schema":"g31.conditional_collection_quiescence.v1","physical_admissions_quiesced_from":floor,"through":now,"future_python_actions_certified_by_native":False})


@pytest.mark.parametrize("phase,moving",[("first_return",False),("first_reuse_route",False),("first_reuse_route",True)])
def test_explicit_supported_storage_or_observed_entry(phase,moving):
    result=guard.later_bundle(**supplied(phase,moving))
    assert result["status"]=="conditional_model_input",result
    assert result["online_information_delivered"] is False
    assert result["native_protection_certified"] is False


@pytest.mark.parametrize("change",[
    "pending","ack_equal","ack_after","missing_ack_time","wrong_owner","missing_action","future_completion","missing_prefix",
    "missing_entry","unobserved_entry","entry_after_floor","exit_equal_now","changed_traversal","changed_occupancy",
    "bool_occupancy","unrepresented","P_release_equal_now","P_wrong_node","E_wrong_job","L_service_equal_now","future_population",
    "changed_static","changed_job","missing_resource","future_python_certainty"])
def test_fails_closed(change):
    v=supplied();floor=v["collection_contract"]["physical_admissions_quiesced_from"]
    if change=="pending":v["owner_pending_tray_requests"]=["x"]
    elif change.startswith("ack_"):v["source_records"][0]["submitted_physical_actions"][0]["last_delivered_ack"]["delivered_at"]=floor if change=="ack_equal" else floor+.001
    elif change=="missing_ack_time":del v["source_records"][0]["submitted_physical_actions"][0]["last_delivered_ack"]["delivered_at"]
    elif change=="wrong_owner":v["source_records"][0]["submitted_physical_actions"][0]["source_owner"]="B"
    elif change=="missing_action":v["source_records"][0]["submitted_physical_actions"]=[]
    elif change=="future_completion":v["terminal_receipts"][0]["completed_at"]=floor+.001
    elif change=="missing_prefix":v["terminal_receipts"]=[]
    elif change=="missing_entry":v["entry_receipts"]=[]
    elif change=="unobserved_entry":v["entry_receipts"][0]["receipt_event"]="RESERVATION"
    elif change=="entry_after_floor":v["entry_receipts"][0]["entered_at"]=floor+.001
    elif change=="exit_equal_now":v["entry_receipts"][0]["derived_edge_exit_at"]=v["now"]
    elif change=="changed_traversal":v["trays"]["E"]["traversal_id"]+=1
    elif change=="changed_occupancy":v["resources"][4]["occupancy"]+=1
    elif change=="bool_occupancy":v["resources"][4]["occupancy"]=True
    elif change=="unrepresented":v["resources"][4]["unrepresented_occupancy"]=0
    elif change=="P_release_equal_now":v["trays"]["P"]["service_ready_at"]=v["now"]
    elif change=="P_wrong_node":v["trays"]["P"]["node"]=1
    elif change=="E_wrong_job":v["trays"]["E"]["business_bag_id"]="blocker"
    elif change=="L_service_equal_now":v["trays"]["L"]["service_ready_at"]=v["now"]
    elif change=="future_population":v["jobs"]["reuse2"]["arrival"]=v["now"]+1
    elif change=="changed_static":v["contract"]["node_records"][0][2]=.2
    elif change=="changed_job":v["jobs"]["blocker"]["destination"]=4
    elif change=="missing_resource":v["resources"].pop(10)
    elif change=="future_python_certainty":v["collection_contract"]["future_python_actions_certified_by_native"]=True
    assert guard.later_bundle(**v)["status"]=="unknown",change


def test_fixed_domain_three_not_a_full_reference():
    rows=runner.probe_rows()
    assert list(rows)==runner.ORDER and len(rows)==3
    assert [rows[k]["vector"] for k in rows]==[guard.construction.actions()[i] for i in (12,24,25)]
    assert all(row["vector"]["return_delay"]==0 for row in rows.values())
    assert runner.fixed_choice({"native_delivery_verified":True},rows[runner.ORDER[-1]]["vector"])["selected_action"] is None


def test_unfinished_not_protected_and_raw_default_no_claim():
    rows=runner.probe_rows()
    assert all(r["status"]=="unknown" and r["strict_protected"] is None for r in runner.comparisons(rows).values())
    assert rows[runner.ORDER[0]]["vector"]["initial_action"]=="native_default"


def test_initial_static_domain_and_facts():
    data=guard.public_input();jobs,trays,resources=guard.construction.initial_facts(data)
    owners={n["node"]:n["resource_owner"] for n in data["node_contracts"]}
    projected={owner:{"jobs":[j for j in jobs.values() if owners[j["origin"]]==owner],"trays":[t for t in trays.values() if owners[t["node"]]==owner],"resources":[r for n,r in resources.items() if owners[n]==owner]} for owner in ("A","B")}
    assert guard.initial_bundle(guard.supported_contract(),projected,.11)["status"]=="conditional_model_input"
    projected["B"]["trays"][0]["generation"]=True
    # Typed identity must not accept bool as generation 1 or 0.
    assert guard.initial_bundle(guard.supported_contract(),projected,.11)["status"]=="unknown"


def test_runtime_overlay_is_exact_and_public_contract_unchanged():
    runtime=runner.native_scene('mechanism')
    assert runtime['owner_notifications']=={'enabled':True}
    assert runner.validate_runtime_input(runtime)==guard.public_input()
    assert 'owner_notifications' not in guard.public_input()
    assert guard.canonical(guard.model.public_contract(runtime))==guard.canonical(guard.supported_contract())
    assert runtime['options']==guard.public_input()['options']


@pytest.mark.parametrize('change',['missing','false','int','extra_overlay','extra_top','capacity','service','fault','trace_limit'])
def test_runtime_overlay_does_not_widen_input_domain(change):
    runtime=runner.native_scene('mechanism')
    if change=='missing':runtime.pop('owner_notifications')
    elif change=='false':runtime['owner_notifications']['enabled']=False
    elif change=='int':runtime['owner_notifications']['enabled']=1
    elif change=='extra_overlay':runtime['owner_notifications']['extra']=1
    elif change=='extra_top':runtime['hidden_override']={}
    elif change=='capacity':runtime['node_contracts'][0]['capacity']+=1
    elif change=='service':runtime['node_records'][0][2]+=.001
    elif change=='fault':runtime['faults'].append({'at':1.})
    elif change=='trace_limit':runtime['options']['trace_limit']+=1
    with pytest.raises(ValueError):runner.validate_runtime_input(runtime)


def test_failed_session_prefix_is_captured_without_advance_or_result():
    class Session:
        physical_time=.11
        def offline_diagnostics(self):return {'now':self.physical_time,'actual':True}
        def result_at(self,*a):raise AssertionError('must not advance result')
        def advance_to(self,*a):raise AssertionError('must not advance')
    class Client:
        calls=[{'at':.11,'request':{'request_id':'actually-submitted'}}]
        rows={'actually-submitted':{'ack':None}}
        creations={};roots=[];ack_handling=[]
    progress={'specification':runner.probe_rows()[runner.ORDER[0]],'input':runner.native_scene('mechanism'),
              'session':Session(),'client':Client(),'initial_owners':{},'native_batches':[],'stage':'owner_notification_continuation'}
    raw=runner.capture_partial(progress,'actual exception')
    assert raw['physical_time']==raw['physical_time_after_diagnostics']==.11
    assert raw['offline_diagnostics']=={'now':.11,'actual':True}
    assert 'result' not in raw and raw['capture_errors']=={}
    assert raw['outbox']==Client.rows and raw['calls']==Client.calls
    assert runner.verify_partial(raw)=='partial_endpoint_collection_not_complete; unknown'
    Client.calls[0]['at']=99
    assert raw['calls'][0]['at']==.11
    assert raw['summary']['strict_protected'] is None


def test_partial_getter_errors_preserve_other_actual_fields():
    class Session:
        physical_time=3.
        def offline_diagnostics(self):raise ValueError('diagnostic unavailable')
    raw=runner.capture_partial({'session':Session(),'initial_owners':{},'native_batches':[{'actual':1}]},'failure')
    assert raw['physical_time']==3 and raw['native_batches']==[{'actual':1}]
    assert 'diagnostic unavailable' in raw['capture_errors']['offline_diagnostics']
    assert raw['summary']['status']=='unknown_failed_partial'
    runner.verify_partial(raw)


def test_run_branch_exception_preserves_live_prefix(monkeypatch):
    def injected(*args,progress,**kwargs):
        progress.update(input=runner.native_scene('mechanism'),stage='test_actual_failure',initial_owners={})
        raise ValueError('injected before native; pure test')
    monkeypatch.setattr(runner,'_run_branch',injected)
    raw=runner.run_branch(None,runner.probe_rows()[runner.ORDER[0]],None,None,accepted_run=None,branch_key=runner.ORDER[0])
    assert raw['partial'] is True and raw['failure_stage']=='test_actual_failure'
    assert 'injected before native' in raw['exception'] and 'physical_time' not in raw
    runner.verify_partial(raw)


@pytest.mark.parametrize('change',['promotion','metric','advanced_clock','nan_clock'])
def test_partial_cannot_be_promoted_or_advanced(change):
    raw=runner.capture_partial({},'failure')
    if change=='promotion':raw['summary']['status']='assessed'
    elif change=='metric':raw['summary']['business_metrics']={'completed':5}
    elif change=='advanced_clock':raw.update(physical_time=.11,physical_time_after_diagnostics=.12)
    elif change=='nan_clock':raw['physical_time']=float('nan')
    with pytest.raises(ValueError):runner.verify_partial(raw)


def test_partial_mapping_only_never_clones_or_mints_native_capability():
    class UncopyableCapability:
        def __deepcopy__(self,memo):raise AssertionError('authority must not be cloned')
        def __reduce_ex__(self,protocol):raise AssertionError('authority must not be pickled')
    class Collected(dict):
        def __deepcopy__(self,memo):raise AssertionError('mapping subclass must not be deepcopied')
    information=Collected(status='conditional_native_delivered_later_v3_model_input',
                          native_delivery_verified=True,raw_endpoints={'view':{'owner':'B','now':8.69}})
    information._accepted=UncopyableCapability();information._session=UncopyableCapability()
    class Policy:
        decisions=[{'phase':'first_reuse_route','information':information,'native_request_id':'actual-route'}]
        exchanges=[];quiet_periods=[]
    raw=runner.capture_partial({'policies':{'B':Policy()}},'failure after real-shaped collection')
    assert raw['capture_errors']=={}
    saved=raw['decisions']['B'][0]['information']
    assert type(saved) is dict and saved==dict(information)
    assert not hasattr(saved,'_accepted') and not hasattr(saved,'_session')
    assert not runner.adapter.is_native_collected(saved)
    assert runner.fixed_choice(saved,runner.probe_rows()[runner.ORDER[2]]['vector'])['selected_action'] is None
    information['raw_endpoints']['view']['now']=99
    assert saved['raw_endpoints']['view']['now']==8.69


@pytest.mark.parametrize('payload',[float('nan'),object()])
def test_partial_unsupported_json_payload_is_explicit_capture_error(payload):
    raw=runner.capture_partial({'initial_owners':{'B':{'information':payload}},'native_batches':[{'actual':True}]},'failure')
    assert 'initial_owners' not in raw and 'initial_owners' in raw['capture_errors']
    assert raw['native_batches']==[{'actual':True}]
    assert raw['summary']['status']=='unknown_failed_partial'
