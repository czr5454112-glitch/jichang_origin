"""Re-run the three sealed query inputs; no simulation continuation."""
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
index=1
while (BASE/f"comparison_{index:03d}").exists():
    index+=1
OUT=BASE/f"comparison_{index:03d}"
OUT.mkdir()
paths=sorted((ROOT/'scripts/experiments/ics_circulation_v3').glob('*.py'))
before={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:
    target=OUT/'source_snapshot'/p.relative_to(ROOT)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(p.read_bytes())
cpu,wall=time.process_time(),time.perf_counter()
report=dict(status='running',physical_continuations=0,standalone_queries=0,rows=[],source_sha256_before=before)
try:
    from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator
    for name in ('free_storage','busy_storage','real_id3_8881'):
        folder=BASE/'baseline_001'/name
        old=json.loads((folder/'query.json').read_text())
        raw=(folder/'snapshot.pickle').read_bytes()
        genraw=(folder/'generator.pickle').read_bytes()
        state=pickle.loads(raw)
        planner=pickle.loads(genraw)
        state_before=pickle.dumps(state)
        qcpu,qwall=time.process_time(),time.perf_counter()
        report['standalone_queries']+=1
        found=planner.generate(state,old['bag_id'],old['tray_id'],old['k'])
        row=dict(name=name,query_cpu_seconds=time.process_time()-qcpu,query_wall_seconds=time.perf_counter()-qwall,
            status=planner.last_search_status,expansions=planner.last_expansions,diagnostics=planner.last_diagnostics,
            candidates=[asdict(c) for c in found],old_status=old['status'],old_expansions=old['expansions'],
            snapshot_sha256=sha256(raw).hexdigest(),generator_sha256=sha256(genraw).hexdigest(),
            unchanged_snapshot=pickle.dumps(state)==state_before,
            validator_acceptance=[ExecutionValidator().validate(state,c).accepted for c in found])
        assert row['unchanged_snapshot'] and all(row['validator_acceptance'])
        report['rows'].append(row)
    report['source_sha256_after']={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in paths}
    assert before==report['source_sha256_after']
    report['status']='passed'
except BaseException:
    report.update(status='failed',failure=traceback.format_exc())
finally:
    report.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
                  scope='imports, unpickle, three queries and common validator recheck; query timings are nested')
    (OUT/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_sha256_before','source_sha256_after','rows')},indent=2))
    print(json.dumps([{k:r[k] for k in ('name','status','expansions','old_status','old_expansions','query_cpu_seconds')} for r in report['rows']],indent=2))
sys.exit(0 if report['status']=='passed' else 1)
