"""Select mechanism-only callback witnesses after seeing the baseline outcomes."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from audit import BRANCH, RUN, load, save, sha
from scripts.experiments.g31_ics_circulation.foundation_airport_observations_v2 import members, encoded


def main():
    raw=load(BRANCH/'raw.json.gz');final=raw['final_result']
    calls=load(BRANCH/'client_calls.json.gz');views=load(BRANCH/'delivered_ack_views.json.gz')
    order=[];request_to_callback={}
    for item in raw['segments']:
        segment=load(item['raw']['path'])
        for tick in segment['control_records']:
            if not 43200<=tick['at']<=59400:continue
            for owner in tick['owner_decisions']:
                attempts=owner['attempts']
                base={'owner_id':owner['owner_id'],'now':tick['at'],'tick':tick['tick'],
                    'trace_sequence':tick['trace_sequence'],'segment_index':item['index'],'segment_raw':item['raw']}
                current={**base,'sequence':len(order),'residual_index':0,'request_prefix':f"protocol:{tick['tick']}"}
                order.append(current)
                for i,attempt in enumerate(attempts):
                    request_to_callback[attempt['request_id']]=current
                    if attempt['reply']['status']=='pending':
                        current={**base,'sequence':len(order),'residual_index':i+1,'request_prefix':f"protocol:{tick['tick']}:residual"}
                        order.append(current)
    transfers={t['request_id']:t for t in final['transfers']}
    legs_by_request=defaultdict(list)
    for leg in final['leg_identities']:
        if leg['kind']=='empty_return':
            request=leg['transport_leg_id'].split(':empty_return:')[0]
            legs_by_request[request].append(leg)
    first_edges={}
    for event in final['receipts']:
        if event['event']=='EDGE_ENTER':first_edges.setdefault(event['transport_leg_id'],event)
    eligible=[]
    for call in calls:
        if call['kind']!='transfer' or call['retry'] or call['at']<57660:continue
        request=call['request'];identity=request['request_id'];transfer=transfers.get(identity)
        acks=[a for a in views[request['owner_id']]['delivered_transfer_acks'] if a['request_id']==identity and a['status'] in ('departed','received')]
        edges=[first_edges[l['transport_leg_id']] for l in legs_by_request[identity] if l['transport_leg_id'] in first_edges]
        if not transfer or not acks or not edges:continue
        edge=min(edges,key=lambda x:x['time'])
        if not 0<=edge['time']-call['at']<=300:continue
        eligible.append({'callback':request_to_callback[identity],'actual_request':request,
            'native_transfer':transfer,'positive_source_delivered_acks':acks,
            'first_edge':edge,'first_edge_delay_seconds':edge['time']-call['at'],
            'first_positive_ack_delay_seconds':min(a['delivered_at'] for a in acks)-call['at'],
            'legs':legs_by_request[identity]})
    selected=eligible[:2]
    wanted={r['callback']['sequence']:r for r in selected};needed=set()
    for payload in members(BRANCH/'policy_observations.jsonl.gz'):
        row=json.loads(payload)
        if row['sequence'] not in wanted:continue
        item=wanted[row['sequence']];identity=item['callback']
        assert row['owner_id']==identity['owner_id'] and row['now']==identity['now']
        assert row['policy_options']['fields']['request_prefix']['value']==identity['request_prefix']
        intents=row['decision']['fields']['intents'];assert intents['kind']=='list' and intents['length']>0
        item['first_intents_blob_sha256']=intents['chunks'][0];needed.add(intents['chunks'][0])
        item['record_reference_json_sha256']=hashlib.sha256(encoded(row)).hexdigest()
    values={}
    for payload in members(BRANCH/'policy_observations.blobs.jsonl.gz'):
        row=json.loads(payload)
        if row['sha256'] in needed:
            assert hashlib.sha256(encoded(row['value'])).hexdigest()==row['sha256']
            values[row['sha256']]=row['value']
        if set(values)==needed:break
    for item in selected:
        intent=values[item['first_intents_blob_sha256']][0]
        actual=dict(intent);actual.pop('expected_version',None)
        actual.update(request_id=item['actual_request']['request_id'],owner_id=item['callback']['owner_id'])
        assert actual==item['actual_request']
        item['recorded_first_intent']=intent
        item['first_intent_to_actual_request_exact_under_original_ProtocolClient_identity_assignment']=True
    report={'schema':'g31.airport_reference_selected_shadow_callbacks.v1','selection_scope':
        'POSTHOC selection after inspecting this baseline: first2 actual late baseline callbacks with source delivered positive ACK and physical first edge within300s. Training-trajectory mechanism diagnostic only; not heldout, policy gain, or random sample.',
        'native_sessions':0,'reference_plan':{'path':str(RUN/'plan.json'),'sha256':sha(RUN/'plan.json')},
        'reference_raw':{'path':str(BRANCH/'raw.json.gz'),'sha256':sha(BRANCH/'raw.json.gz')},
        'reference_observations':load(BRANCH/'policy_observation_receipt.json'),
        'request_calls_sha256':sha(BRANCH/'client_calls.json.gz'),'public_ack_views_sha256':sha(BRANCH/'delivered_ack_views.json.gz'),
        'eligible_callback_count':len(eligible),'selected_count':len(selected),'selected':selected,
        'future_receipts_used_only_offline_for_witness_selection':True,
        'runtime_model_must_read_only_then_available_public_observation':True,
        'scores_select_or_modify_native_action':False,'positive_ACK_within300_required':False,
        'full_observation_materialization_audit_pending':True}
    save('shadow_callback_selection.json',report)
    print(json.dumps({'eligible':len(eligible),'selected':[{'callback':x['callback'],'request':x['actual_request']['request_id'],
        'source':x['actual_request']['source'],'destination':x['actual_request']['destination'],
        'edge_delay':x['first_edge_delay_seconds'],'positive_ack_delay':x['first_positive_ack_delay_seconds']} for x in selected]},ensure_ascii=False))


if __name__=='__main__':main()
