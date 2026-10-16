from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation.review_original_low_wip_reuse_saved import semantic_api_row


def row(wall):
    return {"endpoint": "advance_to", "before": 0., "after": 10., "args": [10.],
            "result": {"wall_seconds": wall, "status": "reached", "physical_time": 10.,
                       "nested": {"wall_seconds": 4.}}}


@pytest.mark.parametrize("wall", [True, False, -1., float("nan"), float("inf"), "0.2", None])
def test_invalid_wall_diagnostic_is_rejected(wall):
    with pytest.raises(ValueError, match="invalid_native_advance_wall_seconds"):
        semantic_api_row(row(wall))


def test_only_exact_field_removed_without_mutating_original():
    original = row(.1); saved = deepcopy(original)
    projected = semantic_api_row(original)
    assert original == saved
    assert projected == {**original, "result": {k: v for k, v in original["result"].items() if k != "wall_seconds"}}
    assert projected["result"]["nested"]["wall_seconds"] == 4.
    other = {"endpoint": "protocol_request", "result": {"wall_seconds": .1}}
    assert semantic_api_row(other) == other


def test_semantic_clock_difference_remains_visible():
    a, b = row(.1), row(.2)
    assert semantic_api_row(a) == semantic_api_row(b)
    b["result"]["physical_time"] = 11.
    assert semantic_api_row(a) != semantic_api_row(b)
