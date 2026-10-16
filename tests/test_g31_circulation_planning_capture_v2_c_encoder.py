"""Draft full-byte gate. No binary means failure, never a skipped C acceptance.

Later owned runner must supply both G31_TYPED_ENCODER_BINARY and its preregistered
G31_TYPED_ENCODER_SHA256, and explicitly archive the imported fixture test source.
No actual fixture, predictor, simulator or benchmark belongs in this gate.
"""
import copy
import hashlib
import os
import struct
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import planning_capture_v2_c_encoder as c
from test_g31_circulation_planning_v2_batched_digest import body, hooked


@pytest.fixture(scope='session')
def candidate():
    path, digest = os.environ.get('G31_TYPED_ENCODER_BINARY'), os.environ.get('G31_TYPED_ENCODER_SHA256')
    assert path and digest, 'An explicitly built/pinned C extension is mandatory; source-only is not a pass.'
    return c.load_candidate(path, digest, c.source_proof())


def exact(candidate, value, *, direct=True):
    expected = c.reference_bytes_v2(value)
    if direct:
        actual = candidate.module.try_typed_bytes(value)
        assert type(actual) is bytes and actual == expected
    assert candidate.typed_bytes_v2(value) == expected
    assert candidate.capture_digest_v2(value) == c.original.capture_digest_v2(value) == hashlib.sha256(expected).hexdigest()
    return expected


def failure(function, value):
    try: function(value)
    except Exception as error: return type(error), error.args
    pytest.fail('expected failure')


def scalar_paths(value, prefix=()):
    if type(value) is dict:
        for key, child in value.items(): yield from scalar_paths(child, prefix+(key,))
    elif type(value) is list:
        for index, child in enumerate(value): yield from scalar_paths(child, prefix+(index,))
    else: yield prefix, value


PATHS = tuple(scalar_paths(body()))


def test_original_oracle_and_direct_C_bound(candidate):
    proof = c.source_proof()
    assert proof['oracle_outer_code_identity'] and proof['oracle_local_identity']
    assert proof['resource_exception_equivalence'] is False
    assert exact(candidate, body())


@pytest.mark.parametrize('path,value', PATHS)
def test_every_consumed_scalar_field_and_position(candidate, path, value):
    left = body(); right = copy.deepcopy(left); parent = right
    for part in path[:-1]: parent = parent[part]
    if value is None:
        parent[path[-1]] = {'sequence': 22, 'delivered_at': 9., 'status': 'received'}
    else:
        parent[path[-1]] = not value if type(value) is bool else value+'!' if type(value) is str else value+1
    assert exact(candidate, left) != exact(candidate, right)


@pytest.mark.parametrize('value', [-1, -(1<<129)+3, (1<<130)+7, True, False, 0, (1<<64)-1, 1<<64])
def test_uint64_mask_all_numeric_groups(candidate, value):
    value_body = body(); local = value_body['local_capture']; extension = value_body['extension']
    local['publication_sequence'] = value
    for key in ('origin','destination','storage_node'): local['jobs'][0][key] = value
    for key in ('node','edge_from','edge_to','reception_node','generation','traversal_id'): local['trays'][0][key] = value
    local['trays'][0]['committed_prefix'] = [value]
    for key in ('node','occupancy','actual_available','unrepresented_occupancy'): local['nodes'][0][key] = value
    local['known_faults'][0].update({'from':value,'to':value})
    local['coverage']['local_node_ids'] = [value]; local['coverage']['unrepresented_occupancy'] = value
    extension['terminal_receipts'][0].update(source_local_sequence=value,destination=value)
    extension['completion_coverage']['source_owned_destination_nodes'] = [value]
    extension['submitted_physical_actions'][0]['last_delivered_ack']['sequence'] = value
    exact(candidate, value_body)


@pytest.mark.parametrize('bits', ['0000000000000000','8000000000000000','0000000000000001',
    '0010000000000000','7fefffffffffffff','7ff0000000000000','fff0000000000000',
    '7ff8000000000042','fff8000000000042','7ff0000000000001'])
def test_all_float_fields_preserve_original_pack_bits(candidate, bits):
    value = struct.unpack('>d', bytes.fromhex(bits))[0]; data = body()
    for path, old in scalar_paths(data):
        if type(old) is float:
            parent = data
            for part in path[:-1]: parent = parent[part]
            parent[path[-1]] = value
    result = exact(candidate, data)
    assert struct.pack('>d', value) in result


@pytest.mark.parametrize('value,direct', [(True,True),(False,True),(0,True),(-7,True),
    (-(1<<63),True),((1<<63)-1,True),(1<<63,False),(1<<100,False)])
def test_exact_integer_double_conversion(candidate, value, direct):
    data=body(); data['local_capture']['jobs'][0]['arrival']=value
    assert (candidate.module.try_typed_bytes(data) is NotImplemented) == (not direct)
    exact(candidate, data, direct=direct)


@pytest.mark.parametrize('value', ['', 'abc\x00def', '甲😀', '\ud800', '\ud83d\ude00'])
def test_strict_UTF8_and_first_encoding_error(candidate, value):
    data=body(); data['local_capture']['jobs'][0]['business_bag_id']=value
    if any(0xd800<=ord(x)<=0xdfff for x in value):
        assert failure(candidate.capture_digest_v2,data)==failure(c.original.capture_digest_v2,data)
        with pytest.raises(UnicodeEncodeError): candidate.module.try_typed_bytes(data)
    else: exact(candidate,data)


@pytest.mark.parametrize('kind', ['text','integer','double','boolean','dict','list','str_subclass'])
def test_unsupported_attempt_invokes_no_supplied_hook_and_one_original(candidate, kind):
    expected_events=[]; expected=c.original.capture_digest_v2(hooked(kind,expected_events))
    events=[]; data=hooked(kind,events)
    assert candidate.module.try_typed_bytes(data) is NotImplemented and events==[]
    assert candidate.capture_digest_v2(data)==expected and events==expected_events


def test_custom_key_is_not_compared_during_probe(candidate):
    events=[]
    class Key:
        def __hash__(self): return hash('schema')
        def __eq__(self, other): events.append(('eq',other)); return False
    data={Key():'unused',**body()}; events.clear()
    assert candidate.module.try_typed_bytes(data) is NotImplemented and events==[]
    expected=c.original.capture_digest_v2(data); expected_events=list(events); events.clear()
    assert candidate.capture_digest_v2(data)==expected and events==expected_events


def test_raising_hook_once_before_later_missing_field(candidate):
    events=[]
    class Value:
        def __float__(self):
            events.append('float')
            raise RuntimeError('original-hook-failure')
    data=body(); data['local_capture']['jobs'][0]['arrival']=Value()
    del data['local_capture']['jobs'][0]['storage_released_at']
    assert candidate.module.try_typed_bytes(data) is NotImplemented and events==[]
    expected=failure(c.original.capture_digest_v2,data); expected_events=list(events); events.clear()
    assert failure(candidate.capture_digest_v2,data)==expected and events==expected_events==['float']


def test_tuple_sequence_preserves_original_fallback_domain(candidate):
    data=body();data['local_capture']['jobs']=tuple(data['local_capture']['jobs'])
    assert candidate.module.try_typed_bytes(data)is NotImplemented
    exact(candidate,data,direct=False)


def test_unused_custom_values_cycles_and_consumed_aliases(candidate):
    class Forbidden:
        def __bool__(self): raise AssertionError('unused value inspected')
    data=body(); data['unused']=Forbidden(); data['cycle']=data
    job=data['local_capture']['jobs'][0]; data['local_capture']['jobs']=[job,job]
    exact(candidate,data)
    assert data['local_capture']['jobs'][0] is data['local_capture']['jobs'][1]


def test_sequence_order_and_empty_sections(candidate):
    data=body(); other=copy.deepcopy(data['local_capture']['jobs'][0]); other['business_bag_id']='other'
    data['local_capture']['jobs'].append(other); first=exact(candidate,data)
    data['local_capture']['jobs'].reverse(); assert exact(candidate,data)!=first
    for key in ('jobs','trays','nodes','known_faults'): data['local_capture'][key]=[]
    for key in ('terminal_receipts','submitted_physical_actions'): data['extension'][key]=[]
    exact(candidate,data)


@pytest.mark.parametrize('defect', ['wrong_int','wrong_double','large_double','missing_late',
    'early_unicode_late_missing','early_double_late_missing','wrong_job','missing_outer'])
def test_original_error_class_args_and_order(candidate, defect):
    data=body(); job=data['local_capture']['jobs'][0]
    if defect=='wrong_int':job['origin']=1.5
    elif defect=='wrong_double':job['arrival']='wrong'
    elif defect=='large_double':job['arrival']=1<<20000
    elif defect=='missing_late':del job['storage_released_at']
    elif defect=='early_unicode_late_missing':job['business_bag_id']='\ud800';del job['storage_released_at']
    elif defect=='early_double_late_missing':job['arrival']='wrong';del job['storage_released_at']
    elif defect=='wrong_job':data['local_capture']['jobs']=[None]
    else:del data['local_capture']['message_id']
    assert failure(candidate.capture_digest_v2,data)==failure(c.original.capture_digest_v2,data)
    assert failure(candidate.typed_bytes_v2,data)==failure(c.reference_bytes_v2,data)


@pytest.mark.parametrize('error_kind',[MemoryError,RecursionError,RuntimeError])
def test_fallback_marker_once_and_real_exception_never_retried(monkeypatch,error_kind):
    data=body(); calls=[]
    monkeypatch.setattr(c,'_ORIGINAL',lambda item:(calls.append(item),'original')[1])
    assert c._digest(lambda item:NotImplemented,data)=='original' and calls==[data]
    calls.clear(); error=error_kind('injected')
    def fail(item):raise error
    with pytest.raises(error_kind) as caught:c._digest(fail,data)
    assert caught.value is error and calls==[]
    with pytest.raises(ValueError):c._digest(lambda item:bytearray(b'wrong'),data)
    assert calls==[]


def test_failure_does_not_mutate_or_poison_next_call(candidate):
    data=body(); before=copy.deepcopy(data); result=exact(candidate,data)
    broken=body();broken['extension']['terminal_receipts'][0]['status']='\ud800'
    with pytest.raises(UnicodeEncodeError):candidate.capture_digest_v2(broken)
    assert data==before and exact(candidate,data)==result
    data['local_capture']['jobs'][0]['deadline']+=1
    assert candidate.typed_bytes_v2(data)!=result and type(result)is bytes


def test_fake_module_has_no_actual_C_authority():
    with pytest.raises(ValueError,match='actual_extension_required'):
        c.Candidate(SimpleNamespace(),{})
