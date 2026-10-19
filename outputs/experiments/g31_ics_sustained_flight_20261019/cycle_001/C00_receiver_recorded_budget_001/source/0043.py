"""A finite wall-resource version of the unchanged recorded airport campaign.

The delegate's policy, native input, recorder and timestamp boundary functions
are unchanged. This entry point binds a new budget and immutable prior evidence
before invoking the same prepare/worker/launch functions in its own process.
"""
from __future__ import annotations

from . import foundation_airport_recorded_campaign as delegate

MODULE = 'scripts.experiments.g31_ics_circulation.foundation_airport_recorded_budget_campaign'
SCHEMA = 'g31.foundation.airport_recorded_wall_resource_calibration.v1'
SOFT_SECONDS, HARD_SECONDS, OUTER_SECONDS = 600, 660, 720
PRIOR = delegate.ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_receiver_recorded_v2_001'
EVIDENCE_SHA256 = {
    'plan.json': 'c089ede73233d223661f82f7dbca8fc05fac231c666a69b4cad847fbfc35926e',
    'receipt.json': '28f6ba147d3a8b6580a6111f34e3fc75b1318379beca69ef3cf201bebc90e049',
    'C00/progress.jsonl': '50d6cfa0326c068589150cca09f223d9e98b0fa0aac15616bde0a27042cb6048',
}
_BASE_SOFT_CONTRACT = delegate.soft_checkpoint_contract
_BASE_ROOTS = delegate.SOURCE_ROOTS
_configured = False


def budget_basis():
    refs = []
    for relative, expected in EVIDENCE_SHA256.items():
        path = PRIOR / relative
        delegate.require(delegate.sha(path) == expected, 'wall_resource_basis_hash')
        refs.append({'path': str(path), 'sha256': expected})
    old = delegate.read(PRIOR / 'receipt.json')
    delegate.require(old['status'] == 'censored_before_requested_window_end'
        and old['process']['status'] == 'exited' and old['process']['exitcode'] == 0
        and old['worker_report']['final_physical_time'] == 54240.
        and not old['worker_report']['warmup_reached'], 'closed_soft_partial_basis')
    return {'schema': 'g31.airport_measured_wall_budget.v1', 'references': refs,
        'last_complete_3600_segment': {'start': 50400., 'end': 54000., 'wall_seconds': 91.5},
        'soft_partial': {'physical_time': 54240., 'progress_wall_seconds': 422.93699999997625},
        'remaining_simulated_seconds': 5160.,
        'projected_remaining_loop_wall_seconds': 131.15,
        'projected_complete_loop_wall_seconds': 554.0869999999762,
        'closure_and_parent_allowance_seconds': 31.,
        'projected_total_with_allowance_seconds': 585.0869999999762,
        'estimate_not_completion_guarantee': True,
        'old_partial_relabelled_or_removed': False,
        'native_input_model_physics_policy_window_changed': False,
        'automatic_retries': 0}


def soft_checkpoint_contract():
    contract = _BASE_SOFT_CONTRACT()
    contract.update(soft_seconds=SOFT_SECONDS, hard_seconds=HARD_SECONDS,
        recommended_outer_hard_seconds=OUTER_SECONDS,
        previous_soft_seconds=420, previous_hard_seconds=480,
        wall_budget_basis='Closed54240@422.937s; last3600 took91.5s; remaining5160 projects131.15s; complete loop554.087s plus31s allowance',
        measured_wall_resource_basis=budget_basis())
    return contract


def configure():
    """Bind only version, resource constants and dependency/evidence metadata."""
    global _configured
    if _configured:
        return delegate
    delegate.require((delegate.SOFT_SECONDS, delegate.HARD_SECONDS) == (420, 480),
        'original_recorded_defaults_required')
    budget_basis()
    delegate.MODULE, delegate.SCHEMA = MODULE, SCHEMA
    delegate.SOFT_SECONDS, delegate.HARD_SECONDS = SOFT_SECONDS, HARD_SECONDS
    delegate.SOURCE_ROOTS = (MODULE, *_BASE_ROOTS)
    delegate.soft_checkpoint_contract = soft_checkpoint_contract
    _configured = True
    return delegate


def main():
    configure().main()


if __name__ == '__main__':
    main()
