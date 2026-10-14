"""Frozen checkpoint shadow queries; no continuation or deployment mutation."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json
import pickle
import sys
import time
import traceback

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
BASE=Path(__file__).resolve().parent
TICK=int(sys.argv[1]) if len(sys.argv)>1 else 10200
ORIGINAL=BASE.parent/f'phase4_round11_validation_20261011/projected_h21600_001/checkpoint_{TICK}.pickle'
index=1
while (BASE/f'diagnosis_{index:03d}').exists(): index+=1
OUT=BASE/f'diagnosis_{index:03d}'
OUT.mkdir()
cpu,wall=time.process_time(),time.perf_counter()
report=dict(status='running',physical_runs=0,physical_continuations=0,standalone_routing_queries=0,rows=[],
            scope=f'read frozen checkpoint{TICK}, restored private cache, per-tray independent shadow query K1/h21600/work10000; no commit/advance')
paths=sorted((ROOT/'scripts/experiments/ics_circulation_v3').glob('*.py'))+[Path(__file__)]
before={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
report['source_sha256_before']=before
for p in paths:
    target=OUT/'source_snapshot'/p.relative_to(ROOT)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(p.read_bytes())

def save():
    (OUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

try:
    from scripts.experiments.ics_circulation_v3.runtime import Simulation,effective_reservations,ExecutionValidator
    from scripts.experiments.ics_circulation_v3.routing_cache_contract import _unwrap
    from scripts.experiments.ics_circulation_v3.terminal_capacity_screen import terminal_capacity_certificate
    raw=ORIGINAL.read_bytes()
    (OUT/f'checkpoint_{TICK}.pickle').write_bytes(raw)
    report.update(checkpoint_original=str(ORIGINAL.relative_to(ROOT)),checkpoint_sha256=sha256(raw).hexdigest())
    checkpoint=pickle.loads(raw)
    engine=Simulation.from_checkpoint(checkpoint)
    state=engine.state
    planner=_unwrap(engine._generator)
    assert state.now==TICK and engine.route_selector is None
    assert engine.search_horizon==21600 and planner.horizon==21600 and planner.expansion_limit==10000
    assert planner.deadline_ms is None and planner.cache_contract=='isolated_replay_v1'
    report.update(now=state.now,phase=engine._phase,route_mode=engine.route_mode,declared_candidate_count=engine.candidate_count,
        actual_request_k=1,search_horizon=planner.horizon,expansion_limit=planner.expansion_limit,cache_contract=planner.cache_contract,
        observed_bags=len(state.bags),completed=len(state.completed),plans=len(state.plans),
        tray_rows=[dict(**asdict(t),has_plan=t.tray_id in state.plans) for t in state.trays.values()],
        cache_sha256=digest(planner._owned_topology_cache.export()))
    (OUT/'snapshot.json').write_text(json.dumps(asdict(state),indent=2))
    slots=effective_reservations(state)
    eligible=[t for t in state.trays.values() if t.mode=='loaded' and t.tray_id not in state.plans and t.node is not None
              and t.available_at<=state.now]
    report['eligible_loaded_no_plan_count']=len(eligible)
    for tray in eligible:
        branch=Simulation.from_checkpoint(checkpoint)
        prestate=asdict(branch.state)
        cache_before=_unwrap(branch._generator)._owned_topology_cache.export()
        bag=branch.state.bags[tray.bag_id]
        certificate=terminal_capacity_certificate(branch.state,tray.tray_id,bag.destination,branch.search_horizon)
        qcpu,qwall=time.process_time(),time.perf_counter()
        report['standalone_routing_queries']+=1
        found=branch._generate(branch.state.trays[tray.tray_id])
        row=dict(tray_id=tray.tray_id,bag=asdict(bag),query_cpu_seconds=time.process_time()-qcpu,
            query_wall_seconds=time.perf_counter()-qwall,status=branch._generator.last_search_status,
            expansions=branch._generator.last_expansions,diagnostics=deepcopy(branch._generator.last_diagnostics),
            candidates=[asdict(c) for c in found],terminal_certificate_shadow=certificate,
            final_node_other_slots=[asdict(s) for s in slots if s.resource=='node:'+bag.destination and s.tray_id!=tray.tray_id],
            storage_progress=asdict(state.storage_progress[bag.bag_id]) if bag.bag_id in state.storage_progress else None,
            cache_before_sha256=digest(cache_before),cache_after_sha256=digest(_unwrap(branch._generator)._owned_topology_cache.export()),
            public_state_unchanged=prestate==asdict(branch.state))
        assert row['cache_before_sha256']==report['cache_sha256'] and row['public_state_unchanged']
        report['rows'].append(row)
        save()
        print(json.dumps({key:row[key] for key in ('tray_id','status','expansions','query_cpu_seconds')}),flush=True)
        if row['status']=='expansion_budget_exhausted':
            # Separate marked instrumented query, restored again from original
            # cache. It is not part of the uninstrumented time above.
            branch=Simulation.from_checkpoint(checkpoint)
            verdicts=[]
            original_validate=ExecutionValidator.validate
            def recording_validate(self,snapshot,candidate,*args,**kwargs):
                result=original_validate(self,snapshot,candidate,*args,**kwargs)
                verdicts.append(dict(reason=result.reason,accepted=result.accepted,
                    unload_complete=candidate.unload_complete,leg_count=len(candidate.legs),
                    final_arrival=candidate.legs[-1].arrive if candidate.legs else snapshot.now))
                return result
            qcpu,qwall=time.process_time(),time.perf_counter()
            ExecutionValidator.validate=recording_validate
            try:
                report['standalone_routing_queries']+=1
                again=branch._generate(branch.state.trays[tray.tray_id])
            finally:
                ExecutionValidator.validate=original_validate
            row['instrumented_replay']=dict(query_cpu_seconds=time.process_time()-qcpu,
                query_wall_seconds=time.perf_counter()-qwall,verdicts=verdicts,
                reasons=dict(Counter(v['reason'] for v in verdicts)),status=branch._generator.last_search_status,
                expansions=branch._generator.last_expansions,
                candidates_equal=[asdict(c) for c in again]==row['candidates'],
                note='instrumentation overhead included; separate shadow query, not deployed runtime')
            assert row['instrumented_replay']['candidates_equal']
            assert row['instrumented_replay']['status']==row['status']
            assert row['instrumented_replay']['expansions']==row['expansions']
            save()
    report['source_sha256_after']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before==report['source_sha256_after']
    assert ORIGINAL.read_bytes()==raw
    report['status']='passed'
except BaseException:
    report.update(status='failed',failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
        timing_note='Main receipt includes imports/read/SHA/source copies/restore/query/certificate/validation/serialization; query CPU nested, do not sum again.',
        unmetered_auxiliary=['prior source reads','script editing','tool orchestration'])
    save()
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256_before','source_sha256_after','rows','tray_rows')},indent=2),flush=True)
raise SystemExit(0 if report['status']=='passed' else 1)
