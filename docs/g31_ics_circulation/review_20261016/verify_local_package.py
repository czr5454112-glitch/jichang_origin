"""Verify only archive integrity, never import or execute the archived project."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath


def safe_name(name):
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name


def main():
    target = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).parent
    errors = []
    archive = zipfile.ZipFile(target) if target.is_file() else None
    if archive:
        names = [i.filename for i in archive.infolist() if not i.is_dir()]
        if len(names) != len(set(names)):
            errors.append('duplicate archive members')
        read = archive.read
    else:
        names = [p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()]
        read = lambda name: (target / name).read_bytes()
    if any(not safe_name(n) for n in names):
        raise ValueError('unsafe member path')
    manifest = json.loads(read('PACKAGE_MANIFEST.json'))
    expected = {x['path']: x for x in manifest['files']}
    if len(expected) != len(manifest['files']):
        errors.append('duplicate manifest entries')
    missing = sorted(set(expected) - set(names))
    unexpected = sorted(set(names) - set(expected) - {'PACKAGE_MANIFEST.json'})
    if missing or unexpected:
        errors.append({'missing': missing, 'unexpected': unexpected})
    total = 0
    for name, item in expected.items():
        if not safe_name(name):
            raise ValueError('unsafe manifest path')
        if name not in names:
            continue
        data = read(name)
        total += len(data)
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            errors.append({'content_mismatch': name})
    if archive:
        archive.close()
    print(json.dumps({'status': 'passed' if not errors else 'failed', 'files_verified': len(expected) - len(missing), 'bytes_verified': total, 'scope': 'integrity only; no project execution or business-claim validation', 'errors': errors}, ensure_ascii=True, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
