"""Real file-open composition with fake subprocesses; no build/load/workload."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import run_planning_v2_c_encoder_gate_v3 as v3

STEPS=('configure','build','dependents','imports','compiler_dependencies')


def composed_parent(tmp_path,monkeypatch,mode,version,fail_step=None):
    ns=(v3.namespace() if version==3 else v3.previous.namespace())
    output=tmp_path/(str(version)+'_'+mode)
    actual_calls=[];records=[];parents=[]
    def process(command,**kwargs):
        assert kwargs['check'] is False and kwargs['cwd']==v3.old.ROOT
        actual_calls.append(command[0])
        kwargs['stdout'].write(('stdout:'+command[0]).encode())
        kwargs['stderr'].write(('stderr:'+command[0]).encode())
        return SimpleNamespace(returncode=1 if command[0]==fail_step else 0)
    ns['subprocess']=SimpleNamespace(run=process)
    def child(command,**kwargs):
        assert kwargs['stdout'].closed is False and kwargs['stderr'].closed is False
        assert 0<kwargs['timeout']<=120
        parents.extend((Path(kwargs['stdout'].name),Path(kwargs['stderr'].name)))
        kwargs['stdout'].write('parent output\n');kwargs['stdout'].flush()
        kwargs['stderr'].write('parent error\n');kwargs['stderr'].flush()
        # The real parent has opened its logs. The fake worker uses the exact
        # original command runner, including exclusive log creation and hashes.
        for step in STEPS:ns['run']([step],output,step,records,{})
        return {'status':'exited','exitcode':0}
    ns['bounded_windows_job']=SimpleNamespace(run=child)
    ns['BOOT']=ns['time'].monotonic()
    args=['gate','--mode',mode,'--output',str(output)]
    if mode!='prepare':args+=['--plan',str(tmp_path/'plan.json'),'--plan-sha256','a'*64]
    if mode=='functional':args+=['--build-output',str(tmp_path/'priorbuild'),
        '--build-receipt-sha256','b'*64,'--build-external-sha256','c'*64]
    monkeypatch.setattr(ns['sys'],'argv',args)
    code=ns['main']()
    return code,output,json.loads((output/'bounded_execution.json').read_text()),actual_calls,records,parents


@pytest.mark.parametrize('mode',('prepare','build','functional'))
def test_parent_and_original_worker_file_open_composition(tmp_path,monkeypatch,mode):
    code,output,result,calls,records,parents=composed_parent(tmp_path,monkeypatch,mode,3)
    assert code==0 and result['status']=='exited' and result['whole_bound_seconds']==120
    assert calls==list(STEPS) and len(records)==len(STEPS)
    assert [p.name for p in parents]==['parent_'+mode+'.stdout.log','parent_'+mode+'.stderr.log']
    assert parents[0].read_text()=='parent output\n' and parents[1].read_text()=='parent error\n'
    for step,record in zip(STEPS,records):
        assert (output/(step+'.stdout.log')).read_bytes()==('stdout:'+step).encode()
        assert (output/(step+'.stderr.log')).read_bytes()==('stderr:'+step).encode()
        assert v3.old.sha(output/(step+'.stdout.log'))==record['stdout_sha256']
        assert v3.old.sha(output/(step+'.stderr.log'))==record['stderr_sha256']
        assert json.loads((output/(step+'.command.json')).read_text())==record


@pytest.mark.parametrize('mode',('prepare','build','functional'))
def test_legacy_actual_open_collision_reproduces_only_build(tmp_path,monkeypatch,mode):
    code,output,result,calls,records,parents=composed_parent(tmp_path,monkeypatch,mode,2)
    if mode=='build':
        assert code==1 and result['status']=='launch_failed'
        assert result['error']['type']=='FileExistsError'
        assert calls==['configure'] and len(records)==1
        assert parents[0].read_text()=='parent output\n'
        assert not (output/'build.command.json').exists()
    else:assert code==0 and calls==list(STEPS)


@pytest.mark.parametrize('mode',('prepare','build','functional'))
def test_command_failure_not_hidden_by_parent_log_repair(tmp_path,monkeypatch,mode):
    code,output,result,calls,records,_=composed_parent(tmp_path,monkeypatch,mode,3,'build')
    assert code==1 and result['status']=='launch_failed'
    assert result['error']['type']=='ValueError' and 'command_failed:build' in result['error']['message']
    assert calls==['configure','build'] and records[-1]['exit_code']==1
    assert (output/'build.stderr.log').read_bytes()==b'stderr:build'


def test_main_only_two_log_expressions_change():
    tree,proof=v3.parent_main_tree()
    assert proof['inverse_AST_equals_frozen_main'] and proof['all_other_main_statements_preserved']
    assert proof['exact_replacements']==['.stdout.log','.stderr.log']
    assert len([n for n in ast.walk(tree) if isinstance(n,ast.Constant) and n.value=='parent_'])==2


def test_all_worker_code_and_full_private_globals_preserved():
    old_before=dict(vars(v3.old));previous_before=dict(vars(v3.previous));ns=v3.namespace()
    for name in ('run','worker','build','functional','verify_plan','direct_probe',
                 'external_build_identity','actual_extension_identity','loaded_sources'):
        assert ns[name].__code__ is getattr(v3.old,name).__code__
        assert ns[name].__globals__ is ns
    assert all(vars(v3.old)[key] is value for key,value in old_before.items())
    assert all(vars(v3.previous)[key] is value for key,value in previous_before.items())
    assert ns['main'].__globals__ is ns and ns['EXPECTED_TESTS']==159


def test_new_build_directory_and_both_output_commands():
    ns=v3.namespace();assert ns['BUILD']==v3.old.ROOT/'build_planning_v2_typed_encoder_002'
    result=ns['commands'](Path('plan'),'a'*64,v3.old.OUT/'planning_v2_C_encoder_build_001',
                          v3.old.OUT/'planning_v2_C_encoder_functional_001')
    assert result['build'][2].endswith('_v3')
    assert result['build'][-1]==str(v3.old.OUT/'planning_v2_C_encoder_build_002')
    functional=result['functional_template_not_yet_executable']
    assert functional[functional.index('--output')+1]==str(v3.old.OUT/'planning_v2_C_encoder_functional_002')
    assert functional[functional.index('--build-output')+1]==str(v3.old.OUT/'planning_v2_C_encoder_build_002')
    assert '--build-receipt-sha256' in functional and '--build-external-sha256' in functional


def test_actual_explicit_command_paths_are_not_remapped(tmp_path):
    ns=v3.namespace();result=ns['commands'](tmp_path/'plan','f'*64,tmp_path/'build',tmp_path/'functional')
    assert result['build'][-1]==str(tmp_path/'build')
    functional=result['functional_template_not_yet_executable']
    assert functional[functional.index('--output')+1]==str(tmp_path/'functional')


def test_fresh_build_guard_precedes_every_external_action(tmp_path):
    ns=v3.namespace();directory=tmp_path/'newbuild';directory.mkdir();marker=directory/'old';marker.write_bytes(b'preserve')
    ns['BUILD']=directory
    ns['environment']=lambda *args:pytest.fail('existing directory must fail before environment')
    with pytest.raises(ValueError,match='fresh_build_directory'):ns['build'](tmp_path,{}, {})
    assert marker.read_bytes()==b'preserve'


def test_existing_parent_output_is_not_reused(tmp_path,monkeypatch):
    ns=v3.namespace();output=tmp_path/'prior';output.mkdir();(output/'receipt.json').write_bytes(b'old')
    ns['bounded_windows_job']=SimpleNamespace(run=lambda *a,**k:pytest.fail('must not launch'))
    monkeypatch.setattr(ns['sys'],'argv',['gate','--mode','prepare','--output',str(output)])
    with pytest.raises(FileExistsError):ns['main']()
    assert (output/'receipt.json').read_bytes()==b'old'


def test_prior_build_failure_and_prepare_timeout_remain_unaccepted():
    failure=v3.old.OUT/'planning_v2_C_encoder_build_001/receipt.json'
    timeout=v3.old.OUT/'planning_v2_C_encoder_gate_prepare_001/bounded_execution.json'
    assert v3.old.sha(failure)=='7024bc068d52648deb36236647942cf360dc3a3329db05bcdd4cd9304b703363'
    row=json.loads(failure.read_text());assert row['status']=='failed' and row['error']['type']=='FileExistsError'
    assert json.loads(timeout.read_text())['status']=='hard_timeout'


def test_new_closure_includes_both_old_and_new_tests_and_launchers():
    mapping=v3.namespace()['project_closure']()
    for name in (v3.TEST,v3.PURE,v3.previous.TEST,v3.previous.PURE):
        assert mapping[name]==v3.old.sha(v3.old.ROOT/name)
    for module in (v3,v3.previous,v3.old):
        name=Path(module.__file__).relative_to(v3.old.ROOT).as_posix()
        assert mapping[name]==v3.old.sha(module.__file__)
