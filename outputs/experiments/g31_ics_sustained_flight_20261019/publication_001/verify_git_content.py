"""Verify actual index/commit blobs, optionally exporting a fresh selected tree.

Uses one git cat-file process and streaming SHA256, without changing Git state.
An export is a new directory only. No native code or training is executed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
PUB = Path(__file__).resolve().parent


def require_exact_changes(actual, expected):
    actual, expected = set(actual), set(expected)
    if actual != expected:
        raise ValueError({'unexpected_changed': sorted(actual-expected),
                          'missing_changed': sorted(expected-actual)})


def require_regular_selected_modes(modes, expected):
    invalid = {name: modes.get(name) for name in expected
               if modes.get(name) not in ('100644', '100755')}
    if invalid:
        raise ValueError({'non_regular_or_missing_selected_paths': invalid})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit')
    p.add_argument('--export', type=Path)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    manifest_path = PUB / 'MANIFEST.json'
    manifest = json.loads(manifest_path.read_bytes())
    expected = {r['path']: r['expected_committed_content_sha256'] for r in manifest['files']}
    for name in ('MANIFEST.json', 'selected_files.txt', 'selection_report.json'):
        local = PUB / name
        expected[local.relative_to(ROOT).as_posix()] = hashlib.sha256(local.read_bytes()).hexdigest()
    if a.commit:
        identity = subprocess.check_output(['git', 'rev-parse', '--verify', a.commit + '^{commit}'], cwd=ROOT, text=True).strip()
        base = subprocess.check_output(['git', 'rev-parse', '--verify',
            manifest['base_commit'] + '^{commit}'], cwd=ROOT, text=True).strip()
        subprocess.run(['git', 'merge-base', '--is-ancestor', base, identity], cwd=ROOT, check=True)
        changed = filter(None, subprocess.check_output(['git', 'diff', '--name-only', '-z',
            base, identity, '--'], cwd=ROOT).decode('utf-8').split('\0'))
        require_exact_changes(changed, expected)
        records = subprocess.check_output(['git', 'ls-tree', '-r', '-z', '--full-tree', identity], cwd=ROOT).split(b'\0')
        blobs = {}; modes = {}
        for row in filter(None, records):
            info, name = row.split(b'\t', 1)
            mode, kind, oid = info.split()
            modes[name.decode('utf-8')] = mode.decode('ascii')
            if kind == b'blob':
                blobs[name.decode('utf-8')] = oid.decode('ascii')
    else:
        identity = 'index'
        records = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT).split(b'\0')
        blobs = {}; modes = {}
        for row in filter(None, records):
            info, name = row.split(b'\t', 1)
            mode, oid, stage = info.split()
            assert stage == b'0', 'Unmerged index'
            blobs[name.decode('utf-8')] = oid.decode('ascii')
            modes[name.decode('utf-8')] = mode.decode('ascii')
        staged = set(filter(None, subprocess.check_output(
            ['git', 'diff', '--cached', '--name-only', '-z'], cwd=ROOT).decode('utf-8').split('\0')))
        require_exact_changes(staged, expected)
    assert set(expected) <= set(blobs), sorted(set(expected)-set(blobs))
    require_regular_selected_modes(modes, expected)
    export = a.export.resolve() if a.export else None
    if export:
        assert export.is_relative_to(ROOT.parent) and not export.exists() and export != ROOT
        export.mkdir(parents=True)
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    failures = []; total = 0; started = time.perf_counter()
    try:
        for name in sorted(expected):
            process.stdin.write((blobs[name]+'\n').encode('ascii')); process.stdin.flush()
            header = process.stdout.readline().split()
            assert len(header) == 3 and header[1] == b'blob'
            remaining = int(header[2]); total += remaining
            h = hashlib.sha256(); output = None
            if export:
                path = (export / name).resolve()
                assert path.is_relative_to(export)
                path.parent.mkdir(parents=True, exist_ok=True)
                output = path.open('xb')
            try:
                while remaining:
                    block = process.stdout.read(min(remaining, 1024*1024))
                    assert block, 'Unexpected cat-file EOF'
                    remaining -= len(block); h.update(block)
                    if output: output.write(block)
            finally:
                if output: output.close()
            assert process.stdout.read(1) == b'\n'
            if h.hexdigest() != expected[name]:
                failures.append({'path': name, 'expected': expected[name], 'actual': h.hexdigest()})
    finally:
        process.stdin.close(); process.stdout.close(); process.wait(timeout=60)
    report = {'schema': 'g31.selected_git_blob_verification.v1', 'status': 'passed' if not failures else 'failed',
              'identity': identity, 'files': len(expected), 'bytes': total, 'failures': failures,
              'export': str(export) if export else None, 'wall_seconds': time.perf_counter()-started,
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'changed_paths_exactly_match_selected_publication': True,
              'selected_git_entries_are_regular_files': True,
              'commit_base_ancestor_verified': bool(a.commit),
              'git_mutated': False, 'native_executed': False, 'training_executed': False}
    with a.report.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
