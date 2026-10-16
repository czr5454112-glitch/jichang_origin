"""Parent lifecycle guards; mocked workers never start native execution."""
import subprocess
import pytest
from scripts.experiments.g31_ics_circulation import launch_preexisting_prepared as launcher


def test_timeout_is_unknown_and_no_retry_or_business_execution(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "verify", lambda *args, **kwargs: {})
    def timeout(command, **kwargs):
        calls.append((command, kwargs)); raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr(launcher.subprocess, "run", timeout)
    result = launcher.launch(tmp_path, tmp_path/"unused.pyd", launcher.sha(launcher.__file__), 180.)
    assert result["status"] == "unknown_worker_hard_timeout"
    assert len(calls) == 1 and calls[0][1]["timeout"] == 180.
    assert "--worker" in calls[0][0] and "--execute" not in calls[0][0]
    assert result["business_metrics"] is None and result["source_and_input_changed"] == []
    assert (tmp_path/"bounded_parent_source.py").is_file()


def test_worker_failure_preserved_without_saved_evidence_admission(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "verify", lambda *args, **kwargs: {})
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 7))
    monkeypatch.setattr(launcher.importlib, "import_module", lambda *args: pytest.fail("must not admit failed worker"))
    result = launcher.launch(tmp_path, tmp_path/"unused.pyd", launcher.sha(launcher.__file__), 10.)
    assert result["status"] == "unknown_failed_verification_or_worker" and result["worker_exit_code"] == 7
    assert "independent_saved_evidence" not in result


@pytest.mark.parametrize("timeout", (0., -1., 180.00001, float("inf"), float("nan")))
def test_unbounded_or_invalid_worker_limit_never_launches(tmp_path, monkeypatch, timeout):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: pytest.fail("no process"))
    with pytest.raises(ValueError, match="timeout_exceeds"):
        launcher.launch(tmp_path, tmp_path/"unused.pyd", "", timeout)
    assert not list(tmp_path.iterdir())


def test_changed_launcher_fails_before_reading_campaign(tmp_path):
    with pytest.raises(ValueError, match="launcher_changed"):
        launcher.verify(tmp_path, tmp_path/"unused.pyd", "a"*64, initial=True)


def test_changed_plan_fails_before_reading_native_binary(tmp_path):
    (tmp_path/"preregistered_protocol.json").write_text("{}")
    with pytest.raises(ValueError, match="plan_changed"):
        launcher.verify(tmp_path, tmp_path/"unused.pyd", launcher.sha(launcher.__file__), initial=True)
