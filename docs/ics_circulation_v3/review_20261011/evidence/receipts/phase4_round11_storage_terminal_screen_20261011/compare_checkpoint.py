"""Screen the two sealed10800 failure queries, retaining prior raw baseline."""
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
OLD=BASE.parent/'phase4_round11_projection_query_diagnosis_20261011/diagnosis_002'
index=1
while (BASE/f'comparison_{index:03d}').exists(): index+=1
OUT=BASE/f'comparison_{index:03d}'
OUT.mkdir()
cpu,wall=time.process_time(),time.perf_counter()
report=dict(status='running',physical_runs=0,standalone_routing_queries=0,rows=[])
paths=sorted((ROOT/'scripts/experiments/ics_circulation_v3').glob('*.py'))+[Path(__file__)]
before={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
report['source_sha256_before']=before
for p in paths:
    target=OUT/'source_snapshot'/p.relative_to(ROOT)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(p.read_bytes())
try:
    from scripts.experiments.ics_circulation_v3.runtime import Simulation
    from scripts.experiments.ics_circulation_v3.routing_cache_contract import _unwrap
    from scripts.experiments.ics_circulation_v3.storage_terminal_screen import install_storage_terminal_screen
    old_raw=(OLD/'result.json').read_bytes()
    raw=(OLD/'checkpoint_10800.pickle').read_bytes()
    (OUT/'old_result.json').write_bytes(old_raw)
    (OUT/'checkpoint_10800.pickle').write_bytes(raw)
    old=json.loads(old_raw)
    report['baseline_result_sha256']=sha256(old_raw).hexdigest()
    report['checkpoint_sha256']=sha256(raw).hexdigest()
    assert report['checkpoint_sha256']==old['checkpoint_sha256']
    for name,digest in old['source_sha256_before'].items():
        if name.startswith('scripts/experiments/ics_circulation_v3/'):
            assert before[name]==digest,('changed baseline source',name)
    checkpoint=pickle.loads(raw)
    for prior in old['rows']:
        engine=Simulation.from_checkpoint(checkpoint)
        assert engine.route_selector is None and engine.search_horizon==21600
        cache_before=deepcopy(_unwrap(engine._generator)._owned_topology_cache.export())
        state_before=asdict(engine.state)
        accounting=install_storage_terminal_screen(engine)
        assert _unwrap(engine._generator).expansion_limit==10000
        qcpu,qwall=time.process_time(),time.perf_counter()
        report['standalone_routing_queries']+=1
        found=engine._generate(engine.state.trays[prior['tray_id']])
        row=dict(tray_id=prior['tray_id'],bag_id=prior['bag']['bag_id'],query_cpu_seconds=time.process_time()-qcpu,
            query_wall_seconds=time.perf_counter()-qwall,candidates=[asdict(c) for c in found],
            status=engine._generator.last_search_status,expansions=engine._generator.last_expansions,
            diagnostics=engine._generator.last_diagnostics,accounting=asdict(accounting),
            baseline_query_cpu_seconds=prior['query_cpu_seconds'],baseline_expansions=prior['expansions'],
            candidate_result_equal=[asdict(c) for c in found]==prior['candidates'],
            private_cache_unchanged=cache_before==_unwrap(engine._generator)._owned_topology_cache.export(),
            public_state_unchanged=state_before==asdict(engine.state),
            declared_search_budget=10000,requested_k=1,search_horizon=21600,
            qualification='same search budget plus measured screen work, not same total logical work budget')
        assert row['candidate_result_equal'] and row['private_cache_unchanged'] and row['public_state_unchanged']
        assert row['status']=='terminal_capacity_certificate'
        report['rows'].append(row)
    report['source_sha256_after']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before==report['source_sha256_after']
    report['status']='passed'
except BaseException:
    report.update(status='failed',failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
        scope='source snapshot/read/SHA/imports/restore/two screen queries/state/cache checks/serialization; query and screen CPU nested, not additive',
        physical_scope='No simulation advance or deployment; old unscreened failures reused from sealed diagnosis_002')
    (OUT/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256_before','source_sha256_after','rows')},indent=2))
    print(json.dumps([{k:r[k] for k in ('bag_id','status','expansions','query_cpu_seconds','baseline_query_cpu_seconds')} for r in report['rows']],indent=2))
raise SystemExit(0 if report['status']=='passed' else 1)
