from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from scripts.eval.g4irsf11_experiment_protocol import (
    EXTENSION_PROTOCOL_VERSION,
    system_extension_cases,
    system_extension_manifest,
)
from scripts.eval.run_g4irsf11_system_extensions import _continuity_audit


class _ReleaseRows(Sequence[dict[str, Any]]):
    def __init__(self, count: int, span: float) -> None:
        self.count = count
        self.span = span

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, index: int) -> dict[str, Any]:
        if index < 0:
            index += self.count
        if index < 0 or index >= self.count:
            raise IndexError(index)
        return {"release_time": index * self.span / max(1, self.count - 1)}


def test_extension_protocol_is_exact_and_never_smoke_limited() -> None:
    cases = system_extension_cases()
    assert len(cases) == 5
    assert all(case.segment_limit is None for case in cases)
    assert {case.scale for case in cases} >= {2.0, 7.0, 8.0, 16.0}
    manifest = system_extension_manifest()
    assert manifest["protocol_version"] == EXTENSION_PROTOCOL_VERSION
    assert manifest["case_count"] == 5


def test_rolling_seven_day_audit_requires_all_rows_and_six_boundaries() -> None:
    base = {
        "case_id": "extension_rolling_7day_full",
        "execution_status": "EXECUTED",
        "workload_segment_count": 305_221,
        "arrival_span_seconds": 6 * 86_400.0 + 1.0,
    }
    exact_rows = _ReleaseRows(305_221, 6 * 86_400.0 + 1.0)
    assert _continuity_audit(base, workload_rows=exact_rows)["no_smoke_substitution_pass"] is True
    truncated = dict(base, workload_segment_count=32_768)
    assert _continuity_audit(truncated, workload_rows=exact_rows)["no_smoke_substitution_pass"] is False
    one_day_rows = _ReleaseRows(305_221, 86_399.0)
    assert _continuity_audit(base, workload_rows=one_day_rows)["no_smoke_substitution_pass"] is False


def test_extension_audit_fails_closed_when_retained_exact_input_is_missing() -> None:
    row = {
        "case_id": "extension_rolling_7day_full",
        "execution_status": "EXECUTED",
        "workload_segment_count": 305_221,
        "arrival_span_seconds": 7 * 86_400.0,
    }
    assert _continuity_audit(row)["no_smoke_substitution_pass"] is False
