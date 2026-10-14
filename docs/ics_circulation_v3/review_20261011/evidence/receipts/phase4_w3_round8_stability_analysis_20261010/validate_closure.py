"""Validate the added extraction receipt chain and real immutable input closure."""
import hashlib
import json
from pathlib import Path
from time import process_time, perf_counter
import analyse_results as analysis


def main():
    cpu, wall = process_time(), perf_counter()
    directory = Path(__file__).resolve().parent
    fixture = directory / 'closure_validation_fixture'
    fixture.mkdir(exist_ok=False)
    checks = []
    original = analysis.HERE
    try:
        analysis.HERE = fixture
        checks.append(('empty receipt history carries no claims', analysis.extraction_bindings() == {}))
        (fixture / 'extraction_001.json').write_text(json.dumps({'compact_files': {'file': 'first'}}), encoding='utf-8')
        (fixture / 'extraction_002.json').write_text(json.dumps({'compact_files': {'file': 'first'}}), encoding='utf-8')
        checks.append(('agreeing receipts merge', analysis.extraction_bindings() == {'file': 'first'}))
        (fixture / 'extraction_003.json').write_text(json.dumps({'compact_files': {'file': 'different'}}), encoding='utf-8')
        try:
            analysis.extraction_bindings()
        except ValueError:
            checks.append(('conflicting shard receipt rejected', True))
        else:
            checks.append(('conflicting shard receipt rejected', False))
    finally:
        analysis.HERE = original
    closure = analysis.immutable_inputs()
    checks.append(('complete actual frozen closure verified', len(closure) > 500))
    claims = analysis.extraction_bindings()
    checks.append(('all actual extracted shard hashes unchanged', all(analysis.sha(Path(name)) == digest for name, digest in claims.items())))
    result = {'checks': checks, 'failures': [name for name, passed in checks if not passed],
        'actual_frozen_files': len(closure), 'actual_bound_compact_files': len(claims),
        'source_sha256': hashlib.sha256((directory / 'analyse_results.py').read_bytes()).hexdigest(),
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'physical_simulations': 0, 'scope': 'Pure-file closure checks, imports and final receipt excluded. Deliberate conflict fixture retained separately.'}
    with (directory / 'closure_validation.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))
    assert not result['failures']


if __name__ == '__main__':
    main()
