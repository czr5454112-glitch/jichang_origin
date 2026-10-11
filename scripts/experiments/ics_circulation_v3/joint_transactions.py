"""Atomic whole-route admission for a same-version set of new commitments.

Jointly departing trays release their own idle reservations together. Each
route still passes the existing identity, deadline, path, module, source-stock
and capacity validator against all other proposed/irrevocable itineraries.
No old plan is cancelled and no currently loaded/held tray becomes an empty
donor. This explicit operator closes the sequential-admission swap gap.
"""
from dataclasses import asdict

from .model import ValidationResult
from .runtime import (ExecutionValidator, _OWNER_LOCK, _merge_reservations,
                      _publish_forecast, actual_action_key, assert_invariants,
                      candidate_reservations, effective_reservations,
                      refresh_conditional_forecasts)


def _stage(snapshot, proposals):
    proposals = tuple(proposals)
    ids = [p.tray_id for p in proposals]
    if len(ids) != len(set(ids)):
        return ValidationResult(False, 'joint_duplicate_tray'), None
    if any(p.dependency_version != snapshot.version for p in proposals):
        return ValidationResult(False, 'stale_joint_version'), None
    if any(tray_id not in snapshot.trays for tray_id in ids):
        return ValidationResult(False, 'joint_unknown_tray'), None
    if any(tray_id in snapshot.plans for tray_id in ids):
        return ValidationResult(False, 'joint_accepted_itinerary_irrevocable'), None
    if any(p.prefix_only for p in proposals):
        return ValidationResult(False, 'joint_requires_full_witness'), None
    scratch = snapshot.clone()
    try:
        original_slots = tuple(s for s in effective_reservations(snapshot) if s.tray_id not in ids)
        proposed_slots = {p.tray_id: candidate_reservations(snapshot, p) for p in proposals}
        for proposal in proposals:
            scratch.plans[proposal.tray_id] = proposal
        scratch.reservations = _merge_reservations(original_slots + tuple(
            slot for proposal in proposals for slot in proposed_slots[proposal.tray_id]), snapshot.now)
        for proposal in proposals:
            # Validate one member with peers already provisionally reserved.
            # Its own full witness is supplied to the validator, not trusted.
            view = scratch.clone()
            del view.plans[proposal.tray_id]
            view.reservations = tuple(s for s in scratch.reservations if s.tray_id != proposal.tray_id)
            verdict = ExecutionValidator().validate(view, proposal, route_mode='whole_route')
            if not verdict.accepted:
                return ValidationResult(False, 'joint_member:' + verdict.reason), None
        if proposals:
            scratch.version += 1
        for proposal in proposals:
            _publish_forecast(scratch, proposal, proposal)
        refresh_conditional_forecasts(scratch)
        assert_invariants(scratch)
    except (KeyError, TypeError, AttributeError, AssertionError) as exc:
        return ValidationResult(False, f'joint_invalid_geometry_or_state:{type(exc).__name__}:{exc}'), None
    return ValidationResult(True, 'joint_accepted'), scratch


def validate_joint(snapshot, proposals):
    with _OWNER_LOCK:
        return _stage(snapshot, proposals)[0]


def commit_joint(snapshot, proposals):
    with _OWNER_LOCK:
        verdict, staged = _stage(snapshot, proposals)
        if verdict.accepted:
            # Publish once, after every member and the aggregate resource sweep
            # have passed. Physical positions and time remain exactly unchanged.
            snapshot.__dict__.update(staged.__dict__)
        return verdict


def commit_joint_actions(engine, proposals):
    """Admit one bundle at the engine's observation boundary and audit it."""
    proposals = tuple(proposals)
    observation = engine.observe()
    if engine.route_mode != 'whole_route':
        return ValidationResult(False, 'joint_whole_route_only')
    verdict = commit_joint(engine.state, proposals)
    if verdict.accepted and proposals:
        keys = [actual_action_key(observation, p, route_mode='whole_route') for p in proposals]
        engine.policy_stats['route_commits'] += len(proposals)
        engine.policy_stats['protected_commits'] += sum(
            p.bag_id is not None and engine.state.bags[p.bag_id].protected for p in proposals)
        engine._check('joint_commit', proposals=[asdict(p) for p in proposals], action_keys=keys)
    elif not verdict.accepted:
        engine.policy_stats['commit_rejections'] += 1
    return verdict
