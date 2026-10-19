"""Export the fixed publication Git blobs and register both source byte layers.

No project module, model or native library is imported. Historical files and
Git state are read-only. New output names must not exist and are never reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys

import verify_publication as verifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
COMMIT = '49e847cb98e8c3154840bd930a59540168710c7e'
OLD = 'outputs/experiments/g31_ics_multirate_20261019/publication_001'
PLAN = 'outputs/experiments/g31_ics_multirate_20261019/final_validation_001/plan.json'


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


class GitBlobs:
    def __init__(self, root):
        self.process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read(self, name):
        verifier.require('\n' not in name and '\r' not in name, 'invalid_git_path')
        self.process.stdin.write((COMMIT + ':' + name + '\n').encode())
        self.process.stdin.flush()
        header = self.process.stdout.readline().decode().strip().split()
        verifier.require(len(header) == 3 and header[1] == 'blob', 'missing_fixed_git_blob:' + name)
        count = int(header[2])
        payload = self.process.stdout.read(count)
        verifier.require(len(payload) == count and self.process.stdout.read(1) == b'\n'
            and verifier.blob_digest(payload) == header[0], 'git_blob_transport_or_hash:' + name)
        return payload, header[0]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        verifier.require(self.process.returncode == 0, 'git_cat_file_exit')


def build(export):
    export = export.resolve()
    # A short sibling inside the user workspace avoids Windows MAX_PATH while
    # running the unchanged historical verifier, which has no long-path shim.
    verifier.require(export.is_relative_to(ROOT.parent) and not export.exists(), 'fresh_workspace_export_required')
    verifier.require(not (HERE / 'MANIFEST.json').exists(), 'immutable_new_publication_manifest')
    export.mkdir(parents=True)
    blobs = GitBlobs(ROOT)
    exported, identities = {}, {}
    try:
        old_bytes, old_blob = blobs.read(OLD + '/MANIFEST.json')
        old = json.loads(old_bytes)
        paths = [row['path'] for row in old['files']] + [OLD + '/MANIFEST.json', OLD + '/verify_publication.py']
        verifier.require(len(paths) == len(set(paths)), 'duplicate_export_path')
        for name in paths:
            payload, blob = blobs.read(name)
            target = verifier.safe_path(export, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(payload)
            exported[name] = payload
            identities[name] = blob
    finally:
        blobs.close()
    prior = subprocess.run([sys.executable, str(export / OLD / 'verify_publication.py')], cwd=export,
        capture_output=True, text=True, timeout=60)
    (HERE / 'original_verifier_stdout.json').write_text(prior.stdout, encoding='utf8', newline='\n')
    (HERE / 'original_verifier_stderr.log').write_text(prior.stderr, encoding='utf8', newline='\n')
    original_result = json.loads(prior.stdout)
    verifier.require(prior.returncode == 1 and original_result['status'] == 'failed', 'expected_original_verifier_failure')
    plan = json.loads(exported[PLAN])
    relations, eol_paths = [], []
    for original, pin in plan['source_pins'].items():
        archived = PureWindowsPath(plan['source_archive'][original]).relative_to(verifier.ORIGINAL).as_posix()
        executed = exported[archived]
        verifier.require(verifier.digest(executed) == pin, 'original_execution_archive_changed:' + original)
        source = PureWindowsPath(original)
        name = source.relative_to(verifier.ORIGINAL).as_posix() if source.is_relative_to(verifier.ORIGINAL) else None
        committed = exported[name] if name is not None else None
        transform = 'external_archive_only' if name is None else 'byte_identical' if executed == committed else 'executed_CRLF_to_committed_LF'
        relation = {'original_path': original, 'repository_path': name, 'execution_archive_path': archived,
            'executed_worktree_sha256': pin, 'executed_bytes': len(executed),
            'committed_content_sha256': verifier.digest(committed) if committed is not None else None,
            'committed_bytes': len(committed) if committed is not None else None,
            'git_blob_sha1': identities[name] if name is not None else None, 'transform': transform}
        verifier.verify_relation(relation, executed, committed)
        if transform == 'executed_CRLF_to_committed_LF':
            eol_paths.append(name)
        relations.append(relation)
    expected_failures = set(eol_paths) | {'tested_source:' + name for name in eol_paths}
    verifier.require(len(eol_paths) == 56 and len(original_result['failures']) == 112
            and set(original_result['failures']) == expected_failures, 'reproduced_failure_domain_differs_from_review')
    files = []
    for old_row in old['files']:
        name = old_row['path']
        payload = exported[name]
        if verifier.digest(payload) != old_row['sha256']:
            verifier.require(name in eol_paths, 'unexpected_non_source_publication_change:' + name)
        files.append({'path': name, 'committed_content_sha256': verifier.digest(payload), 'committed_bytes': len(payload),
            'git_blob_sha1': identities[name], 'executed_publication_worktree_sha256': old_row['sha256'],
            'executed_publication_bytes': old_row['bytes']})
    tree = subprocess.check_output(['git', 'rev-parse', COMMIT + '^{tree}'], cwd=ROOT, text=True).strip()
    manifest = {'schema': verifier.SCHEMA, 'fixed_git_commit': COMMIT, 'fixed_git_tree': tree,
        'historical_publication_manifest': {'path': OLD + '/MANIFEST.json', 'sha256': verifier.digest(old_bytes), 'git_blob_sha1': old_blob},
        'historical_execution_plan': {'path': PLAN, 'sha256': verifier.digest(exported[PLAN]), 'git_blob_sha1': identities[PLAN]},
        'files': files, 'source_relations': relations, 'explicit_EOL_source_paths': sorted(eol_paths),
        'execution_archives_modified': False, 'historical_manifests_modified': False,
        'verification_scope': 'Exact exported fixed Git publication subset and its exact historical execution archives; no evidence normalization.',
        'new_scripts_and_manifest_authentication': 'Their eventual Git commit identity; they are not members of the old fixed publication.',
        'historical_six_missing_sources_resolved': False}
    write_new(HERE / 'MANIFEST.json', manifest)
    new_dir = export / HERE.relative_to(ROOT)
    new_dir.mkdir(parents=True)
    shutil.copyfile(HERE / 'verify_publication.py', new_dir / 'verify_publication.py')
    shutil.copyfile(HERE / 'MANIFEST.json', new_dir / 'MANIFEST.json')
    checked = subprocess.run([sys.executable, str(new_dir / 'verify_publication.py')], cwd=export,
        capture_output=True, text=True, timeout=60)
    verification = json.loads(checked.stdout)
    write_new(HERE / 'git_export_verification.json', verification)
    verifier.require(checked.returncode == 0 and verification['status'] == 'passed', 'new_git_export_verifier_failed')
    report = {'status': 'completed_dual_source_publication_repair', 'fixed_git_commit': COMMIT, 'fixed_git_tree': tree,
        'export_root': str(export), 'export_kind': 'Exact git cat-file blob export of all 4774 manifest members plus original manifest/verifier; not a full repository clone.',
        'exported_fixed_tree_files': len(paths), 'git_blob_hashes_verified': len(identities),
        'original_verifier_returncode': prior.returncode, 'original_failure_count': len(original_result['failures']),
        'original_unique_EOL_sources': len(eol_paths), 'original_failure_paths': original_result['failures'],
        'new_verification': verification, 'source_relation_counts': {kind: sum(row['transform'] == kind for row in relations)
            for kind in ('byte_identical', 'executed_CRLF_to_committed_LF', 'external_archive_only')},
        'old_manifest_sha256': verifier.digest(old_bytes), 'new_manifest_sha256': verifier.digest((HERE / 'MANIFEST.json').read_bytes()),
        'builder_sha256': verifier.digest(Path(__file__).read_bytes()),
        'verifier_sha256': verifier.digest((HERE / 'verify_publication.py').read_bytes()),
        'native_executed': False, 'training_executed': False, 'historical_files_modified': False}
    write_new(HERE / 'repair_report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.export)
    print(json.dumps({key: result[key] for key in ('status', 'original_failure_count', 'original_unique_EOL_sources', 'source_relation_counts')}, indent=2))
