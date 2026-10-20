"""Small offline design audit: fixed input/static contracts only, no native.

Future loader rows are used solely to diagnose the conditional bound and a
possible follow-up; they MUST NOT become inputs to an online donor policy.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from . import research_original_low_wip as base


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output):
    root=base.ROOT;out=base.OUT
    input_path=out/'original_low_wip_prepare_005/input.json.gz'
    plan_path=out/'original_bridge_serialize_once_prepare_001/bridge/preregistered_protocol.json'
    bound_path=out/'original_carrier_bound_002/analysis.json.gz'
    assert sha(input_path)==base.INPUT_SHA
    with gzip.open(input_path,'rt',encoding='utf8') as f:data=json.load(f)
    with gzip.open(bound_path,'rt',encoding='utf8') as f:bound=json.load(f)
    plan=json.loads(plan_path.read_bytes())
    public={k:data[k] for k in ('node_records','edge_records','node_contracts','edge_contracts')}
    graph=base.public_graph(public)
    nodes={r['node']:r for r in data['node_contracts']}
    jobs={r['business_bag_id']:r for r in data['jobs']}
    loader=[]
    for group in bound['loaders']:
        rows=group['jobs_in_native_fifo_order'];first=next(i for i,r in enumerate(rows) if not r['reachable'])
        bad=jobs[rows[first]['business_bag_id']]
        after=[]
        for r in rows[first+1:]:
            if not r['reachable']:break
            j=jobs[r['business_bag_id']]
            after.append({k:j[k] for k in ('business_bag_id','origin','destination','storage_node','arrival','deadline')})
        loader.append({'origin':group['origin'],'zero_bad_prefix':first,
            'first_unreachable':{k:bad[k] for k in ('business_bag_id','origin','destination','storage_node','arrival','deadline')},
            'reachable_after_one_bad_before_next_bad':after,
            'one_bad_relaxed_additional_count':len(after)})
    # One source-bound example of a different LOCAL parked donor. These are
    # static declared positions, not a claim of a currently delivered view.
    reference_node=116;target=49
    baseline=base.paths_from(graph,reference_node).get(target)
    donors=[]
    for parked in plan['parking_plan']['parking']:
        source=parked['destination']
        if nodes[source]['resource_owner']!=nodes[reference_node]['resource_owner']:continue
        path=base.paths_from(graph,source).get(target)
        if path:donors.append({'tray_id':parked['tray_id'],'declared_park_node':source,
                              'free_flow_weight':path[0],'positive_path':path[1]})
    report={'schema':'g31.completion_baton.static_design_audit.v1',
        'status':'offline_source_design_only','native_calls':0,'predictor_calls':0,
        'input':{'path':str(input_path),'sha256':sha(input_path)},
        'bound':{'path':str(bound_path),'sha256':sha(bound_path)},
        'parking_plan':{'path':str(plan_path),'sha256':sha(plan_path)},
        'script':{'path':str(Path(__file__).resolve()),'sha256':sha(__file__)},
        'offered':len(data['jobs']),'existing_trays':len(data['trays']),
        'all_original_R1_false':all(not j.get('allow_suffix_reroute',False) for j in data['jobs']),
        'zero_bad_prefix_sum':sum(r['zero_bad_prefix'] for r in loader),'loaders':loader,
        'first_bad_with_storage':sum(r['first_unreachable']['storage_node']>=0 for r in loader),
        'same_owner_donor_example':{'reference_position':reference_node,'same_target':target,
            'reference_free_flow_weight':baseline[0],'reference_positive_path':baseline[1],
            'donors':sorted(donors,key=lambda r:(r['free_flow_weight'],r['tray_id']))},
        'limitations':['Full future rows and declared parked positions are OFFLINE diagnosis only.',
            'Weights include positive directed travel plus nonnegative service; no congestion/native route choice/ACK guarantee.',
            'One-bad reward ignores permanent FIFO/Storage/resource obstruction. It is not a realizable schedule or authority to load an unreachable job.',
            '39 assumes no unreachable job ever loads, complete FIFO prefixes, no ties/extra carriers/off-carrier release. Not an airport-wide impossibility claim.',
            'No current-view or delivered-capture guard, normal per-job protection, full-day audit or100ms certificate is supplied here.']}
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    print(json.dumps({'status':report['status'],'39':report['zero_bad_prefix_sum'],
        'first_bad_with_storage':report['first_bad_with_storage'],
        'report_sha256':sha(output/'report.json')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
