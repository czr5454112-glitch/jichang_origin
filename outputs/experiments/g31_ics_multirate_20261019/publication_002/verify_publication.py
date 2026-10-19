"""Verify fixed Git content and archived execution bytes as separate identities.

Standard library only. Run against an exact export of the declared Git tree.
Current files are never normalized before hashing. The only transformation is
an explicitly enumerated relation from an exact execution archive to an exact
Git source blob. No raw result, log, manifest or other evidence is normalized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

SCHEMA = 'g31.research_publication.dual_source.v2'
ORIGINAL = PureWindowsPath('C:/PROGRAMING/czr005/.g31_ics_circulation_worktree')
HERE = Path(__file__).resolve().parent


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def blob_digest(payload):
    return hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()


def safe_path(root, name):
    require(type(name) is str and name and '\\' not in name, 'invalid_relative_path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in name.split('/'))
            and ':' not in name, 'unsafe_relative_path:' + name)
    target = root.joinpath(*path.parts).resolve()
    require(target.is_relative_to(root), 'path_escapes_root:' + name)
    return target


def verify_relation(relation, executed, committed):
    require(digest(executed) == relation['executed_worktree_sha256']
            and len(executed) == relation['executed_bytes'], 'executed_source_bytes_changed')
    if relation['transform'] == 'external_archive_only':
        require(relation['repository_path'] is None and committed is None
                and relation['committed_content_sha256'] is None and relation['git_blob_sha1'] is None,
                'external_archive_claims_git_identity')
        return
    require(committed is not None and digest(committed) == relation['committed_content_sha256']
            and len(committed) == relation['committed_bytes']
            and blob_digest(committed) == relation['git_blob_sha1'], 'committed_source_bytes_changed')
    if relation['transform'] == 'byte_identical':
        require(executed == committed, 'declared_identical_source_differs')
    elif relation['transform'] == 'executed_CRLF_to_committed_LF':
        name = relation['repository_path']
        require(type(name) is str and name.startswith('src/czr005/') and name.endswith('.py'),
                'EOL_relation_outside_enumerated_source_domain')
        require(b'\r\n' in executed and b'\r' not in executed.replace(b'\r\n', b'')
                and b'\r' not in committed and executed != committed
                and executed.replace(b'\r\n', b'\n') == committed, 'declared_EOL_relation_not_exact')
    else:
        raise ValueError('unknown_source_transform')


def verify(root, manifest_path):
    root = Path(root).resolve()
    manifest = json.loads(Path(manifest_path).read_bytes())
    require(manifest['schema'] == SCHEMA, 'manifest_schema')
    require(len(manifest['fixed_git_commit']) == 40 and len(manifest['fixed_git_tree']) == 40,
            'fixed_git_identity')
    failures = []
    files, contents = {}, {}
    for row in manifest['files']:
        name = row['path']
        require(name not in files, 'duplicate_publication_path:' + name)
        files[name] = row
        try:
            payload = safe_path(root, name).read_bytes()
            require(len(payload) == row['committed_bytes'] and digest(payload) == row['committed_content_sha256']
                    and blob_digest(payload) == row['git_blob_sha1'], 'committed_file_identity:' + name)
            contents[name] = payload
        except (OSError, ValueError) as error:
            failures.append(str(error))
    old_item = manifest['historical_publication_manifest']
    old_bytes = safe_path(root, old_item['path']).read_bytes()
    require(digest(old_bytes) == old_item['sha256'], 'historical_manifest_bytes_changed')
    old = json.loads(old_bytes)
    old_files = {row['path']: row for row in old['files']}
    require(len(old_files) == len(old['files']) and set(files) == set(old_files), 'original_publication_domain_changed')
    for name, row in files.items():
        require(row['executed_publication_worktree_sha256'] == old_files[name]['sha256']
                and row['executed_publication_bytes'] == old_files[name]['bytes'], 'old_manifest_binding:' + name)
    plan_item = manifest['historical_execution_plan']
    plan_bytes = safe_path(root, plan_item['path']).read_bytes()
    require(digest(plan_bytes) == plan_item['sha256'], 'historical_execution_plan_bytes_changed')
    plan = json.loads(plan_bytes)
    relations = manifest['source_relations']
    require(len(relations) == len(plan['source_pins'])
            and {row['original_path'] for row in relations} == set(plan['source_pins']), 'complete_execution_source_domain')
    current_count, external_count, eol_paths, source_paths = 0, 0, [], set()
    for relation in relations:
        original = relation['original_path']
        require(relation['executed_worktree_sha256'] == plan['source_pins'][original], 'original_execution_pin_changed')
        expected_archive = PureWindowsPath(plan['source_archive'][original]).relative_to(ORIGINAL).as_posix()
        require(relation['execution_archive_path'] == expected_archive, 'execution_archive_mapping_changed')
        original_path = PureWindowsPath(original)
        if original_path.is_relative_to(ORIGINAL):
            repository_path = original_path.relative_to(ORIGINAL).as_posix()
            require(relation['repository_path'] == repository_path and repository_path in files,
                    'original_repository_source_mapping_changed')
            current_count += 1
            source_paths.add(repository_path)
            committed = contents.get(repository_path)
            row = files[repository_path]
            require(relation['committed_content_sha256'] == row['committed_content_sha256']
                    and relation['committed_bytes'] == row['committed_bytes']
                    and relation['git_blob_sha1'] == row['git_blob_sha1']
                    and relation['executed_worktree_sha256'] == row['executed_publication_worktree_sha256'],
                    'two_source_layers_not_bound')
            if relation['transform'] == 'executed_CRLF_to_committed_LF':
                eol_paths.append(repository_path)
        else:
            require(relation['repository_path'] is None, 'external_source_relocated_into_repository')
            external_count += 1
            committed = None
        try:
            executed = safe_path(root, relation['execution_archive_path']).read_bytes()
            verify_relation(relation, executed, committed)
        except (OSError, ValueError) as error:
            failures.append(original + ':' + str(error))
    changed_paths = {name for name, row in files.items()
        if row['executed_publication_worktree_sha256'] != row['committed_content_sha256']}
    require(changed_paths == set(eol_paths) and len(eol_paths) == len(set(eol_paths))
            and sorted(eol_paths) == manifest['explicit_EOL_source_paths'], 'unexplained_publication_byte_difference')
    require(set(eol_paths) <= source_paths, 'EOL_applied_to_non_source_evidence')
    return {'schema': 'g31.research_publication.dual_source_verification.v2',
        'status': 'failed' if failures else 'passed', 'fixed_git_commit': manifest['fixed_git_commit'],
        'fixed_git_tree': manifest['fixed_git_tree'], 'manifest_files': len(files),
        'execution_source_archives': len(relations), 'committed_repository_sources': current_count,
        'external_archive_only_sources': external_count, 'explicit_EOL_source_relations': len(eol_paths),
        'non_source_evidence_normalized': False, 'current_source_files_normalized_before_hashing': False,
        'failures': failures, 'native_executed': False, 'training_executed': False,
        'scope': 'Exact committed content and exact historical execution archives; source-only EOL relations are separately checked.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE.parents[3])
    parser.add_argument('--manifest', type=Path, default=HERE / 'MANIFEST.json')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.root, args.manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'status': 'failed', 'failures': [str(error)], 'native_executed': False, 'training_executed': False}
    encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.report is not None:
        with args.report.open('x', encoding='utf8', newline='\n') as stream:
            stream.write(encoded)
    print(encoded, end='')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
