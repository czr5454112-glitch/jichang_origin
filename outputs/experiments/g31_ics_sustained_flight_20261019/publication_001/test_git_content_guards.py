"""Publication boundary counterexamples; no Git mutation, native or training."""
import pytest
from verify_git_content import require_exact_changes, require_regular_selected_modes


def test_commit_containing_extra_unrequested_file_is_rejected():
    with pytest.raises(ValueError, match='unexpected_changed'):
        require_exact_changes({'approved.py', 'unrelated_private.txt'}, {'approved.py'})


def test_omitted_evidence_is_rejected_even_if_every_present_blob_matches():
    with pytest.raises(ValueError, match='missing_changed'):
        require_exact_changes({'approved.py'}, {'approved.py', 'receipt.json'})


@pytest.mark.parametrize('mode', ['120000', '160000', None])
def test_symlink_submodule_and_missing_entry_cannot_masquerade_as_regular_blob(mode):
    with pytest.raises(ValueError, match='non_regular_or_missing'):
        require_regular_selected_modes({'approved.py': mode}, {'approved.py'})


def test_only_selected_paths_require_regular_modes():
    require_exact_changes(['approved.py', 'receipt.json'], {'receipt.json', 'approved.py'})
    require_regular_selected_modes({'approved.py': '100755', 'receipt.json': '100644',
                                    'unchanged_historical_symlink': '120000'},
                                   {'approved.py', 'receipt.json'})
