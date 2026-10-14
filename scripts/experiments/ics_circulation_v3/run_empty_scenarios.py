"""Point vs eight public synthetic scenarios, all three fixed seeds reported."""
import argparse
import ast
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

from .empty_factorial import SETTINGS, build_empty_factorial_engine
from .empty_scenarios import FACTORS, PublicScenarioSettings, build_scenario_empty_engine
from .experiment_protocol import create_output_directory, write_new_json as save
from .experiment_resources import memory_snapshot
from .label_stability import sustained_scenes
from .network_full_cycle import cycle_state, forecast_expiry
from .phase4_control import ControlSpec
from .run_empty_improvement import endpoint
from .run_public_rollout import deployment_tapes

CODE = Path(__file__).parent
POLICIES = ('point', 'scenario8_s17', 'scenario8_s29', 'scenario8_s43')
SPEC = ControlSpec(routing='timed', planning_horizon=20, slow_period=2)


def source_hashes():
    found, queue = set(), [Path(__file__).name, '__init__.py']
    while queue:
        name = queue.pop()
        if name in found:
            continue
        found.add(name)
        for node in ast.walk(ast.parse((CODE / name).read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                modules = [node.module.split('.')[0]] if node.module else [a.name for a in node.names]
                queue.extend(m + '.py' for m in modules if (CODE / (m + '.py')).is_file() and m + '.py' not in found)
    return {n: sha256((CODE / n).read_bytes()).hexdigest() for n in sorted(found)}


def deploy(scene, policy):
    started, cpu = perf_counter(), process_time()
    if policy == 'point':
        engine = build_empty_factorial_engine(scene, FACTORS, spec=SPEC, settings=SETTINGS)
    else:
        seed = int(policy.split('_s')[1])
        engine = build_scenario_empty_engine(scene, spec=SPEC, settings=SETTINGS,
            scenarios=PublicScenarioSettings(8, seed))
    bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    assert len(bags) == len(scene.initial.bags) + len(scene.future_bags)
    expiry, h80 = forecast_expiry(engine), scene.initial.now + 80
    cap = max(expiry, h80, max((b.arrival for b in bags.values()), default=scene.initial.now)) + 240
    quiet_since = quiet_triggers = None
    endpoints = {}
    status = 'tick_cap_censored'
    while engine.state.now < cap:
        engine.advance(engine.state.now + 1)
        state, now = cycle_state(engine, bags, expiry), engine.state.now
        if now == h80:
            endpoints['h80'] = endpoint(engine, bags, expiry)
        if not (state['transport_drained'] and state['forecast_expired']):
            quiet_since = quiet_triggers = None
        elif quiet_since is None:
            quiet_since, quiet_triggers = now, len(engine.slow_controller.trigger_times)
        elif (now >= h80 and now - quiet_since >= SPEC.slow_period
              and len(engine.slow_controller.trigger_times) > quiet_triggers):
            status = 'controller_quiescent'
            break
    endpoints['final'] = endpoint(engine, bags, expiry)
    history = engine.slow_controller.history
    scores = [r for h in history for r in h['diagnostics']['scored_actions']]
    physical = [p for r in scores for p in r.get('physical_scenarios', [r])]
    metrics = {'status': status, 'h80': endpoints['h80']['metrics'], 'final': endpoints['final']['metrics'],
        'action_evaluations': len(scores), 'requested_scenarios': sum(r.get('requested_scenarios', 1) for r in scores),
        'physical_proxy_calls': len(physical), 'duplicate_reuses': sum(r.get('exact_duplicate_reuses', 0) for r in scores),
        'proxy_statuses': dict(Counter(r['status'] for r in physical)),
        'internal_query_calls': sum(h['diagnostics']['greedy_diagnostics']['search_calls']
            + h['diagnostics']['proposal_search_calls'] for h in history) + sum(r['search_calls'] for r in physical),
        'internal_query_work': sum(h['diagnostics']['greedy_diagnostics']['search_expansions']
            + h['diagnostics']['proposal_search_work'] for h in history) + sum(r['search_work'] for r in physical),
        'fallbacks': sum(h['diagnostics']['fallback_to_greedy'] for h in history),
        'process_cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - started,
        'stopped_at': engine.state.now, 'memory': memory_snapshot()}
    return {'metrics': metrics, 'endpoints': endpoints, 'slow_history': history,
        'route_history': engine.route_selector.history, 'control_contract': engine.control_contract,
        'quiet_since': quiet_since, 'quiet_start_slow_trigger_count': quiet_triggers,
        'final_slow_trigger_count': len(engine.slow_controller.trigger_times), 'cap_at': cap}


def worker(output, si, ti, policy, expected):
    start, cpu = perf_counter(), process_time()
    assert source_hashes() == expected, 'source drift before case'
    original = sustained_scenes()[si]
    tape_name, tape = deployment_tapes(original)[ti]
    scene = replace(original, future_bags=tape)
    identity = f's{si}_t{ti}_{policy}'
    try:
        record = deploy(scene, policy)
    except Exception as exc:
        record = {'metrics': {'status': 'execution_failure', 'scheduled': len(scene.initial.bags) + len(tape)},
                  'failure': {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}}
    record.update(identity=identity, scene=scene.name, tape=tape_name, policy=policy,
                  source_changed=source_hashes() != expected)
    path = Path(output) / 'cases' / (identity + '.json.gz')
    with gzip.open(path, 'xt', encoding='utf-8') as f:
        json.dump(record, f, allow_nan=False, separators=(',', ':'))
    return {k: record[k] for k in ('identity','scene','tape','policy','source_changed')} | record['metrics'] | {
        'file': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
        'invocation_cpu_seconds': process_time() - cpu, 'invocation_wall_seconds': perf_counter() - start}


def run(output, workers=6, pilot=False):
    start, cpu = perf_counter(), process_time()
    output = create_output_directory(output).resolve()
    hashes = source_hashes()
    (output / 'source_snapshot').mkdir()
    (output / 'cases').mkdir()
    for n in hashes:
        (output / 'source_snapshot' / n).write_bytes((CODE / n).read_bytes())
    units = [(s,t) for s in range(4) for t in range(9) if not pilot or t == 0]
    save(output / 'protocol.json', {'schema': 'public_scenario_empty_development_v1', 'pilot': pilot,
        'policies': POLICIES, 'units': units, 'planned_episodes': len(units)*4,
        'source_sha256': hashes, 'spec': asdict(SPEC), 'action_settings': asdict(SETTINGS), 'factors': asdict(FACTORS),
        'prior': 'existing synthetic stress family: cancel/reverse1/8 each, jitter{-2,0,2}; uncalibrated additional model assumption',
        'sampling': '8 common draws seeded by public time+point proxy+fixed seed17/29/43; all three report, no best seed',
        'scenario_memo': 'exact same synthetic tape within same state+action only; multiplicity retained, no action budget unlocked',
        'budget': 'max12 action evaluations x up to8 unique scenarios; branch256queries/300000work between queries; perquery2000',
        'online_information': 'Snapshot, already published forecasts and declared prior only; no actual arrivals or later publications',
        'stopping': 'h80 then original whole-tape/controller quiescence, tail240; cap unresolved not infeasible',
        'scope': '36 reused small synthetic tapes; not original-map OD reversal, operational uncertainty calibration or independent confirmation',
        'reference': 'https://arxiv.org/html/1804.11074', 'workers': workers})
    inputs = []
    for si, ti in units:
        scene = sustained_scenes()[si]
        name, tape = deployment_tapes(scene)[ti]
        inputs.append({'si':si,'ti':ti,'scene':scene.name,'tape':name,'initial':asdict(scene.initial),
            'forecasts':[asdict(f) for f in scene.forecasts],'actual_tasks_event_engine_only':[asdict(b) for b in tape]})
    save(output / 'inputs.json', inputs)
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(worker,str(output),si,ti,p,hashes):(si,ti,p) for si,ti in units for p in POLICIES}
        for job in as_completed(jobs):
            try:
                row = job.result()
            except Exception as exc:
                si,ti,p = jobs[job]
                row = {'identity':f's{si}_t{ti}_{p}','policy':p,'si':si,'ti':ti,'status':'worker_failure',
                    'failure':{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()},
                    'invocation_cpu_seconds':None,'invocation_wall_seconds':None,'source_changed':source_hashes()!=hashes}
                save(output / 'cases' / (row['identity']+'.failure.json'),row)
            rows.append(row)
            print(json.dumps({k:row[k] for k in ('identity','status','invocation_cpu_seconds')}),flush=True)
    summary = {'rows':sorted(rows,key=lambda r:r['identity']), 'planned_episodes':len(units)*4,
        'statuses':dict(Counter(r['status'] for r in rows)),
        'case_cpu_seconds_recorded':sum(r['invocation_cpu_seconds'] or 0 for r in rows),
        'cases_unknown_resources':sum(r['invocation_cpu_seconds'] is None for r in rows),
        'parent_cpu_seconds':process_time()-cpu, 'wall_seconds':perf_counter()-start,
        'source_changed':source_hashes()!=hashes or any(r['source_changed'] for r in rows)}
    save(output/'summary.json',summary)
    save(output/'manifest.json',{p.relative_to(output).as_posix():sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--pilot',action='store_true')
    args=parser.parse_args()
    result=run(args.output,args.workers,args.pilot)
    raise SystemExit(int(result['source_changed'] or any(k in result['statuses'] for k in ('execution_failure','worker_failure'))))
