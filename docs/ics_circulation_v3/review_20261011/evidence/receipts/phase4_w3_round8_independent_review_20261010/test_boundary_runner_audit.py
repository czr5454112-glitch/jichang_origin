"""Independent output-local boundary driver fault injections, no physics."""
from pathlib import Path
from concurrent.futures import Future
import importlib.util
import json
import pytest

PATH = Path(__file__).parent.parent / 'phase4_w3_round8_conditional_boundary_mechanism_20261010/runner.py'
SPEC = importlib.util.spec_from_file_location('independent_boundary_runner', PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')


def bridge_fixture(tmp_path):
    planned = [{'request_key': str(i), 'physical_key': str(i)} for i in range(2)]
    write(tmp_path / 'bridge_rows.json', planned)
    fields = ('evaluation_ledger', 'cache_before', 'cache_after', 'searches', 'search_calls', 'search_work',
              'stopped_at', 'event_trace_suffix', 'selector_history_suffix', 'actual_slow_trigger_times',
              'slow_history_suffix', 'physical_tick_trace', 'forced_intervention')
    rows = []
    for row in planned:
        relative = str(Path('bridge') / (row['physical_key'] + '.json.gz'))
        path = tmp_path / relative
        write(path, {'fixture': row['physical_key']})
        rows.append({**row, 'status': 'controller_quiescent', 'actual_physical_call': True,
                     'invocation_cpu_seconds': 1.0, 'file': relative, 'sha256': runner.file_sha(path),
                     'replication': {'result': {'equal': True}, **{k: True for k in fields}}})
    return {'planned_physical_calls': 2, 'rows': rows, 'source_input_test_unchanged': True,
            'complete_resource_accounting': True}


def seal(tmp_path, summary):
    write(tmp_path / 'bridge/summary.json', summary)
    manifest = {str(p.relative_to(tmp_path)): runner.file_sha(p)
                for p in (tmp_path / 'bridge').iterdir() if p.name != 'manifest.json'}
    write(tmp_path / 'bridge/manifest.json', manifest)


def test_complete_exact_bridge_can_promote(tmp_path):
    summary = bridge_fixture(tmp_path)
    seal(tmp_path, summary)
    runner.require_bridge(tmp_path)


@pytest.mark.parametrize('mutation', ('duplicate_identity', 'empty_replication', 'unlisted_raw'))
def test_gate_rejects_false_full_bridge_evidence(tmp_path, mutation):
    summary = bridge_fixture(tmp_path)
    if mutation == 'duplicate_identity':
        summary['rows'][1] = dict(summary['rows'][0])
    elif mutation == 'empty_replication':
        summary['rows'][0]['replication'] = {}
    seal(tmp_path, summary)
    if mutation == 'unlisted_raw':
        path = tmp_path / 'bridge/manifest.json'
        manifest = json.loads(path.read_text(encoding='utf8'))
        del manifest[summary['rows'][0]['file']]
        write(path, manifest)
    with pytest.raises(ValueError):
        runner.require_bridge(tmp_path)


def test_submit_failure_retains_paid_first_job_and_complete_denominator(tmp_path, monkeypatch):
    planned = [{'request_key': str(i), 'physical_key': str(i)} for i in range(24)]
    write(tmp_path / 'full_rows.json', planned)
    protocol = {'workers': 3, 'resource_scope': 'synthetic fault test'}
    monkeypatch.setattr(runner, 'verify', lambda output: protocol)
    monkeypatch.setattr(runner, 'require_bridge', lambda output: None)

    class PartialSubmitFailure:
        def __init__(self, **kwargs):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, output, stage, row):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError('submit failed after one paid job')
            result = Future()
            result.set_result({**row, 'status': 'controller_quiescent', 'actual_physical_call': True,
                               'invocation_cpu_seconds': 1.25, 'invocation_wall_seconds': 2.0})
            return result

    monkeypatch.setattr(runner, 'ProcessPoolExecutor', PartialSubmitFailure)
    assert runner.run(tmp_path, 'full') != 0
    summary = json.loads((tmp_path / 'full/summary.json').read_text(encoding='utf8'))
    assert len(summary['rows']) == 24
    assert {r['physical_key'] for r in summary['rows']} == {r['physical_key'] for r in planned}
    paid = next(r for r in summary['rows'] if r['physical_key'] == '0')
    assert paid['actual_physical_call'] is True
    assert paid['invocation_cpu_seconds'] == 1.25
    assert summary['case_invocation_cpu_seconds_recorded'] == 1.25
    assert any(r['status'] != 'controller_quiescent' for r in summary['rows'])
    assert all(r['actual_physical_call'] is None for r in summary['rows'] if r['physical_key'] != '0')
