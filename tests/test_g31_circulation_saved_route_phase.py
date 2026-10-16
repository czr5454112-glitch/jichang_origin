"""Pure stream-equivalence and unchanged original case checks; no native."""
from copy import deepcopy
import pytest
import audit_saved_route_native027_phase as a


def row(ordinal=0):
    return {'ordinal':ordinal,'role':'controller','endpoint':'advance_to','args':[9900.],
        'kwargs':{},'before':9600.,'after':9900.,'start_ns':10,'end_ns':20,
        'result':{'status':'reached','horizon_complete':True,'wall_seconds':.1}}


def test_original_case_ast_only_adds_post_validation_callback():
    function,proof=a.verify_case_function()
    assert proof['status']=='original_case_AST_unchanged_except_final_return_callback'
    assert function.__globals__['replay_request'] is a.original.replay_request
    assert function.__globals__['verify_original_prefix'] is a.original.verify_original_prefix
    assert function.__globals__['verify_scheduled_reference'] is a.original.verify_scheduled_reference


def test_stream_equality_is_exact_old_normalized_list_equality():
    left=[row(i) for i in range(3)];right=deepcopy(left)
    for r in right:r.update(start_ns=100,end_ns=200);r['result']['wall_seconds']=.2
    assert a.original.ordered([a.original.api_semantics(r) for r in left])==a.original.ordered([a.original.api_semantics(r) for r in right])
    assert a.compare_api_rows(iter(left),iter(right),'same')==3


@pytest.mark.parametrize('mutation',['omit','extra','role','ordinal','argument','time','response','order','nan','bool'])
def test_stream_rejects_every_semantic_or_invalid_clock_difference(mutation):
    left=[row()];right=deepcopy(left)
    if mutation=='omit':right=[]
    elif mutation=='extra':right.append(row(1))
    elif mutation=='role':right[0]['role']='request'
    elif mutation=='ordinal':right[0]['ordinal']=1
    elif mutation=='argument':right[0]['args']=[9899.]
    elif mutation=='time':right[0]['after']=9899.
    elif mutation=='response':right[0]['result']['horizon_complete']=False
    elif mutation=='order':right[0]['result']={k:right[0]['result'][k] for k in reversed(right[0]['result'])}
    elif mutation=='nan':right[0]['result']['wall_seconds']=float('nan')
    else:right[0]['result']['wall_seconds']=True
    with pytest.raises(ValueError):a.compare_api_rows(iter(left),iter(right),'changed')


def test_compare_does_not_materialize_the_full_input_iterable():
    state={'read':0}
    def left():
        for i in range(4):
            assert state['read']==i
            yield row(i)
    def right():
        for i in range(4):
            state['read']+=1
            yield row(i)
    assert a.compare_api_rows(left(),right(),'same')==4


def test_unmodified_native_phase_validator_is_used():
    assert a.measurement.summarize.__module__=='scripts.experiments.g31_ics_circulation.route_update_phase_measurement'
