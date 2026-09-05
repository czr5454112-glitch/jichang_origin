"""Run unchanged G31 on the exact historical map2 shared-D segment schedule."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT/'src'):
    if str(p) not in sys.path: sys.path.insert(0,str(p))
from czr005 import cpp_backend
from scripts.eval import run_cie_component_activation as activation
from scripts.eval import run_cie_external_baseline_robustness as external

OUT = ROOT/'outputs/runtime/feng_dh_v5_shared_D_20260905'
SCHEDULE = ROOT/'data/processed/feng_table53_segment_schedule.csv'
BASE = ROOT/'data/processed/tasks/inputdata.jsonl'
BINARY = ROOT/'build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))


def main() -> None:
    if OUT.exists(): raise RuntimeError('shared-D result directory already exists; do not overwrite')
    if sha(SCHEDULE)!='a3db0d3f495870437414af0b46a0a140f7cafe8111b40222ca59fcd78e7d4d86':
        raise RuntimeError('historical D identity differs')
    if sha(BINARY)!=external.EXPECTED_G31_BINARY_SHA256:
        raise RuntimeError('not the registered final G31 binary')
    with SCHEDULE.open(encoding='utf-8-sig',newline='') as f:
        schedule={(int(r['raw_bag_id']),int(r['segment_id'])):r for r in csv.DictReader(f)}
    base=[json.loads(line) for line in BASE.read_text(encoding='utf-8').splitlines() if line]
    if len(base)!=43603 or len(schedule)!=43603: raise RuntimeError('wrong population')
    aligned=[];seen=set();changes=0
    for row in base:
        key=int(row['task_id']), 1 if row['leg']=='storage_out' else 0
        if key in seen or key not in schedule: raise RuntimeError('duplicate or foreign leg')
        seen.add(key); s=schedule[key]
        if any(int(row[k])!=int(s[k]) for k in ('start','goal')): raise RuntimeError('OD differs')
        target=dict(row);target['pass_time']=float(s['scheduled_release_seconds'])
        if target['pass_time']!=row['pass_time']: changes+=1
        if {k:v for k,v in target.items() if k!='pass_time'}!={k:v for k,v in row.items() if k!='pass_time'}:
            raise RuntimeError('non-release input changed')
        aligned.append(target)
    if seen!=set(schedule): raise RuntimeError('incomplete schedule match')
    OUT.mkdir(parents=True)
    canonical=OUT/'g31_exact_historical_D.jsonl'
    canonical.write_bytes((''.join(json.dumps(r,sort_keys=True)+'\n' for r in aligned)).encode('utf-8'))
    identity={'schema':'feng.dh.v5.g31_exact_historical_D.v1','status':'RUNNING',
              'started_at':datetime.now(timezone.utc).isoformat(),
              'alignment':'Only canonical pass_time replaced by exact historical workbook D; all other fields unchanged.',
              'source_canonical':str(BASE),'source_canonical_sha256':sha(BASE),
              'schedule':str(SCHEDULE),'schedule_sha256':sha(SCHEDULE),
              'aligned_canonical_sha256':sha(canonical),'changed_pass_time_values':changes,
              'raw_bags':28506,'segments':43603,'OD_and_leg_identity_verified':True,
              'binary_path':str(BINARY),'binary_sha256':sha(BINARY),
              'g31_policy_changed':False,'source_file_sha256':sha(Path(__file__)),
              'reference_v5_run':'outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5',
              'historical_HCA_is_archived_measurement_not_new_run':True,
              'scope':'Original map2 shared-D 1x, separate from jittered external matrix.'}
    write(OUT/'run_identity.json',identity)
    captured={}
    def execute(**request):
        payload=cpp_backend.g4irsf11_event_runtime_from_records(**request)
        captured['payload']=payload
        return payload
    try:
        result=activation.execute_run(map_name='map2',factor=1.0,canonical_path=canonical,binary=BINARY,executor=execute)
        write(OUT/'g31_native_summary.json',result)
        if result['execution_integrity']['pass'] is not True: raise RuntimeError('G31 integrity failed')
        payload=captured['payload']
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
        (OUT/'g31_native_payload.json.gz').write_bytes(gzip.compress(raw,mtime=0))
        canonical_raw=canonical.read_bytes()
        (OUT/'g31_exact_historical_D.jsonl.gz').write_bytes(gzip.compress(canonical_raw,mtime=0))
        identity['native_payload_uncompressed_sha256']=hashlib.sha256(raw).hexdigest()
        identity['outputs']={p.name:sha(p) for p in OUT.iterdir() if p.name!='run_identity.json'}
        identity['status']='COMPLETE'
        print(json.dumps({'status':'COMPLETE','population':result['population'],
                          'timing':result['full_population_timing']},ensure_ascii=False))
    except Exception as error:
        identity.update(status='FAILED',error=str(error));raise
    finally:
        identity['finished_at']=datetime.now(timezone.utc).isoformat()
        write(OUT/'run_identity.json',identity)


if __name__=='__main__': main()
