"""Verify and restore the published, explicitly versioned Windows artifacts."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    root = args.root.resolve()
    here = Path(__file__).resolve().parent
    manifest = json.loads((here/'author_artifacts_manifest.json').read_text(encoding='utf-8'))
    archive = here/manifest['archive']
    sha = lambda data: hashlib.sha256(data).hexdigest()
    if sha(archive.read_bytes()) != manifest['archive_sha256']:
        raise ValueError('artifact archive SHA256 mismatch')
    pending = []
    with zipfile.ZipFile(archive) as z:
        if set(z.namelist()) != set(manifest['files']):
            raise ValueError('archive members differ from manifest')
        for name, expected in manifest['files'].items():
            destination = (root/name).resolve()
            if not destination.is_relative_to(root) or Path(name).is_absolute():
                raise ValueError('artifact path escapes selected checkout')
            data = z.read(name)
            if len(data) != expected['bytes'] or sha(data) != expected['sha256']:
                raise ValueError('artifact bytes mismatch: '+name)
            if destination.exists() and sha(destination.read_bytes()) != expected['sha256']:
                raise ValueError('refusing to replace different existing artifact: '+name)
            pending.append((destination, data))
    for destination, data in pending:
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    print(json.dumps({'status':'verified_and_restored', 'files':len(pending),
        'scope':manifest['scope'], 'root':str(root)}))


if __name__ == '__main__':
    main()
