"""Sidecar integration retains coarse accounting and restores runtime hooks."""
import json
import pytest

from scripts.experiments.g31_ics_circulation import profile_native_request_timing as timing


def test_installed_driver_restores_even_after_error():
    previous = timing.driver.BundleRecorder, timing.driver.analyze_bundles, timing.driver.SOURCE_NAMES
    with pytest.raises(ValueError, match="deliberate"):
        with timing.installed_driver():
            assert timing.driver.BundleRecorder is timing.NativePhaseBundleRecorder
            assert "native_request_timing.py" in timing.driver.SOURCE_NAMES
            raise ValueError("deliberate")
    assert previous == (timing.driver.BundleRecorder, timing.driver.analyze_bundles, timing.driver.SOURCE_NAMES)


def test_recent_bundle_proxy_forwards_explicit_capability():
    calls = []
    class Session:
        def observe_protocol_control_policy_recent(self, owner, validity): return (owner, validity)
    class Recorder:
        session = Session()
        def invoke(self, name, fn, *args):
            calls.append((name, args)); return fn(*args)
    result = timing._RecentBundleProxy(Recorder()).observe_protocol_control_policy_recent("A", 9.)
    assert result == ("A", 9.)
    assert calls == [("observe_protocol_control_policy_recent", ("A", 9.))]


def test_partition_never_discounts_coarse_request_total(monkeypatch):
    coarse = {"status": "complete_conservative_bundle_accounting",
        "requests": [{"request_id": "a", "complete_compute_upper_ns": 777}],
        "exclusive_controller_wall_ns": 888}
    monkeypatch.setattr(timing.bundles, "analyze_bundles", lambda raw: dict(coarse))
    monkeypatch.setattr(timing, "analyze_native_timing", lambda *args: {
        "status": "validated_partial_native_phase_partition", "identified_control_bundle_ns": 1,
        "unclassified_native_remainder_ns": 900, "errors": []})
    result = timing.analyze_phase_bundles({"native_timing": {"batches": [], "call_envelopes": []}})
    assert result["requests"] == coarse["requests"]
    assert result["exclusive_controller_wall_ns"] == 888


def test_failed_export_keeps_coarse_result_but_invalidates_capture(monkeypatch):
    monkeypatch.setattr(timing.bundles, "analyze_bundles", lambda raw: {
        "status": "complete_conservative_bundle_accounting", "requests": [{"complete_compute_upper_ns": 777}]})
    monkeypatch.setattr(timing, "analyze_native_timing", lambda *args: {
        "status": "validated_partial_native_phase_partition", "errors": []})
    result = timing.analyze_phase_bundles({"native_timing": {"batches": [], "call_envelopes": [],
        "capture_errors": ["offline export failed"]}})
    assert result["status"] == "unknown_native_phase_capture"
    assert result["coarse_bundle_accounting_status"] == "complete_conservative_bundle_accounting"
    assert result["requests"][0]["complete_compute_upper_ns"] == 777


def accepted_archive(tmp_path):
    archive = tmp_path/"archive"
    source = archive/"cpp/ics_core/runtime/request_timing_recorder.hpp"
    source.parent.mkdir(parents=True); source.write_text("frozen022")
    binary = tmp_path/"native022.pyd"; binary.write_bytes(b"accepted022")
    sources = {"cpp/ics_core/runtime/request_timing_recorder.hpp": timing.driver.sha(source)}
    bins = {str(binary): timing.driver.sha(binary)}
    build = {"schema": "g31.circulation.build_only.v1", "status": "build_passed_tests_held",
        "source_before": sources, "source_after": sources, "source_changed": [], "binary_sha256": bins}
    build_path = tmp_path/"build.json"; build_path.write_text(json.dumps(build))
    acceptance = {"schema": "g31.native022_acceptance.v1", "status": "passed", "runtime_cases_passed": 16,
        "compiled_source_changed": [], "compiled_source_count": len(sources), "binary_sha256": bins,
        "build_receipt_sha256": timing.driver.sha(build_path), "source_archive": str(archive),
        "cases": {name: {"ordered_raw_semantics_exact": True,
            "native_phase_report_recomputed": "validated_partial_native_phase_partition"}
            for name in ("lost_ack", "original1x_prefix")}}
    acceptance_path = tmp_path/"acceptance.json"; acceptance_path.write_text(json.dumps(acceptance))
    receipt = {"schema": "g31.circulation.native_timing_accepted_build.v1", "status": "passed",
        "source_before": sources, "source_after": sources, "source_changed": [], "binary_sha256": bins,
        "build_receipt": str(build_path), "build_receipt_sha256": timing.driver.sha(build_path),
        "runtime_acceptance": str(acceptance_path), "runtime_acceptance_sha256": timing.driver.sha(acceptance_path),
        "compiled_source_archive": str(archive)}
    path = tmp_path/"accepted.json"; path.write_text(json.dumps(receipt))
    return path, binary, bins[str(binary)], source, acceptance_path, receipt, acceptance


def test_archived_native_identity_is_independent_of_new_live_cpp(tmp_path):
    path, binary, digest, *_ = accepted_archive(tmp_path)
    receipt = timing.verify_build_receipt(path, binary, digest)
    assert receipt["compiled_source_archive"] == str(tmp_path/"archive")


@pytest.mark.parametrize("damage", ["binary", "archive", "archive_missing", "acceptance_file", "unaccepted_case", "different_archive"])
def test_archived_native_acceptance_fails_closed_on_missing_or_changed_evidence(tmp_path, damage):
    path, binary, digest, source, acceptance_path, receipt, acceptance = accepted_archive(tmp_path)
    if damage == "binary": binary.write_bytes(b"different_binary")
    elif damage == "archive": source.write_text("uncompiled_later_source")
    elif damage == "archive_missing": source.unlink()
    elif damage == "acceptance_file": acceptance_path.write_text("{}")
    elif damage == "unaccepted_case":
        acceptance["cases"]["original1x_prefix"]["ordered_raw_semantics_exact"] = False
        acceptance_path.write_text(json.dumps(acceptance))
        receipt["runtime_acceptance_sha256"] = timing.driver.sha(acceptance_path)
    else:
        receipt["compiled_source_archive"] = str(tmp_path/"unrelated_source")
    path.write_text(json.dumps(receipt))
    with pytest.raises((ValueError, FileNotFoundError)):
        timing.verify_build_receipt(path, binary, digest)
