"""One final live-code/artifact check after all required analyses have finished."""
import hashlib
import json
from pathlib import Path
import subprocess
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REVIEW = HERE.parent / 'phase4_w3_round8_independent_review_20261010'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cpu, wall = process_time(), perf_counter()
    before = json.loads((REVIEW / 'full_validation/before.json').read_bytes())
    changed = [name for name, value in before.items() if sha(ROOT / name) != value]
    assert not changed, changed
    assert sha(ROOT / 'cpp/ics_core/runtime/bounded_local_pibt.hpp') == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert head == 'a23cf1c066d1087571b31733f0577c602040aa8d', head
    pipeline = json.loads((HERE / 'pipeline/resource.json').read_bytes())
    assert pipeline['failure'] is None and len(pipeline['rows']) == 4
    assert all(row['returncode'] == 0 for row in pipeline['rows'])
    programs = json.loads((HERE / 'pipeline/before.json').read_bytes())
    assert all(sha(HERE / path) == expected for path, expected in programs.items())
    for name in ('results', 'report', 'service_tradeoffs'):
        manifest = json.loads((HERE / name / 'manifest.json').read_bytes())
        assert all(sha(HERE / name / path) == expected for path, expected in manifest.items())
    resource = json.loads((HERE / 'visuals/resource.json').read_bytes())
    assert all(sha(HERE / 'visuals' / path) == expected for path, expected in resource['figures'].items())
    summary = json.loads((HERE / 'results/summary.json').read_bytes())
    assert (summary['planned_logical'], summary['planned_unique_physical'], summary['memo_aliases']) == (4352, 2468, 1884)
    result = {'head': head, 'frozen_file_count': len(before), 'changed_frozen_files': changed,
        'expected_cpp_preserved': True, 'analysis_programs': programs,
        'planned_logical': summary['planned_logical'], 'planned_unique_physical': summary['planned_unique_physical'],
        'unknown_states': summary['unknown_states'], 'zero_states': summary['zero_states'],
        'complete_states': summary['complete_states'], 'physical_simulations': 0,
        'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'scope': 'Read-only closure; full regression was run on this unchanged source/test set. Git child CPU, imports and final receipt write are outside this parent timer. No commit/push operation. Later prose/resource-ledger edits are outside this source freeze.'}
    with (HERE / 'final_closure.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
