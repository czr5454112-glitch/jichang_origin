"""Small fabricated typed bodies; no historical fixture/native/model execution."""
import copy
import hashlib
import struct

import pytest

from scripts.experiments.g31_ics_circulation import planning_capture_v2_batched_digest as c


def body():
    job = {'business_bag_id': 'job-甲', 'origin': 0, 'destination': 9,
        'arrival': .25, 'deadline': 90., 'storage_node': 4, 'storage_release_at': 5.,
        'storage_min_dwell': 2., 'load_seconds': 1., 'unload_seconds': 1.5,
        'hold_seconds': .5, 'protected_service': True, 'allow_suffix_reroute': False,
        'status': 'loaded', 'loaded_at': .5, 'storage_entered_at': -0., 'storage_released_at': -1.}
    local = {'schema': 'g31.planning_capture.v1', 'message_id': 'opaque',
        'source_owner': 'A', 'target_owner': 'B', 'publication_sequence': 7,
        'captured_at': 10., 'valid_until': 20., 'static_contract_sha256': 'a'*64,
        'semantics': {k: 'fixed-'+k for k in ('queue_discipline', 'resource_semantics',
            'event_semantics', 'scorer_mode', 'merge_grant_rule', 'merge_grant_timing_mode')},
        'jobs': [job], 'trays': [{'tray_id': 'T', 'business_bag_id': 'job-甲', 'mode': 'loaded',
            'ready_kind': 'known', 'node': 0, 'edge_from': -1, 'edge_to': -1, 'reception_node': 0,
            'generation': 3, 'traversal_id': 4, 'available_at': 10., 'service_ready_at': 11.,
            'load_complete_at': .5, 'service_ready_known': True, 'committed_prefix': [0, 2]}],
        'nodes': [{'node':0,'occupancy':1,'actual_available':2,'unrepresented_occupancy':0}],
        'known_faults': [{'from':0,'to':3,'active':False,'received_at':9.}],
        'coverage': {'scope':'local','complete_for_declared_local_scope':True,'local_node_ids':[0,2],
            'tray_ids':['T'],'business_bag_ids':['job-甲'],'unrepresented_occupancy':0,'future_arrivals_included':False}}
    local['semantics']['minimum_service_seconds'] = .001
    ext = {'schema':'g31.planning_extension.v2','source_owner':'A','captured_at':10.,
        'terminal_receipts':[{'receipt_id':'r','source_local_sequence':1,'source_owner':'A',
            'event':'UNLOAD','status':'complete','business_bag_id':'old','destination':0,'tray_id':'T','completed_at':8.}],
        'completion_coverage':{'scope':'own','complete_for_declared_scope':True,'through':10.,
            'source_owned_destination_nodes':[0,2],'future_events_included':False,'completed_business_bag_ids':['old']},
        'submitted_physical_actions':[{'request_id':'q','kind':'route','source_owner':'A',
            'last_delivered_ack':{'sequence':2,'delivered_at':9.,'status':'updated'}},
            {'request_id':'pending','kind':'transfer','source_owner':'A','last_delivered_ack':None}],
        'action_coverage':{'scope':'own','through':10.,'complete_for_declared_scope':True,
            'includes_unsubmitted_python_plans':False,'uses_hidden_execution_truth':False,
            'submitted_request_ids':['q','pending'],'unresolved_request_ids':['pending']}}
    return {'schema':'g31.planning_capture.v2','local_capture':local,'extension':ext}


def exact(value):
    expected = c.reference_bytes_v2(value)
    assert c.typed_bytes_v2(value) == expected
    assert c.capture_digest_v2(value) == c.original.capture_digest_v2(value) == hashlib.sha256(expected).hexdigest()
    return expected


def error(function, value):
    try: function(value)
    except Exception as exc: return type(exc), exc.args
    pytest.fail('expected an exception')


def test_complete_bytes_outer_identity_and_inverse_AST():
    original_globals = dict(c.original.__dict__)
    assert exact(body())
    p = c.source_proof()
    assert p['only_job_loop_body_changed'] and p['inverse_AST_exact']
    assert p['prefix_format'] == '>QQddQdddddBB' and p['suffix_format'] == '>ddd'
    assert c._REFERENCE_BUFFER.__code__ is c.original.capture_digest_v2.__code__
    assert c._BATCHED_BUFFER.__code__ is c.original.capture_digest_v2.__code__
    assert all(c.original.__dict__[k] is v for k, v in original_globals.items())


@pytest.mark.parametrize('field', list(body()['local_capture']['jobs'][0]))
def test_every_job_field_changes_complete_bytes(field):
    a = body(); b = copy.deepcopy(a); value = b['local_capture']['jobs'][0][field]
    b['local_capture']['jobs'][0][field] = (not value if type(value) is bool else value+'!' if type(value) is str else value+1)
    assert exact(a) != exact(b)


@pytest.mark.parametrize('field', ['origin','destination','storage_node'])
@pytest.mark.parametrize('value', [-1, -(1<<129)+3, (1<<130)+7, True])
def test_uint64_mask_and_bool_integer_slots(field, value):
    b=body();b['local_capture']['jobs'][0][field]=value;exact(b)


@pytest.mark.parametrize('bits', ['0000000000000000','8000000000000000','7ff0000000000000',
    'fff0000000000000','7ff8000000000042','fff8000000000042','7ff0000000000001'])
def test_float_ieee_bytes_nonfinite_and_signed_zero(bits):
    b=body();v=struct.unpack('>d',bytes.fromhex(bits))[0]
    for field in ('arrival','deadline','storage_released_at'):b['local_capture']['jobs'][0][field]=v
    output=exact(b);assert struct.pack('>d',v) in output
    if bits=='8000000000000000':
        positive=body()
        for field in ('arrival','deadline','storage_released_at'):positive['local_capture']['jobs'][0][field]=0.
        assert output != exact(positive)


@pytest.mark.parametrize('value', [True,False,0,-7,(1<<63)-1,1<<100])
def test_builtin_integer_double_conversion_including_fallback(value):
    b=body();b['local_capture']['jobs'][0]['arrival']=value;exact(b)


@pytest.mark.parametrize('value', ['', 'abc\x00def', '甲😀', '\ud800', '\ud83d\ude00'])
def test_UTF8_length_and_encoding_errors(value):
    b=body();b['local_capture']['jobs'][0]['business_bag_id']=value
    if any(0xd800<=ord(x)<=0xdfff for x in value):
        assert error(c.capture_digest_v2,b)==error(c.original.capture_digest_v2,b)
        assert error(c.typed_bytes_v2,b)==error(c.reference_bytes_v2,b)
    else:exact(b)


def test_empty_order_and_shared_aliases_are_preserved():
    b=body();job=b['local_capture']['jobs'][0];b['local_capture']['jobs']=[job,job]
    before=c.reference_bytes_v2(b);exact(b)
    assert b['local_capture']['jobs'][0] is b['local_capture']['jobs'][1]
    assert before==c.reference_bytes_v2(b)
    other=copy.deepcopy(job);other['business_bag_id']='other'
    b['local_capture']['jobs']=[job,other];left=exact(b)
    b['local_capture']['jobs'].reverse();assert exact(b)!=left
    for field in ('jobs','trays','nodes','known_faults'):b['local_capture'][field]=[]
    for field in ('terminal_receipts','submitted_physical_actions'):b['extension'][field]=[]
    exact(b)


@pytest.mark.parametrize('defect', ['wrong_int','wrong_double','large_double','missing_late',
    'early_unicode_late_missing','early_double_late_missing','wrong_bool','wrong_job','missing_outer'])
def test_bad_type_overflow_and_original_first_error_order(defect):
    b=body();j=b['local_capture']['jobs'][0]
    if defect=='wrong_int':j['origin']=1.5
    elif defect=='wrong_double':j['arrival']='wrong'
    elif defect=='large_double':j['arrival']=1<<20000
    elif defect=='missing_late':del j['storage_released_at']
    elif defect=='early_unicode_late_missing':j['business_bag_id']='\ud800';del j['storage_released_at']
    elif defect=='early_double_late_missing':j['arrival']='wrong';del j['storage_released_at']
    elif defect=='wrong_bool':j['protected_service']='truthy';exact(b);return
    elif defect=='wrong_job':b['local_capture']['jobs']=[None]
    else:del b['local_capture']['message_id']
    assert error(c.capture_digest_v2,b)==error(c.original.capture_digest_v2,b)
    assert error(c.typed_bytes_v2,b)==error(c.reference_bytes_v2,b)


def hooked(kind, events):
    b=body();j=b['local_capture']['jobs'][0]
    if kind=='text':
        class Value:
            def encode(self, encoding):events.append(('encode',encoding));return b'hook'
        j['status']=Value()
    elif kind=='integer':
        class Value:
            def __and__(self, other):events.append(('and',other));return 5
        j['origin']=Value()
    elif kind=='double':
        class Value:
            def __float__(self):events.append('float');return 1.25
        j['arrival']=Value()
    elif kind=='boolean':
        class Value:
            def __bool__(self):events.append('bool');return True
        j['protected_service']=Value()
    elif kind=='dict':
        class Value(dict):
            def __getitem__(self, key):events.append(('getitem',key));return super().__getitem__(key)
        b['local_capture']=Value(b['local_capture'])
    elif kind=='list':
        class Value(list):
            def __iter__(self):events.append('iter');return super().__iter__()
        b['local_capture']['jobs']=Value([j])
    elif kind=='str_subclass':
        class Value(str):
            def encode(self, encoding):events.append(('encode',encoding));return super().encode(encoding)
        j['status']=Value('loaded')
    return b


@pytest.mark.parametrize('kind', ['text','integer','double','boolean','dict','list','str_subclass'])
def test_custom_hook_count_and_order_equal_one_original_execution(kind, monkeypatch):
    expected_events=[];expected=c.original.capture_digest_v2(hooked(kind,expected_events))
    actual_events=[];b=hooked(kind,actual_events);calls=[]
    def fallback(value):calls.append(value);return c.original.capture_digest_v2(value)
    monkeypatch.setattr(c,'_ORIGINAL',fallback)
    assert c.capture_digest_v2(b)==expected
    assert actual_events==expected_events and len(calls)==1 and calls[0] is b


def test_custom_key_and_metaclass_probe_never_runs_hooks():
    calls=[]
    class Key:
        def __hash__(self):return hash('schema')
        def __eq__(self, other):calls.append('keyeq');return False
    b={Key():'unused',**body()};calls.clear()
    with pytest.raises(c._Unsupported):c._builtin_tree(b)
    assert calls==[]
    class Meta(type):
        def __eq__(self, other):calls.append('metaeq');raise AssertionError('metaclass invoked')
    class Value(metaclass=Meta):pass
    b=body();b['unused']=Value()
    with pytest.raises(c._Unsupported):c._builtin_tree(b)
    assert calls==[]
    assert c.capture_digest_v2(b)==c.original.capture_digest_v2(b)


def test_unused_cycle_and_tuple_fall_back_once_without_rejecting_original_domain(monkeypatch):
    b=body();b['unused']=b;calls=[]
    original=c.original.capture_digest_v2
    monkeypatch.setattr(c,'_ORIGINAL',lambda x:(calls.append(x),original(x))[1])
    assert c.capture_digest_v2(b)==original(b) and len(calls)==1
    b=body();b['local_capture']['jobs']=tuple(b['local_capture']['jobs'])
    assert c.capture_digest_v2(b)==original(b) and len(calls)==2


@pytest.mark.parametrize('stage', ['preflight','writer','hash'])
@pytest.mark.parametrize('kind', [MemoryError,RuntimeError])
def test_resource_unexpected_error_never_falls_back_or_certifies(monkeypatch,stage,kind):
    error_instance=kind('injected');calls=[]
    def fail(*a):raise error_instance
    monkeypatch.setattr(c,'_ORIGINAL',lambda *a:calls.append('fallback'))
    if stage=='preflight':monkeypatch.setattr(c,'_builtin_tree',fail)
    elif stage=='writer':monkeypatch.setattr(c,'_BATCHED_BUFFER',fail)
    else:monkeypatch.setattr(c,'hashlib',type('HashFacade',(),{'sha256':staticmethod(fail)}))
    with pytest.raises(kind) as caught:c.capture_digest_v2(body())
    assert caught.value is error_instance and calls==[]


def test_failed_call_does_not_mutate_or_poison_next_call():
    valid=body();before=copy.deepcopy(valid);expected=exact(valid)
    broken=body();broken['local_capture']['jobs'][0]['status']='\ud800'
    with pytest.raises(UnicodeEncodeError):c.capture_digest_v2(broken)
    assert valid==before and exact(valid)==expected
    out=c.typed_bytes_v2(valid);assert type(out) is bytes
    valid['local_capture']['jobs'][0]['deadline']+=1
    assert c.typed_bytes_v2(valid)!=out


def test_job_numeric_groups_match_handwritten_byte_layout():
    j=body()['local_capture']['jobs'][0];out=bytearray();c._write_job_batched(out,j)
    t=lambda v:struct.pack('>Q',len(v.encode('utf8')))+v.encode('utf8')
    expected=t(j['business_bag_id'])
    for field in ('origin','destination'):expected+=struct.pack('>Q',j[field]&c._MASK)
    for field in ('arrival','deadline'):expected+=struct.pack('>d',j[field])
    expected+=struct.pack('>Q',j['storage_node']&c._MASK)
    for field in ('storage_release_at','storage_min_dwell','load_seconds','unload_seconds','hold_seconds'):
        expected+=struct.pack('>d',j[field])
    expected+=bytes([int(j['protected_service']),int(j['allow_suffix_reroute'])])+t(j['status'])
    for field in ('loaded_at','storage_entered_at','storage_released_at'):expected+=struct.pack('>d',j[field])
    assert bytes(out)==expected
