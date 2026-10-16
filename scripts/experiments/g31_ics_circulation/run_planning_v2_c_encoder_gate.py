"""Separate bounded metadata, build-only and synthetic functional stages.

No simulator, saved capture, predictor, or performance workload is admitted.
The seven reviewed prototype sources remain unchanged. Each invocation has its
own fresh directory and owned 120-second child tree; the external launch clock
must additionally retain Python startup and final parent evidence export.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET
from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
PYTHON = Path('C:/PROGRAMING/python3.11.9/python.exe')
VC = Path('C:/PROGRAMING/visual studio/Visual studio/VC')
VCBIN = VC/'Tools/MSVC/14.41.34120/bin/Hostx64/x64'
CMAKE = Path('C:/Program Files/CMake/bin/cmake.exe')
NINJA = Path('C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe')
CMD = Path('C:/Windows/System32/cmd.exe')
ORIGINAL = OUT/'planning_v2_C_encoder_source_prepare_001/source_plan.json'
ORIGINAL_SHA = 'f644e09943a967e9daf43ff377c6e8ba8a57416186e8ad1c966fa2ac7b6f2592'
REVIEW = ORIGINAL.parent/'independent_narrow_review_legal_001.json'
REVIEW_SHA = 'cf6ed935705dff5395d18b191ae60d6df5bd5a7228da6f0cbdee65d92100fea9'
ROOT_REVIEW = ORIGINAL.parent/'root_source_review_001.json'
ROOT_REVIEW_SHA = '78320a23fd3d28572329a1d5318e27ff9af66e1722f0ee1acc0651ed6c861040'
MODULE = __package__+'.run_planning_v2_c_encoder_gate'
TEST = 'tests/test_g31_circulation_planning_capture_v2_c_encoder.py'
FIXTURE = 'tests/test_g31_circulation_planning_v2_batched_digest.py'
BUILD = ROOT/'build_planning_v2_typed_encoder_001'
EXPECTED_TESTS = 159
ENV_KEYS = ('INCLUDE','LIB','PATH','VCTOOLSVERSION','WINDOWSSDKVERSION','VSCMD_ARG_TGT_ARCH','VSLANG')
SCHEMA = 'g31.planning_v2.C_encoder.gate.v1'


def require(ok, reason):
    if not ok: raise ValueError('typed_C_gate:'+reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2, allow_nan=False)


def snapshot(paths):
    result = {}
    for path in sorted({Path(p).resolve() for p in paths}):
        require(path.is_file(), 'missing_pinned_file:'+str(path))
        result[str(path)] = sha(path)
    return result


def pinned_hash(mapping, path):
    # Windows loader and distribution inventories can spell path case
    # differently. Path equality uses Windows path identity, not a new alias.
    matches=[digest for name,digest in mapping.items() if Path(name)==Path(path)]
    require(len(matches)<=1,'duplicate_pinned_path')
    return matches[0] if matches else None


def project_closure():
    # Explicit fixture entry closes its bare pytest import. Resolution also
    # searches tests/, unlike the earlier generic closure that missed it.
    pending = [MODULE, __package__+'.planning_capture_v2_c_encoder',
               TEST[:-3].replace('/','.'), FIXTURE[:-3].replace('/','.')]
    found = {}
    def resolve(name):
        for parent in (ROOT, ROOT/'src', ROOT/'tests'):
            stem = parent.joinpath(*name.split('.'))
            for path in (stem.with_suffix('.py'), stem/'__init__.py'):
                if path.is_file(): return path
        return None
    while pending:
        name = pending.pop(); path = resolve(name)
        if path is None: continue  # External dependencies are separately pinned.
        key = path.relative_to(ROOT).as_posix()
        if key in found: continue
        raw = path.read_bytes(); found[key] = hashlib.sha256(raw).hexdigest()
        package = name if path.name == '__init__.py' else name.rpartition('.')[0]
        for n in range(1,len(name.split('.'))): pending.append('.'.join(name.split('.')[:n]))
        for node in ast.walk(ast.parse(raw, filename=key)):
            if isinstance(node, ast.Import): pending.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parts = package.split('.')
                    base = '.'.join(parts[:len(parts)-node.level+1]+([base] if base else []))
                if base:
                    pending.append(base); pending.extend(base+'.'+a.name for a in node.names if a.name!='*')
    original = json.loads(ORIGINAL.read_text())
    for name, expected in original['sources'].items():
        require(sha(ROOT/name)==expected, 'reviewed_source_changed:'+name)
        # The first snapshot uses identical relative archive names.
        require(sha(ORIGINAL.parent/'source'/name)==expected, 'reviewed_archive_changed:'+name)
        found[name] = expected
    require(FIXTURE in found and TEST in found, 'explicit_fixture_closure')
    return dict(sorted(found.items()))


def environment(output):
    script = output/'environment.cmd'
    script.write_text('@echo off\ncall "'+str(VC/'Auxiliary/Build/vcvars64.bat')+
        '" >nul\nif errorlevel 1 exit /b %errorlevel%\nset VSLANG=1033\nset\n',encoding='utf8')
    command = [str(CMD), '/d', '/c', str(script)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, check=False)
    (output/'environment.stderr.log').write_bytes(result.stderr)
    write(output/'environment_command.json', {'command':command,'exit_code':result.returncode,
        'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(), 'encoding':'oem',
        'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
    require(result.returncode==0, 'MSVC_environment')
    env = dict(os.environ)
    for line in result.stdout.decode('oem').splitlines():
        if '=' in line and not line.startswith('='):
            key,value=line.split('=',1); env[key.upper()]=value
    require(env.get('VSCMD_ARG_TGT_ARCH')=='x64' and env.get('VCTOOLSVERSION')=='14.41.34120', 'MSVC_version_arch')
    return env


def toolchain_paths(env):
    paths = [PYTHON,PYTHON.parent/'python311.dll',PYTHON.parent/'python3.dll',CMAKE,NINJA,CMD]
    paths.extend(VCBIN.glob('*.exe')); paths.extend(VCBIN.glob('*.dll'))
    paths.extend((VC/'Auxiliary/Build').glob('*.bat'))
    directories = [PYTHON.parent/'include',PYTHON.parent/'libs',
                   Path('C:/Program Files/CMake/share/cmake-4.3/Modules')]
    for key in ('INCLUDE','LIB'):
        directories.extend(Path(p) for p in env.get(key,'').split(';') if p)
    for directory in dict.fromkeys(directories):
        require(directory.is_dir(), 'toolchain_directory:'+str(directory))
        paths.extend(p for p in directory.rglob('*') if p.is_file())
    for name in ('cl.exe','link.exe','dumpbin.exe'):
        path = VCBIN/name; require(path.is_file(),'compiler_tool:'+name); paths.append(path)
    for name in ('rc.exe','mt.exe'):
        path = shutil.which(name,path=env.get('PATH')); require(path is not None,'SDK_tool:'+name)
        paths.append(Path(path))
    return paths


def runtime_paths():
    # Freeze the stdlib and extension support, and exact installed pytest trees.
    # Autoload/conftest are disabled. This installation has three pytest
    # dependencies in user-site, so it remains explicit and fully pinned.
    paths = [PYTHON,PYTHON.parent/'python311.dll',PYTHON.parent/'python3.dll']
    for parent in (PYTHON.parent/'Lib',PYTHON.parent/'DLLs'):
        require(parent.is_dir(),'runtime_directory:'+str(parent))
        for path in parent.rglob('*'):
            if path.is_file() and 'site-packages' not in path.parts and '__pycache__' not in path.parts:
                if path.suffix.lower() in ('.py','.pyd','.dll','.zip','.pth'): paths.append(path)
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
    # Only these concrete CRT/OS DLL candidates may satisfy the extension's
    # named imports. The functional stage additionally checks the actual loaded
    # path, rather than claiming this search list is a loader observation.
    for name in ('kernel32.dll','ucrtbase.dll','vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll'):
        for parent in (PYTHON.parent,Path('C:/Windows/System32')):
            if (parent/name).is_file():paths.append(parent/name)
    return paths, distributions


def commands(plan_path, plan_sha, build_output, functional_output):
    common=[str(PYTHON),'-m',MODULE,'--plan',str(plan_path),'--plan-sha256',plan_sha]
    return {'build':common+['--mode','build','--output',str(build_output)],
        'functional_template_not_yet_executable':common+['--mode','functional','--output',str(functional_output),
            '--build-output',str(build_output),'--build-receipt-sha256','ACTUAL_ACCEPTED_BUILD_RECEIPT_SHA256_REQUIRED',
            '--build-external-sha256','ACTUAL_EXTERNAL_APPLICATION_WALL_SHA256_REQUIRED']}


def prepare(output, report):
    require(sha(ORIGINAL)==ORIGINAL_SHA and sha(REVIEW)==REVIEW_SHA and
        sha(ROOT_REVIEW)==ROOT_REVIEW_SHA,'original_review_reference')
    sources=project_closure(); env=environment(output)
    tools=snapshot(toolchain_paths(env)); runtime_files,distributions=runtime_paths()
    runtime=snapshot(runtime_files)
    for name,digest in sources.items():
        dest=output/'source'/name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest); require(sha(dest)==digest,'archive_source:'+name)
    for path in (PYTHON.parent/'include').rglob('*'):
        if path.is_file():
            dest=output/'CPython_headers'/path.relative_to(PYTHON.parent/'include')
            dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,dest)
            require(sha(dest)==tools[str(path.resolve())],'archive_header')
    plan={'schema':SCHEMA,'status':'prepared_unexecuted', 'source_sha256':sources,
        'source_archive':'source/<relative source name>', 'toolchain_sha256':tools,
        'runtime_sha256':runtime,'distributions':distributions,
        'environment':{k:env.get(k) for k in ENV_KEYS},
        'python_startup_environment':{k:os.environ.get(k) for k in ('PYTHONPATH','PYTHONHOME','PYTHONNOUSERSITE','SETUPTOOLS_USE_DISTUTILS')},
        'original_source_plan':{'path':str(ORIGINAL),'sha256':ORIGINAL_SHA},
        'independent_source_review':{'path':str(REVIEW),'sha256':REVIEW_SHA},
        'root_source_review':{'path':str(ROOT_REVIEW),'sha256':ROOT_REVIEW_SHA},
        'python':str(PYTHON),'CPython_version':[3,11,9],'build_directory':str(BUILD),
        'configure_command':[str(CMAKE),'-S',str(ROOT/'cpp/experimental/planning_v2_typed_encoder'),
            '-B',str(BUILD),'-G','Ninja','-DCMAKE_MAKE_PROGRAM='+str(NINJA),
            '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_TRY_COMPILE_CONFIGURATION=Release',
            '-DPython3_EXECUTABLE='+str(PYTHON),'-DCMAKE_CXX_COMPILER='+str(VCBIN/'cl.exe')],
        'build_command':[str(CMAKE),'--build',str(BUILD),'--config','Release','--parallel','1'],
        'functional':{'test':TEST,'explicit_fixture':FIXTURE,'exact_test_count':EXPECTED_TESTS,
            'expected_direct_probe_count':126,'expected_fallback_probe_count':10,
            'no_skipped_tests':True,'direct_probes_compare_complete_bytes_before_hashing':True,
            'resource_exception_equivalence':False,'pytest_plugin_autoload':False,'conftest':False},
        'external_build_receipt_contract':{'file':'external_application_wall.json',
            'schema':'g31.planning_v2.C_encoder.external_application_wall.v1',
            'required_fields':['command','plan','runner','wrapper','source_changed','exit_code',
                'elapsed_ticks','tick_frequency','whole_python_seconds','output_sha256'],
            'plan_runner_wrapper':'Each is exact path/sha256; wrapper must exist unchanged when functional begins.',
            'output_sha256':'Exact receipt.json and bounded_execution.json hashes from the completed build.',
            'clock':'Elapsed Stopwatch ticks from immediately before starting Python through its actual exit; <=120 seconds.',
            'functional_rejects_unbound_missing_or_overbudget_external_receipt_before_extension_load':True},
        'MSVCP140_scope':{'normalizer_prior_dependents':'Did not import MSVCP140; not proof for this vector implementation.',
            'header_evidence':'MSVC 14.41.34120 vector::_Xlength calls _Xlength_error; xutility declares _CRTIMP2_PURE external.',
            'import_library':'MSVC 14.41.34120 lib/x64/msvcprt.lib, frozen in toolchain; binary import remains to be observed.',
            'read_only_library_evidence':{'path':str(VC/'Tools/MSVC/14.41.34120/lib/x64/msvcprt.lib'),
                'sha256':'4f909f56f07bd0ece6e89abfd8b63417c614f38bbc94d787a8750d9787173958',
                'ASCII_members_observed':['MSVCP140.dll','_Xlength_error','_Xbad_alloc'],
                'not_a_new_binary_dependency_observation':True},
            'pinned_expected_DLL':{'path':'C:/Windows/System32/msvcp140.dll',
                'sha256':'7c26614e1d733892c2deac7e245ce115504b1d80592dd0a01b08e3e5a55f89ca'},
            'allowed_extra_name_only':'msvcp140.dll',
            'actual_resolution_must_match_frozen_concrete_runtime_path':True},
        'budgets':{'prepare_seconds':120,'build_seconds':120,'functional_seconds':120,
            'separate_invocations_not_amortized':True,'automatic_retry_or_extension':False,
            'basis':{'prior_independent_normalizer_build_parent_seconds':54.328,
                     'prior_independent_functional_parent_seconds':41.859,
                     'times_are_context_not_new_WCET_or_prediction':True}},
        'scope':{'actual_fixture_reads':0,'native_simulation_calls':0,'model_calls':0,'performance_runs':0,
            'build_stage_extension_loads':0,'stable_input_and_closed_source_process_required':True,
            'not_adversarial_filesystem_or_OS_sandbox':True,
            'external_clock_required':'Python application launch through exit; retain parent evidence export separately'}}
    require(snapshot(tools)==tools and snapshot(runtime)==runtime and project_closure()==sources,'prepare_drift')
    write(output/'plan.json',plan)
    build_output=OUT/'planning_v2_C_encoder_build_001'; functional_output=OUT/'planning_v2_C_encoder_functional_001'
    write(output/'commands.json',commands(output/'plan.json',sha(output/'plan.json'),build_output,functional_output))
    report.update(status='prepared_unexecuted',plan_sha256=sha(output/'plan.json'),source_count=len(sources),
                  toolchain_count=len(tools),runtime_count=len(runtime),commands_path=str(output/'commands.json'))


def verify_plan(path, expected):
    require(sha(path)==expected,'plan_identity'); plan=json.loads(path.read_text())
    require(plan['schema']==SCHEMA and plan['CPython_version']==[3,11,9],'plan_schema')
    require(project_closure()==plan['source_sha256'],'source_closure_changed')
    for name,digest in plan['source_sha256'].items():
        require(sha(path.parent/'source'/name)==digest,'source_archive_changed:'+name)
    require(snapshot(toolchain_paths(plan['environment']))==plan['toolchain_sha256'],'toolchain_changed')
    require(snapshot(plan['runtime_sha256'])==plan['runtime_sha256'],'runtime_changed')
    require({k:os.environ.get(k) for k in plan['python_startup_environment']}==plan['python_startup_environment'],'python_startup_environment_changed')
    require(sha(ORIGINAL)==ORIGINAL_SHA and sha(REVIEW)==REVIEW_SHA and
        sha(ROOT_REVIEW)==ROOT_REVIEW_SHA,'original_reference_changed')
    return plan


def run(command, output, name, records, env):
    started=time.perf_counter_ns()
    with (output/(name+'.stdout.log')).open('xb') as stdout,(output/(name+'.stderr.log')).open('xb') as stderr:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,check=False)
    record={'command':command,'exit_code':result.returncode,'wall_ns':time.perf_counter_ns()-started,
        'stdout_sha256':sha(output/(name+'.stdout.log')),'stderr_sha256':sha(output/(name+'.stderr.log'))}
    records.append(record); write(output/(name+'.command.json'),record)
    require(result.returncode==0,'command_failed:'+name)


def build(output, plan, report):
    require(not BUILD.exists(),'fresh_build_directory'); BUILD.mkdir()
    env=environment(output); require({k:env.get(k) for k in ENV_KEYS}==plan['environment'],'build_environment_changed')
    require(snapshot(toolchain_paths(env))==plan['toolchain_sha256'],'toolchain_membership_changed')
    records=[]; report['commands']=records
    run(plan['configure_command'],output,'configure',records,env)
    run(plan['build_command'],output,'build',records,env)
    found=list((BUILD/'python').glob('_g31_planning_v2_typed_encoder*.pyd'))
    require(len(found)==1,'exact_binary_count'); binary=found[0]
    for kind in ('DEPENDENTS','IMPORTS'):run([str(VCBIN/'dumpbin.exe'),'/'+kind,str(binary)],output,kind.lower(),records,env)
    lines=(output/'dependents.stdout.log').read_text(encoding='utf8').splitlines()
    imports=[s.strip() for s in lines if re.fullmatch(r'\s+[\w.\-]+\.dll\s*',s,re.I)]
    allowed=lambda s:s.lower() in {'python311.dll','kernel32.dll','vcruntime140.dll','vcruntime140_1.dll','ucrtbase.dll','msvcp140.dll'} or s.lower().startswith('api-ms-win-crt-')
    require('python311.dll' in [s.lower() for s in imports] and all(allowed(s) for s in imports),'unexpected_DLL_imports')
    run([str(NINJA),'-C',str(BUILD),'-t','deps'],output,'compiler_dependencies',records,env)
    archive=output/binary.name; shutil.copyfile(binary,archive)
    report.update(binary={'path':str(binary),'archive':str(archive),'sha256':sha(binary),'bytes':binary.stat().st_size},
        imported_DLLs=imports,imports_inspected_before_load=True,extension_loads=0,
        build_metadata={p.name:sha(p) for p in (BUILD/'CMakeCache.txt',BUILD/'build.ninja',BUILD/'.ninja_deps',BUILD/'.ninja_log')},
        status='build_passed_unloaded')
    require(sha(archive)==report['binary']['sha256'],'binary_archive')


def direct_probe(candidate, test, output):
    import copy
    import struct
    direct=[('base',test.body())]; fallback=[]
    for i,(path,value) in enumerate(test.PATHS):
        data=test.body(); parent=data
        for part in path[:-1]:parent=parent[part]
        parent[path[-1]]=({'sequence':22,'delivered_at':9.,'status':'received'} if value is None else
            not value if type(value)is bool else value+'!' if type(value)is str else value+1)
        direct.append(('scalar_'+str(i),data))
    for i,value in enumerate((-1,-(1<<129)+3,(1<<130)+7,True,False,0,(1<<64)-1,1<<64)):
        data=test.body();data['local_capture']['publication_sequence']=value;direct.append(('uint_'+str(i),data))
    for bits in ('0000000000000000','8000000000000000','0000000000000001','0010000000000000',
                 '7fefffffffffffff','7ff0000000000000','fff0000000000000','7ff8000000000042','fff8000000000042','7ff0000000000001'):
        data=test.body();data['local_capture']['captured_at']=struct.unpack('>d',bytes.fromhex(bits))[0]
        direct.append(('float_'+bits,data))
    data=test.body()
    for key in ('jobs','trays','nodes','known_faults'):data['local_capture'][key]=[]
    for key in ('terminal_receipts','submitted_physical_actions'):data['extension'][key]=[]
    direct.append(('empty',data));data=test.body();job=data['local_capture']['jobs'][0]
    data['local_capture']['jobs']=[job,job];direct.append(('shared_alias',data))
    for i,value in enumerate(('','abc\x00def','甲😀')):
        data=test.body();data['local_capture']['jobs'][0]['business_bag_id']=value;direct.append(('UTF8_'+str(i),data))
    for i,value in enumerate((1<<63,1<<100)):
        data=test.body();data['local_capture']['jobs'][0]['arrival']=value;fallback.append(('large_double_'+str(i),data))
    data=test.body();data['local_capture']['jobs']=tuple(data['local_capture']['jobs']);fallback.append(('tuple',data))
    # Each hook's first raw C attempt must leave its independent event list empty.
    hook_events={}
    for kind in ('text','integer','double','boolean','dict','list','str_subclass'):
        events=[];label='hook_'+kind;hook_events[label]=events;fallback.append((label,test.hooked(kind,events)))
    require(len(direct)==126 and len(fallback)==10,'direct_probe_denominators')
    records=[]
    for label,data in direct:
        actual=candidate.module.try_typed_bytes(data);expected=test.c.reference_bytes_v2(data)
        require(type(actual)is bytes and actual==expected,'direct_full_bytes:'+label)
        require(hashlib.sha256(actual).hexdigest()==test.c.original.capture_digest_v2(data),'direct_SHA:'+label)
        records.append({'label':label,'classification':'direct_C_bytes','expected_hex':expected.hex(),'actual_hex':actual.hex()})
    for label,data in fallback:
        require(candidate.module.try_typed_bytes(data)is NotImplemented,'expected_fallback:'+label)
        if label in hook_events:require(hook_events[label]==[],'C_called_hook:'+label)
        actual=candidate.typed_bytes_v2(data);expected=test.c.reference_bytes_v2(data)
        require(actual==expected,'fallback_bytes:'+label)
        records.append({'label':label,'classification':'original_fallback_not_C_support','expected_hex':expected.hex(),'actual_hex':actual.hex()})
    write(output/'byte_probe.json',records)
    return {'direct_supported_count':len(direct),'fallback_count':len(fallback),'byte_probe_sha256':sha(output/'byte_probe.json'),
            'fallback_is_not_direct_C_support':True,'direct_probe_performance_claim':False}


class Collection:
    def __init__(self):self.candidate=None;self.nodeids=[]
    def pytest_collection_modifyitems(self,items):
        self.nodeids=[item.nodeid for item in items]
        require(len(items)==EXPECTED_TESTS and len(set(self.nodeids))==EXPECTED_TESTS,'exact_collected_tests')
    def pytest_runtest_call(self,item):
        value=item.funcargs.get('candidate')
        if value is not None:
            require(self.candidate is None or self.candidate is value,'candidate_fixture_identity')
            self.candidate=value


def external_build_identity(build_output, expected, plan_path, plan_sha, plan):
    path=build_output/'external_application_wall.json'
    require(sha(path)==expected,'build_external_receipt_identity')
    value=json.loads(path.read_text())
    require(value['schema']=='g31.planning_v2.C_encoder.external_application_wall.v1','external_schema')
    require(value['command']==commands(plan_path,plan_sha,build_output,OUT/'unused')['build'],'external_build_command')
    require(value['plan']=={'path':str(plan_path),'sha256':plan_sha},'external_plan')
    require(value['runner']=={'path':str(Path(__file__).resolve()),'sha256':plan['source_sha256'][Path(__file__).relative_to(ROOT).as_posix()]},'external_runner')
    wrapper=value['wrapper'];require(set(wrapper)=={'path','sha256'} and sha(wrapper['path'])==wrapper['sha256'],'external_wrapper')
    require(value['source_changed']==[] and type(value['exit_code'])is int and value['exit_code']==0,'external_success')
    ticks,frequency,wall=value['elapsed_ticks'],value['tick_frequency'],value['whole_python_seconds']
    require(type(ticks)is int and ticks>=0 and type(frequency)is int and frequency>0,'external_typed_ticks')
    require(type(wall)in(int,float) and math.isfinite(wall) and 0<wall<=120 and
        abs(wall-ticks/frequency)<=1e-9,'external_full_wall_budget')
    expected_outputs={name:sha(build_output/name) for name in ('receipt.json','bounded_execution.json')}
    require(value['output_sha256']==expected_outputs,'external_output_binding')
    return {'path':str(path),'sha256':expected,'whole_python_seconds':wall,'elapsed_ticks':ticks,'tick_frequency':frequency}


def actual_extension_identity(candidate, binary, digest, imports, plan):
    import ctypes
    from ctypes import wintypes
    module=candidate.module;spec=module.__spec__
    require(Path(module.__file__).resolve()==binary.resolve() and Path(spec.origin).resolve()==binary.resolve() and
        Path(spec.loader.path).resolve()==binary.resolve() and sha(binary)==digest,'actual_extension_origin')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetModuleHandleW.argtypes=(wintypes.LPCWSTR,);kernel.GetModuleHandleW.restype=wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes=(wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD)
    kernel.GetModuleFileNameW.restype=wintypes.DWORD
    dlls={}
    for name in imports:
        if name.lower().startswith('api-ms-win-crt-'):
            dlls[name]={'scope':'Windows API-set mapping; not a standalone loaded-file claim'};continue
        handle=kernel.GetModuleHandleW(name);require(bool(handle),'missing_loaded_DLL:'+name)
        buffer=ctypes.create_unicode_buffer(32768);length=kernel.GetModuleFileNameW(handle,buffer,len(buffer))
        require(0<length<len(buffer),'loaded_DLL_path:'+name)
        path=Path(buffer.value).resolve();actual=sha(path)
        require(pinned_hash(plan['runtime_sha256'],path)==actual,'unfrozen_loaded_DLL:'+str(path))
        dlls[name]={'path':str(path),'sha256':actual}
    return {'name':module.__name__,'file':str(Path(module.__file__).resolve()),'spec_origin':spec.origin,
        'loader_type':type(spec.loader).__name__,'loader_path':spec.loader.path,'binary_sha256':digest,
        'contract':module.contract(),'actual_imported_DLL_files':dlls,
        'sys_modules_membership_not_used_as_extension_origin_proof':True}


def functional(output, plan, report, build_output, expected_build_sha, expected_external_sha, plan_path):
    receipt=build_output/'receipt.json'; require(sha(receipt)==expected_build_sha,'build_receipt_identity')
    prior=json.loads(receipt.read_text());outer=json.loads((build_output/'bounded_execution.json').read_text())
    require(prior['status']=='build_passed_unloaded' and prior['plan_sha256']==report['plan_sha256'] and
        prior['identity_verified_on_exit'] is True and prior['extension_loads']==0 and
        outer['status']=='exited' and outer['exitcode']==0,'accepted_build_required')
    report['external_build_receipt']=external_build_identity(build_output,expected_external_sha,plan_path,report['plan_sha256'],plan)
    binary=Path(prior['binary']['path']);digest=prior['binary']['sha256']
    require(sha(binary)==digest and sha(prior['binary']['archive'])==digest,'binary_changed')
    os.environ['G31_TYPED_ENCODER_BINARY']=str(binary);os.environ['G31_TYPED_ENCODER_SHA256']=digest
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';os.environ['PYTEST_ADDOPTS']=''
    import gc
    import pytest
    require(gc.isenabled(),'default_GC_required')
    config=output/'pytest.ini';config.write_text('[pytest]\n',encoding='utf8')
    collector=Collection();argv=[TEST,'-q','--noconftest','-c',str(config),
        '--basetemp='+str(output/'tmp'),'--junitxml='+str(output/'tests.xml')]
    report['pytest_arguments']=argv;code=int(pytest.main(argv,plugins=[collector]))
    rows=ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').exists() else []
    bad=[{'name':r.attrib.get('name'),'type':child.tag} for r in rows for child in r if child.tag in ('failure','error','skipped')]
    report.update(pytest_exit_code=code,test_count=len(rows),bad_tests=bad,collected_nodeids=collector.nodeids,
                  XML_sha256=sha(output/'tests.xml') if rows else None)
    require(code==0 and len(rows)==EXPECTED_TESTS and not bad and collector.candidate is not None,'functional_tests_failed')
    test=sys.modules['test_g31_circulation_planning_capture_v2_c_encoder']
    report['actual_extension']=actual_extension_identity(collector.candidate,binary,digest,prior['imported_DLLs'],plan)
    report['direct_support']=direct_probe(collector.candidate,test,output)
    report['binary']=prior['binary'];report['build_receipt']={'path':str(receipt),'sha256':expected_build_sha}
    require(sha(binary)==digest and gc.isenabled(),'binary_or_GC_changed')
    report['status']='functional_passed_synthetic_full_bytes'


def loaded_sources(plan):
    result={}
    for name,module in sorted(sys.modules.items()):
        value=getattr(module,'__file__',None)
        if not value:continue
        path=Path(value).resolve()
        if path.suffix=='.pyc':path=Path(__import__('importlib.util',fromlist=['source_from_cache']).source_from_cache(str(path)))
        if not path.is_file():continue
        if path.is_relative_to(ROOT):
            if path.suffix in ('.pyd','.dll'):
                require(path.parent==BUILD/'python' and path.name.startswith('_g31_planning_v2_typed_encoder'),'unexpected_project_binary')
            else:
                relative=path.relative_to(ROOT).as_posix()
                require(plan['source_sha256'].get(relative)==sha(path),'unfrozen_loaded_project:'+relative)
        elif path.suffix.lower() in ('.py','.pyd','.dll'):
            require(pinned_hash(plan['runtime_sha256'],path)==sha(path),'unfrozen_loaded_runtime:'+str(path))
        result[name]={'path':str(path),'sha256':sha(path)}
    require(not any('czr005_circulation' in n for n in sys.modules),'simulation_imported')
    return result


def worker(args):
    require(sys.stdin.readline()==args.admission+'\n','owned_admission')
    report={'schema':SCHEMA,'mode':args.mode,'status':'started','PID':os.getpid(),
        'started_UTC':datetime.now(timezone.utc).isoformat(),'actual_fixture_reads':0,
        'native_simulation_calls':0,'predictor_calls':0,'performance_runs':0}
    plan=None
    try:
        require(Path(sys.executable).resolve()==PYTHON.resolve() and sys.version_info[:3]==(3,11,9),'exact_interpreter')
        if args.mode=='prepare':prepare(args.output,report)
        else:
            report['plan_sha256']=args.plan_sha256;plan=verify_plan(args.plan,args.plan_sha256)
            if args.mode=='build':build(args.output,plan,report)
            else:functional(args.output,plan,report,args.build_output,args.build_receipt_sha256,args.build_external_sha256,args.plan.resolve())
    except BaseException as error:
        report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
        (args.output/'exception.txt').write_text(traceback.format_exc(),encoding='utf8')
    finally:
        if plan is not None:
            try:
                verify_plan(args.plan,args.plan_sha256);report['loaded_sources']=loaded_sources(plan)
                report['identity_verified_on_exit']=True
            except BaseException as error:
                report['status']='failed_exit_identity';report['identity_verified_on_exit']=False
                report['exit_error']={'type':type(error).__name__,'message':str(error)}
        report['worker_pre_receipt_export_seconds']=time.monotonic()-BOOT
        report['timing_scope']='BOOT follows time import; excludes first startup and this final receipt write. External launch clock required.'
        write(args.output/'receipt.json',report)
    print(json.dumps({k:report[k] for k in ('mode','status','worker_pre_receipt_export_seconds')}))
    return 0 if report['status'] in ('prepared_unexecuted','build_passed_unloaded','functional_passed_synthetic_full_bytes') else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('prepare','build','functional'),required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--plan',type=Path)
    parser.add_argument('--plan-sha256');parser.add_argument('--build-output',type=Path)
    parser.add_argument('--build-receipt-sha256');parser.add_argument('--worker',action='store_true');parser.add_argument('--admission')
    parser.add_argument('--build-external-sha256')
    args=parser.parse_args();args.output=args.output.resolve()
    if args.worker:return worker(args)
    args.output.mkdir(parents=True,exist_ok=False)
    require(args.mode=='prepare' or (args.plan and args.plan_sha256),'plan_arguments')
    require(args.mode!='functional' or (args.build_output and args.build_receipt_sha256 and args.build_external_sha256),'functional_build_arguments')
    token=uuid.uuid4().hex
    command=[str(PYTHON),'-m',MODULE,'--mode',args.mode,'--output',str(args.output),'--worker','--admission',token]
    if args.plan:command+=['--plan',str(args.plan.resolve()),'--plan-sha256',args.plan_sha256]
    if args.build_output:command+=['--build-output',str(args.build_output.resolve()),'--build-receipt-sha256',args.build_receipt_sha256,
                                  '--build-external-sha256',args.build_external_sha256]
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';os.environ['PYTEST_ADDOPTS']=''
    try:
        with (args.output/(args.mode+'.stdout.log')).open('x',encoding='utf8') as stdout,(args.output/(args.mode+'.stderr.log')).open('x',encoding='utf8') as stderr:
            result=bounded_windows_job.run(command,timeout=120-(time.monotonic()-BOOT),stdout=stdout,stderr=stderr,admission=token,cwd=ROOT)
    except BaseException as error:
        result={'status':'launch_failed','error':{'type':type(error).__name__,'message':str(error)}}
    result.update(command=command,whole_bound_seconds=120,parent_pre_receipt_export_seconds=time.monotonic()-BOOT,
                  final_export_and_pre_BOOT_startup_require_external_clock=True)
    write(args.output/'bounded_execution.json',result);print(json.dumps(result))
    return 0 if result['status']=='exited' and result['exitcode']==0 else 1


if __name__=='__main__':raise SystemExit(main())
