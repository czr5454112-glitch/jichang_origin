"""Focused synthetic tests: no actual saved rows, C extension or native runtime."""
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).with_name("profile_bridge_prefix512.py")
SPEC = importlib.util.spec_from_file_location("prefix512_under_test", SCRIPT)
SUBJECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUBJECT)


@pytest.mark.parametrize("classification", ["direct", "fallback", "error"])
def test_dispatch_and_profile_do_not_repeat_underlying_call(classification):
    calls = []

    def attempt(body):
        calls.append("C_attempt")
        if classification == "error":
            raise MemoryError("retained")
        return NotImplemented if classification == "fallback" else b"payload"

    def fallback(body):
        calls.append("fallback")
        return hashlib.sha256(b"fallback").hexdigest()

    digest = SUBJECT.routing.clone(SUBJECT.encoder._digest, {**SUBJECT.encoder._digest.__globals__, "_ORIGINAL": fallback})
    profile = SUBJECT.Profile({digest.__code__: "complete_digest", attempt.__code__: "C_try_typed_bytes",
                               fallback.__code__: "original_fallback_writer"})
    sys.setprofile(profile.callback)
    try:
        if classification == "error":
            with pytest.raises(MemoryError, match="retained"):
                digest(attempt, {})
        else:
            assert len(digest(attempt, {})) == 64
    finally:
        sys.setprofile(None)
    report = profile.report()
    assert calls == (["C_attempt", "fallback"] if classification == "fallback" else ["C_attempt"])
    assert len(report["digests"]) == 1
    assert report["inclusive_exclusive_conservation"]


def test_513th_call_censors_before_underlying_read():
    tape = SimpleNamespace(index=0)
    profile = SUBJECT.Profile({})
    calls = []

    def underlying():
        calls.append(tape.index)
        tape.index += 1
        return tape.index

    for ordinal in range(512):
        assert SUBJECT.invoke_endpoint(tape, profile, "advance_to", underlying, (), {}) == ordinal + 1
    with pytest.raises(SUBJECT.PrefixCensored):
        SUBJECT.invoke_endpoint(tape, profile, "advance_to", underlying, (), {})
    assert calls == list(range(512)) and tape.index == 512
    assert not issubclass(SUBJECT.PrefixCensored, (ValueError, KeyError, TypeError, Exception))


def test_unavailable_supply_boundary_is_unknown_without_call():
    called = []
    with pytest.raises(SUBJECT.UnsupportedBoundary):
        SUBJECT.invoke_endpoint(SimpleNamespace(index=4), SUBJECT.Profile({}), "submit_protocol_transfer",
                                lambda *args: called.append(args), ({"request_id": "owner:single-supply"},), {})
    assert called == []


def test_original_observer_factory_inverse_ast_preserves_classes(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api/manifest.jsonl").write_text("", encoding="utf-8")
    tape, owner, calls, caps, proof = SUBJECT.observer_factory(SUBJECT.PHYSICAL.ReplayTape,
        SUBJECT.POLICY.BridgeOwner, tmp_path, SUBJECT.Profile({}))
    assert proof["inverse_AST_exact"] and proof["unavailable_first_supply_boundary"] is None
    assert tape.__bases__ == (SUBJECT.PHYSICAL.ReplayTape,) and owner.__bases__ == (SUBJECT.POLICY.BridgeOwner,)
    assert calls == [] and caps == {}


def test_startup_environment_uses_null_removal_not_build_environment():
    keys = ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE", "SETUPTOOLS_USE_DISTUTILS")
    expected = {name: None for name in keys}
    result = SUBJECT.startup_environment({**dict.fromkeys(keys, "wrong"), "PATH": "keep"}, expected)
    assert not set(keys) & set(result) and result["PATH"] == "keep"
    with pytest.raises(ValueError, match="key_domain"):
        SUBJECT.startup_environment({}, {"PATH": "build"})


def test_profile_rejects_invalid_clock_and_overflow():
    profile = SUBJECT.Profile({})
    profile.spans = [{"start_ns": True, "end_ns": 2, "exclusive_ns": 1}]
    with pytest.raises(ValueError, match="invalid_clock"):
        profile.report()
    profile = SUBJECT.Profile({})
    profile.error = "span_overflow"
    with pytest.raises(ValueError, match="unclosed_or_failed"):
        profile.report()
