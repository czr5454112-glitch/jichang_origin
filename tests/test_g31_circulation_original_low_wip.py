from copy import deepcopy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import research_original_low_wip as m


def contract():
    nodes = [[0,1,.1,0,0,[1]], [1,4,.1,0,0,[2]], [2,1,.1,0,0,[3]], [3,4,.1,0,0,[0]], [4,2,.1,0,0,[]]]
    return {"node_records":nodes,"edge_records":[[0,1,1.,1.],[1,2,1.,1.],[2,3,1.,1.],[3,0,1.,1.]],
        "node_contracts":[{"node":i,"resource_owner":"A" if i in (0,1) else "B","zone":"x" if i in (0,1) else "y",
            "capacity":4,"export_min_stock":0,"allow_export":True,"allow_receive":True} for i in range(5)],
        "edge_contracts":[{"from":u,"to":v,"capacity":1} for u,v in [(0,1),(1,2),(2,3),(3,0)]]}


def tray(identity="token",node=1):
    return {"tray_id":identity,"node":node,"mode":"empty","business_bag_id":"","edge_to":-1,"reception_node":-1,"available_at":0.}


def job(identity,arrival,dest=0):
    return {"business_bag_id":identity,"arrival":arrival,"origin":2,"destination":dest,"storage_node":-1,"status":"waiting_for_tray"}


def info(jobs):
    view={**contract(),"owner_id":"A","now":20.,"trays":[tray()]}
    env={"capture":{"local_capture":{"source_owner":"B","captured_at":10.,"jobs":jobs}}}
    return env,view


def test_parking_uses_public_roles_and_opposite_zone_distinct_targets():
    data=contract();plan=m.parking_plan(data,[{"tray_id":"a","node":0},{"tray_id":"b","node":2}])
    assert [(r["source"],r["destination"]) for r in plan["parking"]]==[(0,3),(2,1)]
    assert all(r["stationary_spare_berths"]==3 for r in plan["parking"])
    assert plan["token_tray_id"]=="b" and plan["token_owner"]=="A"


def test_original_static_matching_keeps_whole_inventory_and_input():
    path=m.OUT/"full_stream_native024_001/full1x/input.json.gz"
    data=m.gzread(path); before=deepcopy(data)
    plan=m.parking_plan(data,data["trays"])
    assert len(plan["parking"])==22 and len({r["destination"] for r in plan["parking"]})==22
    assert plan["serial_free_flow_seconds"]==pytest.approx(6753.739)
    assert plan["serial_free_flow_seconds"]<min(j["arrival"] for j in data["jobs"])
    assert data==before


def test_no_parking_is_reported_instead_of_same_zone_fallback():
    data=contract()
    for row in data["node_contracts"]:row["zone"]="same"
    with pytest.raises(ValueError,match="no_distinct_opposite"):m.parking_plan(data,[{"tray_id":"a","node":0}])


def test_minimum_stock_and_spare_capacity_are_not_relaxed():
    data=contract();data["node_contracts"][0]["export_min_stock"]=1
    with pytest.raises(ValueError,match="initial_export"):m.parking_plan(data,[{"tray_id":"a","node":0}])
    data=contract();data["node_contracts"][3]["capacity"]=2
    with pytest.raises(ValueError,match="no_distinct_opposite"):m.parking_plan(data,[{"tray_id":"a","node":0}])


def test_zero_capacity_is_not_traversable():
    data=contract();data["edge_contracts"][1]["capacity"]=0
    assert 3 not in m.paths_from(m.public_graph(data),0)


def test_startup_inventory_must_be_actual_local_empty():
    plan=m.parking_plan(contract(),[{"tray_id":"a","node":0},{"tray_id":"b","node":2}])
    view={"owner_id":"A","now":0.,"trays":[tray("a",0)]}
    m.validate_initial_local(view,plan,"A")
    view["trays"][0]["business_bag_id"]="already_loaded"
    with pytest.raises(ValueError,match="empty_required"):m.validate_initial_local(view,plan,"A")


def test_unreachable_head_does_not_allow_reachable_follower():
    env,view=info([job("bad",1,4),job("good",2,0)])
    assert m.eligible_head(env,view,"token") is None


def test_head_uses_arrival_then_identity_not_capture_order():
    env,view=info([job("later",2),job("earlier",1)])
    assert m.eligible_head(env,view,"token")["job"]["business_bag_id"]=="earlier"


def test_missing_delivered_peer_or_token_stays_unknown():
    env,view=info([job("j",1)])
    assert m.eligible_head(None,view,"token") is None
    assert m.eligible_head(env,view,"different") is None


def test_same_zone_supply_has_no_two_hop_invention():
    env,view=info([job("j",1)])
    view["node_contracts"][2]["zone"]="x"
    assert m.eligible_head(env,view,"token") is None


def test_future_head_is_rejected():
    env,view=info([job("j",11)])
    with pytest.raises(ValueError,match="future_head"):m.eligible_head(env,view,"token")


def test_peer_segment_requires_received_ack_and_own_actual_parked_tray():
    row={"request_id":"r","tray_id":"t","destination":1}
    env={"capture":{"local_capture":{"captured_at":5.},"extension":{"submitted_physical_actions":[
        {"request_id":"r","kind":"transfer","last_delivered_ack":{"status":"received","delivered_at":4.}}]}}}
    view={"now":6.,"trays":[tray("t",1)]}
    assert m.peer_finished(env,[row],view)
    view["trays"][0]["mode"]="empty_transit"
    assert not m.peer_finished(env,[row],view)
    view["trays"][0]["mode"]="empty";env["capture"]["extension"]["submitted_physical_actions"][0]["last_delivered_ack"]["status"]="departed"
    assert not m.peer_finished(env,[row],view)


def message():
    local={"source_owner":"B","target_owner":"A","captured_at":1.,"valid_until":20.,"trays":[],"jobs":[],
        "nodes":[{"node":n} for n in (2,3,4)],
        "coverage":{"complete_for_declared_local_scope":True,"future_arrivals_included":False,"local_node_ids":[2,3,4],
            "unrepresented_occupancy":0,"tray_ids":[],"business_bag_ids":[]}}
    return {"schema":"g31.planning_snapshot.v2","kind":"planning_snapshot_v2","digest_format":"g31.planning_capture_digest.v2",
        "payload_sha256":"digest","status":"conditional","delivered_at":3.,"capture":{"schema":"g31.planning_capture.v2","local_capture":local,
        "extension":{"terminal_receipts":[],"completion_coverage":{"scope":"all_source_owned_destination_unload_completions_through_capture",
            "complete_for_declared_scope":True,"through":1.,"future_events_included":False,"source_owned_destination_nodes":[2,3,4],"completed_business_bag_ids":[]},
            "submitted_physical_actions":[],"action_coverage":{"scope":"all_source_submitted_physical_operations_last_delivered_ack",
            "complete_for_declared_scope":True,"through":1.,"uses_hidden_execution_truth":False,"includes_unsubmitted_python_plans":False,"submitted_request_ids":[],"unresolved_request_ids":[]}}}}


def test_expired_or_receiving_only_capture_waits(monkeypatch):
    monkeypatch.setattr(m,"capture_digest_v2",lambda _:"digest")
    env=message();nodes={r["node"]:r for r in contract()["node_contracts"]}
    assert m.delivered_peer([env],"A","B",5.,nodes)==env
    assert m.delivered_peer([env],"A","B",20.,nodes) is None
    env["capture"]["local_capture"]["coverage"]["unrepresented_occupancy"]=1
    assert m.delivered_peer([env],"A","B",5.,nodes) is None


@pytest.mark.parametrize("field,value,reason",[("payload_sha256","wrong","digest"),("delivered_at",9.,"causality"),("schema","v3","schema")])
def test_capture_tamper_rejected(monkeypatch,field,value,reason):
    monkeypatch.setattr(m,"capture_digest_v2",lambda _:"digest");env=message();env[field]=value
    with pytest.raises(ValueError,match=reason):m.delivered_peer([env],"A","B",5.,{r["node"]:r for r in contract()["node_contracts"]})


def test_source_closure_includes_absolute_eval_and_startup_src():
    paths={p.relative_to(m.ROOT).as_posix() for p in m.source_paths()}
    assert "scripts/eval/run_g4irsf28_service_potential.py" in paths
    # Native loader's actual cpp_backend import can be delayed until runtime;
    # it is therefore part of the mandatory pre-run static dependency archive.
    assert "src/czr005/cpp_backend.py" in paths


def final_fixture():
    physical={str(i):{"kind":"transfer","client_view":{"last_delivered_ack":{"status":"received"}}} for i in range(23)}
    raw={"status":"horizon_complete","physical_time":m.HORIZON,"physical_audit":{"status":"passed"},
        "owners":[{"index":22,"supply":{"choice":{"job":{"business_bag_id":"j"}}},"outbox":{"outbox":physical}}],
        "result":{"advance":{"horizon_complete":True},"trays":[{"tray_id":"token","mode":"empty","job":-1,"edge_to":-1}],
        "receipts":[{"event":event,"tray_id":"token","business_bag_id":"j","time":t}
            for t,event in enumerate(("LOAD_START","UNLOAD_COMPLETE","HOLD_COMPLETE"))]}}
    return raw,{"parking_plan":{"token_tray_id":"token"}}


def test_complete_empty_requires_real_selected_job_lifecycle_not_ack_alone():
    raw,plan=final_fixture();assert m.assess(raw,plan)["status"]=="observed_complete_and_empty"
    raw["result"]["receipts"].pop()
    assert m.assess(raw,plan)["status"]=="unknown_or_no_complete_witness"


@pytest.mark.parametrize("mutation",["missing_ack","censored","other_loaded","parking_missing","token_not_empty","failed_audit"])
def test_completion_fail_closed(mutation):
    raw,plan=final_fixture()
    if mutation=="missing_ack":raw["owners"][0]["outbox"]["outbox"]["0"]["client_view"]={}
    if mutation=="censored":raw["result"]["advance"]["horizon_complete"]=False
    if mutation=="other_loaded":raw["result"]["receipts"].insert(0,{"event":"LOAD_START","tray_id":"other","business_bag_id":"bad","time":0})
    if mutation=="parking_missing":raw["owners"][0]["index"]=21
    if mutation=="token_not_empty":raw["result"]["trays"][0]["mode"]="unloading"
    if mutation=="failed_audit":raw["physical_audit"]["status"]="failed"
    assert m.assess(raw,plan)["status"]=="unknown_or_no_complete_witness"


def test_tape_roundtrip_and_wrong_payload_fail_closed(tmp_path):
    class Fake:
        physical_time=0.
        def submit_protocol_transfer(self,payload):return {"status":"submitted","id":payload["request_id"]}
        def advance_to(self,target,max_events):
            self.physical_time=target;return {"status":"reached","horizon_complete":True}
    directory=tmp_path/"api";record=m.Tape(Fake(),directory)
    assert record.submit_protocol_transfer({"request_id":"r"})["status"]=="submitted"
    record.advance_to(2.,max_events=100000)
    replay=m.ReplayTape(directory);replay.submit_protocol_transfer({"request_id":"r"});replay.advance_to(2.,max_events=100000)
    assert replay.physical_time==2. and replay.index==2
    with pytest.raises(ValueError,match="payload"):m.ReplayTape(directory).submit_protocol_transfer({"request_id":"other"})


def test_tape_missing_or_reordered_manifest_cannot_be_replayed(tmp_path):
    directory=tmp_path/"api";directory.mkdir()
    m.gzwrite(directory/"000000.json.gz",{"ordinal":0})
    (directory/"manifest.jsonl").write_text("")
    with pytest.raises(ValueError,match="omitted_tape_file"):m.ReplayTape(directory)


def test_numeric_horizon_without_complete_native_timestamp_is_unknown(monkeypatch):
    class StubOwner:
        def __init__(self,*args):self.failure=None;self.client=type("Client",(),{"calls":[]})()
        def activate(self):pass
    class StubSession:
        physical_time=0.
        def advance_to(self,target,max_events):self.physical_time=target;return {"status":"budget_exhausted","horizon_complete":False}
    monkeypatch.setattr(m,"Owner",StubOwner)
    _,status,tick=m.run_policy(StubSession(),{"parking_plan":{"owners":["A","B"]}})
    assert status=="unknown_native_budget" and tick==0


def native_namespace_accepts(owner, request_id):
    # The compiled C++ checks a nonempty suffix after this exact byte-length
    # prefix (circulation_protocol_impl.hpp and protocol_commands_impl.hpp).
    prefix = b"live:" + str(len(owner.encode("utf-8"))).encode("ascii") + b":" + owner.encode("utf-8") + b":"
    value = request_id.encode("utf-8")
    return value.startswith(prefix) and len(value) > len(prefix)


@pytest.mark.parametrize("owner,expected",[("A","live:1:A:low-wip:park:t"),
    ("owner:system_domestic","live:21:owner:system_domestic:low-wip:park:t"),
    ("区:A","live:5:区:A:low-wip:park:t")])
def test_request_ids_use_native_utf8_owner_namespace(owner,expected):
    assert m.owner_request_id(owner,"park:t") == expected
    assert native_namespace_accepts(owner,expected)


@pytest.mark.parametrize("owner,request_id",[("A","low-wip:park:t"),("A","low-wip:snapshot:A:0"),
    ("A","low-wip:single-supply"),("A","live:1:B:low-wip:park:t"),
    ("区:A","live:3:区:A:low-wip:park:t"),("A","live:1:A:")])
def test_actual_old_namespace_and_byte_length_counterexamples_are_rejected(owner,request_id):
    assert not native_namespace_accepts(owner,request_id)


class NamespaceCheckingSession:
    def __init__(self, owner="A", now=0.):
        self.physical_time=now;self.owner=owner;self.submissions=[]
    def observe_protocol_control_policy_recent(self,owner,validity):
        return {**contract(),"owner_id":owner,"now":self.physical_time,
            "trays":[tray("a",0)] if self.physical_time==0. else [tray("b",1)]}
    def protocol_planning_snapshots_v2(self,owner):return []
    def submit_protocol_command(self,payload):
        self.submissions.append(deepcopy(payload))
        return {"status":"pending"} if native_namespace_accepts(payload["owner_id"],payload["request_id"]) else {
            "status":"rejected","reason":"owner_request_namespace_required"}
    submit_protocol_transfer=submit_protocol_command


def test_actual_owner_startup_submits_valid_snapshot_and_parking_ids():
    plan=m.parking_plan(contract(),[{"tray_id":"a","node":0},{"tray_id":"b","node":2}])
    session=NamespaceCheckingSession();owner=m.Owner(session,"A",plan);owner.activate()
    assert [r["request_id"] for r in session.submissions]==["live:1:A:low-wip:snapshot:0","live:1:A:low-wip:park:a"]
    assert all(r["submission_reply"]["status"]=="pending" for r in owner.client.state["outbox"].values())


def test_actual_owner_supply_and_peer_quiet_detection_share_the_owned_id(monkeypatch):
    plan=m.parking_plan(contract(),[{"tray_id":"a","node":0},{"tray_id":"b","node":2}])
    session=NamespaceCheckingSession(now=20.);owner=m.Owner(session,"A",plan);owner.index=len(owner.rows)
    envelope={"capture":{"extension":{"submitted_physical_actions":[]}}}
    monkeypatch.setattr(m,"delivered_peer",lambda *args:envelope)
    monkeypatch.setattr(m,"peer_finished",lambda *args:True)
    monkeypatch.setattr(m,"eligible_head",lambda *args:{"tray":tray("b",1),"job":job("j",1)})
    owner.activate()
    assert owner.supply["request_id"]=="live:1:A:low-wip:single-supply"
    assert session.submissions[-1]["request_id"]==owner.supply["request_id"]
    assert all(r["submission_reply"]["status"]=="pending" for r in owner.client.state["outbox"].values())
    receiver_session=NamespaceCheckingSession(owner="B",now=20.);receiver=m.Owner(receiver_session,"B",plan)
    receiver.index=len(receiver.rows)
    envelope["capture"]["extension"]["submitted_physical_actions"]=[{"request_id":owner.supply["request_id"]}]
    receiver.activate()
    assert receiver.quiet and receiver_session.submissions==[]


def prepared_attempt(tmp_path):
    plan={"schema":m.SCHEMA,"status":"prepared_native_unexecuted"}
    m.write(tmp_path/"preregistered_protocol.json",plan)
    m.write(tmp_path/"branch_ledger.json",{"single_candidate":{"status":"unknown_unexecuted"}})
    return plan


def test_parent_repeat_is_rejected_without_mutating_any_evidence(tmp_path):
    plan=prepared_attempt(tmp_path);m.claim_execution(tmp_path,plan)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError,match="execution_artifacts_already_exist"):m.claim_execution(tmp_path,plan)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


@pytest.mark.parametrize("artifact",["receipt.json","worker.log","api","heartbeat.json","raw_final.json.gz","error_prefix.json.gz"])
def test_existing_failed_or_partial_execution_cannot_be_overwritten(tmp_path,artifact):
    plan=prepared_attempt(tmp_path)
    if artifact=="api":(tmp_path/artifact).mkdir()
    else:(tmp_path/artifact).write_bytes(b"preserved evidence")
    with pytest.raises(ValueError,match="execution_artifacts_already_exist"):m.claim_execution(tmp_path,plan)
    assert not (tmp_path/"execution_claim.json").exists()


def test_attempted_ledger_without_other_files_still_cannot_restart(tmp_path):
    plan=prepared_attempt(tmp_path);m.write(tmp_path/"branch_ledger.json",{"single_candidate":{"status":"unknown_hard_timeout"}})
    with pytest.raises(ValueError,match="execution_already_attempted"):m.claim_execution(tmp_path,plan)
    assert not (tmp_path/"execution_claim.json").exists()


def test_worker_repeat_is_rejected_before_any_native_construction(tmp_path):
    plan=prepared_attempt(tmp_path);m.claim_execution(tmp_path,plan);m.claim_worker(tmp_path)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError,match="worker_already_claimed"):m.claim_worker(tmp_path)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


def actual_failed_membership():
    base=m.OUT/"original_low_wip_prepare_003/api"
    view_path=base/"000014.json.gz";message_path=base/"000015.json.gz"
    assert m.sha(view_path)=="563a7b7b87fede4c0a3cce9832b4c0fcaf4a740ef65de4bcc76e62b6612d1375"
    assert m.sha(message_path)=="3d003fbd42935cef49383a4d923bc5379030c9e4d555ad7c1e48e62f88afb315"
    view=m.gzread(view_path)["result"];messages=m.gzread(message_path)["result"]
    return messages,view


def test_actual_native003_unsorted_tray_order_is_accepted_without_modifying_raw():
    messages,view=actual_failed_membership();before=deepcopy(messages)
    local=messages[0]["capture"]["local_capture"]
    assert local["coverage"]["tray_ids"]!=sorted(local["coverage"]["tray_ids"])
    assert m.delivered_peer(messages,view["owner_id"],local["source_owner"],view["now"],
        {r["node"]:r for r in view["node_contracts"]})==messages[0]
    assert messages==before


def test_actual003_complete_saved_api_prefix_replays_past_old_membership_exception():
    directory=m.OUT/"original_low_wip_prepare_003"
    assert m.sha(directory/"preregistered_protocol.json")=="5f9331ddf14ff9af62243d5900a662af3e186b0c4307f1d6f852268e4d72ad81"
    assert m.sha(directory/"api/manifest.jsonl")=="42b1e7081592795cac3674f0262dd1017c8b285618b5767da52745f0c88f02f9"
    replay=m.ReplayTape(directory/"api")
    with pytest.raises(ValueError,match="missing_tape_call"):
        m.run_policy(replay,m.read(directory/"preregistered_protocol.json"))
    assert replay.index==len(replay.manifest)==16 and replay.physical_time==10.
    # The new policy needs the next real native advance; this is prefix
    # conformance only, never fabricated post-failure physical execution.


@pytest.mark.parametrize("defect",["sorted_coverage","reordered_body","duplicate_both","missing_coverage","blank_both"])
def test_actual_native003_coverage_tampering_is_not_reduced_to_set_equality(defect):
    messages,view=actual_failed_membership();env=messages[0];local=env["capture"]["local_capture"]
    ids=local["coverage"]["tray_ids"]
    if defect=="sorted_coverage":ids.sort()
    elif defect=="reordered_body":local["trays"].reverse()
    elif defect=="duplicate_both":local["trays"].append(deepcopy(local["trays"][0]));ids.append(ids[0])
    elif defect=="missing_coverage":ids.pop()
    else:local["trays"][0]["tray_id"]="";ids[0]=""
    env["payload_sha256"]=m.capture_digest_v2(env["capture"])
    with pytest.raises(ValueError,match="message_membership"):
        m.delivered_peer(messages,view["owner_id"],local["source_owner"],view["now"],{r["node"]:r for r in view["node_contracts"]})


@pytest.mark.parametrize("field",["tray_id","business_bag_id","request_id","receipt_id"])
def test_all_string_memberships_preserve_row_order_and_reject_nonunique_or_empty(field):
    rows=[{field:"z"},{field:"a"}]
    assert m.coverage_matches_rows(["z","a"],rows,field)
    assert not m.coverage_matches_rows(["a","z"],rows,field)
    assert not m.coverage_matches_rows(["z","z"],[{field:"z"},{field:"z"}],field)
    assert not m.coverage_matches_rows([""],[{field:""}],field)
    assert not m.coverage_matches_rows([True],[{field:True}],field)


def test_node_coverage_binds_body_order_then_full_owner_membership(monkeypatch):
    monkeypatch.setattr(m,"capture_digest_v2",lambda _:"digest");env=message();local=env["capture"]["local_capture"]
    local["nodes"].reverse();local["coverage"]["local_node_ids"]=[4,3,2]
    env["capture"]["extension"]["completion_coverage"]["source_owned_destination_nodes"]=[4,3,2]
    nodes={r["node"]:r for r in contract()["node_contracts"]}
    assert m.delivered_peer([env],"A","B",5.,nodes)==env
    local["coverage"]["local_node_ids"].sort()
    with pytest.raises(ValueError,match="message_coverage"):m.delivered_peer([env],"A","B",5.,nodes)


@pytest.mark.parametrize("defect",["missing_owned_node","duplicate_node","boolean_node"])
def test_node_body_and_coverage_cannot_jointly_omit_or_duplicate_authority(monkeypatch,defect):
    monkeypatch.setattr(m,"capture_digest_v2",lambda _:"digest");env=message();local=env["capture"]["local_capture"]
    if defect=="missing_owned_node":local["nodes"].pop();local["coverage"]["local_node_ids"].pop()
    elif defect=="duplicate_node":local["nodes"].append({"node":2});local["coverage"]["local_node_ids"].append(2)
    else:local["nodes"][0]["node"]=True;local["coverage"]["local_node_ids"][0]=True
    with pytest.raises(ValueError,match="message_coverage"):
        m.delivered_peer([env],"A","B",5.,{r["node"]:r for r in contract()["node_contracts"]})


def test_terminal_and_action_coverage_are_body_ordered_not_sorted(monkeypatch):
    monkeypatch.setattr(m,"capture_digest_v2",lambda _:"digest");env=message();ext=env["capture"]["extension"]
    ext["terminal_receipts"]=[{"receipt_id":"receipt:z","business_bag_id":"z","source_owner":"B","destination":2},
        {"receipt_id":"receipt:a","business_bag_id":"a","source_owner":"B","destination":3}]
    ext["completion_coverage"]["completed_business_bag_ids"]=["z","a"]
    ext["submitted_physical_actions"]=[{"request_id":"z","kind":"transfer","source_owner":"B","last_delivered_ack":None},
        {"request_id":"a","kind":"route","source_owner":"B","last_delivered_ack":{"status":"updated"}}]
    ext["action_coverage"]["submitted_request_ids"]=["z","a"];ext["action_coverage"]["unresolved_request_ids"]=["z"]
    nodes={r["node"]:r for r in contract()["node_contracts"]}
    assert m.delivered_peer([env],"A","B",5.,nodes)==env
    ext["completion_coverage"]["completed_business_bag_ids"].sort()
    with pytest.raises(ValueError,match="completion_coverage"):m.delivered_peer([env],"A","B",5.,nodes)
    ext["completion_coverage"]["completed_business_bag_ids"]=["z","a"]
    ext["action_coverage"]["submitted_request_ids"].sort()
    with pytest.raises(ValueError,match="action_coverage"):m.delivered_peer([env],"A","B",5.,nodes)
    ext["action_coverage"]["submitted_request_ids"]=["z","a"];ext["action_coverage"]["unresolved_request_ids"]=[]
    with pytest.raises(ValueError,match="action_coverage"):m.delivered_peer([env],"A","B",5.,nodes)


def test_atomic_writer_retries_transient_permission_error_without_skipping_output(tmp_path,monkeypatch):
    target=tmp_path/"heartbeat.json";target.write_text('{"tick":1}',encoding="utf-8")
    original=Path.replace;attempts=[];sleeps=[]
    def transient(source,destination):
        attempts.append((source,destination))
        assert json.loads(target.read_text(encoding="utf-8"))=={"tick":1}
        if len(attempts)<=2:raise PermissionError("injected transient Windows file lock")
        return original(source,destination)
    monkeypatch.setattr(Path,"replace",transient);monkeypatch.setattr(m.time,"sleep",sleeps.append)
    m.write(target,{"tick":2})
    assert len(attempts)==3 and sleeps==[.01,.02]
    assert m.read(target)=={"tick":2} and not target.with_suffix(".json.tmp").exists()


def test_atomic_writer_exhaustion_raises_and_retains_both_prior_output_and_new_temp(tmp_path,monkeypatch):
    target=tmp_path/"heartbeat.json";target.write_text('{"tick":1}',encoding="utf-8")
    attempts=[];sleeps=[];failure=PermissionError("injected persistent Windows file lock")
    def locked(source,destination):attempts.append((source,destination));raise failure
    monkeypatch.setattr(Path,"replace",locked);monkeypatch.setattr(m.time,"sleep",sleeps.append)
    with pytest.raises(PermissionError) as caught:m.write(target,{"tick":2})
    assert caught.value is failure and len(attempts)==7
    assert sleeps==list(m.REPLACE_RETRY_DELAYS) and sum(sleeps)==pytest.approx(.56)
    assert m.read(target)=={"tick":1} and m.read(target.with_suffix(".json.tmp"))=={"tick":2}


def test_atomic_writer_does_not_retry_other_io_errors(tmp_path,monkeypatch):
    calls=[];sleeps=[]
    def other_error(source,destination):calls.append(1);raise OSError("injected unrelated failure")
    monkeypatch.setattr(Path,"replace",other_error);monkeypatch.setattr(m.time,"sleep",sleeps.append)
    with pytest.raises(OSError,match="unrelated"):m.write(tmp_path/"heartbeat.json",{"tick":2})
    assert calls==[1] and sleeps==[]
