from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.eval.g4irsf11_historical_evidence import (
    DEFAULT_BASELINE_ID,
    ROOT,
    historical_formal_completion_validation_errors,
    trusted_baseline,
)
from scripts.eval.g4irsf12_current_identity import (
    create_current_identity_claim,
    validate_current_identity_claim,
)


def _copy_historical_bundle(target_root: Path) -> dict[str, object]:
    baseline = trusted_baseline()
    completion_path = ROOT / str(baseline["completion_manifest_path"])
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    paths = [str(baseline["completion_manifest_path"]), *completion["artifacts"]]
    for relative in paths:
        source = ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return completion


def _identity_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    (tmp_path / "cpp" / "ics_core").mkdir(parents=True)
    (tmp_path / "src" / "czr005").mkdir(parents=True)
    (tmp_path / "scripts" / "eval").mkdir(parents=True)
    (tmp_path / "artifacts" / "configs").mkdir(parents=True)
    (tmp_path / "build" / "python").mkdir(parents=True)
    (tmp_path / "CMakeLists.txt").write_text("project(identity_fixture)\n", encoding="utf-8")
    (tmp_path / "cpp" / "ics_core" / "runtime.hpp").write_text(
        "inline int runtime_version() { return 1; }\n", encoding="utf-8"
    )
    (tmp_path / "src" / "czr005" / "runtime.py").write_text(
        "VERSION = 1\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "eval" / "g4irsf12_probe.py").write_text(
        "PROBE = True\n", encoding="utf-8"
    )
    config = tmp_path / "artifacts" / "configs" / "candidate.json"
    config.write_text('{"resource_semantics_id":"R3"}\n', encoding="utf-8")
    binary = tmp_path / "build" / "python" / "czr005_cpp.pyd"
    binary.write_bytes(b"native-runtime-v1")
    source = tmp_path / "src" / "czr005" / "runtime.py"
    return binary, config, source


def test_historical_completion_reconstructs_the_259608c_source_bundle() -> None:
    # Current G4IRSF12 sources may differ.  The frozen 84/84 evidence must still
    # validate from its producing Git tree and its unchanged artifact bundle.
    assert historical_formal_completion_validation_errors(ROOT) == []
    baseline = trusted_baseline(DEFAULT_BASELINE_ID)
    assert baseline["commit_sha"] == "259608cd536f8ca2f6651a01b7d842675f63a9f7"
    assert baseline["implementation_source_bundle_sha256"] == (
        "99758e68f445d97c00b876e2edb788df2fdb51eb2443af42e9384b66ebd801e5"
    )


def test_unknown_historical_baseline_fails_closed() -> None:
    errors = historical_formal_completion_validation_errors(
        ROOT,
        baseline_id="unreviewed-or-forged-baseline",
    )
    assert errors
    assert any("unknown" in error and "baseline" in error for error in errors)


def test_historical_artifact_tampering_cannot_be_hidden_by_old_completion(
    tmp_path: Path,
) -> None:
    completion = _copy_historical_bundle(tmp_path)
    artifact_path = tmp_path / next(iter(completion["artifacts"]))
    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")
    errors = historical_formal_completion_validation_errors(tmp_path)
    assert errors
    assert any("artifact SHA-256 mismatch" in error for error in errors)


def test_historical_completion_hash_cannot_be_overwritten_in_place(
    tmp_path: Path,
) -> None:
    _copy_historical_bundle(tmp_path)
    baseline = trusted_baseline()
    completion_path = tmp_path / str(baseline["completion_manifest_path"])
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["implementation_source_bundle_sha256"] = "0" * 64
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    errors = historical_formal_completion_validation_errors(tmp_path)
    assert errors
    assert any("differs from the producing Git baseline" in error for error in errors)
    assert any("source bundle differs" in error for error in errors)


def test_current_identity_gate_detects_binary_source_and_config_drift(
    tmp_path: Path,
) -> None:
    binary, config, source = _identity_fixture(tmp_path)
    claim = create_current_identity_claim(
        root=tmp_path,
        binary_path=binary,
        config_paths=[config],
    )
    assert validate_current_identity_claim(
        claim,
        root=tmp_path,
        binary_path=binary,
        config_paths=[config],
    )["status"] == "PASS"

    source.write_text("VERSION = 2\n", encoding="utf-8")
    source_result = validate_current_identity_claim(
        claim,
        root=tmp_path,
        binary_path=binary,
        config_paths=[config],
    )
    assert source_result["status"] == "FAIL"
    assert any(
        "implementation_source_bundle_sha256 mismatch" in error
        for error in source_result["errors"]
    )

    source.write_text("VERSION = 1\n", encoding="utf-8")
    config.write_text('{"resource_semantics_id":"R4"}\n', encoding="utf-8")
    config_result = validate_current_identity_claim(
        claim,
        root=tmp_path,
        binary_path=binary,
        config_paths=[config],
    )
    assert config_result["status"] == "FAIL"
    assert any(
        "candidate_config_sha256 mismatch" in error
        for error in config_result["errors"]
    )

    config.write_text('{"resource_semantics_id":"R3"}\n', encoding="utf-8")
    binary.write_bytes(b"native-runtime-v2")
    binary_result = validate_current_identity_claim(
        claim,
        root=tmp_path,
        binary_path=binary,
        config_paths=[config],
    )
    assert binary_result["status"] == "FAIL"
    assert any(
        "implementation_sha256 mismatch" in error
        for error in binary_result["errors"]
    )


def test_current_identity_gate_rejects_an_unrecorded_config_set(
    tmp_path: Path,
) -> None:
    binary, config, _source = _identity_fixture(tmp_path)
    claim = create_current_identity_claim(
        root=tmp_path,
        binary_path=binary,
        config_paths=[config],
    )
    second = tmp_path / "artifacts" / "configs" / "second.json"
    second.write_text('{"resource_semantics_id":"R4"}\n', encoding="utf-8")
    result = validate_current_identity_claim(
        claim,
        root=tmp_path,
        binary_path=binary,
        config_paths=[config, second],
    )
    assert result["status"] == "FAIL"
    assert any("config_paths mismatch" in error for error in result["errors"])
