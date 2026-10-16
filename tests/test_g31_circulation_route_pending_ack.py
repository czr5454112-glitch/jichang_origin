"""No native session; exact finite-proof/ACK/closure guards."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import route_update_pending_ack as p
from scripts.experiments.g31_ics_circulation import replay_route_pending_ack as replay


def pending(ack=None,target=113,drained=True):
    session=SimpleNamespace(physical_time=9606.)
    u=p.PendingAckRouteUpdate(session,"domestic",clock=lambda:100)
    u.started_ns=1;u.eligibility_schedule={"fired_at":9603.5}
    local={"tray_id":"T","business_bag_id":p.JOB,"generation":0,"traversal_id":1,"committed_prefix":[112]}
    u.intent.decision={"request_id":"own","owner":"domestic","request":{"business_bag_id":p.JOB},
        "local_job":{"business_bag_id":p.JOB},"local_tray":deepcopy(local),"submission_reply":{"status":"updated"}}
    u.intent.edge={"owner":"domestic","from":112,"to":target,"observed_at":9606.,
        "local_tray":{**deepcopy(local),"traversal_id":2},"evidence":"matched_observed_entry_inflight"}
    u.intent.status="awaiting_delivered_ack_and_edge";u.intent.last_now=9606.;u.intent.observation_count=3
    u.intent.reservation={"observed_at":9606.};u.full_view_reads=3
    u.client=SimpleNamespace(state={"outbox":{"own":{"client_view":{"last_delivered_ack":ack}}}})
    u._pin_observed_hop()
    log=[]
    class Bridge:
        def refresh(self):log.append("refresh")
        def finish(self,root,response,**kwargs):
            log.append(("finish",root,deepcopy(response),kwargs))
            return {"status":"returned","output":"encoded","drain":{"physical_time":session.physical_time}} if drained else {"status":"mandatory_drain_incomplete"}
    u.bridge=Bridge()
    return u,log


def test_closure_tail_ast_is_exact():
    assert p.prove_unchanged_closure_tail()["retry_period_seconds"]==60.


@pytest.mark.parametrize("ack_status,target,expected",[("updated",113,"completed"),("updated",53,"terminal_failure"),
    ("rejected",113,"terminal_failure"),("expired",113,"terminal_failure"),("failed",113,"terminal_failure"),("cancelled",113,"terminal_failure")])
def test_real_delivered_ack_required_for_terminal_rules(ack_status,target,expected):
    u,log=pending({"status":ack_status,"delivered_at":9606.},target)
    u._view=lambda *a:pytest.fail("full view repeated after actual hop")
    u.step()
    assert u.closed and log[0]=="refresh" and log[1][0]=="finish"
    assert log[1][3]=={"disposition":expected,"classification_complete":True,"event_budget":100000}
    assert u.next_probe==9666. and u.ack_only_steps==1


@pytest.mark.parametrize("ack",[None,{}, {"status":"accepted","delivered_at":9606.}])
def test_missing_terminal_ack_cannot_close_even_if_submit_reply_updated(ack):
    u,log=pending(ack);u.step()
    assert not u.closed and log==["refresh"] and u.intent.status=="awaiting_delivered_ack_and_edge"


def test_fast_path_preserves_actual_observation_diagnostics():
    u,log=pending();before=deepcopy((u.intent.edge,u.intent.reservation,u.intent.last_now,u.intent.observation_count))
    u.session.physical_time=9607.;u.step()
    assert (u.intent.edge,u.intent.reservation,u.intent.last_now,u.intent.observation_count)==before
    assert u._last_ack_only_at==9607. and u.full_view_reads==3


def test_future_ack_fails_before_terminal_output():
    u,log=pending({"status":"updated","delivered_at":9607.})
    with pytest.raises(ValueError,match="future_ack"):u.step()
    assert not u.closed and log==["refresh"]


def test_drain_cut_keeps_same_root_open():
    u,log=pending({"status":"updated","delivered_at":9606.},drained=False);u.step()
    assert not u.closed and u.intent.status=="updated_ack_and_actual_edge" and log[1][0]=="finish"
    u.step()
    assert not u.closed and len([x for x in log if isinstance(x,tuple) and x[0]=="finish"])==2


@pytest.mark.parametrize("mutation",["decision","edge","request_id","future_proof","clock_regress"])
def test_sticky_evidence_cannot_change_or_move_backwards(mutation):
    u,_=pending()
    if mutation=="decision":u.intent.decision["request"]["business_bag_id"]="other"
    elif mutation=="edge":u.intent.edge["to"]=53
    elif mutation=="request_id":u.intent.decision["request_id"]="other"
    elif mutation=="future_proof":u.session.physical_time=9605.
    else:u._last_ack_only_at=9607.
    with pytest.raises(ValueError):u.step()


def test_reservation_only_never_arms_fast_path(monkeypatch):
    u,_=pending();u.intent.edge=None;u._observed_hop_proof=None
    called=[]
    monkeypatch.setattr(p.reference.RouteUpdate,"_step",lambda self,initial:called.append(initial))
    u.step()
    assert called==[False] and u.ack_only_steps==0 and u._observed_hop_proof is None


def test_external_preexisting_edge_does_not_self_authorize(monkeypatch):
    u,_=pending();u._observed_hop_proof=None;called=[]
    monkeypatch.setattr(p.reference.RouteUpdate,"_step",lambda self,initial:called.append(initial))
    u.step()
    assert called==[False] and u._observed_hop_proof is None


def test_eligibility_wake_must_already_have_happened(monkeypatch):
    u,_=pending();u.eligibility_schedule["fired_at"]=None;called=[]
    monkeypatch.setattr(p.reference.RouteUpdate,"_step",lambda self,initial:called.append(initial))
    u.step();assert called==[False] and u.ack_only_steps==0


def test_initial_path_is_always_original(monkeypatch):
    u,_=pending();called=[]
    monkeypatch.setattr(p.reference.RouteUpdate,"_step",lambda self,initial:called.append(initial))
    u._step(initial=True);assert called==[True] and u.ack_only_steps==0


def test_refresh_exception_is_not_converted_to_completion():
    u,_=pending({"status":"updated","delivered_at":9606.})
    def fail():raise RuntimeError("query outage")
    u.bridge.refresh=fail
    with pytest.raises(RuntimeError):u.step()
    assert not u.closed


def test_new_edge_without_actual_full_view_is_rejected(monkeypatch):
    u,_=pending();edge=deepcopy(u.intent.edge);u.intent.edge=None;u._observed_hop_proof=None
    monkeypatch.setattr(p.reference.RouteUpdate,"_step",lambda self,initial:setattr(self.intent,"edge",edge))
    with pytest.raises(ValueError,match="without_new_public_view"):u.step()


@pytest.mark.parametrize("mutation",["owner","job","evidence","time","generation"])
def test_proof_scope_is_fail_closed(mutation):
    u,_=pending()
    if mutation=="owner":u.intent.edge["owner"]="foreign"
    elif mutation=="job":u.intent.edge["local_tray"]["business_bag_id"]="other"
    elif mutation=="evidence":u.intent.edge["evidence"]="reserved_future_entry"
    elif mutation=="time":u.intent.edge["observed_at"]=float("inf")
    else:u.intent.edge["local_tray"]["generation"]=5
    with pytest.raises(ValueError):u._pin_observed_hop()


def replay_row(endpoint="protocol_command",args=None):
    return {"endpoint":endpoint,"args":args if args is not None else ["own"],"kwargs":{},
        "before":9606.,"after":9606.,"result":{"status":"pending"}}


def test_replay_omits_only_observation_after_proof_and_keeps_query_isolated():
    session=replay.EventReplay();rows=[replay_row("observe_protocol",["domestic"]),replay_row()]
    session.begin(rows,9606.,True)
    result=session.protocol_command("own");result["status"]="mutated"
    assert session.position==1 and len(session.omitted)==1 and rows[1]["result"]["status"]=="pending"
    assert session.consumed[0]["endpoint"]=="protocol_command"


def test_replay_before_proof_cannot_skip_observation():
    session=replay.EventReplay();session.begin([replay_row("observe_protocol",["domestic"]),replay_row()],9606.,False)
    with pytest.raises(ValueError,match="api_mismatch"):session.protocol_command("own")
    assert not session.omitted


@pytest.mark.parametrize("mutation",["request_id","endpoint","before","kwargs"])
def test_replay_rejects_changed_nonobservation_call(mutation):
    row=replay_row()
    if mutation=="request_id":row["args"]=["other"]
    elif mutation=="endpoint":row["endpoint"]="protocol_request"
    elif mutation=="before":row["before"]=9605.
    else:row["kwargs"]={"extra":True}
    session=replay.EventReplay();session.begin([row],9606.,True)
    with pytest.raises(ValueError,match="api_mismatch"):session.protocol_command("own")


def test_replay_cannot_hide_unconsumed_query_at_next_event():
    session=replay.EventReplay();session.begin([replay_row()],9606.,True)
    with pytest.raises(ValueError,match="previous_unconsumed"):session.begin([],9607.,True)


@pytest.mark.parametrize("clock",[True,-1.,float("inf")])
def test_client_call_clock_exclusion_is_narrow(clock):
    with pytest.raises(ValueError,match="invalid_clock"):
        replay.client_calls([{"submit_compute_ms":clock,"request":{"request_id":"own"}}])
