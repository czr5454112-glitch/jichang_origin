import builtins
import copy
import dis
import gzip
import json
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import launch_live_communication_conformance_v2 as launch
from scripts.experiments.g31_ics_circulation import public_live_obligation_communication_projection as model
from scripts.experiments.g31_ics_circulation import live_obligation_delivered_context as context
from scripts.experiments.g31_ics_circulation import validate_live_communication_projection as prior


def global_names(code):
    names={instruction.argval for instruction in dis.get_instructions(code) if instruction.opname=='LOAD_GLOBAL'}
    for item in code.co_consts:
        if isinstance(item,CodeType):names|=global_names(item)
    return names


def missing_globals(function):
    return global_names(function.__code__)-set(function.__globals__)-set(vars(builtins))


@pytest.mark.parametrize('elapsed',[0.,1.,178.])
def test_budget_charges_parent_imports_and_reserves_close(elapsed):
    assert launch.remaining_budget(elapsed)==179.-elapsed


@pytest.mark.parametrize('elapsed',[179.,180.,float('inf')])
def test_no_worker_when_shared_budget_exhausted(elapsed):
    with pytest.raises((ValueError,TimeoutError)):launch.remaining_budget(elapsed)


def test_dynamic_run_all_global_loads_resolve():
    assert missing_globals(model.Projection.run)==set()


def test_missing_dynamic_global_is_detected():
    f=model.Projection.run
    faulty=FunctionType(f.__code__,{k:v for k,v in f.__globals__.items() if k!='legacy'},f.__name__)
    assert 'legacy' in missing_globals(faulty)


def test_entire_dynamic_run_fake_engine_smoke():
    # Execute the complete generated run body on one synthetic tick, not a
    # physical candidate or a native outcome. Seed callbacks deliberately do
    # not enqueue real events. This covers compiled namespace wiring through
    # final result construction; it is not96-model conformance.
    seen=[]
    fake=SimpleNamespace(jobs={'loaded':{'storage_node':4,'loaded_at':.1}},service={0:.5},
        trays={'P':{'load_end':3.}},action={'empty_departure':.11,'initial_action':'native_default'},
        events=[(.11,0,0,'tick',())],completed={},commands=[],dispatches=[],receipts=[],waits=[],
        activation_trace=[],phase_trace=[])
    fake.begin_leg=lambda *args,**kwargs:seen.append('seed_leg')
    fake.schedule=lambda *args:None
    fake.request=lambda *args:seen.append('seed_request')
    fake.before_event=lambda *args:seen.append('before')
    fake.protocol_event=lambda *args:False
    fake.tick=lambda:seen.append('tick')
    fake.after_event=lambda *args:seen.append('after')
    fake.finish=lambda result:result
    result=model.Projection.run(fake)
    assert result['status']=='unknown_unfinished_projection' and result['event_count']==1
    assert seen==['seed_leg','seed_request','before','tick','after']


def test_future_captured_fact_is_rejected_even_with_recomputed_digest():
    root=Path(__file__).resolve().parents[1]
    path=root/'outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_unloading_native_prepare_001/mechanism/vector_00.json.gz'
    raw=json.loads(gzip.decompress(path.read_bytes()))
    args=prior.public_initial(raw,'A')
    assert type(context.initial_context(**args)) is context.SuppliedContext
    late=copy.deepcopy(args);envelope=late['received'][0]
    envelope['capture']['captured_at']=.2;envelope['delivered_at']=.21
    envelope['payload_sha256']=context.initial.capture_digest(envelope['capture'])
    result=context.initial_context(**late)
    assert result['status']=='unknown' and 'causal_time' in str(result['reasons'])
    future=copy.deepcopy(args);envelope=future['received'][0]
    envelope['capture']['jobs'][0]['loaded_at']=.2
    envelope['payload_sha256']=context.initial.capture_digest(envelope['capture'])
    result=context.initial_context(**future)
    assert result['status']=='unknown' and 'future_observed_job_epoch' in str(result['reasons'])
