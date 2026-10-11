"""Pure-file evidence for every task-level regression in full81."""
from hashlib import sha256
import gzip,json
from pathlib import Path
from time import process_time,perf_counter
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
RUN=BASE/'phase4_w3_same_zone_supply_repaired_20261010'

def main():
    cpu,wall=process_time(),perf_counter();target=OUT/'service_regressions.json'
    if target.exists():raise FileExistsError(target)
    bound={};checks=[]
    def read(path):
        data=path.read_bytes();bound[str(path.relative_to(ROOT))]=sha256(data).hexdigest()
        return json.loads((gzip.decompress(data)if path.suffix=='.gz'else data).decode('utf-8-sig'))
    risks=read(OUT/'formal_tradeoffs.json');summary=read(RUN/'full/summary.json')
    rows={r['case_id']:r for r in summary['rows']};result=[]
    for detail in risks['details']:
        if not detail['task_regressions']:continue
        scene=rows[detail['old_case']]['scene']
        original=read(BASE/'phase4_w3_network_role_labels_parallel_20261009'/scene/(scene+'_input.json'))['initial']
        bags={r['bag_id']for r in detail['task_regressions']}
        entry={'cases':{s:detail[s+'_case']for s in ('old','new')},'regressions':detail['task_regressions'],'physical':{}}
        for side in ('old','new'):
            row=rows[entry['cases'][side]];path=RUN/row['file'];s=read(path)
            checks.append({'kind':'raw_binding','case':row['case_id'],'okay':bound[str(path.relative_to(ROOT))]==row['sha256']})
            start=min(r[side]['load_time']for r in detail['task_regressions'])
            end=max(r[side]['completed_at']for r in detail['task_regressions'])
            carried={k:t['bag_id']for k,t in original['trays'].items()};departures=[]
            for event in s['result']['trace']:
                tray=event.get('tray_id');kind=event['event']
                if kind=='load':carried[tray]=event['bag_id']
                elif kind=='unload_complete':carried[tray]=None
                elif kind=='depart'and start<=event['time']<=end:
                    departures.append({**event,'bag_id_at_depart':carried[tray],
                        'edge':original['network']['edges'][event['edge_id']]})
            entry['physical'][side]={'window':[start,end],'all_departures_in_window':departures,
                'all_events_in_window':[e for e in s['result']['trace']if start<=e['time']<=end and e['event']not in ('initial','tick')],
                'regressed_bag_route_opportunities':[r for r in s['opportunities']if r['bag_id']in bags],
                'selector_history':s['selector_history_suffix']}
            del s
        result.append(entry)
    changed=[p for p,h in bound.items()if sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    payload={'schema':'ics_round6_service_regressions_v1','new_physical_simulations':0,
        'selection':'Every delayed load or completion in all27 new/old32 paired deployments, regardless of net objective gain.',
        'details':result,'checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),
        'changed_inputs':changed,'bound_file_sha256':bound,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Pure-file raw trace/public route opportunity read/hash through input verification, excluding final serialization.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items()if k not in ('details','bound_file_sha256')},ensure_ascii=False))
    if changed or payload['failed_checks']:raise SystemExit(1)

if __name__=='__main__':main()
