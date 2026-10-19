"""Read-only, standard-library byte verification from any checkout location.

This verifies the publication manifest, 783 archived pins and 782 current sources.
It does not execute project code, train, run native, or change old path references.
The manifest/verifier themselves are authenticated by the Git commit identity.
"""
import hashlib
import json
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ORIGINAL = PureWindowsPath('C:/PROGRAMING/czr005/.g31_ics_circulation_worktree')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE / 'MANIFEST.json').read_bytes())
    failures = []
    seen = set()
    for row in manifest['files']:
        name = row['path']
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or name in seen:
            raise ValueError('Unsafe or duplicate path: ' + name)
        seen.add(name)
        if not path.is_file() or path.stat().st_size != row['bytes'] or digest(path) != row['sha256']:
            failures.append(name)
    plan = json.loads((HERE.parent / 'final_validation_001/plan.json').read_bytes())
    current_count = 0
    for original, expected in plan['source_pins'].items():
        archived = PureWindowsPath(plan['source_archive'][original]).relative_to(ORIGINAL)
        archive_path = ROOT.joinpath(*archived.parts)
        if not archive_path.is_file() or digest(archive_path) != expected:
            failures.append('archived_source:' + archived.as_posix())
        if PureWindowsPath(original).is_relative_to(ORIGINAL):
            relative = PureWindowsPath(original).relative_to(ORIGINAL)
            path = ROOT.joinpath(*relative.parts)
            current_count += 1
            if not path.is_file() or digest(path) != expected:
                failures.append('tested_source:' + relative.as_posix())
    result = {'status': 'failed' if failures else 'passed',
              'manifest_files': len(seen), 'tested_source_pins': len(plan['source_pins']),
              'current_repository_sources': current_count,
              'failures': failures, 'native_executed': False, 'training_executed': False}
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
