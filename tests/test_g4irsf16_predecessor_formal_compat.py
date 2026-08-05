from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_g4irsf16_predecessor_formal_validator import (
    CompatibilityError,
    OLD_FRAGMENT,
    SEALED_VALIDATOR_SHA256,
    load_patched_validator,
    patched_validator_source,
)


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate_g4irsf15_causal_campaign.py"


def test_real_sealed_validator_has_one_pinned_in_memory_patch() -> None:
    patched, patched_sha256 = patched_validator_source(VALIDATOR)

    assert OLD_FRAGMENT not in patched
    assert (
        'pilot_round_value = plan.get("pilot_round")' in patched
    )
    assert len(patched_sha256) == len(SEALED_VALIDATOR_SHA256) == 64
    assert VALIDATOR.read_text(encoding="utf-8").count(OLD_FRAGMENT) == 1


def test_formal_null_reaches_original_fail_closed_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_patched_validator(VALIDATOR)
    monkeypatch.setattr(
        module,
        "validate_run_state_attestation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        module,
        "validate_h_system_baseline_reference",
        lambda *_args, **_kwargs: {},
    )
    formal_plan = {
        "binary": {"sha256_before": "sealed-binary"},
        "campaign": "formal",
        "pilot_round": None,
        "shards": [],
    }

    with pytest.raises(
        module.ValidationError, match="COMPACT_EVIDENCE_INDEX_DRIFT"
    ):
        module.collect_compact_evidence_labels(
            ROOT,
            "formal",
            formal_plan,
            evidence_bindings=[{}],
            baseline_binding={},
            run_state_attestation={"shards": []},
        )


def test_tampered_validator_is_rejected(tmp_path: Path) -> None:
    tampered = tmp_path / "validator.py"
    tampered.write_bytes(VALIDATOR.read_bytes() + b"\n# drift\n")

    with pytest.raises(
        CompatibilityError, match="SEALED_VALIDATOR_SHA256_DRIFT"
    ):
        load_patched_validator(tampered)
