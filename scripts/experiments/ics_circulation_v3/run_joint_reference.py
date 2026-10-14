"""Fresh tiny exact and sustained rolling-MPC diagnostics; no training/tuning."""
from dataclasses import asdict, dataclass
import argparse
import hashlib
import json
from pathlib import Path

from .joint_reference import JointDomain, JointMPC, solve_joint, reactive_reference
from .learning import RoutingDemandForecast
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .runtime import Simulation


@dataclass(frozen=True)
class JointFixture:
    name: str
    initial: Snapshot
    forecasts: tuple
    future: tuple
    horizon: int


def fixture(name="positive", *, travel=1, horizon=3, repeats=1, unload=0, hold=0):
    nodes = {n: Node(n, n, n, capacity=4) for n in ("A", "B")}
    edges = {name: Edge(name, start, end, travel) for name, start, end in (("AB", "A", "B"), ("BA", "B", "A"))}
    trays = {"tray": Tray("tray", "A")}
    if name == "zero":
        trays["ready"] = Tray("ready", "B")
    initial = Snapshot(0, Network(nodes, edges), trays, {},
                       module=FixedLocalModule(unload_ticks=unload, hold_by_node={"A": hold, "B": hold}))
    spacing = 2 * travel + unload + hold + 2
    forecasts, future = [], []
    for i in range(repeats):
        at = travel + spacing * i
        identity = f"forecast:{i}:0"
        forecasts.append(RoutingDemandForecast(f"forecast:{i}", "B", "A", at, at + travel + unload + 2))
        if name != "false_forecast":
            future.append(Bag(identity, "B", "A", at, at + travel + unload + 2))
    return JointFixture(name, initial, tuple(forecasts), tuple(future), horizon)


def rolling_episode(case, *, planning_horizon=8, work_budget=5000):
    engine = Simulation(case.initial, case.future, control_mode="external", route_mode="whole_route")
    controller = JointMPC(planning_horizon=planning_horizon, expansion_limit=work_budget)
    decisions = []
    while engine.state.now < case.horizon:
        observation = engine.observe()
        published = tuple(f for f in case.forecasts if f.published_at <= observation.now)
        decision = controller.plan(observation, published)
        commits = []
        for candidate in decision.first_actions:
            accepted = engine.intervene(candidate)
            commits.append({"candidate": asdict(candidate), "accepted": accepted.accepted, "reason": accepted.reason})
            if not accepted.accepted:
                break
        decisions.append({"time": observation.now, "search": asdict(decision), "commits": commits,
                          "information": controller.history[-1]})
        engine.advance(observation.now + 1)
    result = engine.result()
    return {"cost": result.total_cost, "components": result.cost_components, "completed": result.completed,
            "uncompleted": result.uncompleted_bag_ids, "decisions": decisions,
            "commit_rejections": sum(not c["accepted"] for d in decisions for c in d["commits"]),
            "complete_proxy_solves": sum(d["search"]["complete"] for d in decisions),
            "budget_incomplete_solves": sum(not d["search"]["complete"] for d in decisions),
            "information": "published forecast proxy only, real tape held solely by evaluation event engine",
            "actual_world_optimality_claim": False}


def run(output, *, long_only=False, work_budget=5000):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Refuse to overwrite prior evidence")
    output.mkdir(parents=True, exist_ok=True)
    names = ("joint_reference.py", "run_joint_reference.py", "runtime.py", "model.py", "routing.py",
             "learning.py", "evaluation.py")
    source = {name: (Path(__file__).parent / name).read_bytes() for name in names}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in source.items()}
    rows = []
    if not long_only:
        for name in ("positive", "zero", "false_forecast"):
            case = fixture(name)
            domain = JointDomain(case.horizon, expansion_limit=100000)
            truth = solve_joint(case.initial, case.future, domain=domain)
            reactive, _ = reactive_reference(case.initial, case.future, domain=domain)
            rolling = rolling_episode(case, planning_horizon=3, work_budget=work_budget)
            rows.append({"name": "tiny_" + name, "initial": asdict(case.initial),
                         "forecasts": [asdict(f) for f in case.forecasts], "future": [asdict(b) for b in case.future],
                         "horizon": case.horizon, "offline_truth_oracle": asdict(truth),
                         "reactive_cost": reactive.total_cost, "rolling": rolling,
                         "rolling_minus_reactive": rolling["cost"] - reactive.total_cost})
        limited = fixture("positive")
        result = solve_joint(limited.initial, limited.future, domain=JointDomain(3, expansion_limit=20))
        rows.append({"name": "explicit_budget_failure", "result": asdict(result)})
    for name in ("positive", "zero", "false_forecast"):
        case = fixture(name, travel=3, horizon=32, repeats=3, unload=1, hold=1)
        reactive, _ = reactive_reference(case.initial, case.future,
                                         domain=JointDomain(case.horizon, route_tail_ticks=3, expansion_limit=100000))
        rolling = rolling_episode(case, planning_horizon=8, work_budget=work_budget)
        rows.append({"name": "sustained_" + name, "initial": asdict(case.initial),
                     "forecasts": [asdict(f) for f in case.forecasts], "future": [asdict(b) for b in case.future],
                     "horizon": case.horizon, "reactive_cost": reactive.total_cost, "rolling": rolling,
                     "rolling_minus_reactive": rolling["cost"] - reactive.total_cost})
    summary = {"schema": "ics_v3_joint_reference_v1", "source_sha256": hashes,
               "source_changed_during_run": any((Path(__file__).parent / name).read_bytes() != value for name, value in source.items()),
               "work_budget_per_rolling_solve": work_budget,
               "domain_limits": ["Tiny exact certificates only for the declared whole_route integer walk/time domain.",
                                 "Offline truth oracle and published-forecast MPC have different information and are labelled separately.",
                                 "Physical source export floor/FIFO loading shared; no greedy first-supply candidate restriction.",
                                 "Protected deadlines enforced on admitted routes; unadmitted backlog remains explicit.",
                                 "Sustained rolling results are realized proxy episodes; budget exhaustion has no optimum/gap claim.",
                                 "No wall-clock real-time or industrial feasibility claim."],
               "results": [{"name": r["name"], "reactive_cost": r.get("reactive_cost"),
                            "rolling_cost": r.get("rolling", {}).get("cost"),
                            "rolling_minus_reactive": r.get("rolling_minus_reactive"),
                            "complete_proxy_solves": r.get("rolling", {}).get("complete_proxy_solves"),
                            "budget_incomplete_solves": r.get("rolling", {}).get("budget_incomplete_solves"),
                            "oracle_status": r.get("offline_truth_oracle", r.get("result", {})).get("status")}
                           for r in rows]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "episodes.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    archive = output / "source_snapshot"
    archive.mkdir()
    for name, value in source.items():
        (archive / name).write_bytes(value)
    if summary["source_changed_during_run"]:
        raise RuntimeError("Source changed during diagnostics; records retained")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--long-only", action="store_true")
    parser.add_argument("--work-budget", type=int, default=5000)
    args = parser.parse_args()
    run(args.output, long_only=args.long_only, work_budget=args.work_budget)
