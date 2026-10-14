"""Causal, candidate-matched public-forecast rollout comparator.

This selector receives an observation and a public control cursor, never an
engine checkpoint or its private arrival tape. Each candidate pays for a full
timed-policy continuation with the same slow clock. Published point forecasts
are an explicit proxy distribution, not actual future observations.
"""
from dataclasses import asdict, replace
from time import perf_counter, process_time

from .joint_feedback import published_proxy
from .label_stability import digest
from .phase4_control import ControlSpec
from .runtime import actual_action_key


class PublicRolloutSelector:
    def __init__(self, forecasts=(), *, spec=None):
        self.spec = spec or ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
        if self.spec.routing != "timed":
            raise ValueError("public rollout continuation must be explicitly timed")
        self.forecasts = tuple(forecasts)
        self.context = None
        self.history = []

    def set_decision_context(self, context):
        # Context contains a public cursor and slow-clock phase, not callbacks,
        # pending arrivals, or an execution-engine reference.
        self.context = context

    def __call__(self, state, candidates):
        from .role_coverage import CursorSimulation

        if not candidates or self.context is None:
            raise ValueError("public rollout requires candidates and a current decision context")
        context, self.context = self.context, None
        if tuple(context.cursor.pending_options or ()) != tuple(candidates):
            raise ValueError("decision context does not match the supplied candidates")
        visible = tuple(f for f in self.forecasts if f.published_at <= state.now)
        horizon = state.now + self.spec.planning_horizon
        proxy = published_proxy(state, visible, horizon)
        keys = [actual_action_key(state, c, route_mode=self.spec.route_mode) for c in candidates]
        rows = []
        wall, cpu = perf_counter(), process_time()
        # No outcome-dependent pruning: all supplied K candidates receive the
        # same continuation and forecast tape, including equal physical paths
        # with different retained conditional release witnesses.
        for index, candidate in enumerate(candidates):
            branch = CursorSimulation.from_visible(state, context, proxy, self.spec, visible)
            branch.choose_pending(candidate)
            result = branch.advance(horizon)
            rows.append({"index": index, "actual_action_key": keys[index],
                         "cost": result.total_cost, "cost_components": result.cost_components,
                         "completed": len(result.completed),
                         "unfinished_ids": list(result.uncompleted_bag_ids),
                         "slow_trigger_times": branch.slow_controller.trigger_times if branch.slow_controller else [],
                         "policy_stats": result.policy_stats})
        chosen = min(range(len(rows)), key=lambda i: (rows[i]["cost"], i))
        self.history.append({"time": state.now, "node": state.trays[candidates[0].tray_id].node,
                             "state_sha256": digest(asdict(state)),
                             "published_forecasts": [asdict(f) for f in visible],
                             "proxy_bags": [asdict(b) for b in proxy],
                             "horizon": horizon, "cursor": asdict(context.cursor),
                             "next_slow_trigger_at": context.next_slow_trigger_at,
                             "actual_action_keys": keys, "candidate_count": len(candidates),
                             "rollouts": rows, "chosen_index": chosen,
                             "wall_seconds": perf_counter() - wall,
                             "process_cpu_seconds": process_time() - cpu,
                             "interpretation": "extra_budget_public_point_forecast_timed_continuation"})
        return candidates[chosen]


def build_public_rollout_engine(scene, spec=None):
    """The actual task tape goes only to the event engine, never its selector."""
    from .phase4_control import build_engine
    from .role_coverage import CursorSimulation

    continuation = spec or ControlSpec(routing="timed", planning_horizon=20, slow_period=2)
    selector = PublicRolloutSelector(scene.forecasts, spec=continuation)
    engine = build_engine(scene.initial, scene.forecasts, scene.future_bags,
                          replace(continuation, routing="external"), route_selector=selector,
                          selector_manifest={"implementation": "PublicRolloutSelector",
                                             "continuation": asdict(continuation),
                                             "forecast_proxy": "currently_published_point_estimates_only"})
    return CursorSimulation.from_base_checkpoint(engine.checkpoint(), contract=engine.control_contract)
