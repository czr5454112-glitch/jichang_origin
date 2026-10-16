"""Source/fixture-only driver gates; no original future proof import/call."""
import json
import copy
from pathlib import Path
import sys

import pytest

from scripts.experiments.g31_ics_circulation import diagnose_future_source_inventory as subject


def test_canonical_archive_keeps_current_bytes_and_is_contained(tmp_path):
    root, output = tmp_path/'root', tmp_path/'output'
    current = root/'a/code.py'; current.parent.mkdir(parents=True); current.write_bytes(b'pass\n')
    files = {'a/code.py': b'pass\n'}
    mapping = subject.archive_sources(root, output, files)
    plan = {'source_sha256': {'a/code.py': subject.sha(current)}, 'source_archive': mapping}
    subject.verify_archive(root, output, plan)
    assert mapping == {'a/code.py': 'source/a/code.py'}
    assert current.read_bytes() == b'pass\n'
    assert (output/'source/a/code.py').read_bytes() == b'pass\n'
    with pytest.raises(ValueError, match='archive_target_exists'):
        subject.archive_sources(root, output, files)


@pytest.mark.parametrize('key', ['/absolute.py', 'C:/absolute.py', '../escape.py', 'a\\bad.py', 'a//bad.py'])
def test_noncanonical_source_keys_fail_before_write(tmp_path, key):
    output = tmp_path/'output'
    with pytest.raises(ValueError):
        subject.archive_sources(tmp_path/'root', output, {'valid.py': b'pass\n', key: b'bad\n'})
    assert not output.exists()


def test_archive_must_not_be_current_source(tmp_path):
    root = tmp_path/'out/source'; root.mkdir(parents=True)
    current = root/'a.py'; current.write_bytes(b'original\n')
    with pytest.raises(ValueError, match='containment'):
        subject.archive_sources(root, tmp_path/'out', {'a.py': b'replacement\n'})
    assert current.read_bytes() == b'original\n'


def test_existing_last_target_rejects_entire_domain_before_first_write(tmp_path):
    output = tmp_path/'output'
    existing = output/'source/already.py'; existing.parent.mkdir(parents=True)
    existing.write_bytes(b'preserved\n')
    with pytest.raises(ValueError, match='archive_target_exists'):
        subject.archive_sources(tmp_path/'root', output,
            {'first.py': b'first\n', 'already.py': b'replacement\n'})
    assert not (output/'source/first.py').exists() and existing.read_bytes() == b'preserved\n'


@pytest.mark.parametrize('target_length', [259, 260])
def test_real_archive_write_exact_path_boundary(tmp_path, target_length):
    root, output = tmp_path/'root', tmp_path/'out'
    prefix = len(str((output/'source').resolve()))+1
    filename_length = target_length-prefix
    assert 4 <= filename_length <= 255
    name = 'x'*(filename_length-3)+'.py'
    root.mkdir(); current = root/name; current.write_bytes(b'pass\n')
    files = {name: b'pass\n'}
    if target_length == 259:
        mapping = subject.archive_sources(root, output, files)
        plan = {'source_sha256': {name: subject.sha(current)}, 'source_archive': mapping}
        subject.verify_archive(root, output, plan)
        assert len(str((output/mapping[name]).resolve())) == 259
        assert (output/mapping[name]).read_bytes() == b'pass\n'
    else:
        with pytest.raises(ValueError, match='archive_path_under260'):
            subject.archive_sources(root, output, files)
        assert not output.exists()
        plan = {'source_sha256': {name: subject.sha(current)}, 'source_archive': {name: 'source/'+name}}
        with pytest.raises(ValueError, match='archive_path_under260'):
            subject.verify_archive(root, output, plan)
    assert current.read_bytes() == b'pass\n'


def test_finalization_saves_all_rows_after_incremental_write_was_missed(tmp_path):
    report = subject.empty_report()
    report['rows'][0].update(status='unknown_return_encoding_or_export_failure', invoked=True)
    report['actual_calls'] = 1
    subject.finalize_report(tmp_path, report)
    rows = subject.read(tmp_path/'rows.json'); saved = subject.read(tmp_path/'report.json')
    assert len(rows) == 65 and rows[0]['invoked'] is True and rows[-1]['status'] == 'unknown_unexecuted'
    assert saved['rows'] == rows and saved['rows_file']['sha256'] == subject.sha(tmp_path/'rows.json')


def test_finalization_cannot_shrink_denominator(tmp_path):
    report = subject.empty_report(); report['rows'].pop()
    with pytest.raises(ValueError, match='denominator'):
        subject.finalize_report(tmp_path, report)
    assert not (tmp_path/'report.json').exists()


def test_prepare_uses_saved_original_proof_and_canonical_complete_plan(tmp_path, monkeypatch):
    root, base = tmp_path/'root', tmp_path/'base'; root.mkdir(); base.mkdir()
    current = root/'helper.py'; current.write_bytes(b'pass\n')
    base_data = {'source_proof': {'proof': True, 'schema': 'synthetic'}}
    for name in ('plan.json', 'receipt.json', 'root_saved_review_001.json', 'entry_pins.json',
                 'exit_pins.json', 'bounded_execution.json', 'external_application_wall.json'):
        subject.write(base/name, base_data if name == 'plan.json' else {})
    monkeypatch.setattr(subject, 'ROOT', root); monkeypatch.setattr(subject, 'BASE', base)
    monkeypatch.setattr(subject, 'base_gate', lambda: base_data)
    monkeypatch.setattr(subject, 'pure_gate', lambda: {})
    monkeypatch.setattr(subject, 'source_files', lambda: {'helper.py': b'pass\n'})
    output = tmp_path/'prepared'; subject.prepare(output)
    plan, ready = subject.read(output/'plan.json'), subject.read(output/'ready.json')
    assert ready['plan']['sha256'] == subject.sha(output/'plan.json')
    assert ready['source_count'] == 1 and ready['original_proof_calls_during_preparation'] == 0
    assert plan['comparison_origin']['JSON_field'] == 'source_proof'
    assert (output/'target.json').read_bytes() == subject.kernel.encoded(base_data['source_proof'])
    assert current.read_bytes() == b'pass\n'
    subject.check_plan(output, plan)
    (output/'target.json').write_bytes(b'{"proof":false}')
    with pytest.raises(ValueError, match='target_identity'):
        subject.check_plan(output, plan)
    assert subject.remaining(0.) == 119.
    with pytest.raises(ValueError, match='remaining_budget'):
        subject.remaining(119.)


def test_worker_setup_failure_exports_all65_without_original_import(tmp_path):
    original_name = 'scripts.experiments.g31_ics_circulation.live_obligation_future_later_fork'
    assert original_name not in sys.modules
    code = subject.worker(tmp_path, 'missing-plan')
    report = subject.read(tmp_path/'report.json'); receipt = subject.read(tmp_path/'receipt.json')
    assert code == 1 and report['status'] == 'unknown_worker_failure'
    assert len(report['rows']) == 65 and report['actual_calls'] == 0 and report['unexecuted_rows'] == 65
    assert receipt['report']['sha256'] == subject.sha(tmp_path/'report.json')
    assert original_name not in sys.modules


def test_bounded_prepare_uses_metadata_child_and_distinct_logs(tmp_path, monkeypatch):
    from scripts.experiments.g31_ics_circulation import bounded_windows_job
    output = tmp_path/'short_prepare'
    calls = []
    def fake_job(command, *, timeout, admission, stdout, stderr, cwd):
        assert '--prepare-worker' in command and '--worker' not in command
        assert command[-1] == admission and 0 < timeout <= 119 and cwd == subject.ROOT
        calls.append(command)
        output.mkdir(); subject.write(output/'plan.json', {'synthetic': True})
        subject.write(output/'ready.json', {'status': 'prepared_unexecuted', 'plan': subject.ref(output/'plan.json')})
        return {'status': 'exited', 'exitcode': 0}
    monkeypatch.setattr(bounded_windows_job, 'run', fake_job)
    monkeypatch.setattr(subject, 'BOOT', subject.time.monotonic())
    assert subject.prepare_bounded(output) == 0 and len(calls) == 1
    report = subject.read(output.with_name(output.name+'.prepare_bounded.json'))
    assert report['status'] == 'prepared_bounded_unexecuted' and report['original_proof_calls'] == 0
    assert not (output/'stdout.log').exists() and not (output/'execution_claim.json').exists()
    assert output.with_name(output.name+'.prepare.stdout.log').exists()
    with pytest.raises(ValueError, match='prepare_output_exists'):
        subject.prepare_bounded(output)


def external_fixture(tmp_path, monkeypatch, seconds=1.25):
    output = tmp_path/'pure'; output.mkdir()
    wrapper = tmp_path/'audited.ps1'; wrapper.write_bytes(b'audited synthetic wrapper\n')
    monkeypatch.setattr(subject, 'WRAPPER', wrapper)
    monkeypatch.setattr(subject, 'WRAPPER_SHA', subject.sha(wrapper))
    command = subject.pure_command(output)
    plan = {'output_directory': str(output.resolve()), 'external_wrapper': subject.verify_wrapper(),
        'environment': {'python': sys.executable, 'sha256': subject.sha(sys.executable)}}
    subject.write(output/'plan.json', plan)
    (output/'tests.xml').write_bytes(b'<testsuites/>')
    receipt = {'plan_sha256': subject.sha(output/'plan.json')}
    subject.write(output/'receipt.json', receipt)
    bounded = {'output_directory': str(output.resolve()), 'command': command,
        'receipt_sha256': subject.sha(output/'receipt.json')}
    subject.write(output/'bounded_parent_receipt.json', bounded)
    frequency = 1_000_000
    external = {'schema': subject.EXTERNAL_SCHEMA, 'status': 'exited_zero', 'command': command,
        'cwd': str(subject.ROOT.resolve()), 'output_directory': str(output.resolve()),
        'python_sha256': subject.sha(sys.executable), 'python_after_sha256': subject.sha(sys.executable),
        'exitcode': 0, 'wrapper_exitcode': 0, 'stopwatch_frequency': frequency,
        'elapsed_ticks': int(seconds*frequency), 'external_application_seconds': seconds,
        'clock_scope': 'immediately_before_python_launch_through_process_return',
        'wrapper': subject.verify_wrapper(), 'wrapper_after_sha256': subject.WRAPPER_SHA,
        'outputs': {name: subject.ref(output/name) for name in ('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json')},
        'native_calls': 0, 'model_predictions': 0, 'real_original_proof_calls': 0}
    return output, plan, receipt, bounded, external


@pytest.mark.parametrize('seconds', [0., 120.])
def test_external_exact_zero_and_budget_boundary_pass(tmp_path, monkeypatch, seconds):
    output, plan, receipt, bounded, external = external_fixture(tmp_path, monkeypatch, seconds)
    result = subject.verify_external(external, output, plan, receipt, bounded)
    assert result['status'] == 'validated_complete_external_pure_lifetime'


@pytest.mark.parametrize('change', [
    'schema', 'status', 'command', 'output', 'cwd', 'exit_bool', 'exit_nonzero',
    'wrapper_exit', 'frequency_bool', 'frequency_zero', 'ticks_bool', 'ticks_negative',
    'seconds_nan', 'seconds_inf', 'seconds_bool', 'seconds_mismatch', 'over_budget_tick',
    'wrapper_hash', 'wrapper_after', 'python_hash', 'output_hash', 'output_path',
    'missing_output', 'extra_field', 'native_bool',
])
def test_external_malformed_or_unbound_whole_lifetime_rejected(tmp_path, monkeypatch, change):
    output, plan, receipt, bounded, original = external_fixture(tmp_path, monkeypatch)
    external = copy.deepcopy(original)
    if change == 'schema': external['schema'] = 'another-schema'
    elif change == 'status': external['status'] = 'failed'
    elif change == 'command': external['command'][2] = 'another.module'
    elif change == 'output': external['output_directory'] = str(tmp_path/'other')
    elif change == 'cwd': external['cwd'] = str(tmp_path)
    elif change == 'exit_bool': external['exitcode'] = False
    elif change == 'exit_nonzero': external['exitcode'] = 1
    elif change == 'wrapper_exit': external['wrapper_exitcode'] = 1
    elif change == 'frequency_bool': external['stopwatch_frequency'] = True
    elif change == 'frequency_zero': external['stopwatch_frequency'] = 0
    elif change == 'ticks_bool': external['elapsed_ticks'] = False
    elif change == 'ticks_negative': external['elapsed_ticks'] = -1
    elif change == 'seconds_nan': external['external_application_seconds'] = float('nan')
    elif change == 'seconds_inf': external['external_application_seconds'] = float('inf')
    elif change == 'seconds_bool': external['external_application_seconds'] = True
    elif change == 'seconds_mismatch': external['external_application_seconds'] += .1
    elif change == 'over_budget_tick':
        external['elapsed_ticks'] = 120*external['stopwatch_frequency']+1
        external['external_application_seconds'] = external['elapsed_ticks']/external['stopwatch_frequency']
    elif change == 'wrapper_hash': external['wrapper']['sha256'] = '0'*64
    elif change == 'wrapper_after': external['wrapper_after_sha256'] = '0'*64
    elif change == 'python_hash': external['python_sha256'] = '0'*64
    elif change == 'output_hash': external['outputs']['plan.json']['sha256'] = '0'*64
    elif change == 'output_path': external['outputs']['tests.xml']['path'] = str(tmp_path/'other.xml')
    elif change == 'missing_output': del external['outputs']['tests.xml']
    elif change == 'extra_field': external['unreviewed_field'] = True
    elif change == 'native_bool': external['native_calls'] = False
    else: raise AssertionError(change)
    with pytest.raises(ValueError):
        subject.verify_external(external, output, plan, receipt, bounded)
