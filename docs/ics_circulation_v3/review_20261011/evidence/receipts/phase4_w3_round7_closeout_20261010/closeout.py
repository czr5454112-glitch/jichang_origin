"""Final read-only code/document identity checks; no simulation or Git writes."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
from time import process_time, perf_counter


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cpu, wall = process_time(), perf_counter()
    root = Path.cwd()
    destination = Path(__file__).parent / 'closeout.json'
    if destination.exists():
        raise FileExistsError(destination)
    base = root / 'scripts/experiments/ics_circulation_v3'
    documents = [base / name for name in ('PHASE4_MATCHED_CONTINUATION.md', 'PHASE4.md', 'PROGRESS.md')]
    validation = root / 'outputs/experiments/ics_circulation_v3/phase4_w3_round7_independent_review_20261010/full_validation_terminal/result.json'
    frozen = json.loads(validation.read_text(encoding='utf-8'))
    source_changes = [name for name, expected in frozen['after'].items()
                      if not (root / name).is_file() or sha(root / name) != expected]
    links = []
    for document in documents:
        for link in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if link.startswith(('http:', 'https:', '#')):
                continue
            target = (document.parent / link.split('#')[0]).resolve()
            links.append({'document': str(document.relative_to(root)), 'link': link,
                          'target': str(target), 'exists': target.exists()})
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    diff = subprocess.run(['git', 'diff', '--check', '--', 'scripts/experiments/ics_circulation_v3',
                           'tests', 'cpp/ics_core/runtime/bounded_local_pibt.hpp'], capture_output=True, text=True)
    cpp = root / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
    new_names = ['same_zone_labels.py', 'run_same_zone_labels.py', 'same_zone_query_probe.py',
                 'same_zone_query_coverage.py', 'run_same_zone_query_coverage.py',
                 'physical_observation.py', 'terminal_capacity_screen.py', 'run_terminal_capacity_screen.py']
    new_tests = ['same_zone_labels', 'same_zone_labels_audit', 'same_zone_query_probe',
                 'same_zone_query_coverage', 'physical_observation', 'terminal_capacity_screen',
                 'terminal_capacity_screen_audit', 'terminal_capacity_screen_runner']
    paths = documents + [base / name for name in new_names] + [
        root / f'tests/test_ics_circulation_v3_{name}.py' for name in new_tests]
    whitespace = [{'file': str(path.relative_to(root)), 'line': index}
                  for path in paths for index, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
                  if line.rstrip() != line]
    result = {
        'checks': {
            'all_local_md_links_exist': all(row['exists'] for row in links),
            'source_test_cpp_match_final_879_suite': not source_changes,
            'new_files_no_trailing_whitespace': not whitespace,
            'git_diff_check': diff.returncode == 0,
            'head_unchanged': head == 'a23cf1c066d1087571b31733f0577c602040aa8d',
            'cpp_unchanged': sha(cpp) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951',
        },
        'head': head, 'cpp_sha256': sha(cpp), 'source_changes': source_changes,
        'local_md_links': links, 'whitespace_paths': whitespace,
        'file_sha256': {str(path.relative_to(root)): sha(path) for path in paths},
        'validation_sha256': sha(validation), 'git_diff_check_stdout': diff.stdout,
        'git_diff_check_stderr': diff.stderr,
        'resources': {'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
                      'scope': 'Final identity/document checks only. Zero simulation. Not included in earlier sealed resource ledger; Git subprocess CPU not captured.'},
    }
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps({'checks': result['checks'], 'output': str(destination)}))
    assert all(result['checks'].values()), result['checks']


if __name__ == '__main__':
    main()
