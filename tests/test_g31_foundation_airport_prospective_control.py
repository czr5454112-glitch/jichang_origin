"""Prospective current-only R2 inputs and one-patch residual invariants."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_prospective_control as control
from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import digest
from test_g31_foundation_airport_pairs import fixture, opportunity, PARENT
from test_g31_foundation_airport_pair_ranker import forecast_evidence


def parent():
    return dict(PARENT, calendar_start_epoch_seconds=1700000000.)


def forecast(obs):
    result = forecast_evidence({"parent": parent(), "observation": obs})
    result["observed_at_epoch_seconds"] = parent()["calendar_start_epoch_seconds"]+obs["now"]
    result["forecast"]["forecast_origin"] = obs["now"]
    result["forecast"]["remaining_support_until"] = obs["now"]+1800.
    result["forecast_sha256"] = digest(result["forecast"])
    return result


def make(selector, **options):
    obs, baseline = fixture()
    return control.make_prospective_planner(lambda *_a, **_kw: deepcopy(baseline),
        parent=parent(), policy_id="frozen", information_variant=options.pop("information_variant", "C01"),
        selector=selector, activate_at=100., **options)


def test_inference_rows_contain_current_actions_and_no_outcome_or_target_fields():
    obs, baseline = fixture()
    rows = control.current_candidate_rows(obs, baseline, opportunity(obs, baseline),
        parent=parent(), information_variant="C01", forecast_evidence={"forbidden": "plan"})
    forbidden = {"target_return", "paired_advantage_bag_seconds", "actual_execution",
        "transition", "candidate_labels", "forecast_evidence"}
    assert all(not forbidden.intersection(row) for row in rows)
    assert rows[0]["semantic_action"]["tray_id"] == rows[1]["semantic_action"]["tray_id"] == "a"
    assert [row["semantic_action"]["destination"] for row in rows] == [1, 2]
    rows[1]["observation"]["version"] += 1
    assert obs["version"] == rows[0]["observation"]["version"]


def test_positive_selector_patches_one_tray_preserves_other_then_skips_residual():
    calls = []
    planning = make(lambda *rows: calls.append(rows) or 1.)
    obs, baseline = fixture()
    selected = planning(obs, predictive=True, message_delay=2., request_prefix="protocol:2")
    assert selected["intents"][0]["destination"] == 2
    assert selected["intents"][1:] == baseline["intents"][1:]
    planning(obs, predictive=True, request_prefix="protocol:2:residual")
    planning(obs, predictive=True, request_prefix="protocol:2")
    assert len(calls) == 1
    assert planning.records[0]["mode"] == "isolated_evaluation_only"
    assert not planning.records[0]["native_execution_authority"]


def test_hold_suppression_persists_only_current_owner_timestamp():
    planning = make(lambda *_rows: 1., patch_rank=2)
    obs, baseline = fixture()
    selected = planning(obs, predictive=True, request_prefix="protocol:2")
    residual = planning(obs, predictive=True, request_prefix="protocol:2:residual")
    assert selected["intents"] == residual["intents"] == baseline["intents"][1:]
    obs["now"] = 160.
    # A later residual must not inherit yesterday's held-tray exclusion.
    assert planning(obs, predictive=True, request_prefix="protocol:3:residual")["intents"] == baseline["intents"]


def test_C01_never_calls_or_forwards_forecast_provider():
    def forbidden(**_kwargs):
        raise AssertionError("C01 cannot read a plan")
    planning = make(lambda reference, patch: 1. if all("forecast_evidence" not in row
        for row in (reference, patch)) else -1., forecast_at=forbidden)
    obs, _ = fixture()
    assert planning(obs, predictive=True)["batch_patch"]["kind"] == "replace_optional"


def test_plan_variant_uses_one_actual_current_forecast_for_both_actions():
    calls, seen = [], []
    def provider(**kwargs):
        calls.append(kwargs)
        return forecast(kwargs["observation"])
    planning = make(lambda *rows: seen.extend(rows) or 1.,
        information_variant="C10", forecast_at=provider)
    obs, _ = fixture()
    planning(obs, predictive=True, message_delay=2.)
    assert len(calls) == 1 and len(seen) == 2
    assert seen[0]["forecast_evidence"] == seen[1]["forecast_evidence"]
    assert planning.records[0]["status"] == "isolated_current_patch_proposed"


@pytest.mark.parametrize("mutation", ["stale_forecast", "model_exception", "nan_score", "state_mutation"])
def test_invalid_current_or_scoring_returns_ordinary_baseline_with_reason(mutation):
    obs, baseline = fixture()
    def selector(*_rows):
        if mutation == "model_exception":
            raise ValueError("unavailable_frozen_model")
        return float("nan") if mutation == "nan_score" else 1.
    def provider(**kwargs):
        result = forecast(kwargs["observation"])
        if mutation == "stale_forecast":
            result["observed_at_epoch_seconds"] -= 1.
        elif mutation == "state_mutation":
            kwargs["observation"]["version"] += 1
        return result
    planning = make(selector, information_variant="C10", forecast_at=provider)
    selected = planning(obs, predictive=True)
    assert selected == baseline and planning.records[0]["status"] == "reference_fallback"
    assert planning.records[0]["reason"]


def test_warmup_has_no_model_or_forecast_work():
    def forbidden(*_a, **_kw):
        raise AssertionError("before activation")
    planning = make(forbidden, information_variant="C11", forecast_at=forbidden)
    obs, baseline = fixture()
    obs["now"] = 99.
    assert planning(obs, predictive=True) == baseline
    assert planning.records == []
