from copy import deepcopy
import xml.etree.ElementTree as ET

import pytest

from scripts.experiments.g31_ics_circulation import run_native027_semantic_gate as gate


def xml(path):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests="21", failures="0", errors="0", skipped="0")
    for name, count in gate.EXPECTED.items():
        for i in range(count): ET.SubElement(suite, "testcase", name=name + (f"[{i}]" if count > 1 else ""))
    ET.ElementTree(root).write(path)
    return root, suite


def test_complete_exact_denominator(tmp_path):
    path = tmp_path / "tests.xml"; xml(path)
    assert len(gate.validate_xml(path)) == 21


@pytest.mark.parametrize("mutation", ["skip", "failure", "error", "missing", "duplicate", "wrong_test", "suite_error"])
def test_invalid_xml_is_not_acceptance(tmp_path, mutation):
    path = tmp_path / "tests.xml"; root, suite = xml(path)
    first = suite[0]
    if mutation in {"skip", "failure", "error"}: ET.SubElement(first, {"skip": "skipped"}.get(mutation, mutation))
    elif mutation == "missing": suite.remove(first)
    elif mutation == "duplicate": suite[1].set("name", first.get("name"))
    elif mutation == "wrong_test": first.set("name", "test_not_the_required_test")
    else: suite.set("errors", "1")
    ET.ElementTree(root).write(path)
    with pytest.raises(ValueError): gate.validate_xml(path)


def worker():
    sources = {str(gate.TEST): "test-hash", "dependency.py": "dependency-hash"}
    plan = {"binary": "native027.pyd", "binary_sha256": gate.BINARY_SHA, "source_sha256": sources}
    actual = {"exit_code": 0, "unarchived_loaded_sources": [], "fixture_module_loaded": True,
        "binary_sha256_after": gate.BINARY_SHA, "actual_binary_sha256": gate.BINARY_SHA,
        "actual_binary_path": plan["binary"], "native_host_identity": {"resolved_path": plan["binary"], "sha256": gate.BINARY_SHA},
        "loaded_source_sha256": deepcopy(sources)}
    return plan, actual


def test_actual_worker_identity_and_loaded_sources():
    plan, actual = worker(); gate.validate_worker(plan, actual)


@pytest.mark.parametrize("mutation", ["failed", "unarchived", "fixture", "binary", "path", "identity", "source", "missing_test"])
def test_worker_evidence_rejects_gaps(mutation):
    plan, actual = worker()
    if mutation == "failed": actual["exit_code"] = 1
    elif mutation == "unarchived": actual["unarchived_loaded_sources"] = ["x.py"]
    elif mutation == "fixture": actual["fixture_module_loaded"] = False
    elif mutation == "binary": actual["actual_binary_sha256"] = "0" * 64
    elif mutation == "path": actual["actual_binary_path"] = "other.pyd"
    elif mutation == "identity": actual["native_host_identity"]["sha256"] = "0" * 64
    elif mutation == "source": actual["loaded_source_sha256"]["dependency.py"] = "changed"
    else: del actual["loaded_source_sha256"][str(gate.TEST)]
    with pytest.raises(ValueError): gate.validate_worker(plan, actual)
