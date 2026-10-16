import copy
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import delivered_peer_cost_probe as m


def fixture():
    return {'endpoint':'protocol_planning_snapshots_v2','args':['A'],'kwargs':{},
        'before':10.0,'after':10.0,'result':[]}, {'node_contracts':[
            {'node':1,'resource_owner':'A'}, {'node':2,'resource_owner':'B'}]}


def test_original_full_namespace_and_source_proof():
    original = dict(m._VALIDATOR.__globals__)
    timer = m.DigestTimer(m._DIGEST)
    bound = m.bind(timer)
    assert bound.__code__ is m._VALIDATOR.__code__
    assert bound.__defaults__ is m._VALIDATOR.__defaults__
    assert bound.__closure__ is m._VALIDATOR.__closure__
    assert bound.__kwdefaults__ is m._VALIDATOR.__kwdefaults__
    assert set(bound.__globals__) == set(original)
    assert [k for k in original if original[k] is not bound.__globals__[k]] == ['capture_digest_v2']
    assert m.source_proof()['not_optimized_arm']
    assert all(m._VALIDATOR.__globals__[k] is v for k,v in original.items())


def test_exact_arguments_and_no_envelope_selection():
    row, public = fixture(); row['result'] = [{'untrusted':'source'}, {'second':True}]
    args = m.arguments(row, public)
    assert args[0] is row['result'] and args[1:4] == ('A','B',10.0)
    assert args[4][1] is public['node_contracts'][0]


@pytest.mark.parametrize('change', ['endpoint','owner','owners','before','after','time_type','error','kwargs','args','nodes','result'])
def test_bad_context_rejected(change):
    row, public = fixture()
    if change=='endpoint': row['endpoint']='other'
    elif change=='owner': row['args']=['C']
    elif change=='owners': public['node_contracts'][1]['resource_owner']='A'
    elif change=='before': row['before']=float('nan')
    elif change=='after': row['after']=11.0
    elif change=='time_type': row['after']=10
    elif change=='error': row['error']='failure'
    elif change=='kwargs': row['kwargs']={'extra':1}
    elif change=='args': row['args']=['A','B']
    elif change=='nodes': public['node_contracts'].append(copy.deepcopy(public['node_contracts'][0]))
    elif change=='result': row['result']=None
    with pytest.raises(ValueError): m.arguments(row, public)


def test_digest_return_and_reference_preserved():
    value=object(); clocks=iter((10,17)); timer=m.DigestTimer(lambda body:body,lambda:next(clocks))
    assert timer(value) is value
    assert (timer.entered,timer.completed,timer.raised,timer.nanoseconds)==(1,1,0,7)


@pytest.mark.parametrize('error', [ValueError,MemoryError,KeyboardInterrupt])
def test_digest_original_exception_preserved_even_when_final_clock_fails(error):
    original=error('original'); calls=[]
    def digest(body): raise original
    def clock():
        calls.append(1)
        if len(calls)==2: raise RuntimeError('clock failed')
        return 10
    timer=m.DigestTimer(digest,clock)
    with pytest.raises(error) as caught: timer(None)
    assert caught.value is original and timer.failed and timer.raised==1


def test_successful_digest_clock_failure_rejects_measurement():
    clocks=iter((20,10)); timer=m.DigestTimer(lambda _:None,lambda:next(clocks))
    with pytest.raises(ValueError,match='digest_clock'): timer(None)
    assert timer.failed


@pytest.mark.parametrize('error', [ValueError,KeyError,TypeError])
def test_ordinary_rejection_preserved(error):
    exc=error('reason')
    def fail(*args): raise exc
    assert m.invoke(fail,()) == {'status':'rejected','exception_type':error.__name__,'exception_text':str(exc)}


@pytest.mark.parametrize('error', [MemoryError,RecursionError,RuntimeError])
def test_resource_and_other_errors_not_reclassified(error):
    def fail(*args): raise error('stop')
    with pytest.raises(error): m.invoke(fail,())


def test_accepted_identity_and_absent():
    env={}; args=([env],)
    assert m.invoke(lambda rows:rows[0],args)['envelope'] is env
    assert m.invoke(lambda rows:None,args)=={'status':'absent'}
    with pytest.raises(ValueError,match='return_identity'): m.invoke(lambda rows:{},args)


def test_original_empty_path_no_digest_and_clock_conservation():
    row,public=fixture();args=m.arguments(row,public)
    for arm in ('A','B'):
        ticks=iter((100,150)); value,metrics=m.measure(args,arm,lambda:next(ticks))
        assert value=={'status':'absent'} and metrics['validator_ns']==50
        if arm=='B': assert metrics['digest_entered']==metrics['digest_ns']==0 and metrics['validator_outside_digest_ns']==50
        else: assert metrics['digest_entered'] is None


def test_actual_digest_callsite_reached_through_private_namespace(monkeypatch):
    # Tiny synthetic header; stub only original digest identity, never full rows.
    called=[]
    def digest(body): called.append(body); return 'sha'
    monkeypatch.setattr(m,'_DIGEST',digest)
    envelope={'schema':'g31.planning_snapshot.v2','kind':'planning_snapshot_v2',
        'digest_format':'g31.planning_capture_digest.v2','payload_sha256':'sha','status':'expired',
        'delivered_at':2.,'capture':{'schema':'g31.planning_capture.v2','local_capture':
            {'source_owner':'B','target_owner':'A','captured_at':1.,'valid_until':3.}}}
    ticks=iter((100,110,130,160)); value,metrics=m.measure(([envelope],'A','B',4.,{}),'B',lambda:next(ticks))
    assert value=={'status':'absent'} and called==[envelope['capture']]
    assert metrics['validator_ns']==60 and metrics['digest_ns']==20 and metrics['validator_outside_digest_ns']==40
    assert metrics['digest_entered']==metrics['digest_completed']==1 and metrics['digest_raised']==0


def test_pre_digest_rejection_is_not_dropped():
    ticks=iter((100,160)); value,metrics=m.measure(([{},{}],'A','B',4.,{}),'B',lambda:next(ticks))
    assert value['status']=='rejected' and 'unexpected_or_duplicate' in value['exception_text']
    assert metrics['digest_entered']==0


def test_reject_unverified_timer():
    with pytest.raises(ValueError,match='original_digest_timer'): m.bind(SimpleNamespace())
    with pytest.raises(ValueError,match='original_digest_timer'): m.bind(m.DigestTimer(lambda _:None))
