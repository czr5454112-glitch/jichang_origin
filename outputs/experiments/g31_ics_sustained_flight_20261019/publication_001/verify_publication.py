"""Portable exact-byte publication verification; no native execution or training.

Historical executed sources are checked against their own immutable archives,
not against a newer source file in the checkout. Runtime binaries/interpreters
outside this selected publication remain explicitly external dependencies.
"""
from pathlib import Path, PureWindowsPath
import argparse
import hashlib
import json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(root, manifest):
    root = root.resolve()
    failures = []
    paths = set()
    for row in manifest['files']:
        relative = row['path']
        target = (root / relative).resolve()
        if row['expected_committed_content_sha256'] != row['executed_worktree_sha256']:
            failures.append({'path': relative, 'reason': 'undeclared_publication_transform'})
        if relative in paths or not target.is_relative_to(root) or not target.is_file():
            failures.append({'path': relative, 'reason': 'duplicate_missing_or_outside_root'})
        elif sha(target) != row['executed_worktree_sha256']:
            failures.append({'path': relative, 'reason': 'exact_publication_bytes_mismatch'})
        paths.add(relative)
    archive_checks = 0; chunked_checks = 0
    for relative in sorted(paths):
        path = root / relative
        if not path.is_file() or not path.resolve().is_relative_to(root):
            continue
        if path.name == 'CHUNKS.json':
            chunks = json.loads(path.read_bytes())
            if chunks.get('schema') != 'g31.lossless_evidence_chunks.v1':
                failures.append({'path': relative, 'reason': 'unknown_chunk_schema'})
                continue
            original = chunks.get('original_path')
            if (not isinstance(original, str) or not original
                    or Path(original).is_absolute() or PureWindowsPath(original).drive
                    or PureWindowsPath(original).root
                    or not (root / original.replace('\\', '/')).resolve().is_relative_to(root)
                    or (root / original.replace('\\', '/')).resolve() == root):
                failures.append({'path': relative, 'reason': 'original_stream_path_outside_root'})
                continue
            whole = hashlib.sha256(); total = 0
            for row in chunks['chunks']:
                part = (path.parent / row['path']).resolve()
                if (not part.is_relative_to(path.parent.resolve()) or not part.is_file()
                        or part.relative_to(root).as_posix() not in paths):
                    failures.append({'path': relative, 'reason': 'missing_or_outside_chunk'})
                    continue
                block = part.read_bytes(); whole.update(block); total += len(block)
                if len(block) != row['bytes'] or hashlib.sha256(block).hexdigest() != row['sha256']:
                    failures.append({'path': relative, 'reason': 'chunk_bytes_mismatch'})
            if total != chunks['original_bytes'] or whole.hexdigest() != chunks['original_sha256']:
                failures.append({'path': relative, 'reason': 'original_executed_stream_mismatch'})
            chunked_checks += 1
        if path.name == 'plan.json':
            plan = json.loads(path.read_bytes())
            if 'source_archive' not in plan or 'source_sha256' not in plan:
                continue
            if set(plan['source_archive']) != set(plan['source_sha256']):
                failures.append({'path': relative, 'reason': 'historical_source_archive_domain'})
                continue
            for source, archive in plan['source_archive'].items():
                archived = (path.parent / archive.replace('\\', '/')).resolve()
                expected = plan['source_sha256'][source]
                if (not archived.is_relative_to(path.parent.resolve()) or not archived.is_file()
                        or archived.relative_to(root).as_posix() not in paths or sha(archived) != expected):
                    failures.append({'path': relative, 'source': source, 'reason': 'historical_executed_source_bytes'})
                archive_checks += 1
        if path.name == 'registration.json' and path.parent.parent.name == 'attempts':
            registration = json.loads(path.read_bytes())
            for index, (source, expected) in enumerate(registration['source_pins'].items()):
                archived = path.parent / 'source' / (f'{index:04d}' + Path(source).suffix)
                if (not archived.is_file() or archived.relative_to(root).as_posix() not in paths
                        or sha(archived) != expected):
                    failures.append({'path': relative, 'source': source, 'reason': 'outer_attempt_executed_source_bytes'})
                archive_checks += 1
    return {'status': 'passed' if not failures else 'failed', 'files_checked': len(paths),
            'historical_source_archive_checks': archive_checks, 'failures': failures,
            'lossless_original_stream_checks': chunked_checks,
            'native_executed': False, 'training_executed': False,
            'semantic_success_inferred_from_hashes': False,
            'external_runtime_dependencies_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('MANIFEST.json'))
    args = parser.parse_args()
    result = verify(args.root, json.loads(args.manifest.read_bytes()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
