from __future__ import annotations

import copy

from scripts.eval import run_feng_native_cie_dh as audit


def _frozen_summary() -> dict[str, object]:
    return {
        "runs": [
            {
                "run_id": "run_01",
                "profile": "full",
                "status": "complete",
                "comparison_eligible": True,
                "canonical_segment_count": 43_603,
                "completed_segment_count": 43_603,
                "canonical_raw_bag_count": 28_506,
                "complete_raw_bag_count": 28_506,
                "canonical_success_rate": 1.0,
                "survivor_only": False,
                "denominators": {
                    "processed_attempt": {
                        "count": 28_506,
                        "seconds": {
                            "min": 188.0,
                            "mean": 236.710166280783,
                            "max": 357.0,
                        },
                    }
                },
            }
        ]
    }


def test_frozen_hca_parser_passes_exact_values_and_fails_drift() -> None:
    passing = audit.validate_hca_summary(_frozen_summary())
    assert passing["pass"] is True
    assert passing["status"] == audit.HCA_STATUS

    drifted = copy.deepcopy(_frozen_summary())
    drifted["runs"][0]["denominators"]["processed_attempt"]["seconds"]["mean"] += 1e-9
    failing = audit.validate_hca_summary(drifted)
    assert failing["pass"] is False
    assert failing["status"] == audit.HCA_FAIL_STATUS
    assert failing["runs"][0]["checks"]["processed_mean_exact"] is False


def test_java_lexer_ignores_comments_strings_and_gui_cycle_text() -> None:
    source = r'''
        // moving stopped BTI DDI DH 0.2
        String label = "DH moving stopped BTI DDI 0.2";
        /* CIE_DH 0.2 */
        private double cycle = 200;
        void route() { moving = true; }
    '''
    code = audit._strip_java_non_code(source)

    assert "cycle = 200" in code
    assert "moving = true" in code
    assert code.count("moving") == 1
    assert "stopped" not in code
    assert "BTI" not in code
    assert "DDI" not in code
    assert "0.2" not in code
