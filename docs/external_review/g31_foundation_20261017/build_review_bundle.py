from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[3]
RELEASE = Path(__file__).resolve().parent
FOUNDATION = ROOT / 'outputs/experiments/g31_ics_foundation_learning_20261017'
CAMPAIGN = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/compatible_initial_native_20261017_004'
BASE = 'a7f7821f250fa5296f7b8d9766cbffc8fa1ce8ef'
APPROVED = {'.gitattributes', 'configs/g31_ics_circulation/learning_pilot_v1.json',
            'tests/fixtures/g31_component_counterexample.json'}
APPROVED.update('scripts/experiments/g31_ics_circulation/' + name + '.py' for name in [
    'audit_review_regressions', 'foundation_budgeted_probe', 'foundation_budgeted_provider',
    'foundation_learning_data', 'foundation_native_environment', 'foundation_ranker',
    'live_obligation_component_compatibility', 'review_physical_contract_20261017',
    'run_compatible_initial_native', 'run_learning_pipeline', 'live_obligation_initial_candidate_provider',
    'live_obligation_online_initial_dispatch', 'live_obligation_owned_initial_provider',
    'live_obligation_owned_prefix_evaluator', 'research_live_obligation_initial_methods'])
APPROVED.update('tests/' + name + '.py' for name in [
    'test_foundation_learning', 'test_g31_circulation_candidate_batch_seal',
    'test_g31_circulation_compatible_initial_native', 'test_g31_circulation_component_compatibility',
    'test_g31_foundation_budgeted_probe', 'test_g31_foundation_budgeted_provider',
    'test_g31_foundation_learning_pipeline', 'test_g31_foundation_native_environment',
    'test_g31_circulation_online_initial_dispatch', 'test_g31_circulation_online_initial_methods',
    'test_g31_circulation_owned_initial_runtime'])
APPROVED.update('docs/g31_ics_circulation/' + name for name in [
    'NEXT_ACTION.md', 'RESEARCH_STATE.json', 'COMPONENT_COMPATIBILITY_CONTRACT_20261017.md',
    'GPTPRO_100MS与多时间尺度预测调度审阅请求_20261017.md', 'LEARNING_READINESS.md',
    'PHYSICAL_CONTRACT_DECISION.md', 'REPAIR_METHOD_BOUNDARY_20261017.md',
    'REVIEW_FOLLOWUP_20261017.md', 'GPTPRO_FOUNDATION_STAGE_REVIEW_20261017.md'])
APPROVED.update('docs/external_review/g31_foundation_20261017/' + name for name in [
    'README.md', 'source_plan.md', 'build_review_bundle.py', 'verify_offline_evidence.py'])


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT)


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def relative(path):
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def file_record(path):
    content = path.read_bytes()
    return {'path': relative(path), 'bytes': len(content), 'sha256': digest(content)}


def prepare():
    if git('rev-parse', 'HEAD').decode().strip() != BASE:
        raise ValueError('prepare requires the reviewed base commit')
    if git('diff', '--cached', '--name-only').strip():
        raise ValueError('existing staged changes must not be mixed into the release')
    changed = git('diff', '--name-only', '-z').decode().split('\0')
    if set(filter(None, changed)) - APPROVED:
        raise ValueError('unexpected tracked changes outside approved release paths')
    selected = {ROOT / name for name in changed if name}
    scopes = ['scripts/experiments/g31_ics_circulation', 'tests', 'docs/g31_ics_circulation',
              'configs/g31_ics_circulation', relative(RELEASE)]
    names = git('ls-files', '--others', '--exclude-standard', '-z', '--', *scopes).decode().split('\0')
    if set(filter(None, names)) - APPROVED:
        raise ValueError('unexpected untracked files outside approved release paths')
    selected.update(ROOT / name for name in names if name)
    selected.update(path for path in (ROOT / 'audit/review_20261017').iterdir()
                    if path.is_file() and path.suffix in {'.py', '.json', '.md', '.xml'})
    groups = ['native_001', 'l0_001', 'l0_002', 'budgeted_001', 'budgeted_learned_001',
              'pilot_001', 'final_validation_001']
    for group in groups:
        for path in (FOUNDATION / group).rglob('*'):
            if not path.is_file():
                continue
            parents = path.relative_to(FOUNDATION / group).parts[:-1]
            if any(part in {'tmp', '__pycache__', '.pytest_cache'} or 'pytest_tmp' in part for part in parents):
                continue
            selected.add(path)
    selected.update(path for path in FOUNDATION.iterdir() if path.is_file())
    selected.update(path for path in CAMPAIGN.rglob('*') if path.is_file() and not path.name.endswith('.partial.json'))
    tested = read_json(FOUNDATION / 'final_validation_001/plan.json')['source_pins']
    tracked = set(git('ls-files', '-z').decode().split('\0'))
    for name, expected in tested.items():
        path = Path(name)
        if digest(path.read_bytes()) != expected:
            raise ValueError('tested source changed: ' + name)
        if relative(path) not in tracked and path not in selected:
            raise ValueError('unpublished tested dependency: ' + name)
    archived = selected | {Path(name) for name in tested}
    archived.add(ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json')
    for name in git('ls-files', '-z', '--', 'cpp/ics_core', 'CMakeLists.txt', 'pyproject.toml', 'requirements.txt').decode().split('\0'):
        if name:
            archived.add(ROOT / name)
    native_pins = {}
    for acceptance_path in ['native_001/acceptance.json', 'budgeted_learned_001/native/acceptance.json',
                            'pilot_001/smoke/baseline/native/acceptance.json']:
        for name, expected in read_json(FOUNDATION / acceptance_path)['evidence_sha256'].items():
            if name in native_pins and native_pins[name] != expected:
                raise ValueError('native dependency hash conflict: ' + name)
            native_pins[name] = expected
    omitted = []
    for name, expected in native_pins.items():
        path = Path(name)
        if path not in archived:
            omitted.append({'original_path': name, 'expected_sha256': expected,
                            'bytes_on_author_machine': path.stat().st_size if path.is_file() else None})
    omissions = RELEASE / 'NATIVE_REPLAY_DEPENDENCIES_NOT_BUNDLED.json'
    write_new(omissions, {'fresh_native_execution_portable': False, 'native_dependency_union_count': len(native_pins), 'reason':
              'Review bundle is not a complete native026/native027 build and admission environment; original absolute paths remain unchanged.',
              'omitted_count': len(omitted), 'dependencies': omitted})
    selected.add(omissions)
    archived.add(omissions)
    records = [file_record(path) for path in sorted(selected)]
    if sum(record['bytes'] for record in records) > 100 * 1024 * 1024:
        raise ValueError('release exceeds the selected evidence budget')
    manifest = {'schema': 'g31.foundation.release_scope.v1', 'base_commit': BASE,
                'branch': git('branch', '--show-current').decode().strip(),
                'tested_source_count': len(tested), 'tested_sources_unchanged': True,
                'excluded': ['test temporary directories', 'Python caches', 'unrelated historical campaigns',
                             '004 redundant partial JSON (final raw preserved)', 'native binary/build environment'],
                'release_files': records, 'bundle_repository_paths': sorted(relative(path) for path in archived),
                'bundle_files': [file_record(path) for path in sorted(archived)],
                'scope_manifest_self_hash_excluded': True}
    scope_path = RELEASE / 'RELEASE_SCOPE.json'
    write_new(scope_path, manifest)
    paths = sorted([record['path'] for record in records] + [relative(scope_path)])
    (RELEASE / 'stage_paths.nul').write_bytes(b'\0'.join(name.encode('utf-8') for name in paths) + b'\0')
    print(json.dumps({'release_files': len(paths), 'release_bytes': sum(record['bytes'] for record in records),
                      'bundle_paths': len(archived) + 1, 'omitted_native_dependencies': len(omitted)}))


def package(destination, verification):
    scope = read_json(RELEASE / 'RELEASE_SCOPE.json')
    publication = read_json(verification)
    commit = git('rev-parse', 'HEAD').decode().strip()
    if publication['local_commit'] != commit or publication['remote_commit'] != commit:
        raise ValueError('publication receipt does not verify current HEAD')
    expected = {row['path']: row['sha256'] for row in scope['bundle_files']}
    paths = set(scope['bundle_repository_paths']) | {relative(RELEASE / 'RELEASE_SCOPE.json')}
    entries = {}
    for name in sorted(paths):
        payload = (ROOT / name).read_bytes()
        if name in expected and digest(payload) != expected[name]:
            raise ValueError('release file changed after registration: ' + name)
        committed = git('show', commit + ':' + name)
        if payload != committed:
            raise ValueError('workspace bytes differ from committed bytes: ' + name)
        entries['repo/' + name] = payload
    request = ROOT / 'docs/g31_ics_circulation/GPTPRO_FOUNDATION_STAGE_REVIEW_20261017.md'
    entries['00_给GPTPro的审阅请求.md'] = request.read_bytes()
    entries['publication.json'] = verification.read_bytes()
    entries['changes_from_a7f7821f.patch'] = git('diff', '--binary', BASE, commit, '--',
        '.gitattributes', 'scripts', 'tests', 'configs', 'docs/g31_ics_circulation', relative(RELEASE))
    manifest = {'schema': 'g31.review_bundle.sha256.v1', 'code_commit': commit,
                'self_hash_excluded': 'MANIFEST.sha256.json',
                'files': [{'path': name, 'bytes': len(payload), 'sha256': digest(payload)}
                          for name, payload in sorted(entries.items())]}
    entries['MANIFEST.sha256.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / 'G31_20261017_阶段代码与重算证据.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for name, payload in sorted(entries.items()):
            bundle.writestr(name, payload)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('archive CRC failure')
        for row in manifest['files']:
            if digest(bundle.read(row['path'])) != row['sha256']:
                raise ValueError('archive content digest mismatch')
    (destination / 'G31_给GPTPro的阶段审阅请求_20261017.md').write_bytes(request.read_bytes())
    (destination / 'publication.json').write_bytes(verification.read_bytes())
    write_new(destination / 'bundle_validation.json', {'status': 'passed', 'file_count': len(entries),
              'all_archive_member_hashes_verified': True, 'all_repository_files_equal_committed_bytes': True,
              'zip_sha256': digest(archive.read_bytes()), 'zip_bytes': archive.stat().st_size,
              'code_commit': commit, 'fresh_native_execution_portable': False})
    print(json.dumps({'archive': str(archive), 'files': len(entries), 'bytes': archive.stat().st_size,
                      'sha256': digest(archive.read_bytes())}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'package'])
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--verification', type=Path)
    arguments = parser.parse_args()
    if arguments.mode == 'prepare':
        prepare()
    else:
        if arguments.destination is None or arguments.verification is None:
            parser.error('package requires --destination and --verification')
        package(arguments.destination, arguments.verification)


if __name__ == '__main__':
    main()
