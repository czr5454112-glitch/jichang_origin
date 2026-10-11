"""Reachable-decision opportunity and paired common-future diagnostics.

Checkpoints are used only by the offline evaluator. Every continuation restores
the actual controller and slow-clock phase from the collected episode. Neither
the feature extractor nor a controller receives a sampled future tape.
"""
from collections import defaultdict
from dataclasses import asdict, replace
from hashlib import sha256
import json
import random

import numpy as np

from .feedback_scenarios import feedback_scene
from .learning import RoutingDemandForecast, TimedAnalyticEvaluator
from .model import Bag
from .phase4_control import ControlSpec, GeneratorFactory, build_engine
from .runtime import ExecutionValidator, Simulation, actual_action_key


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sustained_scenes():
    """Four declared development streams, three rounds and two finite trays."""
    scenes = []
    for length, extra, slack in ((2, 1, 3), (2, 3, 0), (4, 1, 3), (4, 3, 0)):
        scene = feedback_scene(shared_travel=length, detour_extra=extra)
        initial = scene.initial.clone()
        initial.bags['initial'] = replace(initial.bags['initial'], deadline=length + 3 + slack)
        forecasts, truth = list(scene.forecasts), list(scene.future_bags)
        for round_index, start in enumerate((20, 40), 1):
            for kind, origin, destination, at, margin in (
                    ('loaded', 'S', 'G', start, length + 3 + slack),
                    ('need', 'B', 'C', start + length + 2, 20)):
                identity = f'round{round_index}:{kind}'
                forecasts.append(RoutingDemandForecast(identity, origin, destination, at, at + margin,
                                                        published_at=start - 6, unit_ids=(identity,)))
                truth.append(Bag(identity, origin, destination, at, at + margin))
        scenes.append(replace(scene, name=f'stream_L{length}_D{extra}_slack{slack}', initial=initial,
                              forecasts=tuple(forecasts), future_bags=tuple(truth), horizon=72,
                              factors={**scene.factors, 'rounds': 3, 'loaded_deadline_slack': slack,
                                       'source_role': 'constructed_development_not_confirmation'}))
    return tuple(scenes)


def candidate_pool(snapshot, tray, spec, *, expanded_count=12):
    normal_generator = GeneratorFactory(spec)()
    normal = normal_generator.generate(snapshot, tray.bag_id, tray.tray_id, k=spec.candidate_count)
    expanded_generator = GeneratorFactory(replace(spec, candidate_count=expanded_count))()
    expanded = expanded_generator.generate(snapshot, tray.bag_id, tray.tray_id, k=expanded_count)
    validator = ExecutionValidator()
    pool, normal_keys, seen = [], [], set()
    for group, candidates in (('normal', normal), ('expanded', expanded)):
        for candidate in candidates:
            if not validator.validate(snapshot, candidate, route_mode=spec.route_mode).accepted:
                continue
            key = actual_action_key(snapshot, candidate, route_mode=spec.route_mode)
            if group == 'normal':
                normal_keys.append(key)
            if key not in seen:
                seen.add(key)
                pool.append(candidate)
    return tuple(pool), tuple(dict.fromkeys(normal_keys)), {
        'normal_raw_count': len(normal), 'expanded_raw_count': len(expanded),
        'normal_search_status': normal_generator.last_search_status,
        'expanded_search_status': expanded_generator.last_search_status,
        'normal_work': normal_generator.last_expansions, 'expanded_work': expanded_generator.last_expansions,
        'coverage_scope': 'bounded_larger_candidate_pool_not_exhaustive_physical_oracle'}


def collect_decisions(scene, spec, *, bands=(0, 20, 40), expanded_count=12):
    """First eligible soft decision in each time band, selected before labels.

    All routing boundaries and their first pending loaded decision remain in
    the denominator, including no-candidate and single-intervention states.
    Sampling never uses a cost, label, future outcome or a successful finish.
    """
    if spec.coordination_order != 'route_then_prebalance':
        raise ValueError('collector requires the declared route-first continuation')
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    sampled, history, used_bands = [], [], set()
    while engine.state.now < scene.horizon:
        state = engine.observe()
        eligible = sorted((t for t in state.trays.values() if t.mode == 'loaded'
                           and t.tray_id not in state.plans and t.node is not None and t.available_at <= state.now),
                          key=lambda t: (not state.bags[t.bag_id].protected, t.tray_id))
        band = max((b for b in bands if b <= state.now), default=None)
        record = {'time': state.now, 'version': state.version, 'band': band,
                  'state_sha256': digest(asdict(state)), 'eligible_loaded_count': len(eligible),
                  'completed_count': len(state.completed), 'visible_bag_count': len(state.bags),
                  'in_transit_count': sum(t.mode == 'in_transit' for t in state.trays.values()),
                  'waiting_count': sum(b not in state.load_times and b not in state.completed for b in state.bags),
                  'sampled': False}
        if eligible:
            tray = eligible[0]
            pool, normal_keys, generation = candidate_pool(state, tray, spec, expanded_count=expanded_count)
            record.update(first_tray_id=tray.tray_id, first_bag_id=tray.bag_id,
                          protected=state.bags[tray.bag_id].protected,
                          distinct_interventions=len(pool), normal_interventions=len(normal_keys), **generation)
            if pool and band is not None and band not in used_bands and not record['protected']:
                # Prepared before any decision at this tick: phase, accumulated
                # costs, earlier accepted plans and exact slow phase are kept.
                checkpoint = engine.checkpoint()
                visible = tuple(f for f in scene.forecasts if f.published_at <= state.now)
                evaluator = TimedAnalyticEvaluator(state.now + spec.planning_horizon, visible)
                sampled.append({'identity': f'{scene.name}:{spec.routing}:t{state.now}:{tray.bag_id}',
                                'checkpoint': checkpoint, 'pool': pool, 'normal_keys': normal_keys,
                                'features': [evaluator.features(state, p) for p in pool],
                                'generation': generation, 'band': band,
                                'continuation_contract': engine.control_contract})
                used_bands.add(band)
                record['sampled'] = True
        history.append(record)
        engine.advance(state.now + 1)
    return sampled, history, engine.result()


def sampled_futures(nominal, state, *, count=32, seed=0):
    """Declared synthetic uncertainty, not an estimated airport posterior.

    Independent per pending task: cancel with 1/8 probability; reverse OD with
    1/8; otherwise keep OD. Jitter {-2,0,2} is uniform and clipped after now.
    The original task IDs persist. Existing observations are never changed.
    """
    if type(count) is not int or count < 1:
        raise ValueError('positive future count required')
    pending = sorted((b for b in nominal if b.bag_id not in state.bags and b.arrival > state.now),
                     key=lambda b: b.bag_id)
    rng, futures = random.Random(seed), []
    for _ in range(count):
        bags = []
        for bag in pending:
            event = rng.randrange(8)
            jitter = rng.choice((-2, 0, 2))
            if event == 0 and not bag.protected:
                continue
            arrival = max(state.now + 1, bag.arrival + jitter)
            reverse = event == 1 and not bag.protected
            bags.append(replace(bag, origin=bag.destination if reverse else bag.origin,
                                destination=bag.origin if reverse else bag.destination,
                                arrival=arrival, deadline=bag.deadline + arrival - bag.arrival))
        futures.append(tuple(sorted(bags, key=lambda b: (b.arrival, b.bag_id))))
    return tuple(futures)


def branch_with_future(checkpoint, candidate, future, horizon):
    """Offline tape replacement preserves the runtime's controller checkpoint."""
    if horizon <= checkpoint.state.now or checkpoint.phase != 'routes':
        raise ValueError('labels require a prepared decision and a later horizon')
    identifiers = [b.bag_id for b in future]
    if len(set(identifiers)) != len(identifiers) or any(
            b.arrival <= checkpoint.state.now or b.bag_id in checkpoint.state.bags for b in future):
        raise ValueError('future tape must contain unique unobserved later tasks')
    if checkpoint.observer is not None:
        raise ValueError('offline labels require a side-effect-free observer contract')
    restored = checkpoint.clone()
    restored.pending_arrivals = defaultdict(list)
    for bag in future:
        restored.pending_arrivals[bag.arrival].append(bag)
    engine = Simulation.from_checkpoint(restored)
    verdict = engine.intervene(candidate)
    if not verdict.accepted:
        raise ValueError('label intervention rejected:' + verdict.reason)
    return engine.advance(horizon)


def stability_summary(costs, normal_indices, analytic_scores, *, sizes=(2, 8, 32)):
    """costs[replicate, candidate, future], paired within every future column."""
    values = np.asarray(costs, dtype=float)
    if values.ndim != 3 or values.shape[0] < 2 or not np.isfinite(values).all():
        raise ValueError('need finite paired costs from at least two replicate groups')
    if max(sizes) > values.shape[2] or not normal_indices:
        raise ValueError('insufficient future count or empty normal candidate set')
    normal_indices = tuple(normal_indices)
    analytic_choice = min(normal_indices, key=lambda i: (analytic_scores[i], i))
    full = values.mean(axis=(0, 2))
    best = int(np.argmin(full))
    normal_best = min(normal_indices, key=lambda i: (full[i], i))
    rows = []
    for replicate in range(len(values)):
        heldout_means = np.delete(values, replicate, axis=0).mean(axis=(0, 2))
        reference = values[replicate, 0]
        for size in sizes:
            prefix = values[replicate, :, :size]
            means = prefix.mean(axis=1)
            chosen = int(np.argmin(means))
            delta = prefix - reference[:size]
            stderr = delta.std(axis=1, ddof=1) / np.sqrt(size)
            rows.append({'replicate': replicate, 'future_count': size,
                         'winner': chosen, 'cost_means': means.tolist(),
                         'paired_delta_to_baseline': delta.mean(axis=1).tolist(),
                         'paired_delta_standard_errors': stderr.tolist(),
                         'other_replicates_regret': float(heldout_means[chosen] - min(heldout_means)),
                         'same_block_32_winner': int(np.argmin(values[replicate].mean(axis=1))),
                         'same_block_32_optimal_tie': bool(abs(values[replicate].mean(axis=1)[chosen]
                                                            - min(values[replicate].mean(axis=1))) <= 1e-9)})
    return {'all_replicates_cost_means': full.tolist(), 'best_index': best,
            'value_range': float(max(full) - min(full)),
            'bounded_pool_coverage_loss': float(full[normal_best] - full[best]),
            'timed_choice_index': analytic_choice,
            'timed_selection_loss_within_normal_pool': float(full[analytic_choice] - full[normal_best]),
            'paired_variance_scope': 'descriptive Monte Carlo error within a declared synthetic future law; not independent airport days',
            'selection_reference': 'other replicate groups exclude the choosing group; prefix 2/8/32 are nested',
            'rows': rows}
