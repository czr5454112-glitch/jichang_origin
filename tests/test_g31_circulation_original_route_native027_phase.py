"""Pure diagnostic/parity guards; no NativeSession is constructed."""
from copy import deepcopy
import ast
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import route_update_phase_measurement as m
from scripts.experiments.g31_ics_circulation import probe_original_route_update_native027_phase as p
from scripts.experiments.g31_ics_circulation import verify_original_route_update_native027_phase as v
from scripts.experiments.g31_ics_circulation import launch_original_route_update_native027_phase as launch


def fixture(monkeypatch):
    monkeypatch.setattr(m,"analyze_candidate_partition",lambda batches,envelopes:{"status":"structurally_valid_native027_candidate_partition"})
    tape=[{"ordinal":0,"endpoint":"observe_protocol","role":"request","args":["A"],"kwargs":{},"before":9600.,"after":9600.,"result":{},"start_ns":115,"end_ns":145},
          {"ordinal":1,"endpoint":"advance_to","role":"controller","args":[9900.],"kwargs":{},"before":9600.,"after":9900.,"result":{"wall_seconds":0.},"start_ns":170,"end_ns":190}]
    envelopes=[{"api_endpoint":"observe_protocol","call_ordinal":1,"start_ns":120,"end_ns":140},
               {"api_endpoint":"advance_to","call_ordinal":2,"start_ns":175,"end_ns":185}]
    spans=[{"id":0,"parent":None,"phase":"request_service_invocation","start_ns":105,"end_ns":160,"exception":False,"at":9600.,"initial":True},
           {"id":1,"parent":0,"phase":"request_public_observation_and_filter","start_ns":110,"end_ns":150,"exception":False}]
    diagnostic={"timed":True,"capacity":m.CAPACITY,"capture_errors":[],"native_batches":[{"rows":[
        {"span_id":0,"parent_span_id":-1,"call_ordinal":1,"phase":0,"start_ns":1,"end_ns":16},
        {"span_id":1,"parent_span_id":0,"call_ordinal":1,"phase":20,"start_ns":3,"end_ns":13},
        {"span_id":2,"parent_span_id":-1,"call_ordinal":2,"phase":0,"start_ns":20,"end_ns":26}]}],"native_envelopes":envelopes,
                "python_spans":spans,"capture_setup":{"start_ns":50,"end_ns":90},"capture_take":{"start_ns":210,"end_ns":230}}
    root={"started_ns":100,"returned_ns":200,"censored_ns":None,"steps":[{"at":9600.,"initial":True}]}
    events=[{"initial":True,"at":9600.,"first_api":0,"after_api":1}]
    return diagnostic,tape,root,events


def test_partition_conserves_native_and_all_remainder(monkeypatch):
    result=m.summarize(*fixture(monkeypatch))
    assert result["root_total_ns"]==100
    assert result["root_native_envelope_ns"]==30
    assert result["root_python_request_service_remainder_ns"]==35
    assert result["root_other_unclassified_ns"]==35
    assert result["python_exclusive_bundles_including_nested_native_ns"]=={"request_service_invocation":15,"request_public_observation_and_filter":40}
    assert result["root_native_phase_bundles"]["native_inner_total_ns"]==21
    assert result["root_native_phase_bundles"]["binding_and_wrapper_remainder_ns"]==9
    assert result["partition_exact"] and result["physics_subtracted_ns"]==0
    assert result["complete_computation_available"] is False


def test_tail_is_not_silently_added_to_root(monkeypatch):
    d,t,r,e=fixture(monkeypatch);r["returned_ns"]=155
    result=m.summarize(d,t,r,e)
    assert result["root_total_ns"]==55 and result["diagnostic_step_tail_outside_root_ns"]==5
    assert result["root_native_envelope_ns"]==20 and result["partition_exact"]


@pytest.mark.parametrize("edge",["start","end"])
def test_straddling_native_envelope_rejected(monkeypatch,edge):
    d,t,r,e=fixture(monkeypatch)
    if edge=="start":
        d["native_envelopes"][0]["start_ns"]=95;t[0]["start_ns"]=90
    else:r["returned_ns"]=130
    with pytest.raises(ValueError,match="root_cuts_native_call"):m.summarize(d,t,r,e)


@pytest.mark.parametrize("mutation",["count","phase","error","overflow","setup","take","event_at","event_initial","event_index","event_missing","request_identity","query_identity"])
def test_capture_or_identity_omission_fails_closed(monkeypatch,mutation):
    d,t,r,e=fixture(monkeypatch)
    if mutation=="count":d["native_envelopes"].pop()
    elif mutation=="phase":d["python_spans"][1]["phase"]="physics_exempt"
    elif mutation=="error":d["capture_errors"]=["native_error"]
    elif mutation=="overflow":monkeypatch.setattr(m,"analyze_candidate_partition",lambda *a:{"status":"unknown"})
    elif mutation=="setup":d["capture_setup"]["end_ns"]=110
    elif mutation=="take":d["capture_take"]["start_ns"]=190
    elif mutation=="event_at":e[0]["at"]=9601.
    elif mutation=="event_initial":e[0]["initial"]=False
    elif mutation=="event_index":e[0]["first_api"]=1
    elif mutation=="event_missing":e.clear()
    elif mutation=="request_identity":
        t[0].update(endpoint="submit_protocol_command",args=[{"request_id":"own"}]);d["native_envelopes"][0].update(api_endpoint="submit_protocol_command",protocol_request_id="other")
    elif mutation=="query_identity":
        t[0].update(endpoint="protocol_command",args=["A","own"]);d["native_envelopes"][0].update(api_endpoint="protocol_command",protocol_request_id="other")
    with pytest.raises(ValueError):m.summarize(d,t,r,e)


@pytest.mark.parametrize("mutation",["bool_id","bool_time","negative","parent","overlap","unknown","exception","missing_end"])
def test_python_span_guards(monkeypatch,mutation):
    d,_,_,_=fixture(monkeypatch);rows=d["python_spans"]
    if mutation=="bool_id":rows[0]["id"]=False
    elif mutation=="bool_time":rows[0]["start_ns"]=True
    elif mutation=="negative":rows[0]["start_ns"]=-1
    elif mutation=="parent":rows[1]["parent"]=1
    elif mutation=="overlap":rows.append({**rows[1],"id":2,"start_ns":140,"end_ns":155})
    elif mutation=="unknown":rows[1]["phase"]="unknown"
    elif mutation=="exception":rows[1]["exception"]=True
    else:rows[1]["end_ns"]=None
    with pytest.raises(ValueError):m.validate_python_spans(rows)


def test_python_spans_exception_and_nested_order():
    clock=iter([1,2,3,4]).__next__;spans=m.PythonSpans(clock)
    with pytest.raises(RuntimeError):
        with spans.span("request_service_invocation"):
            with spans.span("candidate_and_intent_update"):raise RuntimeError("kept")
    assert spans.stack==[] and len(spans.rows)==2
    assert spans.rows[0]["exception"] and spans.rows[1]["exception"]
    assert spans.rows[1]["parent"]==0


def test_intent_delegate_has_no_policy_copy_or_new_decision():
    class Intent:
        decision={"node":112}
        def observe(self,*args,**kwargs):return (args,kwargs)
        def snapshot(self):return {"decision":self.decision}
    original=Intent();delegate=m.ObservedIntent(original,m.PythonSpans())
    assert delegate.decision is original.decision
    assert delegate.observe(3,test=4)==((3,),{"test":4})
    assert delegate.snapshot()==original.snapshot()


def test_phase_tape_plain_no_capture(monkeypatch,tmp_path):
    class Native:
        physical_time=9600.
        def observe_protocol(self,owner):return {"owner":owner}
    monkeypatch.setattr(m,"Native027TimingCapture",lambda *a,**k:pytest.fail("plain enabled timing"))
    tape=m.PhaseTape(Native(),native_module=None,reference={},timed=False)
    tape.begin(tmp_path/"tape.gz");assert tape.observe_protocol("A")=={"owner":"A"};tape.close()
    diag=tape.diagnostic(m.PythonSpans());assert diag["native_batches"]==[] and diag["capture_setup"] is None


def test_phase_tape_takes_once_and_keeps_errors(monkeypatch,tmp_path):
    class Native:physical_time=9600.
    class Capture:
        physical_time=9600.
        def __init__(self,*a,**k):self.batches=[];self.envelopes=[];self.errors=[];self.takes=0
        def take_completed(self):self.takes+=1;self.batches.append({"rows":[]})
    monkeypatch.setattr(m,"Native027TimingCapture",Capture)
    tape=m.PhaseTape(Native(),native_module=None,reference={},timed=True)
    tape.begin(tmp_path/"tape.gz");tape.close();tape.close()
    assert tape.capture.takes==1 and tape.capture_take is not None
    tape.capture.errors.append("retained")
    diag=tape.diagnostic(m.PythonSpans());diag["native_batches"].append({})
    assert len(tape.capture.batches)==1 and tape.diagnostic(m.PythonSpans())["capture_errors"]==["retained"]


def test_timing_only_api_exclusions_are_narrow(monkeypatch):
    _,t,_,_=fixture(monkeypatch);row=t[1]
    changed=deepcopy(row);changed["start_ns"]=999;changed["end_ns"]=1000;changed["result"]["wall_seconds"]=123.
    assert v.api_semantics(row)==v.api_semantics(changed)
    changed["after"]=9800.;assert v.api_semantics(row)!=v.api_semantics(changed)
    changed=deepcopy(row);changed["result"]["wall_seconds"]=True
    with pytest.raises(ValueError):v.api_semantics(changed)


def test_six_cells_and_fixed_scope():
    assert p.CASES=={"baseline":0,"drop_first_ack":1,"ack_withheld_in_window":100}
    assert p.ARMS==("plain","timed") and p.phase_contract()["sessions"]==6
    assert p.ADMISSION==9600. and p.HORIZON==9900. and p.PARENT_SECONDS==launch.LIMIT==600.
    assert p.policy.RouteUpdate is p.RouteUpdate


def test_private_worker_environment_leaves_policy_globals_unmodified():
    tree=ast.parse(Path(p.__file__).read_text())
    worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="worker")
    calls=[n for n in ast.walk(worker) if isinstance(n,ast.Call)]
    assert any(isinstance(n.func,ast.Name) and n.func.id=="FunctionType" and ast.unparse(n.args[0])=="policy.worker.__code__" for n in calls)
    assert not any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and ast.unparse(t).startswith("policy.") for t in n.targets) for n in ast.walk(worker))


def test_source_closure_includes_each_new_file_and_accepted_gate():
    paths={path.name for path in p.source_paths()}
    assert {"native027_timing_gate.py","capture_native027_request_timing.py","native027_request_timing.py",
        "route_update_phase_measurement.py","probe_original_route_update_native027_phase.py",
        "verify_original_route_update_native027_phase.py","launch_original_route_update_native027_phase.py",
        Path(__file__).name} <= paths


def test_actual_accepted_inventory_is_hash_bound_not_boolean():
    pins=p.accepted_inventory()
    assert pins[p.CONTRACT["path"]]==p.CONTRACT["sha256"]
    contract=p.old.read(p.CONTRACT["path"])
    assert pins[contract["runtime_acceptance"]["path"]]==contract["runtime_acceptance"]["sha256"]
    assert any(path.endswith(".process.json") for path in pins)
    assert any(digest==p.policy.old.BINARY_SHA and path.endswith(".pyd") for path,digest in pins.items())
    assert len(pins)>300


def test_source_cache_rehashes_and_rejects_drift(monkeypatch,tmp_path):
    file=tmp_path/"source.py";file.write_text("value=1")
    monkeypatch.setattr(p,"_SOURCE_CACHE",((file,),{file:p.old.sha(file)}))
    assert p.source_paths()==(file,)
    file.write_text("value=2")
    with pytest.raises(ValueError,match="cached_source_changed"):p.source_paths()


def test_measured_route_replays_actual_saved_request_identically(monkeypatch):
    directory=p.REFERENCE/"baseline"
    raw=p.old.gzread(directory/"raw.json.gz");rows=v.read_api(directory/"service_tape.jsonl.gz")
    spans=m.PythonSpans();measured=m.measured_route_type(spans)
    monkeypatch.setattr(p,"RouteUpdate",measured)
    update=v.replay_request(raw,rows)
    assert update.closed and len([r for r in spans.rows if r["parent"] is None])==len(raw["root"]["steps"])
    assert update.intent.snapshot()==raw["root"]["intent"]


def test_take_failure_remains_unknown_without_repeated_take(monkeypatch,tmp_path):
    class Native:physical_time=9600.
    class Capture:
        physical_time=9600.
        def __init__(self,*a,**k):self.batches=[];self.envelopes=[];self.errors=[];self.takes=0
        def take_completed(self):self.takes+=1;raise RuntimeError("take failed")
    monkeypatch.setattr(m,"Native027TimingCapture",Capture)
    tape=m.PhaseTape(Native(),native_module=None,reference={},timed=True);tape.begin(tmp_path/"tape.gz")
    with pytest.raises(RuntimeError):tape.close()
    tape.close()
    assert tape.capture.takes==1 and "take_failed" in tape.capture.errors[0] and tape.capture_take is not None
