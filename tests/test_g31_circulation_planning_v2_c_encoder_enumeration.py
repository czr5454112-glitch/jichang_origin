"""Synthetic membership and private-binding tests; never loads C or real data."""
import ast
import inspect
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import run_planning_v2_c_encoder_gate_v2 as v2


def original_members(parent):
    return {p for p in parent.rglob('*') if p.is_file() and
        'site-packages' not in p.parts and '__pycache__' not in p.parts and
        p.suffix.lower() in ('.py','.pyd','.dll','.zip','.pth')}


@pytest.mark.parametrize('name', ['one.py','mixed.PY','a/file.pyd','a/file.DLL','x.zip','paths.pth',
    'a/note.txt','site-packages/no.py','a/site-packages/no.dll','__pycache__/no.py',
    'a/__pycache__/no.pyd','site-packages-lookalike/yes.py','__pycache__lookalike/yes.py',
    'a/empty','a/a.b.py'])
def test_selected_members_exact(tmp_path,name):
    path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic')
    assert set(v2.stdlib_files(tmp_path))==original_members(tmp_path)


def test_many_excluded_descendants_keep_same_set(tmp_path):
    for number in range(150):
        parent=tmp_path/('site-packages' if number%2 else '__pycache__')/str(number)
        parent.mkdir(parents=True);(parent/'ignored.py').write_text('not imported')
    (tmp_path/'selected.py').write_text('included')
    assert set(v2.stdlib_files(tmp_path))==original_members(tmp_path)=={tmp_path/'selected.py'}


def test_prunes_before_descent(monkeypatch,tmp_path):
    seen=[]
    def walk(parent,followlinks=False):
        assert followlinks is False
        directories=['site-packages','__pycache__','keep'];yield str(parent),directories,[]
        seen.extend(directories)
    monkeypatch.setattr(v2.os,'walk',walk)
    assert list(v2.stdlib_files(tmp_path))==[] and seen==['keep']


def test_inverse_AST_preserves_full_inventory_function():
    proof=v2.source_proof()
    assert proof['only_stdlib_enumeration_changed'] and proof['compiler_runtime_and_functional_gates_preserved']


def test_private_globals_keep_build_and_functional_code():
    before=dict(vars(v2.old));ns=v2.namespace()
    for name in ('main','worker','build','functional','verify_plan','direct_probe','external_build_identity','actual_extension_identity'):
        assert ns[name].__code__ is getattr(v2.old,name).__code__
        assert ns[name].__globals__ is ns
    assert all(vars(v2.old)[name] is value for name,value in before.items())
    assert ns['EXPECTED_TESTS']==159 and ns['BUILD']==v2.old.BUILD
    assert ns['MODULE'].endswith('_v2') and ns['__file__']==v2.__file__


def test_journal_limit_is_not_expanded(tmp_path):
    journal=v2.Journal(tmp_path/'journal.jsonl')
    try:
        for number in range(40):journal.append('test','started',number=number)
        with pytest.raises(ValueError,match='bounded_journal_exhausted'):journal.append('extra','started')
    finally:journal.close()
    assert len((tmp_path/'journal.jsonl').read_text().splitlines())==40


def test_functional_commands_keep_required_external_binding():
    ns=v2.namespace();commands=ns['commands'](Path('plan'), 'a'*64, Path('build'), Path('functional'))
    future=commands['functional_template_not_yet_executable']
    assert '--build-receipt-sha256' in future and '--build-external-sha256' in future
    assert commands['build'][2].endswith('_v2')


def test_original_timeout_remains_unaccepted():
    import json
    path=v2.old.OUT/'planning_v2_C_encoder_gate_prepare_001/bounded_execution.json'
    value=json.loads(path.read_text())
    assert value['status']=='hard_timeout' and value['whole_bound_seconds']==120
