"""Inventory of guarded supplied phase-B facts, not a restart-state certificate."""
from __future__ import annotations

from . import live_obligation_delivered_context as context

VERSION = 'g31.live_obligation.phase_b_support_inventory.v1'

MISSING_RESTART_FACTS = (
    'complete_remaining_edge_headway_history',
    'complete_resource_calendars_and_fifo_waiters',
    'last_arbitration_epochs_and_native_event_tie_order',
    'peer_private_immutable_action_payloads_not_delivered_in_public_messages',
    'peer_policy_pending_quiet_seen_reply_budget_state',
    'complete_protocol_retry_notification_and_event_history',
)


def inspect_supplied_context(supplied_context):
    """Rerun all original guards, then enumerate facts without minting authority.

    A validated contemporary endpoint pair is not a Markov state.  This function
    deliberately does not accept a native session, saved outcome or model point
    and cannot resolve missing model history by copying from a remote endpoint.
    """
    checked = context.revalidate(supplied_context)
    if checked.get('status') != 'conditional_validated_later_v3_data':
        return context.unknown('phase_b_support:later_context_guard')
    payload = supplied_context.audit_copy()['payload']
    if payload['phase'] != 'first_reuse_route':
        return context.unknown('phase_b_support:first_reuse_route_required')
    bundle = checked['bundle']
    return {
        'schema': VERSION,
        'status': 'conditional_supplied_fact_inventory',
        'phase': payload['phase'], 'owner': payload['owner'], 'at': payload['at'],
        'supplied_context_sha256': supplied_context.audit_copy()['sha256'],
        'represented_job_ids': list(bundle['jobs']),
        'represented_tray_ids': list(bundle['trays']),
        'represented_resource_ids': list(bundle['resources']),
        'completed_prefix_job_ids': list(bundle['completed_prefix']),
        'original_endpoint_current_action_lifecycle_guards_rerun': True,
        'retained_evidence': [
            'current_deciding_owner_view', 'selected_own_publication_endpoint',
            'selected_delivered_peer_capture', 'own_immutable_submission_prefix',
            'retained_prior_public_contracts',
        ],
        'restart_status': 'unknown_missing_model_history',
        'missing_restart_facts': list(MISSING_RESTART_FACTS),
        'model_history_coverage_certified': False,
        'conditional_model_point_is_native_authority': False,
        'native_delivery_verified': False, 'online_executable': False,
        'native_protection_certified': False,
        'future_filter_requirements': [
            'Prove the retained model-state set covers all states allowed by the lawful history.',
            'Bind actual opaque IDs to projected IDs by evidence-constrained one-to-one relations; never parse ID spellings or discard IDs.',
            'Rerun actual current-owner and delivered-message guards at each decision.',
            'Do not infer hidden queue/calendar/message equality from prior endpoint/chronology conformance.',
            'Every surviving state and every strong method must use the same information, candidates and charged computation.',
        ],
    }
