"""Verify code-commit files with the explicitly declared release-only overlay."""
from pathlib import Path
import hashlib
import json


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    source_path = here/'source_manifest.json'
    source = json.loads(source_path.read_text(encoding='utf-8'))
    files = dict(source['files'])
    release_path = here/'release_manifest.json'
    release = json.loads(release_path.read_text(encoding='utf-8'))
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != release['source_manifest_sha256']:
        raise ValueError('fixed code manifest identity mismatch')
    files.update(release['files'])
    mismatches = []
    for name, expected in files.items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            mismatches.append({'path': name, 'reason': 'missing_or_outside_checkout'})
            continue
        data = path.read_bytes()
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            mismatches.append({'path': name, 'reason': 'bytes_or_sha256_mismatch'})
    print(json.dumps({'status': 'failed' if mismatches else 'passed', 'files': len(files),
        'code_commit': release['code_commit'], 'mismatches': mismatches}, ensure_ascii=False))
    return 1 if mismatches else 0


if __name__ == '__main__':
    raise SystemExit(main())
