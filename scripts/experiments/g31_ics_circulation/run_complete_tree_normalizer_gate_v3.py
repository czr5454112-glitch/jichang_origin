"""Bounded isolated data-helper build or functional test; no simulation or saved18."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
from datetime import datetime, timezone
import hashlib
import json
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
PLAN = OUT/'c_tree_normalizer_build_prepare_003/plan.json'
ORIGINAL_PLAN = OUT/'c_tree_normalizer_prototype_001/source_plan.json'
ORIGINAL_PLAN_SHA = '4253992c420d32a0e918724e3d398704025d21bfd1ac9420f2525f875ee5f9c1'
PYTHON = Path('C:/PROGRAMING/python3.11.9/python.exe')
VC = Path('C:/PROGRAMING/visual studio/Visual studio/VC')
VCBIN = VC/'Tools/MSVC/14.41.34120/bin/Hostx64/x64'
BUILD = ROOT/'build_complete_tree_normalizer_003'
TEST = 'tests/test_g31_circulation_complete_tree_normalizer_candidate.py'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding='utf8')


def require(ok, reason):
    if not ok: raise ValueError('c_normalizer_gate:'+reason)


def source_inventory(plan, functional):
    names = set(plan['source_sha256']) | {
        str(Path(__file__).relative_to(ROOT)).replace('\\', '/'),
        str(Path(bounded_windows_job.__file__).relative_to(ROOT)).replace('\\', '/'),
        'scripts/experiments/g31_ics_circulation/initial_owner_route_json_v3.py',
        'scripts/experiments/g31_ics_circulation/initial_owner_route_image.py',
        'scripts/experiments/g31_ics_circulation/complete_root_evidence_codec.py'}
    if functional:
        from . import initial_owner_route_image as image
        files = image.source_closure(ROOT, (__package__+'.run_complete_tree_normalizer_gate_v3',
            __package__+'.complete_tree_normalizer_candidate', TEST[:-3].replace('/', '.')))
        names.update(files)
    return {name: sha(ROOT/name) for name in sorted(names)}


def frozen_identity():
    references = {'initial_owner_route_entry_codec_campaign_prepare_001/campaign.json':
        '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a',
        'complete_root_evidence_codec_pair_prepare_001/plan.json':
        '11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'}
    checked = {}
    for relative, expected in references.items():
        path = OUT/relative; require(sha(path) == expected, 'frozen_plan_changed')
        plan = json.loads(path.read_text()); rows = {}
        for name in ('initial_owner_route_json_v3.py', 'initial_owner_route_image.py', 'complete_root_evidence_codec.py'):
            live = ROOT/'scripts/experiments/g31_ics_circulation'/name
            key = str(live); digest = plan['source_sha256'][key]
            archive = path.parent/plan['source_archive'][key]
            require(sha(live) == digest and sha(archive) == digest, 'frozen_original_changed:'+name)
            rows[key] = {'sha256': digest, 'archive': str(archive)}
        checked[relative] = {'plan_sha256': expected, 'source_count': len(plan['source_sha256']), 'checked_originals': rows}
    return checked


def snapshot(paths):
    return {str(path.resolve()): sha(path) for path in sorted(set(paths)) if path.is_file()}


def tool_paths(env):
    # Pin installed headers and static import/runtime libraries before compiling,
    # not merely whichever subset later happened to be recorded in ninja's deps.
    paths = [PYTHON, PYTHON.parent/'python311.dll', PYTHON.parent/'python3.dll',
             Path('C:/Program Files/CMake/bin/cmake.exe'),
             Path('C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe'), Path('C:/Windows/System32/cmd.exe')]
    paths += list(VCBIN.glob('*.exe'))+list(VCBIN.glob('*.dll'))
    paths += list((VC/'Auxiliary/Build').glob('*.bat'))
    roots = [PYTHON.parent/'include', PYTHON.parent/'libs']
    for key in ('INCLUDE', 'LIB'):
        roots.extend(Path(s) for s in env.get(key, '').split(';') if s)
    for directory in dict.fromkeys(roots):
        require(directory.is_dir(), 'missing_tool_directory:'+str(directory))
        paths.extend(p for p in directory.rglob('*') if p.is_file())
    for directory in (Path('C:/Program Files/CMake/share/cmake-4.3/Modules/FindPython'),
                      Path('C:/Program Files/CMake/share/cmake-4.3/Modules/FindPython3')):
        if directory.is_dir(): paths.extend(directory.rglob('*.cmake'))
    paths.append(Path('C:/Program Files/CMake/share/cmake-4.3/Modules/FindPython3.cmake'))
    for name in ('rc.exe', 'mt.exe'):
        found = shutil.which(name, path=env.get('PATH'))
        require(found is not None, 'SDK_tool:'+name); paths.append(Path(found))
    return paths


def run_command(command, output, name, commands, env=None):
    started = time.perf_counter_ns()
    with (output/(name+'.stdout.log')).open('xb') as stdout, (output/(name+'.stderr.log')).open('xb') as stderr:
        process = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, check=False)
    record = {'command': command, 'exit_code': process.returncode,
              'wall_ns': time.perf_counter_ns()-started,
              'stdout_sha256': sha(output/(name+'.stdout.log')),
              'stderr_sha256': sha(output/(name+'.stderr.log'))}
    commands.append(record); write(output/'commands.json', commands)
    require(process.returncode == 0, name+'_exit_'+str(process.returncode))


def build_worker(output, plan, report):
    require(not BUILD.exists(), 'fresh_build_required')
    BUILD.mkdir()
    env_script = output/'environment.cmd'
    env_script.write_text('@echo off\ncall "'+str(VC/'Auxiliary/Build/vcvars64.bat')+'" >nul\n'
        'if errorlevel 1 exit /b %errorlevel%\nset VSLANG=1033\nset\n', encoding='utf8')
    # Keep cmd argv[0] in native Windows spelling: a forward-slash argv[0]
    # fails before the batch starts (diagnostic001/002). Ordinary OEM output
    # follows the accepted027 launcher. The earlier /u hypothesis is unproven.
    env_command = [str(Path('C:/Windows/System32/cmd.exe')), '/d', '/c', str(env_script)]
    process = subprocess.run(env_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, cwd=ROOT)
    (output/'environment.stderr.log').write_bytes(process.stderr)
    report['environment_command'] = {'argv': env_command, 'exit_code': process.returncode,
        'stdout_sha256': hashlib.sha256(process.stdout).hexdigest(),
        'stderr_sha256': hashlib.sha256(process.stderr).hexdigest(), 'encoding': 'oem'}
    require(process.returncode == 0, 'MSVC_environment')
    env = dict(os.environ)
    for line in process.stdout.decode('oem').splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1); env[key.upper()] = value
    report['build_environment'] = {k: env.get(k) for k in ('INCLUDE', 'LIB', 'PATH', 'VCTOOLSVERSION',
        'WINDOWSSDKVERSION', 'VSCMD_ARG_TGT_ARCH', 'VSLANG')}
    require(env.get('VSCMD_ARG_TGT_ARCH') == 'x64', 'MSVC_arch')
    paths = tool_paths(env); before = snapshot(paths)
    report['toolchain_before'] = before
    write(output/'toolchain_before.json', before)
    for path in (PYTHON.parent/'include').rglob('*'):
        if path.is_file():
            dest = output/'CPython_headers'/path.relative_to(PYTHON.parent/'include')
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, dest)
            require(sha(dest) == before[str(path.resolve())], 'header_archive')
    commands = []
    report['commands'] = commands
    try:
        run_command(plan['configure_command'], output, 'configure', commands, env)
        run_command(plan['build_command'], output, 'build', commands, env)
        binaries = list((BUILD/'python').glob('_g31_complete_tree_normalizer*.pyd'))
        require(len(binaries) == 1, 'exact_binary_count')
        binary = binaries[0]
        report['binary'] = {'path': str(binary), 'sha256': sha(binary), 'size': binary.stat().st_size}
        for kind in ('DEPENDENTS', 'IMPORTS'):
            run_command([str(VCBIN/'dumpbin.exe'), '/'+kind, str(binary)], output, kind.lower(), commands, env)
        lines = (output/'dependents.stdout.log').read_text(encoding='utf8', errors='strict').splitlines()
        imports = [line.strip() for line in lines if re.fullmatch(r'\s+[\w.\-]+\.dll\s*', line, re.I)]
        require(imports and 'python311.dll' in [s.lower() for s in imports], 'Python_DLL_import')
        allowed = lambda name: name.lower() in {'python311.dll', 'kernel32.dll', 'vcruntime140.dll',
            'vcruntime140_1.dll', 'ucrtbase.dll'} or name.lower().startswith('api-ms-win-crt-')
        require(all(allowed(name) for name in imports), 'unexpected_import:'+repr(imports))
        report['imported_DLLs'] = imports
        report['imports_inspected_before_any_extension_load'] = True
        resolved = {}
        for name in imports:
            candidates = [PYTHON.parent/name, VCBIN/name, Path('C:/Windows/System32')/name]
            hit = next((p for p in candidates if p.is_file()), None)
            resolved[name] = {'path': str(hit), 'sha256': sha(hit)} if hit else {'API_set_resolution': 'Windows loader contract'}
        report['resolved_runtime_identity'] = resolved
        run_command([str(Path('C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe')), '-C', str(BUILD), '-t', 'deps'],
            output, 'compiler_dependencies', commands, env)
        report['build_metadata'] = {str(p.relative_to(BUILD)): sha(p) for p in
            (BUILD/'CMakeCache.txt', BUILD/'build.ninja', BUILD/'.ninja_deps', BUILD/'.ninja_log') if p.is_file()}
        report['status'] = 'build_passed_imports_inspected_unloaded'
    finally:
        after = snapshot(paths); report['toolchain_after'] = after
        report['toolchain_changed'] = [p for p in set(before)|set(after) if before.get(p) != after.get(p)]
        write(output/'toolchain_after.json', after)
        if report['toolchain_changed']: report['status'] = 'failed_toolchain_changed'


def functional_worker(output, plan, report, build_output):
    build = json.loads((build_output/'receipt.json').read_text())
    outer = json.loads((build_output/'bounded_execution.json').read_text())
    require(build['status'] == 'build_passed_imports_inspected_unloaded' and not build['source_changed'] and
        not build['toolchain_changed'] and outer['status'] == 'exited' and outer['exitcode'] == 0 and
        build['imports_inspected_before_any_extension_load'], 'accepted_build_required')
    binary = Path(build['binary']['path'])
    require(sha(binary) == build['binary']['sha256'], 'binary_changed')
    require(snapshot(Path(p) for p in build['toolchain_before']) == build['toolchain_before'], 'toolchain_changed')
    report['build_receipt'] = {'path': str(build_output/'receipt.json'), 'sha256': sha(build_output/'receipt.json')}
    report['binary'] = build['binary']; report['binary_before'] = sha(binary)
    os.environ['G31_TREE_NORMALIZER_BINARY'] = str(binary)
    os.environ['G31_TREE_NORMALIZER_SHA256'] = report['binary_before']
    import gc
    report['GC_enabled_before'] = gc.isenabled()
    import pytest
    command = plan['future_functional_command'][3:]+['--basetemp='+str(output/'tmp'), '--junitxml='+str(output/'tests.xml')]
    report['pytest_arguments'] = command
    exit_code = pytest.main(command)
    report['pytest_exit_code'] = int(exit_code)
    rows = ET.parse(output/'tests.xml').getroot().findall('.//testcase') if (output/'tests.xml').is_file() else []
    report['tests'] = len(rows)
    report['bad_tests'] = [{'name': r.attrib.get('name'), 'type': n.tag, 'message': n.attrib.get('message')}
        for r in rows for n in r if n.tag in ('failure', 'error', 'skipped')]
    report['XML_sha256'] = sha(output/'tests.xml') if rows else None
    report['GC_enabled_after'] = gc.isenabled()
    report['binary_after'] = sha(binary)
    report['toolchain_changed'] = snapshot(Path(p) for p in build['toolchain_before']) != build['toolchain_before']
    report['loaded_project_modules'] = {name: {'path': str(Path(m.__file__).resolve()), 'sha256': sha(m.__file__)}
        for name, m in sorted(sys.modules.items()) if getattr(m, '__file__', None) and
        Path(m.__file__).resolve().is_relative_to(ROOT) and Path(m.__file__).suffix == '.py'}
    for item in report['loaded_project_modules'].values():
        relative = str(Path(item['path']).relative_to(ROOT)).replace('\\', '/')
        require(report['source_before'].get(relative) == item['sha256'], 'loaded_source_not_archived:'+relative)
    require(not any('czr005_circulation' in name for name in sys.modules), 'simulation_module_loaded')
    require(exit_code == 0 and len(rows) >= 60 and not report['bad_tests'] and
        report['binary_before'] == report['binary_after'] and not report['toolchain_changed'] and
        report['GC_enabled_before'] and report['GC_enabled_after'], 'functional_gate_failed')
    report['status'] = 'functional_passed_saved18_excluded'


def worker(args):
    require(sys.stdin.readline() == args.admission+'\n', 'admission')
    output = args.output.resolve()
    report = {'schema': 'g31.complete_tree_normalizer.execution.v1', 'mode': args.mode, 'status': 'started',
        'started_UTC': datetime.now(timezone.utc).isoformat(), 'PID': os.getpid(),
        'source_plan_sha256': sha(PLAN), 'extension_load_requested': args.mode == 'functional',
        'native_simulation_calls': 0, 'predictor_calls': 0, 'saved18_reads': 0, 'performance_runs': 0}
    before = {}
    try:
        require(sha(PLAN) == args.plan_sha256 and sha(ORIGINAL_PLAN) == ORIGINAL_PLAN_SHA and
            Path(sys.executable).resolve() == PYTHON.resolve(), 'plan_or_python')
        plan = json.loads(PLAN.read_text())
        require(sha(Path(__file__)) == plan['amendment']['runner_sha256'], 'execution_runner_changed')
        require(plan['source_sha256'] == json.loads(ORIGINAL_PLAN.read_text())['source_sha256'], 'core_source_revision')
        report['frozen_originals_before'] = frozen_identity()
        before = source_inventory(plan, args.mode == 'functional')
        require(all(before.get(p) == h for p, h in plan['source_sha256'].items()), 'reviewed_source_changed')
        report['source_before'] = before
        for name, digest in before.items():
            dest = output/'source'/name; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, dest); require(sha(dest) == digest, 'archive_changed')
        shutil.copyfile(PLAN, output/'source_plan.json')
        shutil.copyfile(ORIGINAL_PLAN, output/'original_source_plan.json')
        write(output/'receipt.json', report)
        if args.mode == 'build': build_worker(output, plan, report)
        else: functional_worker(output, plan, report, args.build_output.resolve())
    except BaseException as error:
        report['status'] = 'failed'; report['error'] = {'type': type(error).__name__, 'message': str(error)}
        (output/'exception.txt').write_text(traceback.format_exc(), encoding='utf8')
    finally:
        after = {name: sha(ROOT/name) for name in before}
        report['source_after'] = after
        report['source_changed'] = [p for p in before if before[p] != after[p]]
        if report['source_changed']: report['status'] = 'failed_source_changed'
        try:
            report['frozen_originals_after'] = frozen_identity()
            require(report.get('frozen_originals_before') == report['frozen_originals_after'], 'frozen_originals_drift')
        except BaseException as error:
            report['status'] = 'failed_frozen_originals'; report['frozen_exit_error'] = str(error)
        report['worker_seconds_including_imports'] = time.monotonic()-BOOT
        write(output/'receipt.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'mode', 'worker_seconds_including_imports', 'source_changed')}))
    return 0 if report['status'] in ('build_passed_imports_inspected_unloaded', 'functional_passed_saved18_excluded') else 1


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--mode', choices=('build', 'functional'), required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--build-output', type=Path)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--admission')
    args = parser.parse_args()
    if args.worker: return worker(args)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    cap = 180 if args.mode == 'build' else 120
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', __package__+'.run_complete_tree_normalizer_gate_v3', '--mode', args.mode,
        '--output', str(output), '--worker', '--admission', token, '--plan-sha256', args.plan_sha256]
    if args.build_output: command += ['--build-output', str(args.build_output.resolve())]
    with (output/'stdout.log').open('x', encoding='utf8') as out, (output/'stderr.log').open('x', encoding='utf8') as err:
        process = bounded_windows_job.run(command, timeout=cap-(time.monotonic()-BOOT),
            stdout=out, stderr=err, admission=token, cwd=ROOT)
    process['command'] = command; process['whole_bound_seconds'] = cap
    process['launcher_seconds_including_imports'] = time.monotonic()-BOOT
    write(output/'bounded_execution.json', process)
    print(json.dumps(process))
    return 0 if process['status'] == 'exited' and process['exitcode'] == 0 else 1


if __name__ == '__main__': raise SystemExit(main())
