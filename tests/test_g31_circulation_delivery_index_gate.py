"""Fail-closed evidence identity checks; no native module is loaded."""
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import accept_native_delivery_indices as gate


def build():
    return dict(status="build_passed_tests_held", source_changed=[], commands=[{"exit_code": 0}],
                binary_sha256={"intended.pyd": gate.OLD_BINARY_SHA})


@pytest.mark.parametrize("change", [
    {"status": "failed"}, {"source_changed": ["header.hpp"]}, {"commands": []},
    {"commands": [{"exit_code": 1}]},
    {"binary_sha256": {"candidate.pyd": gate.NEW_BINARY_SHA}},
    {"binary_sha256": {"one.pyd": gate.OLD_BINARY_SHA, "two.pyd": gate.OLD_BINARY_SHA}},
])
def test_build_receipt_rejects_failure_or_substituted_baseline(monkeypatch, change):
    value=build();value.update(change)
    monkeypatch.setattr(gate, "sha", lambda path: gate.OLD_BINARY_SHA)
    with pytest.raises(ValueError): gate.validate_build(value, gate.OLD_BINARY_SHA)


def test_actual_binary_hash_required(monkeypatch):
    monkeypatch.setattr(gate, "sha", lambda path: "0"*64)
    with pytest.raises(ValueError, match="binary_changed"):gate.validate_build(build(), gate.OLD_BINARY_SHA)


def test_valid_intended_build(monkeypatch):
    monkeypatch.setattr(gate, "sha", lambda path: gate.OLD_BINARY_SHA)
    assert gate.validate_build(build(), gate.OLD_BINARY_SHA)==Path("intended.pyd")


@pytest.mark.parametrize("actual", [{}, {"helper.py": "changed"}, {"helper.py": "same", "new.py": "added"}])
def test_runtime_source_closure_cannot_drop_mutate_or_add_helper(monkeypatch, actual):
    monkeypatch.setattr(gate, "imported_sources", lambda: [Path(p) for p in actual])
    monkeypatch.setattr(gate, "sha", lambda p: actual[str(p)])
    with pytest.raises(ValueError, match="runtime_source_closure_changed"):
        gate.verify_import_closure({"source_before":{"helper.py":"same"}})


def test_gate_semantic_comparison_preserves_nested_payload_field_and_order():
    value={"client_calls":[{"submit_compute_ms":1.,"request":{"submit_compute_ms":7.,"a":1,"b":2}}]}
    changed=deepcopy(value);changed["client_calls"][0]["submit_compute_ms"]=2.
    assert gate.ordered(gate.semantic(value))==gate.ordered(gate.semantic(changed))
    changed["client_calls"][0]["request"]["submit_compute_ms"]=8.
    assert gate.ordered(gate.semantic(value))!=gate.ordered(gate.semantic(changed))
    assert gate.ordered({"a":1,"b":2})!=gate.ordered({"b":2,"a":1})
