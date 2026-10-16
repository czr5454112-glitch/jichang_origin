from copy import deepcopy
import gc
import io
import json

import pytest

from scripts.experiments.g31_ics_circulation import run_regional_path_pool as run
from scripts.experiments.g31_ics_circulation import verify_regional_path_pool as verify


def fixture():
    owner=dict(owner_id="A",owner_epoch=0,refreshed=[],causes={},compute_wall_ms=.1,compute_cpu_ms=0.)
    batch=dict(start_at=0.,end_at=1.,requested_public_deadline=1.,status="horizon_reached",timestamp_complete=True,wall_ms=.1,cpu_ms=0.)
    part=dict(control_records=[owner],native_batches=[batch],client_calls=[])
    capture=dict(segment=10,start_ns=1,end_ns=100,gc_enabled=True,errors=[],collections=[],
        rows=[dict(segment=10,owner="A",epoch=0,start_ns=2,end_ns=20,cpu_ns=2)])
    rows=[dict(ordinal=0,segment=10,method="physical_time",args=[],kwargs={},start_ns=3,end_ns=4,before=0.,after=0.,returned=0.),
        dict(ordinal=1,segment=10,method="observe_protocol_control_policy_recent",args=["A",120.],kwargs={},start_ns=5,end_ns=6,before=0.,after=0.,returned={"owner_id":"A"}),
        dict(ordinal=2,segment=10,method="advance_until_owner_notification",args=[["A"],{"A":0},1.],kwargs={"max_events":1000000},
            start_ns=25,end_ns=30,before=0.,after=1.,returned=dict(status="horizon_reached",physical_time=1.,timestamp_complete=True,horizon_complete=True,notifications={}))]
    return rows,part,capture


def test_closed_api_fixture_and_actual_capability_shape():
    rows,part,capture=fixture()
    assert verify.validate_api_rows(rows,part,capture,0,10,["A"])==3
    assert callable(getattr(run.ApiTape,"observe_protocol_control_policy_recent"))
    assert callable(getattr(run.ApiTape,"observe_protocol_control_policy"))


@pytest.mark.parametrize("defect",["gap","duplicate","reorder","drop_policy","wrong_segment","missing_return",
    "exception","changed_status","changed_clock","changed_args","unknown_endpoint","bad_gc","bad_owner","overlap"])
def test_record_tampering_fails_closed(defect):
    rows,part,capture=fixture()
    if defect=="gap":rows[-1]["ordinal"]=4
    elif defect=="duplicate":rows[-1]["ordinal"]=1
    elif defect=="reorder":rows[0],rows[1]=rows[1],rows[0]
    elif defect=="drop_policy":rows.pop(1);rows[-1]["ordinal"]=1
    elif defect=="wrong_segment":rows[-1]["segment"]=11
    elif defect=="missing_return":del rows[-1]["returned"]
    elif defect=="exception":rows[-1]["exception"]={"message":"x"}
    elif defect=="changed_status":rows[-1]["returned"]["status"]="notified"
    elif defect=="changed_clock":rows[0]["returned"]=1.
    elif defect=="changed_args":rows[-1]["kwargs"]["max_events"]=999
    elif defect=="unknown_endpoint":rows[1]["method"]="observe_private_truth"
    elif defect=="bad_gc":capture["collections"]=[dict(generation=2,start_ns=0,end_ns=3,owner_context=None)]
    elif defect=="bad_owner":capture["rows"][0]["owner"]="B"
    else:rows[-1]["start_ns"]=5
    with pytest.raises(ValueError):verify.validate_api_rows(rows,part,capture,0,10,["A"])


def test_clocks_removed_only_at_declared_locations():
    _,part,_=fixture();part.update(wall_seconds=1.,diagnostic_seal_wall_ms=3.)
    part["control_records"][0]["causes"]={"wall_seconds":7.}
    normalized=verify.normalize_part(part)
    assert "wall_seconds" not in normalized and "compute_wall_ms" not in normalized["control_records"][0]
    assert normalized["control_records"][0]["causes"]["wall_seconds"]==7.
    changed=deepcopy(part);changed["control_records"][0]["causes"]["wall_seconds"]=8.
    with pytest.raises(ValueError):verify.exact(normalized,verify.normalize_part(changed),"payload_clock_not_measurement")


def test_ordered_endpoint_comparison_preserves_dict_order_and_notification_body():
    rows,_,_=fixture();changed=deepcopy(rows)
    changed[-1]["returned"]["notifications"]={"A":{"sequence":2,"change_mask":16,"observed_at":1.}}
    with pytest.raises(ValueError):verify.exact([verify.api_semantic(r) for r in rows],[verify.api_semantic(r) for r in changed],"actual_notification")
    with pytest.raises(ValueError):verify.exact({"a":1,"b":2},{"b":2,"a":1},"order")


def test_api_proxy_records_original_return_without_retaining_mutable_rows():
    class Fake:
        physical_time=0.
        def observe_protocol_control_policy_recent(self,owner,validity):return {"owner":owner,"nested":[validity]}
    tape=run.ApiTape(Fake());tape.stream=io.StringIO();tape.segment=10
    returned=tape.observe_protocol_control_policy_recent("A",120.)
    returned["nested"].append(999)
    saved=json.loads(tape.stream.getvalue())
    assert saved["returned"]=={"owner":"A","nested":[120.]} and tape.ordinal==1
    with pytest.raises(AttributeError):tape.hidden_truth()


def test_api_exception_is_preserved_and_no_silent_skip():
    class Fake:
        physical_time=0.
        def protocol_request(self,*args):raise RuntimeError("native_fixture")
    tape=run.ApiTape(Fake());tape.stream=io.StringIO();tape.segment=10
    with pytest.raises(RuntimeError,match="native_fixture"):tape.protocol_request("A","id")
    assert json.loads(tape.stream.getvalue())["exception"]=={"type":"RuntimeError","message":"native_fixture"}


def test_callback_and_owner_factory_cleanup_on_failure():
    original=run.control._activate_owner;callbacks=list(gc.callbacks)
    with pytest.raises(RuntimeError):
        with run.activation_capture(10) as capture:
            assert run.control._activate_owner is not original
            raise RuntimeError("fixture")
    assert run.control._activate_owner is original and gc.callbacks==callbacks
    assert capture["end_ns"]>=capture["start_ns"] and capture["errors"]==[]


def test_exclusive_artifact_writer_preserves_prior_evidence(tmp_path):
    path=tmp_path/"claim.json";run.write(path,{"original":True})
    with pytest.raises(FileExistsError):run.write(path,{"original":False})
    assert run.read(path)=={"original":True}


def test_loaded_source_closure_includes_absolute_repository_imports():
    # Exercise archive introspection only; this test also works in a broader
    # suite which may already have loaded a native module for unrelated tests.
    files=run.imported_sources()
    assert run.ROOT/"scripts/experiments/g31_ics_circulation/run_regional_path_pool.py" in files
    assert run.ROOT/"scripts/eval/run_g4irsf28_service_potential.py" in files
