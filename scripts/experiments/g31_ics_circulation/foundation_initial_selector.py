"""Budgeted initial proposals; only the existing live dispatch owns submission.

The scorer sees detached owner-public features and action semantics. Conditional
forecasts screen its choices against the unchanged five-job incumbent reference.
Historical evaluator callbacks remain advice-only and are not used here.
"""
from __future__ import annotations

import copy
import math

from . import foundation_budgeted_provider as provider
from . import foundation_ranker as ranker

SCHEMA = 'g31.foundation.initial_selector.v1'
MODES = ('incumbent', 'learned', 'fixed12')


def require(value, reason):
    if not value:
        raise ValueError('foundation_initial_selector:' + reason)


def select_report(report, *, mode, model_version):
    """Construct a proposal from this request's sealed forecasts, not authority."""
    require(mode in MODES, 'known_mode')
    owner, queried, rows = report['owner'], report['requested_indices'], report['rows']
    require(owner in ('A', 'B') and report['public_compatibility_filter']['enabled'] is True,
        'public_compatible_domain_required')
    base = {'schema': SCHEMA, 'selector_mode': mode, 'model_version': model_version,
        'selected_index': None, 'selected_action': None,
        'accounting': {'query_indices': list(queried)}, 'allowed_candidate_indices': list(queried),
        'provider_evidence': copy.deepcopy(report), 'dispatch_authorized': False,
        'native_authority': False, 'native_protection_certified': False}
    checked = provider.compatibility.select_component(base, owner, 4)
    eligible = checked['eligible_queried_indices']
    complete = report['status'] == 'conditional_forecasts_complete'
    # A failed source/close or partial forecast cannot be rescued by old rows.
    if not complete:
        eligible = []
    selected = None
    if owner == 'A' or mode == 'incumbent':
        selected = 4 if 4 in eligible else None
    elif mode == 'fixed12':
        selected = 12 if 12 in eligible else None
    elif eligible:
        scores = report['scores']
        require(type(scores) is list and len(scores) == len(rows)
            and all(type(scores[i]) in (int, float) and math.isfinite(scores[i]) for i in eligible),
            'finite_queried_scores')
        selected = min(eligible, key=lambda i: (-scores[i], i))
    base.update(selected_index=selected,
        selected_action=copy.deepcopy(rows[selected]['action']) if selected is not None else None,
        allowed_candidate_indices=[] if selected is None else [selected],
        protected_compatible_indices=list(eligible),
        candidate_mask=[{'candidate_index': i, 'enabled': i in eligible,
            'reason': None if i in eligible else 'unknown_or_original_protection_or_compatibility'} for i in queried],
        selection_rule='highest_frozen_score_among_queried_protected_compatible' if mode == 'learned' and owner == 'B'
            else 'explicit_fixed_candidate_if_queried_protected_compatible',
        status='selected_conditional_proposal' if selected is not None else 'unknown_no_admissible_estimate')
    return base


def make_selector(mode='incumbent', model_version=None):
    require(mode in MODES, 'known_mode')
    if mode == 'learned':
        require(model_version in ranker._MODELS, 'explicit_loaded_frozen_model_required')
        model = ranker._MODELS[model_version]
        require(model['feature_schema'] == ranker.data.SCHEMA and len(model['feature_names']) == 43
            and model['native_execution_authority'] is False, 'frozen_initial_43_feature_model')

    def selector(decision):
        provider.origin.require_current(decision)
        audit = decision.audit_copy()
        if audit['owner'] == 'A' or mode == 'incumbent':
            options = {'budget': 1, 'prefix_budget': 1, 'candidate_indices': [4]}
        elif mode == 'fixed12':
            options = {'budget': 2, 'prefix_budget': 2, 'candidate_indices': [4, 12]}
        else:
            options = {'budget': 4, 'prefix_budget': 2, 'scorer': ranker.score_candidates,
                'model_version': model_version}
        measured = provider.evaluate_budgeted(decision, compatible_only=True, **options)
        report = measured['batch'].audit_copy()
        provider.origin.require_current(decision)
        require(report['owner'] == audit['owner'] and report['initial_public_sha256'] == audit['public_sha256']
            and report['actual_collection_at'] == audit['at'], 'same_current_batch')
        result = select_report(report, mode=mode, model_version=model_version)
        result['timing'] = {key: measured[key] for key in ('compute_wall_ms', 'seal_wall_ms')}
        return result

    return selector
