"""List this stage's explicit namespaces; never stage or modify Git state."""
from pathlib import Path
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
MODIFIED = [
    '.gitattributes',
    'cpp/ics_core/bindings/circulation.cpp',
    'cpp/ics_core/bindings/circulation_session_binding.hpp',
    'cpp/ics_core/runtime/circulation.hpp',
    'cpp/ics_core/runtime/circulation_checkpoint.hpp',
    'cpp/ics_core/runtime/circulation_planning_snapshot_impl.hpp',
    'cpp/ics_core/runtime/circulation_runtime_impl.hpp',
    'cpp/tests/test_circulation_runtime.cpp',
    'scripts/experiments/g31_ics_circulation/research_synthetic_reuse_chain.py',
    'scripts/experiments/g31_ics_circulation/research_native_preexisting_v3_bound.py',
]
NEW_NAMESPACES = ['scripts/experiments/g31_ics_circulation', 'tests',
                  'configs/g31_ics_circulation', 'docs/g31_ics_circulation']
EVIDENCE_ROOTS = [
    'outputs/experiments/g31_ics_sustained_flight_20261019',
    'outputs/experiments/g31_ics_multirate_20261019/publication_002',
]
EXCLUDE_DIR = re.compile(r'(^__pycache__$|^\.pytest_cache$|^tmp($|_)|^pytest|pytest_|_tests_\d+$|^targeted_scratch$)')
EXCLUDE_FILES = {'MANIFEST.json', 'selected_files.txt', 'selection_report.json',
                 'git_index_verification.json', 'git_export_verification.json'}


def select():
    selected = set(MODIFIED)
    names = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--',
                                     *NEW_NAMESPACES], cwd=ROOT, text=True).splitlines()
    for name in names:
        if name.startswith('tests/') and name != 'tests/fixtures/g31_airport_conditional_release_seq32.json' and not re.fullmatch(
                r'tests/test_g31_(foundation_.*|native028_.*|airport_event_budget_preparation|airport_recording_v2|airport_recorded_budget_campaign|airport_shadow_planner|airport_shadow_campaign|sustained_learning_ledger)\.py', name):
            raise ValueError('Review unexpected new test before publishing: ' + name)
        selected.add(name)
    for namespace in EVIDENCE_ROOTS:
        for directory, dirs, files in os.walk(ROOT / namespace):
            dirs[:] = [d for d in dirs if not EXCLUDE_DIR.search(d)]
            for filename in files:
                path = Path(directory) / filename
                if path.suffix in ('.pyc', '.lock'):
                    continue
                if path.parent == HERE and filename in EXCLUDE_FILES:
                    continue
                selected.add(path.relative_to(ROOT).as_posix())
    # Published saved test summaries are evidence; their scratch fixtures are not.
    for p in (ROOT / 'outputs/experiments/g31_ics_repeated_tests_20261019').glob('*_junit.xml'):
        selected.add(p.relative_to(ROOT).as_posix())
    chunked = []
    for relative in sorted(selected):
        if relative.endswith('/CHUNKS.json'):
            manifest = json.loads((ROOT / relative).read_bytes())
            assert manifest['schema'] == 'g31.lossless_evidence_chunks.v1'
            source = manifest['original_path']
            assert source in selected, source
            selected.remove(source)
            chunked.append({'original_path': source, 'chunk_manifest': relative})
    rows = sorted(selected)
    missing = [x for x in rows if not (ROOT / x).is_file()]
    assert not missing, missing
    assert all((ROOT / x).stat().st_size < 100 * 1024 * 1024 for x in rows)
    (HERE / 'selected_files.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    report = {'files': len(rows), 'bytes': sum((ROOT / x).stat().st_size for x in rows),
              'modified_tracked_allowlist': MODIFIED, 'new_code_namespaces': NEW_NAMESPACES,
              'evidence_roots': EVIDENCE_ROOTS, 'scratch_directory_exclusion': EXCLUDE_DIR.pattern,
              'lossless_chunked_originals_excluded_from_git_only': chunked,
              'git_mutated': False, 'all_paths_require_actual_git_index_verification': True}
    (HERE / 'selection_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    select()
