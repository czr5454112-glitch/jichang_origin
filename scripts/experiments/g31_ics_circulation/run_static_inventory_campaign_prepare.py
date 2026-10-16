"""Unexecuted owned120 metadata launcher for the frozen sicp1 candidate.

The only preparation-function rebinding extends its source archive with this
launcher and its measured outer wrapper. No campaign, C loader, model or native
execution is dispatched. The reviewed preparation function retains its code,
defaults, closure and every other defining global.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType
import uuid

from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = __package__ + '.run_static_inventory_campaign_prepare'
WRAPPER = ROOT/'outputs/invoke_sicm1.ps1'
PURE = ROOT/'outputs/sicp1'
PURE_PINS = {
    'plan.json': 'b34a896cf0b9c503536198fc6131faa18b0acfd00629560d62bf14a333805d6a',
    'receipt.json': '63ac2801d83165115d4710b500c04df43064b1b705a5944aeb284c9ce50e64fb',
    'external_application_wall.json': '2fea6cfa084b295919d17c0020228082ef830d79238260f27832f554a178bb13',
    'root_saved_review_001.json': 'f2921a9d07a5a7c6ed7b40d33d0bfc27771d514c59bad48de0cf4b0ca36d93e7',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def worker(output, pure_directory):
    # This import occurs only after owned Job assignment and stdin admission.
    from . import prepare_initial_owner_route_static_inventory_campaign as frozen
    if Path(pure_directory).resolve() != PURE.resolve():
        raise ValueError('metadata_exact_sicp1_directory')
    for name, digest in PURE_PINS.items():
        if sha(PURE/name) != digest:
            raise ValueError('metadata_sicp1_evidence_changed:' + name)
    sidecar = output/'metadata_source_binding.json'
    if (not sidecar.resolve().is_relative_to(output.resolve())
            or len(str(sidecar.resolve())) >= 260 or sidecar.exists()):
        raise ValueError('metadata_sidecar_preflight')

    def source_files(directory):
        files = frozen.source_files(directory)
        closure = frozen.c.image.source_closure(ROOT, (MODULE,))
        closure[WRAPPER.relative_to(ROOT).as_posix()] = WRAPPER.read_bytes()
        for name, data in frozen.archive.canonical_sources(closure).items():
            if name in files and files[name] != data:
                raise ValueError('metadata_source_union_conflict')
            files[name] = data
        return frozen.archive.canonical_sources(files)

    namespace = {**frozen.prepare.__globals__, 'source_files': source_files}
    prepare = FunctionType(frozen.prepare.__code__, namespace,
        frozen.prepare.__name__, frozen.prepare.__defaults__, frozen.prepare.__closure__)
    prepare.__kwdefaults__ = frozen.prepare.__kwdefaults__
    if (set(namespace) != set(frozen.prepare.__globals__)
            or any(value is not (source_files if name == 'source_files'
                else frozen.prepare.__globals__[name]) for name, value in namespace.items())
            or prepare.__code__ is not frozen.prepare.__code__
            or prepare.__defaults__ is not frozen.prepare.__defaults__
            or prepare.__closure__ is not frozen.prepare.__closure__
            or prepare.__kwdefaults__ is not frozen.prepare.__kwdefaults__):
        raise ValueError('metadata_original_prepare_full_globals')
    result = prepare(output, pure_directory)
    for name, digest in PURE_PINS.items():
        if sha(PURE/name) != digest:
            raise ValueError('metadata_sicp1_evidence_exit_changed:' + name)
    write(sidecar, {
        'schema': 'g31.static_inventory_campaign.metadata_binding.v1',
        'status': 'prepared_without_execution',
        'original_prepare_code_defaults_closure_retained': True,
        'only_prepare_global_rebinding': 'source_files',
        'archive_addition': 'This launcher, its complete import closure and the outer measured wrapper; original all-target preflight and current/archive exit checks are retained.',
        'pure_evidence': {name: {'path': str(PURE/name), 'sha256': digest}
            for name, digest in PURE_PINS.items()},
        'campaign': result['campaign'], 'native_calls': 0, 'C_loads': 0,
        'model_calls': 0, 'performance_runs': 0,
    })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pure-directory', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        if sys.stdin.readline() != args.admission+'\n':
            raise ValueError('owned_metadata_admission')
        print(json.dumps(worker(output, args.pure_directory)))
        return 0
    if not output.is_relative_to((ROOT/'outputs').resolve()) or output.exists():
        raise ValueError('owned_metadata_output_exists_or_outside')
    siblings = {name: output.with_name(output.name+suffix) for name, suffix in (
        ('claim', '.metadata_claim.json'), ('stdout', '.metadata_worker.stdout.log'),
        ('stderr', '.metadata_worker.stderr.log'), ('receipt', '.metadata_parent.json'))}
    # Validate every parent target before writing even the claim.
    if any(path.exists() or len(str(path)) >= 260 or path.parent != output.parent
            for path in siblings.values()):
        raise ValueError('owned_metadata_parent_target_preflight')
    token = uuid.uuid4().hex
    command = [sys.executable, '-m', MODULE, '--output', str(output),
        '--pure-directory', str(args.pure_directory.resolve()), '--worker', '--admission', token]
    write(siblings['claim'], {'shared_seconds': 120., 'output': str(output),
        'command': command, 'cwd': str(ROOT), 'purpose': 'metadata_only'})
    process, error = None, None
    try:
        with siblings['stdout'].open('x', encoding='utf8') as stdout, siblings['stderr'].open('x', encoding='utf8') as stderr:
            remaining = 120.-(time.monotonic()-BOOT)-1.
            if remaining <= 0:
                raise TimeoutError('owned_metadata_budget_before_worker')
            process = bounded_windows_job.run(command, timeout=remaining, stdout=stdout,
                stderr=stderr, admission=token, cwd=ROOT)
    except BaseException as exc:
        error = repr(exc)
    elapsed = time.monotonic()-BOOT
    passed = (error is None and process is not None and process['status'] == 'exited'
        and process['exitcode'] == 0 and elapsed < 120.)
    receipt = {'status': 'passed' if passed else 'failed_or_unknown',
        'process': process, 'error': error, 'command': command, 'cwd': str(ROOT),
        'output_directory': str(output), 'shared_seconds': 120.,
        'before_parent_receipt_seconds': elapsed,
        'native_calls': 0, 'C_loads': 0, 'model_calls': 0, 'performance_runs': 0,
        'external_full_startup_exit_clock_required': True}
    write(siblings['receipt'], receipt)
    print(json.dumps(receipt))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
