"""Synthetic fixed24 full-worker tests; no model, native or saved actual data."""
import copy
import gzip
from pathlib import Path
from types import FunctionType, SimpleNamespace
import pytest
import test_g31_circulation_initial_scoped_inputs_cost as previous_tests
from scripts.experiments.g31_ics_circulation import measure_owned_initial_bundle_six as m
from scripts.experiments.g31_ics_circulation import run_owned_initial_bundle_cost_pure as runner


@pytest.fixture
def fixture(tmp_path):
    factory=previous_tests.fixture.__wrapped__
    private=FunctionType(factory.__code__,{**factory.__globals__,'m':m},factory.__name__,factory.__defaults__,factory.__closure__)
    private.__kwdefaults__=factory.__kwdefaults__
    value=private(tmp_path)
    for row in value.plan['rows'].values():
        row['comparison_only_initial_scope_prediction']=row.pop('comparison_only_v2_prediction')
    previous_tests.write(value.output/'plan.json',value.plan)
    return value


def fake_worker(fixture, **kwargs):
    old=previous_tests.fake_worker
    private=FunctionType(old.__code__,{**old.__globals__,'m':m},old.__name__,old.__defaults__,old.__closure__)
    private.__kwdefaults__=old.__kwdefaults__
    return private(fixture,**kwargs)


def execute(fixture, **kwargs):
    function,calls,reads,pins=fake_worker(fixture,**kwargs)
    function(fixture.output,m.sha(fixture.output/'plan.json'))
    return m.read(fixture.output/'report.json'),m.read(fixture.output/'ledger.json'),calls,reads,pins


def test_worker_code_full_namespace_and_only_four_bindings():
    proof=m.source_proof(); old=m.prior.worker_function(); new=m.worker_function()
    assert new.__code__ is old.__code__ and new.__closure__ is old.__closure__
    assert new.__defaults__ is old.__defaults__ and new.__kwdefaults__ is old.__kwdefaults__
    changed={k for k,v in old.__globals__.items() if new.__globals__[k] is not v}
    assert changed==set(proof['changed_private_globals_only'])
    assert new.__globals__['lazy'].predict is m._reference
    assert new.__globals__['candidate'].predict is m._candidate
    assert 'SCHEMA' not in new.__globals__
    pure_proof=runner.source_proof()
    assert pure_proof['explicit_bare_helper']=='tests.test_g31_circulation_initial_scoped_inputs_cost'
    assert pure_proof['current_and_prior_archive_checked'] and pure_proof['fixed_tests']==25
    # Verify the actual facade calls the original resolver with the missing
    # qualified entry, without a second full source scan in a unit test.
    seen=[]; helper=(runner.frozen.ROOT/runner.HELPER_PATH).read_bytes()
    def resolver(root,entries): seen.append(entries); return {runner.HELPER_PATH:helper}
    fake=SimpleNamespace(**{**vars(runner.frozen),'image':SimpleNamespace(source_closure=resolver)})
    private=FunctionType(runner._source_closure.__code__,{**runner._source_closure.__globals__,'frozen':fake})
    result=private(runner.frozen.ROOT,('main','test'))
    assert seen==[('main','test',runner.HELPER_MODULE)] and result[runner.HELPER_PATH]==helper


def test_frozen_globals_and_sources_not_mutated_by_binding():
    old=m.prior.worker_function(); before=dict(m.prior.frozen.worker.__globals__)
    m.worker_function(); m.source_proof()
    assert m.prior.worker_function().__code__ is old.__code__
    assert set(before)==set(m.prior.frozen.worker.__globals__)
    assert all(m.prior.frozen.worker.__globals__[key] is value for key,value in before.items())


def test_fake24_exact_all_fields_status_denominator_and_versions(fixture):
    report,ledger,calls,reads,pins=execute(fixture)
    assert report['exact']==24 and report['unknown']==0 and len(ledger)==24
    assert ''.join(row['arm'] for row in calls)=='ABBA'*6
    assert report['summary_ms']['A']['count']==report['summary_ms']['B']['count']==12
    assert all(row['status']=='exact_initial_scope_full_output' for row in report['initial_scope_full_output_checks'])
    assert len(reads)==48 and len(pins)==3
    assert 'v2_full_output_checks' not in report
    assert report['A_version']=='initial_scope_original_bundle_copy'
    assert report['B_version']=='initial_scope_private_owned_bundle'
    assert not report['allocation_failure_timing_equivalent']
    assert report['schema']==m.SCHEMA
    assert m.read(fixture.output/'receipt.json')['report']==m.ref(fixture.output/'report.json')


def test_all_component_work_between_sample_clocks_and_no_cleanup_claim(fixture):
    report,ledger,calls,*_=execute(fixture)
    assert all(row['started_ns']<call['at']<row['finished_ns'] for row,call in zip(ledger,calls))
    assert report['both_initial_context_constructions_and_fact_comparisons_inside_each_sample']
    assert not report['per_sample_cycle_cleanup_certified'] and not report['complete_request100ms_certified']


@pytest.mark.parametrize('function,name',[(m._reference,'reference'),(m._candidate,'predict')])
def test_arm_receives_same_public_and_action_and_no_target(function,name):
    public={'action':object()}; calls=[]; answer=object()
    facade=SimpleNamespace(**{name:lambda value:calls.append(value) or answer})
    private=FunctionType(function.__code__,{**function.__globals__,'component':facade})
    assert private(public,public['action']) is answer and calls==[public]


@pytest.mark.parametrize('function',[m._reference,m._candidate])
def test_other_equal_action_is_rejected(function):
    with pytest.raises(ValueError,match='same_action_object'): function({'action':{}},{})


@pytest.mark.parametrize('index',[0,1,12,23])
def test_component_failure_retains24_unknown_and_no_speed_summary(fixture,index):
    report,ledger,calls,*_=execute(fixture,fail_at=index)
    assert len(calls)==len(ledger)==24 and report['exact']==23 and report['unknown']==1
    assert ledger[index]['status']=='unknown_error' and 'elapsed_ns' in ledger[index]
    assert report['summary_ms']=={} and report['status']=='unknowns_preserved'


@pytest.mark.parametrize('change',['type','signed_zero','key_order','extra_field','list_order'])
def test_initial_scope_target_checks_all_fields_and_final_receipt_counts(fixture,change):
    value=copy.deepcopy(fixture.prediction)
    if change=='type': value['completion']['j']=1
    elif change=='signed_zero': value['completion']['j']=-0.0
    elif change=='key_order': value=dict(reversed(list(value.items())))
    elif change=='extra_field': value['extra']=False
    else: value['projected_collections']=[2,1]
    row=fixture.plan['rows'][m.ORDER[0]]; path=Path(row['comparison_only_initial_scope_prediction']['path'])
    path.write_bytes(gzip.compress(m.frozen.base.bytes_of(value),mtime=0))
    row['comparison_only_initial_scope_prediction']=m.ref(path);previous_tests.write(fixture.output/'plan.json',fixture.plan)
    report,ledger,calls,*_=execute(fixture);receipt=m.read(fixture.output/'receipt.json')
    assert len(calls)==24 and report['exact']==receipt['exact']==20
    assert report['unknown']==receipt['unknown']==4 and report['summary_ms']=={}
    assert all(row['status']=='unknown_saved_initial_scope_error' for row in report['initial_scope_full_output_checks'][:4])
    assert all('raw' in row for row in ledger)


@pytest.mark.parametrize('mutation',['remove','reverse','arm'])
def test_extra_audit_rejects_denominator_tamper(fixture,mutation):
    ledger=[{**row,'status':'unknown_unexecuted'} for row in m.frozen.declaration()]
    if mutation=='remove': ledger.pop()
    elif mutation=='reverse': ledger.reverse()
    else: ledger[0]['arm']='B'
    with pytest.raises(ValueError,match='full_ledger'): m._extend_report(fixture.output,fixture.plan,ledger,{})


def test_disabled_GC_prevents_any_component(fixture):
    function,calls,*_=fake_worker(fixture,gc_enabled=False)
    with pytest.raises(ValueError,match='fixed_scope'): function(fixture.output,m.sha(fixture.output/'plan.json'))
    assert not calls


def test_last_pin_failure_is_not_promoted(fixture):
    function,calls,reads,pins=fake_worker(fixture,fail_final_pins=True)
    with pytest.raises(ValueError,match='post_extra_audit_pins'): function(fixture.output,m.sha(fixture.output/'plan.json'))
    assert len(calls)==24 and len(pins)==3 and not (fixture.output/'receipt.json').exists()


def test_failed_input_retains_all_four_rows(fixture):
    Path(fixture.plan['rows'][m.ORDER[0]]['input']['path']).write_text('{broken',encoding='utf8')
    report,ledger,calls,*_=execute(fixture)
    assert len(calls)==20 and report['unknown']==4
    assert all(row['status']=='unknown_setup_error' for row in ledger[:4])


def test_no_returned_output_cannot_become_exact(fixture):
    ledger=[{**row,'status':'unknown_unexecuted'} for row in m.frozen.declaration()]
    report=m._extend_report(fixture.output,fixture.plan,ledger,{'exact':24,'unknown':0})
    assert report['exact']==0 and report['unknown']==24 and report['summary_ms']=={}


def test_owned_launcher_keeps_full_globals_and_only_explicit_rebindings(monkeypatch):
    namespace={'sentinel':object()}
    exec('def main(): return globals()',namespace)
    old=namespace['main'];monkeypatch.setattr(m,'prior',SimpleNamespace(main=old))
    bound=m.main()
    assert set(bound)==set(namespace)|{'BOOT','MODULE','prepare','worker_function'}
    assert all(bound[key] is value for key,value in namespace.items())
    assert bound['MODULE']==m.MODULE and bound['BOOT']==m.BOOT
    assert bound['prepare'] is m.prepare and bound['worker_function'] is m.worker_function
    assert m.LIMIT==m.frozen.LIMIT==m.frozen.base.LIMIT==120.
