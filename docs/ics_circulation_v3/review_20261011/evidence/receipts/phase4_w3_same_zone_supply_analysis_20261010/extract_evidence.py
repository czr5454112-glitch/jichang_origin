"""Extract selected existing JSON/source evidence; no simulator imports."""
from hashlib import sha256
import json
from pathlib import Path
from time import process_time, perf_counter

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/experiments/ics_circulation_v3'

def main():
    cpu0,wall0=process_time(),perf_counter()
    target=OUT/'analysis.json'
    if target.exists():raise FileExistsError(target)
    hashes={}
    def read(path):
        data=path.read_bytes();hashes[str(path.relative_to(ROOT))]=sha256(data).hexdigest()
        return json.loads(data.decode('utf-8-sig'))
    original=read(BASE/'phase4_w3_network_role_labels_parallel_20261009/counterflow/counterflow_input.json')
    forecasts=[f for f in original['forecasts']if f['forecast_id']=='counterflow:round2:flow1']
    meta=read(BASE/'phase4_w3_network_nominal_opportunities_repaired_20261010/collections/counterflow/d0040.json')
    review=read(BASE/'phase4_w3_network_nominal_analysis_20261010/mechanisms.json')
    state=meta['state'];network=state['network']
    edges=[network['edges'][name]for name in ('46->39','39->40','40->52','52->26')]
    sources=['prebalance.py','runtime.py','distributed_local.py','distributed_slow.py','phase4_control.py','phase4_network_workloads.py']
    for name in sources:
        p=ROOT/'scripts/experiments/ics_circulation_v3'/name
        hashes[str(p.relative_to(ROOT))]=sha256(p.read_bytes()).hexdigest()
    checks={
        'exact_publication':len(forecasts)==1 and forecasts[0]['published_at']==116 and forecasts[0]['at']==156,
        'published_before_current_fast_decision':len(forecasts)==1 and forecasts[0]['published_at']<=meta['time'],
        'current_time126_next_slow127':meta['time']==126 and meta['next_slow_trigger_at']==127,
        'same_zone':network['nodes']['26']['logistics_zone']==network['nodes']['46']['logistics_zone'],
        'different_owner':network['nodes']['26']['control_partition']!=network['nodes']['46']['control_partition'],
        'static_path13':sum(e['travel_time']for e in edges)==13,
        'static_positive_capacities':all(e['capacity']>0 for e in edges),
        'warm_tray_available':state['trays']['warm_tray']['node']=='46'and state['trays']['warm_tray']['mode']=='empty'and state['trays']['warm_tray']['available_at']<=meta['time'],
        'warm_tray_uncommitted': 'warm_tray'not in state['plans'] and 'warm_tray'not in state['empty_targets'],
        'prior_mechanism_audit_passed':review['failed_checks']==0 and review['checks']==74,
    }
    changed=[name for name,h in hashes.items()if sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    payload={'schema':'ics_same_zone_source_diagnostic_v1','new_physical_simulations':0,
        'new_candidate_searches':0,'pickle_loads':0,'checks':len(checks),'failed_checks':sum(not v for v in checks.values()),
        'check_results':checks,'forecast':forecasts,'decision_time':meta['time'],'actual_next_slow':meta['next_slow_trigger_at'],
        'cursor_stage_index':meta['cursor']['stage_index'],'warm_tray':state['trays']['warm_tray'],
        'selected_nodes':{k:network['nodes'][k]for k in ('26','46','114')},'static_edges':edges,
        'source_sha256':hashes,'changed_inputs':changed,'read_only_forecast_scope':'Freeze input forecast tuple only; engine-only future is not used in selected evidence or candidate construction. No candidate construction performed.',
        'limitation':'Static positive-capacity 13tick route is not a timing-feasibility certificate for any new slow checkpoint.',
        'cpu_seconds':process_time()-cpu0,'wall_seconds':perf_counter()-wall0,
        'resource_scope':'Pure-file extraction and SHA verification; final serialization and preceding ad hoc shell reads excluded.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'notes_sha256':sha256((OUT/'SAME_ZONE_SUPPLY.md').read_bytes()).hexdigest()}
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:payload[k]for k in ('checks','failed_checks','changed_inputs','cpu_seconds','wall_seconds')}))
    if payload['failed_checks']or changed:raise SystemExit(1)

if __name__=='__main__':main()
