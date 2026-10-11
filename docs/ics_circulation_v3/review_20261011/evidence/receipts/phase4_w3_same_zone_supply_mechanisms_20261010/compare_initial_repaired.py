"""Pure-file preservation check across the comparator-only repair."""
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import process_time,perf_counter

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
OUT=Path(__file__).resolve().parent

def strip_ms(value):
    if isinstance(value,dict):return {k:strip_ms(v)for k,v in value.items()if not k.endswith('_ms')}
    if isinstance(value,list):return [strip_ms(v)for v in value]
    return value

def main():
    cpu,wall=process_time(),perf_counter();target=OUT/'initial_repaired_consistency.json'
    if target.exists():raise FileExistsError(target)
    bound={}
    def read(path):
        data=path.read_bytes();bound[str(path.relative_to(ROOT))]=sha256(data).hexdigest()
        return json.loads((gzip.decompress(data)if path.suffix=='.gz'else data).decode('utf-8-sig'))
    olddir=BASE/'phase4_w3_same_zone_supply_20261010/mechanism'
    newdir=BASE/'phase4_w3_same_zone_supply_repaired_20261010/mechanism'
    oldsum,newsum=read(olddir/'summary.json'),read(newdir/'summary.json')
    oldrows={r['case_id']:r for r in oldsum['rows']};newrows={r['case_id']:r for r in newsum['rows']}
    checks=[{'field':'denominator','okay':set(oldrows)==set(newrows)and len(oldrows)==6}]
    rows=[]
    fields=('result','original_endpoint','searches','cache_before','cache_after','stopped_at',
            'initial_state','initial_cursor','forced_intervention','evaluation_ledger',
            'slow_calls','slow_history_suffix','actual_slow_trigger_times','opportunities',
            'selector_history_suffix','physical_tick_trace','event_trace_suffix','milestones')
    for case in sorted(oldrows):
        a=read(olddir/Path(oldrows[case]['file']).name);b=read(newdir/Path(newrows[case]['file']).name)
        comparisons={k:strip_ms(a[k])==strip_ms(b[k])for k in fields}
        checks += [{'case':case,'field':k,'okay':v}for k,v in comparisons.items()]
        rows.append({'case_id':case,'initial_summary_status':oldrows[case]['status'],
            'repaired_summary_status':newrows[case]['status'],
            'initial_replication':a.get('old32_replication'),'repaired_replication':b.get('old32_replication'),
            'field_equal':comparisons})
        del a,b
    changed=[name for name,h in bound.items()if sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    result={'schema':'ics_round6_same_zone_initial_repaired_consistency_v1','new_physical_simulations':0,
        'checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),'failures':[c for c in checks if not c['okay']],
        'rows':rows,'bound_file_sha256':bound,'changed_inputs':changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'scope':'Pure-file physical/control comparison through hash verification. Final output serialization excluded.',
        'excluded':'Only keys ending _ms within compared physical/control payloads. Run-level CPU/wall, source overlay of changed comparator, and the intentionally repaired replication labels are not physical/control payloads.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('checks','failed_checks','failures','changed_inputs','cpu_seconds','wall_seconds')}))
    if result['failed_checks']or changed:raise SystemExit(1)

if __name__=='__main__':main()
