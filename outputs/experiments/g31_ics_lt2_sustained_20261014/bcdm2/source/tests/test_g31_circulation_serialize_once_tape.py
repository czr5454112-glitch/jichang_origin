from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import serialize_once_low_wip_tape as candidate

old = candidate.reference


def decoded(tape, ordinal=0):
    return json.loads(gzip.decompress((tape.directory / tape.rows[ordinal]['path']).read_bytes()))


def ordered(value):
    # JSON strings expose nested insertion order as well as float signed zero.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def invoke_pair(tmp_path, factory, args=(), kwargs=None, name='protocol_request'):
    answers = []
    for label, cls in [('old', old.Tape), ('new', candidate.SerializedOnceTape)]:
        session = factory()
        tape = cls(session, tmp_path / label)
        failure = None
        try:
            returned = getattr(tape, name)(*deepcopy(args), **deepcopy(kwargs or {}))
        except BaseException as error:
            returned = None
            failure = (type(error), str(error))
        answers.append((session, tape, returned, failure))
    a, b = answers
    assert a[3] == b[3]
    assert len(a[1].rows) == len(b[1].rows)
    if a[1].rows:
        assert ordered(decoded(a[1])) == ordered(decoded(b[1]))
    return answers


@pytest.mark.parametrize('value', [None, {}, [], [1, 2.0, -0.0, True, False, None],
    {'Unicode': '盘😀', 'tuple': (1, '2'), 'nested': {'x': [3]}},
    {1: 'first', '1': 'last', 'after': 3},
    {'1': 'first', 1: 'last', 'after': 3},
    {None: 'none', 'null': 'string', False: 'false', 'false': 'string2'},
    {-0.0: 'zero', '-0.0': 'sameJSONkey', '0.0': 'distinct'},
    {'x': 10**100, 'y': 1.2345678901234567}])
def test_legacy_order_values_key_collisions_and_scalar_types(tmp_path, value):
    invoke_pair(tmp_path, lambda: SimpleNamespace(physical_time=1.,
        protocol_request=lambda *a, **k: deepcopy(value)), ({1:'a','1':'b'},), {'kw':value})


def test_precall_snapshot_native_mutation_and_postreturn_alias_isolation(tmp_path):
    def factory():
        session = SimpleNamespace(physical_time=0.)
        def call(arg, *, kw):
            arg['values'].append(2); kw['values'].append(3)
            session.physical_time = 2.
            return {'arg': arg, 'kw': kw, 'again': arg}
        session.protocol_request = call
        return session
    pair = invoke_pair(tmp_path, factory, ({'values':[1]},), {'kw':{'values':[8]}})
    for _, tape, returned, _ in pair:
        assert decoded(tape)['args'] == [{'values':[1]}]
        assert decoded(tape)['kwargs'] == {'kw':{'values':[8]}}
        returned['arg']['values'].append(999)
        assert decoded(tape)['result']['arg']['values'] == [1,2]
        assert decoded(tape)['before'] == 0. and decoded(tape)['after'] == 2.


@pytest.mark.parametrize('value', [float('nan'), float('inf'), {('not','JSON'):'key'}, object()])
def test_bad_result_records_same_error_without_result(tmp_path, value):
    pair = invoke_pair(tmp_path, lambda: SimpleNamespace(physical_time=1., protocol_request=lambda: value))
    assert pair[0][3] is not None
    assert 'result' not in decoded(pair[1][1]) and 'error' in decoded(pair[1][1])


def test_cyclic_result_records_same_canonical_failure(tmp_path):
    value=[]; value.append(value)
    pair=invoke_pair(tmp_path,lambda:SimpleNamespace(physical_time=0.,protocol_request=lambda:value))
    assert pair[0][3][0] is ValueError


@pytest.mark.parametrize('keyword', [False, True])
def test_bad_arguments_do_not_invoke_native_or_create_row(tmp_path, keyword):
    calls=[]
    def factory():
        return SimpleNamespace(physical_time=0.,protocol_request=lambda *a,**k:calls.append(True))
    pair=invoke_pair(tmp_path,factory,() if keyword else (float('nan'),),{'bad':object()} if keyword else {})
    assert calls==[] and all(not x[1].rows for x in pair)


def test_native_error_after_mutation_is_saved_before_reraise(tmp_path):
    def factory():
        session=SimpleNamespace(physical_time=1.)
        def call(arg):
            arg.append(2);session.physical_time=1.5
            raise ValueError('real failure')
        session.protocol_request=call
        return session
    pair=invoke_pair(tmp_path,factory,([1],))
    assert decoded(pair[1][1]) == {'ordinal':0,'endpoint':'protocol_request','args':[[1]],'kwargs':{},
        'before':1.,'error':"ValueError('real failure')",'after':1.5}


def test_returned_shared_aliases_get_distinct_decoded_subtrees(tmp_path):
    shared=[1];value={'a':shared,'b':shared}
    pair=invoke_pair(tmp_path,lambda:SimpleNamespace(physical_time=0.,protocol_request=lambda:value))
    result=decoded(pair[1][1])['result'];result['a'].append(3)
    assert result['b']==[1]


def test_result_encoding_error_can_continue_when_error_row_fully_saved(tmp_path):
    state={'value':float('nan')}
    tape=candidate.SerializedOnceTape(SimpleNamespace(physical_time=0.,protocol_request=lambda:state['value']),tmp_path/'api')
    with pytest.raises(ValueError):tape.protocol_request()
    state['value']=3;tape.protocol_request()
    assert tape.capture_failure is None and [decoded(tape,i)['ordinal'] for i in range(2)]==[0,1]


def test_diagnostic_failure_is_sticky_and_retains_accepted_prefix(tmp_path,monkeypatch):
    calls=[];session=SimpleNamespace(physical_time=0.,protocol_request=lambda:calls.append(1) or 3)
    tape=candidate.SerializedOnceTape(session,tmp_path/'api');tape.protocol_request()
    original=(tape.directory/'000000.json.gz').read_bytes()
    def fail(*args):raise OSError('full disk')
    monkeypatch.setattr(candidate,'write_row',fail)
    with pytest.raises(OSError,match='full disk'):tape.protocol_request()
    with pytest.raises(RuntimeError,match='prior_capture_failure'):tape.protocol_request()
    assert len(calls)==2 and len(tape.rows)==1 and tape.capture_failure['ordinal']==1
    assert (tape.directory/'000000.json.gz').read_bytes()==original


def test_unpaired_unicode_is_not_silently_escaped_into_success(tmp_path):
    tapes=[]
    for label,cls in [('old',old.Tape),('new',candidate.SerializedOnceTape)]:
        tape=cls(SimpleNamespace(physical_time=0.,protocol_request=lambda:'\ud800'),tmp_path/label)
        with pytest.raises(UnicodeEncodeError) as caught:tape.protocol_request()
        assert caught.value.encoding=='utf-8' and caught.value.reason=='surrogates not allowed'
        assert not tape.rows;tapes.append(tape)
    # Error offsets/partial bytes differ when a whole row is written at once;
    # neither path certifies a row, and the new recorder refuses continuation.
    assert tapes[1].capture_failure is not None


@pytest.mark.parametrize('value',['\ud83d\ude00',{'\ud83d\ude00':1,'😀':2},
    {'😀':1,'\ud83d\ude00':2},['literal \\ud800', '\ud83d\ude00']])
def test_surrogate_pair_normalization_and_key_collision_match_legacy(tmp_path,value):
    invoke_pair(tmp_path,lambda:SimpleNamespace(physical_time=0.,protocol_request=lambda:value), (value,))


def test_surrogate_fallback_does_not_reenumerate_stateful_caller():
    class Stateful(dict):
        def __init__(self):super().__init__(x='\ud83d\ude00');self.count=0
        def items(self):self.count+=1;return super().items()
    value=Stateful();text=candidate.encode(value)
    assert value.count==1 and json.loads(text)=={'x':'😀'}


def test_exclusive_directory_and_endpoint_whitelist(tmp_path):
    session=SimpleNamespace(physical_time=0.)
    tape=candidate.SerializedOnceTape(session,tmp_path/'api')
    with pytest.raises(FileExistsError):candidate.SerializedOnceTape(session,tmp_path/'api')
    with pytest.raises(ValueError,match='unclassified_endpoint'):tape.offline_diagnostics()


def test_short_write_fails_instead_of_certifying_partial_row(tmp_path,monkeypatch):
    class Short:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def write(self,text):return len(text)-1
    monkeypatch.setattr(candidate.gzip,'open',lambda *a,**k:Short())
    with pytest.raises(OSError,match='short_row_write'):candidate.write_row(tmp_path/'row.gz','{}')


def test_saved_actual005_first_and_last_each_endpoint_ordered_parity(tmp_path):
    # Closed historical source only. No NativeSession or model is invoked.
    case=old.OUT/'original_low_wip_prepare_005'
    bootstrap=old.read(old.OUT/'original_cooperative_bridge_prepare_001/bridge/preregistered_protocol.json')['bootstrap_pins']
    assert old.sha(case/'api/manifest.jsonl')==bootstrap['api/manifest.jsonl']
    manifest=[json.loads(line) for line in (case/'api/manifest.jsonl').read_text().splitlines()]
    endpoints={}
    for item in manifest:
        endpoints.setdefault(item['endpoint'],[item,item])[1]=item
    assert set(endpoints)==old.ENDPOINTS
    for endpoint, entries in endpoints.items():
        for position,item in enumerate(entries):
            path=case/'api'/item['path'];assert old.sha(path)==item['sha256']
            row=old.gzread(path)
            assert 'result' in row and 'error' not in row
            def factory():
                session=SimpleNamespace(physical_time=row['before'])
                def call(*args,**kwargs):
                    assert old.canonical(args)==row['args'] and old.canonical(kwargs)==row['kwargs']
                    session.physical_time=row['after'];return deepcopy(row['result'])
                setattr(session,endpoint,call);return session
            sub=tmp_path/f'{endpoint}_{position}';sub.mkdir()
            pair=invoke_pair(sub,factory,tuple(row['args']),row['kwargs'],endpoint)
            actual=decoded(pair[1][1]);actual['ordinal']=row['ordinal']
            assert ordered(actual)==ordered(row)


def test_original_tape_function_and_globals_not_replaced():
    assert candidate.SerializedOnceTape.__init__ is not old.Tape.__init__
    assert candidate.SerializedOnceTape.physical_time is old.Tape.physical_time
    assert old.sha(old.__file__)==candidate.REFERENCE_SHA256
    assert old.Tape.__getattr__.__module__==old.__name__
