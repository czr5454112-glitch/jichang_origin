"""Small synthetic redirection/lifecycle tests; no producer raw or native reads."""
import inspect
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import audit_bridge_serialize_once_saved as a


def paths(tmp_path):
    source=tmp_path/'source';output=tmp_path/'audit';source.mkdir();(source/'bridge').mkdir();output.mkdir()
    return source,output


def test_exact_single_derived_write_hash_and_explicit_mapping(tmp_path):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output);data={'jobs':[{'id':'J','time':-0.0}]}
    d.gzwrite(d.old,data);digest=d.sha(d.old)
    result={'evidence_sha256':{'prior':'unchanged',str(d.old):digest,'later':'unchanged'},'status':'fixture'}
    mapped,proof=d.map_result(result)
    assert not d.old.exists() and a.base.gzread(d.new)==data
    assert list(mapped['evidence_sha256'])==['prior',str(d.new),'later']
    assert str(d.old) in result['evidence_sha256'] and proof['original_path_written'] is False
    assert proof['redirected_gzwrite_calls']==proof['redirected_sha_calls']==1


@pytest.mark.parametrize('kind',['inside_source','old_exists','new_exists'])
def test_unsafe_or_existing_output_rejected(tmp_path,kind):
    source,output=paths(tmp_path)
    if kind=='inside_source':output=source/'elsewhere'
    elif kind=='old_exists':(source/'bridge/all_job_states.json.gz').write_bytes(b'old')
    else:(output/'all_job_states.json.gz').write_bytes(b'new')
    with pytest.raises(ValueError):a.DerivedOutput(source,output)


def test_foreign_write_duplicate_write_and_premature_hash_rejected(tmp_path):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output)
    with pytest.raises(ValueError,match='hash_before'):d.sha(d.old)
    with pytest.raises(ValueError,match='unexpected_write'):d.gzwrite(source/'other.json.gz',{})
    d.gzwrite(d.old,{})
    with pytest.raises(ValueError,match='unexpected_write'):d.gzwrite(d.old,{})
    assert not (source/'other.json.gz').exists() and not d.old.exists()


def test_non_derived_hash_delegates_unchanged(tmp_path):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output);p=source/'input';p.write_bytes(b'exact')
    assert d.sha(p)==a.base.sha(p) and d.hashes==0


def test_failed_export_cannot_produce_complete_mapping(tmp_path,monkeypatch):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output)
    def fail(*args):raise OSError('injected')
    monkeypatch.setattr(a.base,'gzwrite',fail)
    with pytest.raises(OSError,match='injected'):d.gzwrite(d.old,{})
    with pytest.raises(ValueError,match='denominator'):d.map_result({'evidence_sha256':{}})
    assert d.writes==0 and not d.old.exists()


def test_runtime_domain_rejects_new_unpinned_module(monkeypatch,tmp_path):
    p=tmp_path/'allowed.py';p.write_text('pass')
    plan={'source_before':{str(p):a.base.sha(p)}}
    monkeypatch.setattr(a,'loaded_sources',lambda:{str(p)})
    assert a.check_runtime(plan)==[str(p)]
    monkeypatch.setattr(a,'loaded_sources',lambda:{str(p),str(tmp_path/'new.py')})
    with pytest.raises(ValueError,match='unlisted'):a.check_runtime(plan)


def test_runtime_domain_rejects_changed_module(monkeypatch,tmp_path):
    p=tmp_path/'allowed.py';p.write_text('pass');plan={'source_before':{str(p):a.base.sha(p)}};p.write_text('changed')
    monkeypatch.setattr(a,'loaded_sources',lambda:{str(p)})
    with pytest.raises(ValueError,match='changed'):a.check_runtime(plan)


def test_binding_preserves_both_original_codes_and_global_modules(tmp_path):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output)
    before=dict(vars(a.base));old_runtime=a.r.verify_pins
    bound=a.bound_verifier({'source_before':{}},d)
    assert bound.__code__ is a.original.verify_case.__code__
    nested=bound.__globals__['verifier_function'](a.base.ReplayTape)
    assert nested.__code__ is a.original.original.verify_case.__code__
    assert nested.__globals__['base'].gzwrite==d.gzwrite and nested.__globals__['base'].sha==d.sha
    assert nested.__globals__['r'].isolated_base.__globals__['verify_pins'] is nested.__globals__['r'].verify_pins
    assert a.r.verify_pins is old_runtime and vars(a.base)==before


def test_old_pin_checks_retained_with_explicit_runtime_union(tmp_path,monkeypatch):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output);calls=[]
    monkeypatch.setattr(a.r,'verify_pins',lambda directory,plan,runtime=False:calls.append(('old',runtime)))
    monkeypatch.setattr(a,'check_runtime',lambda plan:calls.append(('union',True)))
    fn=a.bound_verifier({'source_before':{}},d).__globals__['verifier_function'](a.base.ReplayTape)
    fn.__globals__['r'].verify_pins(source,{},runtime=True)
    assert calls==[('old',False),('union',True)]


def test_no_native_or_producer_output_in_audit_entry_source():
    text=inspect.getsource(a.audit)
    assert 'NativeSession' not in text and 'load_native' not in text
    assert '37270' in text and '27218' in text and a.LIMIT==600


def test_new_result_mapping_requires_actual_derived_digest(tmp_path):
    source,output=paths(tmp_path);d=a.DerivedOutput(source,output);d.gzwrite(d.old,{});d.sha(d.old)
    with pytest.raises(ValueError,match='mapping_identity'):d.map_result({'evidence_sha256':{str(d.old):'0'*64}})


@pytest.mark.parametrize('changed',['receipt','XML'])
def test_saved_audit_rechecks_pure_receipt_and_xml_bytes(tmp_path,changed):
    receipt=tmp_path/'receipt.json';xml=tmp_path/'tests.xml';receipt.write_text('{}');xml.write_text('<testsuite/>')
    plan={'pure':{'path':str(receipt),'sha256':a.base.sha(receipt),'XML_path':str(xml),'XML_sha256':a.base.sha(xml)}}
    a.check_pure_references(plan)
    (receipt if changed=='receipt' else xml).write_text('changed')
    with pytest.raises(ValueError,match='pure_reference_changed'):a.check_pure_references(plan)


def test_inherited2400_text_is_preserved_but_never_current_budget():
    original={'same_policy_old001_complete_prefix':{'cost':'Runs inside the same saved replay and shared2400 parent; no time deducted.','rows':27218},'other':'exact'}
    result,metadata=a.current_cost_metadata(original)
    assert original['same_policy_old001_complete_prefix']['cost']==metadata['original_verifier_cost_text']
    assert 'separate saved-only600s' in result['same_policy_old001_complete_prefix']['cost']
    assert result['same_policy_old001_complete_prefix']['rows']==27218 and result['other']=='exact'
    assert metadata['current_owned_budget_seconds']==600
