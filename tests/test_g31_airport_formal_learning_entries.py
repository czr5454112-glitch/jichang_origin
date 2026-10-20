"""The airport bridge must not turn residuals or unknown tails into FQI data."""
from copy import deepcopy
import pytest

from scripts.experiments.g31_ics_circulation.foundation_multistep_learning import (
    airport_paired_transition_gate,
)
from scripts.experiments.g31_ics_circulation.foundation_fqi_checkpoint_selection import (
    select_airport_paired_checkpoint,
)


def pair():
    row = dict(unexecuted_candidate_label=False,
        observation=dict(now=100., owner_id="A"),
        transition=dict(next_state=dict(now=160., owner_id="A"), elapsed_seconds=60.,
            reward=-120., reward_unit="negative_bag_seconds",
            unexecuted_candidates_have_labels=False, candidate_labels=None,
            supported_next_action_ids=["actual-reference"]))
    return dict(schema="g31.foundation.airport_pair_dataset.v1",
        pair=dict(status="closed_actual_pair"), rows=[row, deepcopy(row)])


@pytest.mark.parametrize("change", ["residual", "wrong_owner", "invented_label", "zero_terminal"])
def test_false_multistep_evidence_is_rejected(change):
    data = pair()
    transition = data["rows"][0]["transition"]
    if change == "residual":
        transition["elapsed_seconds"] = 0.
        transition["next_state"]["now"] = 100.
    elif change == "wrong_owner":
        transition["next_state"]["owner_id"] = "B"
    elif change == "invented_label":
        transition["candidate_labels"] = {"unexecuted-alternative": 0.}
    else:
        transition.update(next_state=None, elapsed_seconds=None, reward=0.)
    with pytest.raises(ValueError):
        airport_paired_transition_gate([data])


def test_actual_successor_and_unknown_tail_do_not_authorize_bootstrap():
    data = pair()
    data["rows"][1]["transition"] = dict(next_state=None, elapsed_seconds=None, reward=None)
    result = airport_paired_transition_gate([data])
    assert result["natural_successors"] == result["unknown_successors"] == 1
    assert result["mc_pair_targets_available"] and not result["bootstrap_authorized"]


def test_selection_entry_rejects_test_before_checkpoint_evaluation():
    models = [{"schema": "g31.foundation.airport_pair_ranker.v1"}]
    with pytest.raises(ValueError, match="development_only"):
        select_airport_paired_checkpoint(models, [{"pair": {"parent": {"split": "test"}}}])
