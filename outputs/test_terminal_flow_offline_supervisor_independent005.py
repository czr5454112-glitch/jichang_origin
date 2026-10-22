"""Independent pure supervisor review; synthetic files only, zero real processes."""
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'outputs/experiments/g31_ics_inventory_spi_20261020/cycle_001/report_support/offline_owned_resource_001.py'


@pytest.mark.parametrize('mode', ['timeout', 'leader_exits_descendant_remains', 'zero_query_fails', 'success'])
def test_real_supervisor_control_flow_with_only_fake_processes(tmp_path, monkeypatch, mode):
    spec = importlib.util.spec_from_file_location('independent_owned_supervisor', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    events, clock = [], [0.0]
    monkeypatch.setattr(helper.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(helper.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    class Gate(io.StringIO):
        def write(self, value):
            events.append('release_gate')
            return super().write(value)

    class FakeProcess:
        pid = 123
        returncode = None

        def __init__(self):
            self.stdin = Gate()
            self.waited = False

        def poll(self):
            if mode != 'timeout':
                self.returncode = 0
            return self.returncode

        def wait(self, timeout):
            events.append('wait_direct_child')
            self.waited = True
            assert self.returncode is not None
            return self.returncode

        def kill(self):
            raise AssertionError('Unexpected unassigned process kill')

    process = FakeProcess()

    class FakeJob:
        def __init__(self, limit):
            self.active, self.snapshots = 1, 0
            events.append('create_job')

        def creation(self, owned):
            assert owned is process
            return 123456

        def assign(self, owned):
            assert owned is process
            events.append('assign_job')

        def snapshot(self, owned):
            self.snapshots += 1
            if mode == 'success' and self.snapshots > 1:
                self.active = 0
            return dict(active_processes=self.active, job_peak_commit_bytes=1)

        def query(self, code, result_type):
            assert code == 1
            if process.waited:
                events.append('query_after_wait')
                if mode == 'zero_query_fails':
                    raise RuntimeError('synthetic aggregate query failure')
            return SimpleNamespace(ActiveProcesses=self.active)

        def terminate(self):
            events.append('terminate_owned_job')
            self.active = 0
            if process.returncode is None:
                process.returncode = 1223

        def close(self):
            events.append('close_job_handle')

    def fake_popen(*args, **kwargs):
        events.append('popen_fake')
        assert kwargs['close_fds'] is True and kwargs['creationflags'] == 0x08000000
        return process

    monkeypatch.setattr(helper, 'Job', FakeJob)
    monkeypatch.setattr(helper.subprocess, 'Popen', fake_popen)
    resources = dict(at_utc='synthetic', physical_available_bytes=100 * 1024**3,
                     commit_available_bytes=100 * 1024**3, disk_free_bytes=100 * 1024**3)
    report = helper.run(['never-executed'], timeout=2, stdout=io.StringIO(), stderr=io.StringIO(),
                        admission='synthetic-token', cwd=str(tmp_path), directory=tmp_path,
                        resource_probe=lambda: resources)
    assert events.index('assign_job') < events.index('release_gate')
    assert events.index('wait_direct_child') < events.index('query_after_wait') < events.index('close_job_handle')
    assert report['direct_child_wait_completed'] is True
    assert (tmp_path / 'process_closed.json').is_file()
    if mode == 'zero_query_fails':
        assert report['closure_verified'] is False and report['cleanup_errors']
    else:
        assert report['closure_verified'] is True
        assert report['job_active_processes_zero_verified'] is True
    if mode == 'timeout':
        assert report['status'] == 'hard_timeout'
        assert report['termination_reason'] == 'original_job_timeout'
        assert report['wall_seconds'] == 2
    elif mode != 'success':
        assert report['termination_reason'] == 'remaining_owned_descendants_after_direct_exit'
    else:
        assert report['status'] == 'exited' and report['exitcode'] == 0
        assert report['termination_reason'] is None
