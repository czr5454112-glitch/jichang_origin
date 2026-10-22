"""Descriptive callback totals and a bounded cross-owner receiver-claim case."""
import collections
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
DATA=Path(__file__).resolve().parent
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'

def bind(p):
    p=Path(p).resolve()
    with p.open('rb') as f:return dict(path=str(p),sha256=hashlib.file_digest(f,'sha256').hexdigest())
def read(ref):
    assert bind(ref['path'])==ref
    p=Path(ref['path'])
    with (gzip.open(p,'rt',encoding='utf8') if p.suffix=='.gz' else p.open(encoding='utf8')) as f:return json.load(f)

def main():
    output=DATA/'supplemental_descriptive_005_001.json';assert not output.exists()
    source=bind(CYCLE/'sources/terminal_flow_runtime_005/source_manifest.json');manifest=read(source)
    relative='scripts/experiments/g31_ics_circulation/foundation_airport_json_stream.py'
    stream=bind(Path(manifest['root'])/relative);assert stream['sha256']==manifest['files'][relative]
    loader=importlib.util.spec_from_file_location('supplemental_frozen_stream',stream['path'])
    module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
    summary_ref=bind(DATA/'final_contract_summary_005_001.json');summary=read(summary_ref)
    refs=[bind(__file__),source,stream,summary_ref];groups=collections.defaultdict(list)
    for row in summary['runs']:groups[row['method']].append(row)
    performance=[]
    for method,runs in sorted(groups.items()):
        calls=[r['measured_callback'] for r in runs];stages=collections.Counter()
        for c in calls:
            for key,value in c.get('stages',{}).items():stages[key]+=value['total_seconds']
        total=sum(c['total_seconds'] for c in calls)
        performance.append(dict(method=method,runs=len(runs),count=sum(c['count'] for c in calls),
            callback_seconds=total,per_run_p95_range_seconds=[min(c['p95_seconds'] for c in calls),max(c['p95_seconds'] for c in calls)],
            stage_seconds=dict(stages),stage_share_of_measured_callback={k:v/total for k,v in stages.items()},
            worker_seconds=sum(r['runtime']['worker_wall_seconds'] for r in runs)))
    run=CYCLE/'runs/TF_bridge_all_005_TF-B1-60_P2203'
    decisions_ref=bind(run/'decisions.json.gz');book_ref=bind(DATA/'unified_orders_005_001/P2203_TF-B1-60_unified_orders.json.gz')
    refs.extend([decisions_ref,book_ref]);book=read(book_ref)
    expected={(9780.,'owner:system_domestic'),(9900.,'owner:system_international')};cases=[]
    for decision in module.iter_json_array_gz(decisions_ref['path']):
        if decision['decision_time']>9900:break
        key=decision['decision_time'],decision['owner_id']
        if key not in expected:continue
        action=decision['requested_action'];assert action['action_type']=='transfer' and action['destination']==57
        chain=[r for r in book['frozen_unified_order_book']['chains'] if r.get('actual_submission',{}).get('issued_at')==key[0]
            and r.get('owner_scope')==key[1] and r.get('physical_tray_id')==action['tray_id']]
        assert len(chain)==1
        plan=decision['selection']['flow_plan']
        cases.append(dict(decision_id=decision['decision_id'],owner=key[1],at=key[0],action=action,
            receiver_claims_deducted=plan['receiver_claims_deducted'],
            receiver=[s for s in plan['station_table'] if s['node']==57],planned_order=decision['empty_transport_order'],
            audited_request_chain=chain[0]))
    assert len(cases)==2
    cases.sort(key=lambda r:r['at']);first,second=cases
    assert first['audited_request_chain']['native_transfer']['received_at']>second['at']
    assert second['receiver_claims_deducted']['57']==1 and second['receiver'][0]['receiver']['available_slots']==2
    for ref in refs:assert bind(ref['path'])==ref
    result=dict(status='descriptive_completed_evidence',inputs=refs,performance=performance,
        performance_scope='6968 callbacks per method include endpoint callbacks; p95 ranges are not pooled percentiles. Callback excludes catalogue, protocol, native and final export.',
        cross_owner_receiver_case=cases,
        cross_owner_scope='Two distinct owners use destination57 while the first request is still in transit. Second recorded plan deducts one logical claim and has two remaining receiver slots. This is not an identical-capacity-slot collision test or causal service benefit.',
        native_starts=0,raw_observations_read=False,full_owner_ACK_read=False,complete_request_100ms_certified=False)
    with output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(bind(output)))

if __name__=='__main__':main()
