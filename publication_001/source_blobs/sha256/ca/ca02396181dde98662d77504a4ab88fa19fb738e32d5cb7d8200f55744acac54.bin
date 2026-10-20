"""Versioned enumeration-only repair; frozen first gate and timeout remain.

Prune directory trees the old selection rule already excluded. Compiler,
runtime, byte gates and 120-second limits are inherited without reduction.
The bounded journal locates phases; it does not turn a timeout into success.
"""
from __future__ import annotations
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import time
from types import FunctionType
from . import run_planning_v2_c_encoder_gate as old

OLD_SHA='ce0cddd9fc24ec4ca6aa402f852a1f88afff9ec63b3512597e965601546567b5'
TEST='tests/test_g31_circulation_planning_v2_c_encoder_enumeration.py'
PURE='scripts/experiments/g31_ics_circulation/run_planning_v2_c_encoder_enumeration_pure.py'
JOURNAL_LIMIT=40


def stdlib_files(parent):
    """Same file predicate as v1, with excluded subtrees never descended."""
    for directory, directories, files in os.walk(parent, followlinks=False):
        directories[:]=[name for name in directories if name not in ('site-packages','__pycache__')]
        for name in files:
            path=Path(directory)/name
            if path.is_file() and 'site-packages' not in path.parts and '__pycache__' not in path.parts:
                if path.suffix.lower() in ('.py','.pyd','.dll','.zip','.pth'):yield path


def runtime_paths():
    # This is the whole frozen function with only the stdlib enumeration loop
    # replaced. source_proof inverts that single statement and checks all else.
    paths = [PYTHON,PYTHON.parent/'python311.dll',PYTHON.parent/'python3.dll']
    for parent in (PYTHON.parent/'Lib',PYTHON.parent/'DLLs'):
        require(parent.is_dir(),'runtime_directory:'+str(parent))
        paths.extend(stdlib_files(parent))
    distributions = {}
    for name in ('pytest','pluggy','iniconfig','packaging','colorama','pygments','setuptools','pywin32'):
        dist=importlib.metadata.distribution(name); distributions[name]=dist.version
        require(dist.files is not None,'distribution_inventory:'+name)
        for member in dist.files:
            path=Path(dist.locate_file(member)).resolve()
            if path.suffix.lower() in ('.py','.pyd','.dll','.pth') or path.name in ('METADATA','RECORD','entry_points.txt'):
                paths.append(path)
    import site
    sites=[PYTHON.parent/'Lib/site-packages',Path(site.getusersitepackages())]
    for parent in sites:paths.extend(parent.glob('*.pth'))
    for name in ('sitecustomize.py','usercustomize.py'):
        for parent in (*sites,PYTHON.parent/'Lib'):
            if (parent/name).exists(): paths.append(parent/name)
    for name in ('kernel32.dll','ucrtbase.dll','vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll'):
        for parent in (PYTHON.parent,Path('C:/Windows/System32')):
            if (parent/name).is_file():paths.append(parent/name)
    return paths, distributions


def source_proof():
    old.require(old.sha(old.__file__)==OLD_SHA,'v1_source_changed')
    left=ast.parse(inspect.getsource(old.runtime_paths)).body[0]
    right=ast.parse(inspect.getsource(runtime_paths)).body[0]
    old_loop=left.body[1];new_loop=right.body[1]
    old.require(isinstance(old_loop,ast.For) and isinstance(new_loop,ast.For) and
        len(old_loop.body)==2 and len(new_loop.body)==2,'enumeration_loop_shape')
    expected=ast.parse('paths.extend(stdlib_files(parent))').body[0]
    old.require(ast.dump(new_loop.body[1],include_attributes=False)==ast.dump(expected,include_attributes=False),
                'single_enumeration_replacement')
    new_loop.body[1]=old_loop.body[1]
    old.require(ast.dump(left,include_attributes=False)==ast.dump(right,include_attributes=False),'runtime_inventory_inverse_AST')
    return {'v1_source_sha256':OLD_SHA,'only_stdlib_enumeration_changed':True,
        'selected_file_predicate_unchanged':True,'compiler_runtime_and_functional_gates_preserved':True,
        'old_prepare001_timeout_preserved':True,'C_builds_or_loads_in_proof':0}


class Journal:
    def __init__(self,path):self.path=Path(path);self.sequence=0;self.stream=self.path.open('x',encoding='utf8')
    def append(self,phase,event,**details):
        old.require(self.sequence<JOURNAL_LIMIT,'bounded_journal_exhausted')
        value={'sequence':self.sequence,'phase':phase,'event':event,'at_ns':time.perf_counter_ns(),**details}
        self.sequence+=1;self.stream.write(json.dumps(value,ensure_ascii=True,allow_nan=False)+'\n');self.stream.flush()
    def close(self):self.stream.close()


def namespace():
    source_proof()
    ns=dict(vars(old));ns['__file__']=__file__;ns['MODULE']=__package__+'.run_planning_v2_c_encoder_gate_v2'
    for name,value in vars(old).items():
        if isinstance(value,FunctionType) and value.__globals__ is vars(old):
            clone=FunctionType(value.__code__,ns,value.__name__,value.__defaults__,value.__closure__)
            clone.__kwdefaults__=value.__kwdefaults__;ns[name]=clone
    original_closure=ns['project_closure']
    def project_closure():
        result=original_closure()
        result[TEST]=old.sha(old.ROOT/TEST)
        result[PURE]=old.sha(old.ROOT/PURE)
        return dict(sorted(result.items()))
    ns['project_closure']=project_closure
    ns['stdlib_files']=stdlib_files
    ns['runtime_paths']=FunctionType(runtime_paths.__code__,ns,runtime_paths.__name__)
    base_prepare=ns['prepare'];active={'journal':None};snapshot_number=[0]
    def traced(name,function):
        def invoke(*args,**kwargs):
            journal=active['journal']
            if journal is None:return function(*args,**kwargs)
            label=name
            if name=='snapshot':
                snapshot_number[0]+=1;label='snapshot_'+str(snapshot_number[0])
            journal.append(label,'started')
            try:result=function(*args,**kwargs)
            except BaseException as error:
                journal.append(label,'failed',error_type=type(error).__name__,message=str(error));raise
            count=len(result) if isinstance(result,(dict,list)) else None
            if name=='runtime_paths':count=len(result[0])
            journal.append(label,'completed',member_count=count)
            return result
        return invoke
    for name in ('project_closure','environment','toolchain_paths','runtime_paths','snapshot'):
        ns[name]=traced(name,ns[name])
    def prepare(output,report):
        journal=Journal(output/'preparation_stages.jsonl');active['journal']=journal
        report['enumeration_repair_proof']=source_proof()
        report['journal_scope']='Stage timestamps bracket calls; gaps include archive/export. No phase from the old timeout is inferred.'
        try:
            journal.append('prepare','started');base_prepare(output,report);journal.append('prepare','completed')
        except BaseException as error:
            journal.append('prepare','failed',error_type=type(error).__name__,message=str(error));raise
        finally:active['journal']=None;journal.close()
    ns['prepare']=prepare
    return ns


def main():return namespace()['main']()


if __name__=='__main__':raise SystemExit(main())
