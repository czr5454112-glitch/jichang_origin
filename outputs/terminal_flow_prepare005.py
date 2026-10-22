"""Freeze and verify corrected source005, then register its finite successor.

Runs pure pytest only. It never starts native work or changes historical sources.
"""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_campaign as flow
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import bound, read_bound

spec = importlib.util.spec_from_file_location('finite_driver', ROOT/'outputs/terminal_flow_workflow004.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
spec = importlib.util.spec_from_file_location('release_helper', ROOT/'outputs/terminal_flow_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

old_dir = campaign.CYCLE/'terminal_flow/workflow_004'
old_registration = flow.read(old_dir/'registration.json')
dispatch = [json.loads(row) for row in (old_dir/'dispatch_001.jsonl').read_text(encoding='utf8').splitlines()]
assert dispatch[-1]['exception_type'] == 'SupervisorSupersededBeforeDispatch'
assert dispatch[-1]['native_starts_in_workflow'] == 0
directory = campaign.CYCLE/'terminal_flow/workflow_005'
assert not directory.exists(), 'fresh workflow005 required'
assert not Path(old_registration['model_output']).exists(), 'full model must not already exist'
directory.mkdir()
source = campaign.freeze_sources('terminal_flow_runtime_005')
manifest = driver.validate_source(source)
old_manifest = read_bound(old_registration['source_bundle'])
changed = sorted(name for name, sha in manifest['files'].items() if old_manifest['files'].get(name) != sha)
assert changed and set(old_manifest['files']) == set(manifest['files'])
print(json.dumps(dict(event='source005_frozen', source=source, changed_source_files=changed)), flush=True)

prior_gate = read_bound(old_registration['pure_gate'])
test_files = sorted(set(prior_gate['test_files']) | {
    'tests/test_g31_terminal_workflow004.py',
    'tests/test_g31_terminal_projection_capture.py',
    'tests/test_g31_foundation_airport_joint_projection.py'})
test_xml = ROOT/'outputs/terminal_flow_pytest_runtime005_001.xml'
test_log = ROOT/'outputs/terminal_flow_pytest_runtime005_001.log'
assert not test_xml.exists() and not test_log.exists()
test_sources = {name: bound(ROOT/name) for name in test_files}
with test_log.open('x', encoding='utf8') as stream:
    process = subprocess.run([sys.executable, '-m', 'pytest', *test_files, '-q', '--junitxml', str(test_xml)],
                             cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
assert process.returncode == 0, 'pure tests failed; preserve source and report'
suite = ET.parse(test_xml).getroot().find('testsuite')
assert all(int(suite.get(key, '-1')) == 0 for key in ('failures', 'errors', 'skipped'))
assert all(bound(ROOT/name) == ref for name, ref in test_sources.items()), 'tests changed during verification'
driver.validate_source(source)
gate = dict(schema='g31.terminal_flow.frozen_source_pure_gate.v1', source_bundle=source,
    test_result=bound(test_xml), test_log=bound(test_log),
    tests=int(suite.get('tests')), failures=0, errors=0, skipped=0,
    elapsed_seconds=float(suite.get('time')), test_files=test_sources,
    changed_source_files_from_runtime004=changed,
    source_files_verified=len(manifest['files']), working_and_frozen_source_hashes_match=True)
flow.write_once(directory/'pure_gate_001.json', gate)

archive_dir = campaign.CYCLE/'publication/terminal_flow_001'
archive = archive_dir/'terminal_flow_runtime_005_sources.zip'
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
    for name in sorted(manifest['files']):
        stream.write(Path(manifest['root'])/name, arcname=name)
    stream.write(Path(source['path']), arcname='source_manifest.json')
release.verify_archive(archive, Path(source['path']))
flow.write_once(archive_dir/'source_archive_005.json', dict(schema='g31.terminal_flow.source_archive.v1',
    source='terminal_flow_runtime_005', source_manifest=source['sha256'],
    archive=archive.relative_to(ROOT).as_posix(), bytes=archive.stat().st_size,
    sha256=bound(archive)['sha256'], files=len(manifest['files']), all_archived_bytes_verified=True,
    archive_paths_are_relative_to_source_root=True, worker_evidence_contract=manifest['worker_evidence_contract'],
    publication_and_execution_identity_separate=True))

registration = copy.deepcopy(old_registration)
registration.update(registered_at_utc=budget.now(), source_bundle=source,
    current_budget_snapshot=budget.status(campaign.CYCLE), pure_gate=bound(directory/'pure_gate_001.json'),
    driver_pure_tests=bound(test_xml),
    supersedes_unstarted_workflow=dict(registration=bound(old_dir/'registration.json'),
        dispatch=bound(old_dir/'dispatch_001.jsonl'), native_starts=0,
        reason='Correct received/issued claim capture timestamp dominance before any successor dispatch.'),
    changed_source_files_from_runtime004=changed,
    driver_reused_without_changes=True, preparation=bound(__file__))
for entry in registration['stages']:
    assert entry['name'].endswith('_004')
    entry['name'] = entry['name'][:-4]+'_005'
driver.validate_registration(registration)
flow.write_once(directory/'registration.json', registration)
budget.append(campaign.CYCLE, 'terminal_flow_finite_workflow_registered',
    registration=bound(directory/'registration.json'), predecessor=registration['predecessor_block'],
    supersedes=registration['supersedes_unstarted_workflow'],
    new_native_starts=32, new_budget=False, requires_closed_predecessor=True)
print(json.dumps(dict(event='source005_successor_registered', registration=bound(directory/'registration.json'),
    source=source, tests=gate['tests'], native_started=False)), flush=True)
