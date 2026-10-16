"""Pure runtime scheduling and exact-source difference tests; no native."""
import ast
from copy import deepcopy
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import event_protocol_control as original
from scripts.experiments.g31_ics_circulation import event_protocol_control_deadline as scheduled
from scripts.experiments.g31_ics_circulation import probe_original_route_update_internal_deadline as p
from scripts.experiments.g31_ics_circulation import verify_original_route_update_internal_deadline as v


def test_entire_controller_ast_diff_is_only_optional_deadline_hook():
    before = ast.parse(Path(original.__file__).read_text(encoding="utf8"))
    after = ast.parse(Path(scheduled.__file__).read_text(encoding="utf8"))
    after.body = [n for n in after.body if not isinstance(n, ast.FunctionDef) or n.name != "_bounded_public_deadline"]
    fn = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == "run_event_protocol_control")
    assert fn.args.kwonlyargs[-1].arg == "_public_deadline" and isinstance(fn.args.kw_defaults[-1], ast.Constant) and fn.args.kw_defaults[-1].value is None
    fn.args.kwonlyargs.pop(); fn.args.kw_defaults.pop()
    loop = next(n for n in fn.body if isinstance(n, ast.While))
    hook = [n for n in loop.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name) and n.value.func.id == "_bounded_public_deadline"]
    assert len(hook) == 1
    loop.body.remove(hook[0])
    assert ast.dump(after, include_attributes=False) == ast.dump(before, include_attributes=False)


@pytest.mark.parametrize("existing,now,due,expected", [(60.,0.,3.5,3.5),(0.,0.,3.5,0.),(2.,1.,3.5,2.),(3.5,3.5,3.5,3.5),(60.,0.,None,60.)])
def test_hook_uses_only_earlier_true_deadline_preserving_current_drains(existing,now,due,expected):
    assert scheduled._bounded_public_deadline(existing,now,lambda t:due)==expected
    assert scheduled._bounded_public_deadline(existing,now,None)==existing


@pytest.mark.parametrize("due", [True,-1.,float('nan'),float('inf'),"3.5"])
def test_invalid_hook_value_rejected_before_native(due):
    with pytest.raises(ValueError,match="invalid_caller_public_deadline"):
        scheduled._bounded_public_deadline(60.,0.,lambda t:due)


class Session:
    def __init__(self): self.physical_time=0.;self.boundaries=[];self.results=[]
    def advance_until_owner_notification(self,owners,after,deadline,*,max_events):
        assert deadline>=self.physical_time
        self.boundaries.append(deadline);self.physical_time=deadline
        return {"status":"horizon_reached","timestamp_complete":True,"notifications":{}}
    def result_at(self,horizon):
        self.results.append(horizon);assert self.physical_time==horizon
        return {"advance":{"status":"reached","horizon_complete":True}}


class Client:
    def __init__(self,*args,**kwargs):self.state={};self.calls=[]


def test_intermediate_native_horizon_does_not_materialize_result_or_reset_period(monkeypatch):
    monkeypatch.setattr(scheduled,"ProtocolClient",Client)
    monkeypatch.setattr(scheduled,"_activate_owner",lambda client,owner,current,cause,**kwargs:{"owner_id":owner,"at":0.})
    session=Session()
    result=scheduled.run_event_protocol_control(session,["A"],horizon=10.,control_period=60.,
        _public_deadline=lambda now:3.5 if now<3.5 else None)
    assert session.boundaries==[0.,0.,3.5,10.] and session.results==[10.]
    assert [r["requested_public_deadline"] for r in result["native_batches"]]==session.boundaries
    assert all(r["status"]=="horizon_reached" for r in result["native_batches"])
    assert result["controller_state"]["start"]==0. and result["controller_state"]["next_tick"]==1
    assert "_public_deadline" not in str(result["controller_state"])


@pytest.mark.parametrize("closed,censored,fired",[(True,None,None),(False,1,None),(False,None,3.5)])
def test_completed_or_fired_root_no_longer_injects_deadline(closed,censored,fired):
    update=type('Update',(),{"closed":closed,"censored_ns":censored,"eligibility_schedule":{"deadline":3.5,"fired_at":fired}})()
    assert p.public_deadline(update,4.) is None


def test_unfired_missed_deadline_fails_instead_of_reading_past_or_relabeling():
    update=type('Update',(),{"closed":False,"censored_ns":None,"eligibility_schedule":{"deadline":3.5,"fired_at":None}})()
    assert p.public_deadline(update,3.5)==3.5
    with pytest.raises(ValueError,match="wakeup_missed"):p.public_deadline(update,4.)
    assert p.public_deadline(None,0.) is None


def test_eligibility_and_boundary_are_exact_existing_implementations():
    assert p.RouteUpdate is p.eligibility.RouteUpdate
    assert p.Boundary is p.base.Boundary
    assert p.CASES==p.eligibility.CASES and p.HORIZON==9900. and p.PARENT_SECONDS==600.


def test_each_logged_native_deadline_equals_actual_tape_argument():
    call={"role":"controller","endpoint":"advance_until_owner_notification","args":[["A"],{},3.5],
        "before":0.,"after":3.5,"result":{"status":"horizon_reached","timestamp_complete":True}}
    batch={"requested_public_deadline":3.5,"start_at":0.,"end_at":3.5,"status":"horizon_reached","timestamp_complete":True}
    v.verify_native_boundary_log([call],[batch])
    for key,value in (("requested_public_deadline",60.),("end_at",60.),("status","notified"),("timestamp_complete",False)):
        wrong={**batch,key:value}
        with pytest.raises(ValueError):v.verify_native_boundary_log([call],[wrong])
    with pytest.raises(ValueError):v.verify_native_boundary_log([call],[])


def test_request_comparator_keeps_all_semantics_only_narrow_diagnostic_exclusion():
    row={"endpoint":"advance_to","args":[3.5],"kwargs":{"max_events":100000},"before":3.5,"after":3.5,
        "result":{"physical_time":3.5,"status":"reached","horizon_complete":True,"wall_seconds":.1},
        "ordinal":50,"start_ns":1,"end_ns":2,"role":"request"}
    a=v.request_native_semantics(row);changed=deepcopy(row);changed['result']['wall_seconds']=.2
    assert v.request_native_semantics(changed)==a and row['result']['wall_seconds']==.1
    changed['result']['horizon_complete']=False
    assert v.request_native_semantics(changed)!=a
    row['result']['wall_seconds']=True
    with pytest.raises(ValueError):v.request_native_semantics(row)


def test_outer_diagnostic_target_remains9900_not_eligibility_time():
    item={"target":9900.,"physical_time":9900.};part={"status":"reached",
        "control_continuation":{"requested_horizon":9900.},"controller_state":{"native_timestamp_complete":True},
        "native_batches":[{"start_at":0.,"end_at":3.5,"requested_public_deadline":3.5}]}
    v.validate_warm_target(item,part,{},{});item['target']=3.5
    with pytest.raises(ValueError):v.validate_warm_target(item,part,{},{})
