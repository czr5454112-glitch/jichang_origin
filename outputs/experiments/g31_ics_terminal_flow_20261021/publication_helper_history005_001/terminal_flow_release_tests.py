"""Pure publication-boundary tests; no native execution or Git mutation."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('terminal_release', Path(__file__).with_name('terminal_flow_release.py'))
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.gz':
        with gzip.open(path, 'wt', encoding='utf8') as stream:
            json.dump(value, stream)
    else:
        path.write_text(json.dumps(value), encoding='utf8')
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def journal(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf8')


@pytest.mark.parametrize('rows', [
    [dict(event='runner_open', runner_id='active')],
    [dict(event='native_start', task_id='unfinished')],
    [dict(event='native_finish', task_id='never_started')],
    [dict(event='native_start', task_id='twice'), dict(event='native_finish', task_id='twice'),
     dict(event='native_start', task_id='twice')],
])
def test_active_unresolved_or_retried_work_prevents_finalization(tmp_path, rows):
    path = tmp_path/'ledger.jsonl'
    journal(path, rows)
    with pytest.raises(ValueError):
        release.idle_ledger(path)


def test_partial_jsonl_tail_is_never_published_as_closed(tmp_path):
    path = tmp_path/'dispatch.jsonl'
    path.write_bytes(b'{"event":"successor_process_finished"')
    with pytest.raises(ValueError, match='partial_jsonl_tail'):
        release.jsonl(path)


@pytest.fixture
def complete(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp('r')
    monkeypatch.setattr(release, 'CYCLE_REL', Path('c'))
    monkeypatch.setattr(release, 'REPORTS_REL', Path('outputs/reports'))
    cycle = root/release.CYCLE_REL
    workflow = cycle/'terminal_flow/workflow_005'
    workflow.mkdir(parents=True)
    source_paths = []
    for number in range(1, 6):
        source = cycle/'sources'/f'terminal_flow_runtime_{number:03d}'/'source_manifest.json'
        manifest = dict(runtime=number, files={'code.py': hashlib.sha256(b'code').hexdigest()},
            worker_evidence_contract=release.COMPACT_ACK_CONTRACT)
        save(source, manifest)
        source_paths.append(source)
        archive = cycle/'publication/terminal_flow_001'/f'terminal_flow_runtime_{number:03d}_sources.zip'
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('code.py', b'code')
            stream.writestr('source_manifest.json', source.read_bytes())
    parent_ref = save(cycle/'parents/P2101/input.json', {'jobs': []})
    directory = cycle/'runs/TF_mock'
    plan_ref = save(directory/'plan.json', dict(task_id='TF_mock', horizon=59400., input=parent_ref,
        worker_evidence_contract=release.COMPACT_ACK_CONTRACT,
        source_bundle=dict(path=str(source_paths[-1]), sha256=hashlib.sha256(source_paths[-1].read_bytes()).hexdigest())))
    worker = dict(scientific_status='closed', process_status='completed', final_physical_time=59400.)
    save(directory/'worker_report.json', worker)
    save(directory/'receipt.json', dict(plan_sha256=plan_ref['sha256'], worker=worker, process=dict(exitcode=0)))
    save(directory/'trajectory.json.gz', dict(scientific_status='closed_finite_horizon', process_status='completed',
        logs_complete=True, physical_clock=59400.))
    save(directory/'terminal_evidence.json.gz', {'physical_clock': 59400.})
    save(directory/'observations.json.gz', ['local raw owner history'])
    journal(directory/'progress.jsonl', [dict(physical_clock=59400.)])
    save(cycle/'terminal_flow/complete_block/block.json', dict(task_plans=[plan_ref]))
    registration = save(workflow/'registration.json', dict(stages=[dict(name='complete_block')],
        source_bundle=dict(path=str(source_paths[-1]), sha256=hashlib.sha256(source_paths[-1].read_bytes()).hexdigest())))
    save(workflow/'completion.json', dict(registration=registration, all_registered_development_tasks_closed=True,
        TEST_unlocked=False))
    journal(workflow/'dispatch_001.jsonl', [dict(event='successor_process_finished', exitcode=0)])
    journal(cycle/'ledger.jsonl', [dict(event='runner_open', runner_id='done'),
        dict(event='native_start', task_id='TF_mock'), dict(event='native_finish', task_id='TF_mock'),
        dict(event='runner_close', runner_id='done')])
    historical = cycle/'terminal_flow/workflow_004'
    old_stages = [dict(name=phase+'_004', phase=phase)
        for phase in ('export_gate', 'train_demand', 'bridge', 'bins', 'period', 'predictor')]
    old_registration = save(historical/'registration.json', dict(stages=old_stages,
        source_bundle=dict(path=str(source_paths[-2]), sha256=hashlib.sha256(source_paths[-2].read_bytes()).hexdigest())))
    recorder = save(root/'outputs/terminal_flow_record004_supersession.py', {'fixture': True})
    journal(historical/'dispatch_001.jsonl', [dict(event='waiting_for_frozen_predecessor', registration=old_registration),
        dict(event='dispatch_failed', exception_type='SupervisorSupersededBeforeDispatch', registration=old_registration,
            native_starts_in_workflow=0, predecessor_native_untouched=True, frozen_runtime004_unchanged=True,
            reason='Confirmed stale capture defect; replace before dispatch.', supervisor_action='Stopped only waiting dispatcher.',
            recorder=recorder)])
    ledger_rows = release.jsonl(cycle/'ledger.jsonl')[1]
    ledger_rows.append(dict(event='terminal_flow_unstarted_workflow_superseded', registration=old_registration,
        dispatch=dict(path=str(historical/'dispatch_001.jsonl'),
            sha256=hashlib.sha256((historical/'dispatch_001.jsonl').read_bytes()).hexdigest()),
        native_starts=0, predecessor_native_untouched=True, reason='Confirmed stale capture defect; replace before dispatch.'))
    journal(cycle/'ledger.jsonl', ledger_rows)
    head_records = {release.RESEARCH_RECORDS[0]: b'{"id":"historical"}\n', release.RESEARCH_RECORDS[1]: b'# Existing ledger\n'}
    for name, data in head_records.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(release, 'head_bytes', lambda _, name: head_records[name])
    disposition = save(workflow/'release_disposition.json', dict(schema=release.SCHEMA+'.disposition',
        registration_sha256=registration['sha256'], outcome='complete', reason='All fixed development work closed.',
        nonclosed_tasks={}, unprepared_stages={}))
    monkeypatch.setattr(release, 'git_inventory', lambda _: dict(unexpected_tracked=[], unrelated_new_source=[]))
    return dict(root=root, cycle=cycle, workflow=workflow, run=directory, plan_ref=plan_ref,
                historical=historical, registration=workflow/'registration.json', head_records=head_records,
                disposition=Path(disposition['path']), output=root/'outputs/publication_final_001')


def test_complete_release_copies_journals_and_excludes_raw_history_with_full_hashes(complete):
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    manifest = release.read(Path(result['manifest']))
    raw = next(row for row in manifest['entries'] if row['path'].endswith('/observations.json.gz'))
    assert raw['bundled'] is False and len(raw['sha256']) == 64 and raw['bytes'] > 0
    ledger = next(row for row in manifest['entries'] if row['path'].endswith('/ledger.jsonl'))
    assert ledger['bundled'] is True and '/snapshots/' in ledger['publish_path']
    assert (complete['root']/ledger['publish_path']).read_bytes() == (complete['cycle']/'ledger.jsonl').read_bytes()
    paths = Path(result['pathspec']).read_bytes().split(b'\0')
    assert paths[-1] == b'' and all(path.startswith(b':(literal)') for path in paths[:-1])
    assert (':(literal)'+ledger['path']).encode() not in paths
    assert (':(literal)'+ledger['publish_path']).encode() in paths
    assert len(manifest['source_archives']) == 5
    assert manifest['gate']['registration']['path'] == str(complete['registration'])
    old = manifest['gate']['historical_workflows'][0]
    assert old['scientifically_closed'] is False and old['native_starts_verified'] == 0
    assert len(old['unprepared_stages']) == 6
    assert release.verify_manifest(complete['root'], Path(result['manifest']))['verified_included_files'] > 0


def test_size_ceiling_keeps_oversize_evidence_local_and_reports_scope(complete, monkeypatch):
    monkeypatch.setattr(release, 'MAX_FILE_BYTES', 20000)
    path = complete['run']/'large-evidence.bin'
    path.write_bytes(b'x'*20001)
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    manifest = release.read(Path(result['manifest']))
    record = next(row for row in manifest['entries'] if row['path'].endswith('large-evidence.bin'))
    assert record['bundled'] is False and record['reason'] == 'above_publication_single_file_limit'
    assert record['bytes'] == 20001 and record['sha256'] == hashlib.sha256(b'x'*20001).hexdigest()


@pytest.mark.parametrize('case', ['active', 'dispatch_pending', 'wrong_registration', 'invalid_closed', 'unprepared',
                                 'unacknowledged_old_plan', 'unrelated_source'])
def test_final_gates_fail_without_creating_output(complete, monkeypatch, case):
    if case == 'active':
        journal(complete['cycle']/'ledger.jsonl', [dict(event='runner_open', runner_id='still-active')])
    elif case == 'dispatch_pending':
        journal(complete['workflow']/'dispatch_001.jsonl', [dict(event='successor_started')])
    elif case == 'wrong_registration':
        value = release.read(complete['disposition'])
        value['registration_sha256'] = 'wrong'
        save(complete['disposition'], value)
    elif case == 'invalid_closed':
        save(complete['run']/'trajectory.json.gz', dict(physical_clock=58000.))
    elif case == 'unprepared':
        registration = release.read(complete['workflow']/'registration.json')
        registration['stages'].append(dict(name='never-prepared'))
        ref = save(complete['workflow']/'registration.json', registration)
        disposition = release.read(complete['disposition'])
        disposition['registration_sha256'] = ref['sha256']
        save(complete['disposition'], disposition)
    elif case == 'unacknowledged_old_plan':
        save(complete['cycle']/'runs/TF_superseded/plan.json', dict(task_id='TF_superseded', horizon=18000.))
    else:
        monkeypatch.setattr(release, 'git_inventory', lambda _: dict(unexpected_tracked=['src/other.py'], unrelated_new_source=[]))
    with pytest.raises(ValueError):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert not complete['output'].exists()


def test_missing_receipt_after_start_is_not_mislabeled_not_started(complete):
    (complete['run']/'receipt.json').unlink()
    result = release.task_state(complete['plan_ref'], attempted=True)
    assert result['status'] == 'missing_receipt_after_native_start'


def test_explicit_failure_stop_retains_every_failure_without_claiming_complete(complete):
    worker = dict(scientific_status='budget_partial', process_status='completed', final_physical_time=10000.)
    save(complete['run']/'receipt.json', dict(plan_sha256=complete['plan_ref']['sha256'], worker=worker,
        process=dict(exitcode=0)))
    journal(complete['workflow']/'dispatch_001.jsonl', [dict(event='successor_process_finished', exitcode=1)])
    disposition = release.read(complete['disposition'])
    disposition.update(outcome='stopped_after_failure', reason='Registered task hit its existing finite budget.',
        nonclosed_tasks={'TF_mock': dict(status='budget_partial', reason='Retained failure; no automatic retry.')})
    save(complete['disposition'], disposition)
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert release.read(Path(result['manifest']))['gate']['outcome'] == 'stopped_after_failure'


def test_archive_roster_or_bytes_mismatch_blocks_publication(complete):
    archive = complete['cycle']/'publication/terminal_flow_001/terminal_flow_runtime_004_sources.zip'
    with zipfile.ZipFile(archive, 'a') as stream:
        stream.writestr('unreviewed.py', b'extra')
    with pytest.raises(ValueError, match='source_archive_member_roster'):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert not complete['output'].exists()


def test_verify_detects_changed_published_file_before_staging(complete):
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    save(complete['run']/'terminal_evidence.json.gz', {'edited': True})
    with pytest.raises(ValueError, match='published_file_changed'):
        release.verify_manifest(complete['root'], Path(result['manifest']))


def test_verify_rejects_an_unreviewed_path_inserted_into_stage_file(complete):
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    with Path(result['pathspec']).open('ab') as stream:
        stream.write(b':(literal)src/unrelated.py\0')
    with pytest.raises(ValueError, match='pathspec_does_not_exactly_match_reviewed_files'):
        release.verify_manifest(complete['root'], Path(result['manifest']))


def test_new_activity_during_hashing_prevents_half_written_release(complete, monkeypatch):
    original = release.final_gate
    calls = 0
    def race(root, disposition, registration):
        nonlocal calls
        calls += 1
        if calls == 2:
            journal(complete['cycle']/'ledger.jsonl', [dict(event='runner_open', runner_id='new-work')])
        return original(root, disposition, registration)
    monkeypatch.setattr(release, 'final_gate', race)
    with pytest.raises(ValueError, match='active_or_unresolved_native_work'):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert not complete['output'].exists()


def test_existing_output_is_never_overwritten(complete):
    complete['output'].mkdir(parents=True)
    (complete['output']/'user-file').write_text('keep', encoding='utf8')
    with pytest.raises(ValueError, match='fresh_output_directory'):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert (complete['output']/'user-file').read_text(encoding='utf8') == 'keep'


@pytest.mark.parametrize('case', ['missing_archive', 'missing_manifest', 'missing_pair', 'extra_archive', 'bad_latest_archive'])
def test_every_runtime_is_paired_contiguous_and_verified(complete, case):
    sources = complete['cycle']/'sources'
    archives = complete['cycle']/'publication/terminal_flow_001'
    if case == 'missing_archive':
        (archives/'terminal_flow_runtime_005_sources.zip').unlink()
    elif case == 'missing_manifest':
        (sources/'terminal_flow_runtime_005/source_manifest.json').unlink()
    elif case == 'missing_pair':
        (archives/'terminal_flow_runtime_003_sources.zip').unlink()
        (sources/'terminal_flow_runtime_003/source_manifest.json').unlink()
        (sources/'terminal_flow_runtime_003').rmdir()
    elif case == 'extra_archive':
        (archives/'terminal_flow_runtime_006_sources.zip').write_bytes(b'unpaired')
    else:
        with zipfile.ZipFile(archives/'terminal_flow_runtime_005_sources.zip', 'w') as stream:
            stream.writestr('code.py', b'changed')
            stream.writestr('source_manifest.json', (sources/'terminal_flow_runtime_005/source_manifest.json').read_bytes())
    with pytest.raises(ValueError):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert not complete['output'].exists()


@pytest.mark.parametrize('case', ['started', 'prepared_block', 'prepared_plan', 'ledger_omitted', 'dispatch_changed',
    'predecessor_touched', 'recorder_changed', 'missing_history', 'five_stages'])
def test_superseded004_cannot_be_published_as_a_closed_or_executed_workflow(complete, case):
    historical, cycle = complete['historical'], complete['cycle']
    if case == 'started':
        rows = release.jsonl(cycle/'ledger.jsonl')[1]
        source = release.read(historical/'registration.json')['source_bundle']
        rows += [dict(event='native_start', task_id='unrelated-looking-name', source_manifest_sha256=source['sha256']),
                 dict(event='native_finish', task_id='unrelated-looking-name')]
        journal(cycle/'ledger.jsonl', rows)
    elif case == 'prepared_block':
        save(cycle/'terminal_flow/export_gate_004/block.json', dict(task_plans=[]))
    elif case == 'prepared_plan':
        save(cycle/'runs/TF_export_gate_004_C00_P2101/plan.json', dict(task_id='TF_export_gate_004_C00_P2101'))
    elif case == 'ledger_omitted':
        journal(cycle/'ledger.jsonl', [row for row in release.jsonl(cycle/'ledger.jsonl')[1]
            if row['event'] != 'terminal_flow_unstarted_workflow_superseded'])
    elif case in ('dispatch_changed', 'predecessor_touched'):
        rows = release.jsonl(historical/'dispatch_001.jsonl')[1]
        if case == 'dispatch_changed':
            rows.insert(1, dict(event='successor_started'))
        else:
            rows[-1]['predecessor_native_untouched'] = False
        journal(historical/'dispatch_001.jsonl', rows)
    elif case == 'recorder_changed':
        (complete['root']/'outputs/terminal_flow_record004_supersession.py').write_bytes(b'changed')
    elif case == 'missing_history':
        (historical/'registration.json').unlink()
    else:
        registration = release.read(historical/'registration.json')
        registration['stages'].pop()
        save(historical/'registration.json', registration)
    with pytest.raises(ValueError):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert not complete['output'].exists()


def test_explicit_workflow_rejects_using_superseded004_as_active(complete):
    with pytest.raises(ValueError, match='active_workflow_not_latest_runtime'):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['historical']/'registration.json')


def test_only_reviewed_new_research_entries_are_appended(complete):
    appended = {release.RESEARCH_RECORDS[0]: b'{"id":"terminal-final"}\n',
                release.RESEARCH_RECORDS[1]: b'\n## Final terminal result\nObserved development evidence only.\n'}
    disposition = release.read(complete['disposition'])
    disposition['research_record_appends'] = {}
    for name, data in appended.items():
        (complete['root']/name).write_bytes(complete['head_records'][name]+data)
        disposition['research_record_appends'][name] = dict(sha256=hashlib.sha256(data).hexdigest(),
            reason='Final operator reviewed only this turn\'s appended final research entry.')
    save(complete['disposition'], disposition)
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    audited = release.read(Path(result['manifest']))['gate']['research_record_appends']
    assert set(audited) == set(appended)
    for name, record in audited.items():
        assert record['head_sha256'] == hashlib.sha256(complete['head_records'][name]).hexdigest()
        assert record['append_bytes'] == len(appended[name])


@pytest.mark.parametrize('case', ['history_edited', 'unreviewed', 'wrong_digest', 'duplicate_id', 'partial_tail', 'extra_review'])
def test_research_record_append_boundary_is_enforced(complete, case):
    name = release.RESEARCH_RECORDS[0]
    original = complete['head_records'][name]
    appended = b'{"id":"terminal-final"}\n'
    if case == 'duplicate_id':
        appended = b'{"id":"historical"}\n'
    elif case == 'partial_tail':
        appended = appended.rstrip(b'\n')
    path = complete['root']/name
    path.write_bytes((original.replace(b'historical', b'edited') if case == 'history_edited' else original)+appended)
    disposition = release.read(complete['disposition'])
    reviewed = dict(sha256=hashlib.sha256(appended).hexdigest(), reason='Reviewed final appended result.')
    if case != 'unreviewed':
        disposition['research_record_appends'] = {name: reviewed}
    if case == 'wrong_digest':
        reviewed['sha256'] = 'not-the-appendix'
    elif case == 'extra_review':
        disposition['research_record_appends'][release.RESEARCH_RECORDS[1]] = reviewed
    save(complete['disposition'], disposition)
    with pytest.raises(ValueError):
        release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    assert not complete['output'].exists()


def compact_views():
    scope = 'local physical sensors, client-owned payloads and immutable delivered messages/ACKs'
    return {'A': dict(schema='g31.owner_protocol_observation.v1', now=59400., owner_id='A', scope=scope,
        delivered_transfer_acks=[dict(request_id='transfer-1', sequence=1, attempt=1, observed_at=15.,
            delivered_at=16., status='received', reason='received', received_at=15., delivered_copies=1)],
        client_transfer_ledger=[dict(request_id='transfer-1', tray_id='tray-1', source=1, destination=2,
            issued_at=1., earliest_departure=2., expiry=100., message_delay=1., transfer_scope='remote_empty_transfer',
            status='received', received_at=15., reason='received', status_scope='own_payload_and_last_delivered_ack_only')],
        evidence_scope=dict(schema='g31.airport_joint_campaign.v1.transfer_ack_subset.v1',
            complete_owner_protocol_view=False, full_transfer_ack_history_preserved=True,
            full_client_transfer_ledger_preserved=True, owner_protocol_fields_retained=list(release.ACK_VIEW_FIELDS),
            owner_protocol_fields_omitted=['client_commands', 'delivered_command_acks'],
            original_owner_protocol_scope=scope, online_actor_input=False))}


@pytest.fixture
def compact(tmp_path):
    manifest = save(tmp_path/'source_manifest.json', dict(worker_evidence_contract=release.COMPACT_ACK_CONTRACT))
    plan = save(tmp_path/'plan.json', dict(source_bundle=manifest, worker_evidence_contract=release.COMPACT_ACK_CONTRACT))
    path = tmp_path/'delivered_ack_evidence.json.gz'
    save(path, compact_views())
    return dict(root=tmp_path, manifest=Path(manifest['path']), plan=Path(plan['path']), path=path)


def test_verified_compact_ack_is_published_and_full_histories_stay_local(complete):
    save(complete['run']/'delivered_ack_evidence.json.gz', compact_views())
    save(complete['run']/'control_trace.json.gz', ['local control history'])
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    manifest = release.read(Path(result['manifest']))
    ack = next(row for row in manifest['entries'] if row['path'].endswith('/delivered_ack_evidence.json.gz'))
    assert ack['bundled'] is True and ack['ack_publication']['publish'] is True
    assert manifest['compact_transfer_ack_files'] == 1
    assert manifest['compact_transfer_ack_byte_limit_exclusive'] == 30_000_000
    assert ack['ack_publication']['delivery_truth_certified'] is False
    assert ack['ack_publication']['decimal_byte_limit_exclusive'] == 30_000_000
    assert all(not row['bundled'] for row in manifest['entries']
        if row['path'].endswith(('/observations.json.gz', '/control_trace.json.gz')))
    assert release.verify_manifest(complete['root'], Path(result['manifest']))['verified_included_files'] > 0


@pytest.mark.parametrize('size', [30_000_000, 30_000_001])
def test_decimal_ack_limit_rejects_equality_without_decompressing(compact, monkeypatch, size):
    with compact['path'].open('wb') as stream:
        stream.truncate(size)
    def forbidden(*args, **kwargs):
        raise AssertionError('Rejected large ACK evidence must never be opened with gzip.')
    monkeypatch.setattr(release.gzip, 'open', forbidden)
    result = release.compact_transfer_ack_guard(compact['path'], compact['root'])
    assert not result['publish'] and result['reason'] == 'ack_at_or_above_compact_decimal_byte_limit'


@pytest.mark.parametrize('case', ['legacy_plan', 'legacy_source', 'changed_source', 'missing_plan'])
def test_contract_rejection_precedes_ack_decompression(compact, monkeypatch, case):
    if case == 'missing_plan':
        compact['plan'].unlink()
    elif case == 'legacy_plan':
        plan = release.read(compact['plan']); plan['worker_evidence_contract'] = 'full_intermediate_results_and_full_owner_ack_views_v1'
        save(compact['plan'], plan)
    elif case == 'legacy_source':
        reference = save(compact['manifest'], dict(worker_evidence_contract='unknown_contract'))
        plan = release.read(compact['plan']); plan['source_bundle'] = reference
        save(compact['plan'], plan)
    else:
        save(compact['manifest'], dict(worker_evidence_contract=release.COMPACT_ACK_CONTRACT, changed=True))
    def forbidden(*args, **kwargs):
        raise AssertionError('Rejected contract must never open ACK gzip.')
    monkeypatch.setattr(release.gzip, 'open', forbidden)
    assert not release.compact_transfer_ack_guard(compact['path'], compact['root'])['publish']


@pytest.mark.parametrize('case', ['full_history', 'missing_scope', 'wrong_owner', 'wrong_schema', 'false_history_claim',
    'full_view_flag', 'online_flag', 'extra_scope_field', 'nested_full_history', 'wrong_retained', 'overlapping_omitted',
    'duplicate_json_key', 'bad_gzip'])
def test_only_exact_compact_subset_structure_is_eligible(compact, case):
    views = compact_views(); view = views['A']
    if case == 'full_history':
        view['delivered_command_acks'] = []
    elif case == 'missing_scope':
        del view['evidence_scope']
    elif case == 'wrong_owner':
        view['owner_id'] = 'B'
    elif case == 'wrong_schema':
        view['schema'] = 'complete_owner_view'
    elif case == 'false_history_claim':
        view['evidence_scope']['full_transfer_ack_history_preserved'] = False
    elif case == 'full_view_flag':
        view['evidence_scope']['complete_owner_protocol_view'] = True
    elif case == 'online_flag':
        view['evidence_scope']['online_actor_input'] = True
    elif case == 'extra_scope_field':
        view['evidence_scope']['full_history'] = []
    elif case == 'nested_full_history':
        view['delivered_transfer_acks'][0]['client_commands'] = []
    elif case == 'wrong_retained':
        view['evidence_scope']['owner_protocol_fields_retained'].pop()
    elif case == 'overlapping_omitted':
        view['evidence_scope']['owner_protocol_fields_omitted'].append('delivered_transfer_acks')
    save(compact['path'], views)
    if case == 'duplicate_json_key':
        with gzip.open(compact['path'], 'wt', encoding='utf8') as stream:
            stream.write('{"A":'+json.dumps(view)+',"A":'+json.dumps(view)+'}')
    elif case == 'bad_gzip':
        compact['path'].write_bytes(b'not gzip')
    assert not release.compact_transfer_ack_guard(compact['path'], compact['root'])['publish']


def test_unverified_ack_is_omitted_by_default_with_its_hash(complete):
    save(complete['run']/'delivered_ack_evidence.json.gz', {'A': {'client_commands': ['full history']}})
    result = release.finalize(complete['root'], complete['output'], complete['disposition'], complete['registration'])
    manifest = release.read(Path(result['manifest']))
    ack = next(row for row in manifest['entries'] if row['path'].endswith('/delivered_ack_evidence.json.gz'))
    assert ack['bundled'] is False and ack['ack_publication']['publish'] is False
    assert len(ack['sha256']) == 64 and ack['bytes'] > 0
