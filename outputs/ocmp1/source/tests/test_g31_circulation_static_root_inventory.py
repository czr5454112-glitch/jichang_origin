"""DRAFT synthetic gate. No accepted C provider, native/model or saved raw.

There are no bare sibling-test imports. The private Python publisher fixture is
explicitly not accepted by the real verified-C binder. One private constructor
fixture bypasses only native admission to exercise subsequent unchanged checks;
that fixture never becomes a production entry point.
"""
from __future__ import annotations

import ast
import builtins
import copy
import dis
import inspect
import struct
import sys
import textwrap
from types import CodeType, FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import initial_owner_route_static_inventory as m
from scripts.experiments.g31_ics_circulation import run_static_root_inventory_pure as runner


def live_fixture():
    publisher = m.owned.publisher
    raw = publisher.reference._bind_provider(publisher.owned.normalization.normalize)
    return m.owned._compose(publisher._compose(raw))


def binding_fixture():
    return m.bind(live_fixture())


class Session:
    def __init__(self):
        self.physical_time = 4.171
        self.calls = []

    def advance_to(self, now, **kwargs):
        self.calls.append(('advance_to', now, kwargs))
        return {'status': 'reached', 'physical_time': now, 'horizon_complete': True}


def root_fixture(binding):
    root = object.__new__(binding.CapturedRequest)
    root.session = Session()
    root.client = binding.make_client(root.session)
    root.native, root.accepted = object(), {}
    root.request_id = 'synthetic:static-inventory'
    root.started_ns, root.deadline_ns, root.cutoff_ns = 1, 100_000_001, 60_000_001
    root.choice, root.command_id = 'native_default', None
    root.state, root.hop = 'closed_native_default_first_hop', {'from': 0, 'to': 1, 'observed_at': 4.171}
    root.events = [{'stage': 'synthetic', 'value': {'x': -0.0}}]
    root.initial_endpoint_records = [{'fixture': 'A0'}, {'fixture': 'A1'}]
    root.B_endpoint_records = [{'fixture': 'B0', 'value': (1, 2)}]
    root.last_boundary = None
    return root


def synthetic_constructor(binding):
    request = m.integration.request
    adapter = SimpleNamespace(**{**vars(request.adapter), '_valid_handle': lambda *args: True})
    request_facade = SimpleNamespace(**{**vars(request), 'adapter': adapter})
    return m.private(binding.ActualAdvanceChain.__init__, {'request': request_facade})


def construct(binding, root, policies=None):
    chain = object.__new__(binding.ActualAdvanceChain)
    synthetic_constructor(binding)(chain, root.session, root.client, root, policies or {})
    return chain


def profiles(function):
    counts = {}
    previous = sys.getprofile()
    def observer(frame, event, arg):
        if event == 'call':
            code = frame.f_code
            counts[code] = counts.get(code, 0) + 1
    sys.setprofile(observer)
    try:
        value = function()
    finally:
        sys.setprofile(previous)
    return value, counts


def test_cold_original_inventories_once_and_warm_no_source_inspection():
    binding, cold = profiles(binding_fixture)
    assert cold.get(m.integration.gated.inventory.__code__) == 1
    assert cold.get(m.integration.collection_inventory.__code__) == 1
    value = root_fixture(binding)
    _, warm = profiles(lambda: construct(binding, value))
    for fn in (m.integration.gated.inventory, m.integration.collection_inventory,
               m.integration.gate.tree, m.integration.generated_template_inventory,
               m.integration._code_digest, inspect.getsource):
        assert warm.get(fn.__code__, 0) == 0
    assert value._observation_advance_chain.root is value


@pytest.mark.parametrize('order', [(), ('A', 'B'), ('B', 'A')])
def test_original_method_inventory_exact_order_and_function_code_identity(order):
    binding = binding_fixture()
    root = root_fixture(binding)
    policies = {name: object.__new__(binding.TracedContinuationOwner) for name in order}
    original = m.integration.gated.inventory(policies, root.client)
    cached = binding._static_inventory.methods(policies, root.client)
    assert list(original) == list(cached)
    for key in original:
        assert list(original[key]) == list(cached[key])
        assert original[key]['function'] is cached[key]['function']
        assert original[key]['code'] is cached[key]['code']
        assert original[key]['source_sha256'] == cached[key]['source_sha256']


def test_every_root_owns_new_proof_containers():
    binding = binding_fixture()
    first = construct(binding, root_fixture(binding))
    second = construct(binding, root_fixture(binding))
    assert first.method_inventory == second.method_inventory
    assert first.collection_source_inventory == second.collection_source_inventory
    key = next(iter(first.method_inventory))
    first.method_inventory[key]['source_sha256'] = 'bad'
    first.collection_source_inventory['generated_template']['ordered_code_hooks'].clear()
    assert second.method_inventory[key]['source_sha256'] != 'bad'
    assert len(second.collection_source_inventory['generated_template']['ordered_code_hooks']) == 6
    assert len(binding.collection_inventory()['generated_template']['ordered_code_hooks']) == 6


def test_public_constructor_retains_real_native_admission_rejection():
    binding = binding_fixture()
    root = root_fixture(binding)
    with pytest.raises(ValueError, match='accepted_session'):
        binding.ActualAdvanceChain(root.session, root.client, root, {})
    assert root.session.calls == [] and not hasattr(root, '_observation_advance_chain')


@pytest.mark.parametrize('method', ['collect', 'observe_after_boundary', 'drain_and_finish_if_closed', '_record'])
def test_dynamic_wrong_root_method_still_rejected(method):
    binding = binding_fixture()
    root = root_fixture(binding)
    setattr(root, method, (lambda self: None).__get__(root))
    with pytest.raises(ValueError):
        construct(binding, root)
    assert root.session.calls == []


def test_original_constructor_AST_code_classcell_and_new_exact_drain():
    binding = binding_fixture()
    old = binding._source_binding.ActualAdvanceChain.__init__
    new = binding.ActualAdvanceChain.__init__
    assert new.__code__ is old.__code__ and new.__closure__ is old.__closure__
    assert ast.dump(ast.parse(textwrap.dedent(inspect.getsource(new)))) == ast.dump(
        ast.parse(textwrap.dedent(inspect.getsource(old))))
    root = root_fixture(binding)
    chain = construct(binding, root)
    assert type(chain) is binding.ActualAdvanceChain
    assert binding._actual_root_drain(root, root.session.physical_time)['horizon_complete']
    assert len(chain.calls) == len(root.session.calls) == 1
    with pytest.raises(ValueError, match='missing_actual_root_chain'):
        m.integration._actual_root_drain(root, root.session.physical_time)


def test_original_single_use_and_foreign_session_checks_remain():
    binding = binding_fixture()
    root = root_fixture(binding)
    construct(binding, root)
    with pytest.raises(ValueError, match='single_use_chain'):
        construct(binding, root)
    fresh = root_fixture(binding)
    with pytest.raises(ValueError, match='foreign_session'):
        synthetic_constructor(binding)(object.__new__(binding.ActualAdvanceChain), Session(),
            fresh.client, fresh, {})


@pytest.mark.parametrize('mutation', ['transport_subclass', 'trace_type', 'trace_foreign_client'])
def test_exact_transport_and_current_trace_binding_remain(mutation):
    binding = binding_fixture()
    root = root_fixture(binding)
    if mutation == 'transport_subclass':
        class Subclass(type(root.client)): pass
        replacement = object.__new__(Subclass)
        replacement.__dict__.update(vars(root.client))
        root.client = replacement
    elif mutation == 'trace_type':
        root.client._root_outbox_trace = SimpleNamespace(client=root.client)
    else:
        root.client._root_outbox_trace.client = object()
    with pytest.raises(ValueError, match='unknown_exact_transport'):
        construct(binding, root)
    assert root.session.calls == []


@pytest.mark.parametrize('mutate', ['owner', 'session', 'client', 'activate', 'one_owner'])
def test_all_current_policy_instance_checks_remain(mutate):
    binding = binding_fixture()
    root = root_fixture(binding)
    policies = {}
    for owner in ('A', 'B'):
        p = object.__new__(binding.TracedContinuationOwner)
        p.owner, p.session, p.client = owner, root.session, root.client
        policies[owner] = p
    if mutate == 'one_owner':
        policies.pop('B')
    elif mutate == 'activate':
        policies['A'].activate = (lambda self: None).__get__(policies['A'])
    else:
        setattr(policies['A'], mutate, object())
    with pytest.raises(ValueError, match='unknown_policy_instances'):
        construct(binding, root, policies)


@pytest.mark.parametrize('mutation', ['code', 'defaults', 'kwdefaults', 'globals', 'closure', 'attribute'])
def test_fixed_function_boundary_rejects_drift_without_source_parse(mutation):
    namespace = {'x': object(), '__builtins__': builtins.__dict__}
    def make():
        captured = {'a': [1]}
        def fn(value=([],), *, option=None):
            return captured, value, option
        return fn
    original = make()
    fn = FunctionType(original.__code__, namespace, 'fn', original.__defaults__, original.__closure__)
    fn.__kwdefaults__ = {'option': None}
    boundary = m._ProgramBoundary(functions=(fn,))
    if mutation == 'code':
        fn.__code__ = make().__code__.replace(co_name='changed')
    elif mutation == 'defaults':
        fn.__defaults__[0][0].append(7)
    elif mutation == 'kwdefaults':
        fn.__kwdefaults__['option'] = 1
    elif mutation == 'globals':
        namespace['x'] = object()
    elif mutation == 'closure':
        fn.__closure__[0].cell_contents['a'].append(2)
    else:
        fn.extra = True
    with pytest.raises(ValueError, match='static_'):
        boundary.check()


@pytest.mark.parametrize('mutation', ['add_method', 'replace_method', 'bases'])
def test_class_mapping_and_MRO_boundary(mutation):
    class First: pass
    class Second: pass
    class Example(First):
        def f(self): return 1
    boundary = m._ProgramBoundary(classes=(Example,))
    if mutation == 'add_method': Example.new = lambda self: 2
    elif mutation == 'replace_method': Example.f = lambda self: 2
    else: Example.__bases__ = (Second,)
    with pytest.raises(ValueError, match='static_class_or_MRO_changed'):
        boundary.check()


@pytest.mark.parametrize('descriptor', ['static', 'class', 'property_get', 'property_set', 'property_del'])
def test_exact_descriptor_underlying_code_mutation_rejected(descriptor):
    def function(*args): return None
    class Example: pass
    if descriptor == 'static':
        Example.value = staticmethod(function)
    elif descriptor == 'class':
        Example.value = classmethod(function)
    else:
        kwargs = {'fget': None, 'fset': None, 'fdel': None}
        kwargs[{'property_get': 'fget', 'property_set': 'fset', 'property_del': 'fdel'}[descriptor]] = function
        Example.value = property(**kwargs)
    original_descriptor = vars(Example)['value']
    boundary = m._ProgramBoundary(classes=(Example,))
    function.__code__ = function.__code__.replace(co_name='changed_underlying_code')
    assert vars(Example)['value'] is original_descriptor
    with pytest.raises(ValueError, match='static_function_changed'):
        boundary.check()


def test_distinct_NaN_payload_in_static_container_rejected():
    first = struct.unpack('>d', bytes.fromhex('7ff8000000000001'))[0]
    second = struct.unpack('>d', bytes.fromhex('7ff8000000000002'))[0]
    assert first.hex() == second.hex() == 'nan'
    value = {'nan': first}
    boundary = m._ProgramBoundary(containers=(value,))
    value['nan'] = second
    with pytest.raises(ValueError, match='static_proof_container_changed'):
        boundary.check()


@pytest.mark.parametrize('mutation', ['proof', 'template_code', 'alias', 'new_request_method'])
def test_real_static_dependencies_reject_mutation(monkeypatch, mutation):
    binding = binding_fixture()
    if mutation == 'proof':
        monkeypatch.setitem(m.integration.single._AST_PROOF, 'inserted_before_after_hooks', 5)
    elif mutation == 'template_code':
        fn = m.integration.single._TEMPLATE
        monkeypatch.setattr(fn, '__code__', fn.__code__.replace(co_name='changed_template'))
    elif mutation == 'alias':
        monkeypatch.setattr(m.integration.single.initial, 'validate_pair', lambda *a: None)
    else:
        binding.CapturedRequest.collect = lambda self: None
    with pytest.raises(ValueError, match='static_'):
        binding.collection_inventory()


def test_cached_proof_tampering_rejected_not_served():
    binding = binding_fixture()
    binding._static_inventory.collection['generated_template']['ordered_code_hooks'].clear()
    with pytest.raises(ValueError, match='static_proof_container_changed'):
        binding.collection_inventory()


def test_no_custom_hooks_in_static_shape():
    class Forbidden:
        def __eq__(self, other): raise AssertionError('custom equality')
        def __iter__(self): raise AssertionError('custom iteration')
    value = Forbidden()
    tree = {'opaque': value, 'signed_zero': -0.0, 'items': []}
    tree['items'].append(tree)
    boundary = m._ProgramBoundary(containers=(tree,))
    boundary.check()
    tree['signed_zero'] = 0.0
    with pytest.raises(ValueError): boundary.check()


def all_codes(code):
    yield code
    for value in code.co_consts:
        if type(value) is CodeType:
            yield from all_codes(value)


def test_branch_full_globals_and_all_publication_collection_paths_unchanged():
    binding = binding_fixture()
    branch = m.branch_function(binding)
    assert branch.__globals__['CapturedRequest'] is binding.CapturedRequest
    assert branch.__globals__['FixedDefaultRequest'] is binding.FixedDefaultRequest
    assert branch.__globals__['run_continuation'] is binding.run_continuation
    assert branch.__globals__['publish_root'] is binding.publish_root
    assert branch.__globals__['call_with_recorded_collection'] is binding.call_with_recorded_collection
    assert binding.run_continuation.__globals__['ActualAdvanceChain'] is binding.ActualAdvanceChain
    for fn in (branch, binding.run_continuation, binding.ActualAdvanceChain.__init__,
               binding.TRACKED_DRAIN, binding._actual_root_drain):
        for code in all_codes(fn.__code__):
            assert not {i.argval for i in dis.get_instructions(code)
                if i.opname in ('LOAD_GLOBAL', 'LOAD_NAME')
                and i.argval not in fn.__globals__ and not hasattr(builtins, i.argval)}


def test_static_cache_never_retains_current_root_or_client_and_checks_stay_explicit():
    binding = binding_fixture()
    root = root_fixture(binding)
    cache = binding._static_inventory
    construct(binding, root)
    assert not any(value is root or value is root.client or value is root.session
        for value in vars(cache).values())
    proof = m.binding_proof(binding)
    assert proof['dynamic_session_handle_transport_owner_ACK_current_checks_removed'] == 0
    assert not proof['cross_request_observation_or_result_cache']
    assert not proof['actual_C_support_or_campaign_ready_or_speed_claimed']
    assert not proof['per_sample_cycle_reclamation_certified']
    assert not proof['allocation_failure_equivalence_claimed']


def test_canonical_archive_absolute_relative_duplicate_agreement(tmp_path):
    root = tmp_path/'root'
    source = root/'pkg/a.py'
    files = runner.canonical_sources({str(source): b'a', 'pkg/a.py': b'a'}, root)
    assert files == {'pkg/a.py': b'a'}
    with pytest.raises(ValueError, match='canonical_duplicate_bytes'):
        runner.canonical_sources({str(source): b'a', 'pkg/a.py': b'b'}, root)


@pytest.mark.parametrize('name', ['../escape.py', '/absolute.py', 'a/../escape.py'])
def test_all_archive_targets_checked_before_any_write(tmp_path, name):
    root, output = tmp_path/'r', tmp_path/'o'
    with pytest.raises(ValueError, match='canonical_archive_key'):
        runner.archive_sources(root, output, {'valid.py': b'good', name: b'bad'})
    assert not output.exists()


def test_archive_never_writes_current_source_and_uses_short_contained_root(tmp_path):
    root, output = tmp_path/'r', tmp_path/'r/outputs/short'
    current = root/'pkg/a.py'
    current.parent.mkdir(parents=True)
    current.write_bytes(b'original')
    saved = runner.archive_sources(root, output, {'pkg/a.py': b'original'})
    assert current.read_bytes() == b'original'
    target = output/saved['pkg/a.py']
    assert target != current and target.is_relative_to(output/'source')
    assert target.read_bytes() == b'original'
    with pytest.raises(ValueError, match='archive_target_exists'):
        runner.archive_sources(root, output, {'pkg/a.py': b'original'})


def test_later_target_over_259_characters_prevents_even_first_archive_write(tmp_path):
    root, output = tmp_path/'r', tmp_path/'o'
    long_name = '/'.join(['segment'] * 40 + ['late.py'])
    assert len(str((output/'source'/long_name).resolve())) > 259
    with pytest.raises(ValueError, match='archive_containment_or_path_length'):
        runner.archive_sources(root, output, {'first.py': b'valid', long_name: b'too_long'})
    assert not output.exists()
    assert not (output/'source/first.py').exists()
