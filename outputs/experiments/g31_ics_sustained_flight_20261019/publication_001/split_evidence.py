"""Lossless fixed-size publication of large executed artifacts; originals stay intact.

--split creates a new directory of chunks. --restore reconstructs exact original
bytes only when the destination is missing, and refuses to overwrite differences.
No native code or model is executed.
"""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = 'g31.lossless_evidence_chunks.v1'
CHUNK_BYTES = 24 * 1024 * 1024


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def split(source, output):
    source, output = source.resolve(), output.resolve()
    assert source.is_relative_to(ROOT) and source.is_file()
    assert output.is_relative_to(ROOT) and not output.exists()
    output.mkdir(parents=True)
    whole = hashlib.sha256(); rows = []; size = 0
    with source.open('rb') as f:
        while block := f.read(CHUNK_BYTES):
            p = output / f'{len(rows):04d}.bin'
            p.write_bytes(block); whole.update(block); size += len(block)
            rows.append({'path': p.name, 'bytes': len(block), 'sha256': hashlib.sha256(block).hexdigest()})
    assert size == source.stat().st_size and whole.hexdigest() == sha(source)
    manifest = {'schema': SCHEMA, 'original_path': source.relative_to(ROOT).as_posix(),
                'original_bytes': size, 'original_sha256': whole.hexdigest(), 'chunks': rows,
                'transform': 'ordered byte partition only; original executed bytes are unchanged',
                'original_kept_locally': True, 'complete_scientific_run_inferred': False}
    (output / 'CHUNKS.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'split_exact_bytes', 'original_path': manifest['original_path'],
                      'bytes': size, 'chunks': len(rows), 'sha256': whole.hexdigest()}))


def restore(manifest_path, root):
    manifest_path, root = manifest_path.resolve(), root.resolve()
    m = json.loads(manifest_path.read_bytes())
    assert m['schema'] == SCHEMA
    target = (root / m['original_path']).resolve()
    assert target.is_relative_to(root)
    if target.exists():
        assert target.is_file() and target.stat().st_size == m['original_bytes'] and sha(target) == m['original_sha256']
        return
    # Verify every chunk before opening the destination.
    chunks = []; verified = hashlib.sha256(); verified_size = 0
    for row in m['chunks']:
        p = (manifest_path.parent / row['path']).resolve()
        assert p.is_relative_to(manifest_path.parent) and p.is_file()
        assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
        chunks.append(p)
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                verified.update(block); verified_size += len(block)
    assert verified_size == m['original_bytes'] and verified.hexdigest() == m['original_sha256']
    target.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(); size = 0
    with target.open('xb') as out:
        for p in chunks:
            with p.open('rb') as f:
                for block in iter(lambda: f.read(1024 * 1024), b''):
                    out.write(block); h.update(block); size += len(block)
    assert size == m['original_bytes'] and h.hexdigest() == m['original_sha256']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--split', type=Path); g.add_argument('--restore', type=Path)
    p.add_argument('--output', type=Path); p.add_argument('--root', type=Path, default=ROOT)
    a = p.parse_args()
    if a.split:
        assert a.output is not None
        split(a.split, a.output)
    else:
        restore(a.restore, a.root)


if __name__ == '__main__':
    main()
