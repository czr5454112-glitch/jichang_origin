"""Layer1: hash/CRC/reference closure and selected public fields, not full rows."""
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import json
import time

from audit import BRANCH, HERE, RUN, load, save, sha
from scripts.experiments.g31_ics_circulation.foundation_airport_observations_v2 import members, encoded


def main():
    started=time.monotonic()
    plan,receipt=load(RUN/'plan.json'),load(RUN/'receipt.json')
    worker,accepted=load(BRANCH/'worker_report.json'),load(BRANCH/'acceptance.json')
    assert receipt['process']['status']=='exited' and receipt['process']['exitcode']==0
    assert receipt['status']==worker['status']
    assert accepted['status']=='closed_run_acceptance_passed' and not accepted['invalid']
    assert sha(RUN/'plan.json')==receipt['plan_sha256_at_launch']
    assert sha(BRANCH/'raw.json.gz')==worker['raw']['sha256']
    assert sha(BRANCH/'acceptance.json')==worker['acceptance']['sha256']
    for source,digest in plan['source_sha256'].items():
        assert sha(source)==digest and sha(RUN/plan['source_archive'][source])==digest
    raw=load(BRANCH/'raw.json.gz')
    complete=receipt['status']=='requested_calibration_end_reached'
    if complete:
        assert raw['final_physical_time']==raw['final_result']['physical_clock']==59400
        boundary=load(BRANCH/'warmup_boundary.json')
        assert boundary['physical_time']==57600 and boundary['native_state_sha256']==raw['warmup_native_state_sha256']
        assert sha(boundary['raw']['path'])==boundary['raw']['sha256']
    assert len(raw['final_result']['jobs'])==28506
    assert raw['session_instance_count']==1 and raw['physical_reset_count']==0
    recording=load(BRANCH/'policy_observation_receipt.json')
    for name in ['artifact','blobs']:
        assert sha(recording[name]['path'])==recording[name]['sha256']
    blobs_path=recording['blobs']['path']
    index={}
    for payload,offset,length in members(blobs_path,with_offsets=True):
        row=json.loads(payload);digest=row['sha256'];value=row['value']
        assert digest not in index and hashlib.sha256(encoded(value)).hexdigest()==digest
        index[digest]=(offset,length,len(value) if type(value) is list else None)
    print(json.dumps({'stage':'all_blob_crc_and_sha_verified','blobs':len(index),'wall_seconds':time.monotonic()-started}),flush=True)

    @lru_cache(maxsize=128)
    def blob(digest):
        offset,length,_=index[digest]
        with open(blobs_path,'rb') as f:
            f.seek(offset);row=json.loads(gzip.decompress(f.read(length)))
        assert row['sha256']==digest and hashlib.sha256(encoded(row['value'])).hexdigest()==digest
        return row['value']

    def validate(ref):
        kind=ref['kind']
        if kind=='inline':
            assert set(ref)=={'kind','value'} and (ref['value'] is None or type(ref['value']) in (str,int,float,bool))
        elif kind=='value':
            assert set(ref)=={'kind','sha256'} and ref['sha256'] in index
        elif kind=='list':
            assert set(ref)=={'kind','length','chunks'} and type(ref['length']) is int and ref['length']>=0
            assert type(ref['chunks']) is list and all(k in index and index[k][2] is not None for k in ref['chunks'])
            assert sum(index[k][2] for k in ref['chunks'])==ref['length']
        elif kind=='object':
            assert set(ref)=={'kind','fields'} and type(ref['fields']) is dict
            for value in ref['fields'].values():validate(value)
        else:raise AssertionError('unknown reference kind')

    def selected(ref):
        kind=ref['kind']
        if kind=='inline':return ref['value']
        if kind=='value':return blob(ref['sha256'])
        if kind=='list':return [item for key in ref['chunks'] for item in blob(key)]
        if kind=='object':return {k:selected(v) for k,v in ref['fields'].items()}
        raise AssertionError('unknown reference kind')

    count=0; gates=Counter(); owners=Counter(); late=[];supply_checked=0
    first=last=None
    for count,payload in enumerate(members(recording['artifact']['path']),start=1):
        row=json.loads(payload)
        assert row['sequence']==count-1 and row['schema']=='g31.foundation.airport_policy_observation.v2'
        assert row['readonly'] and not row['native_execution_authority'] and row['candidate_conditional_labels'] is None
        for field in ['observation','policy_options','decision']:validate(row[field])
        obs,decision=row['observation']['fields'],row['decision']['fields']
        assert selected(obs['owner_id'])==row['owner_id']
        assert selected(obs['now'])==selected(decision['now'])==row['now']
        assert 43200<=row['now']<=min(raw['final_physical_time'],59400)
        first=row['now'] if first is None else first;last=row['now'];owners[row['owner_id']]+=1
        if row['now']<plan['planner_activate_at']:continue
        supplies=selected(decision['supplies']);intents=selected(decision['intents'])
        actual=[s for s in supplies if s['ledger']=='actual_available']
        trays={t['tray_id']:t for t in selected(obs['trays'])}
        contracts={n['node']:n for n in selected(obs['node_contracts'])}
        assert len(actual)==len({s['tray_id'] for s in actual})
        for supply in actual:
            tray=trays[supply['tray_id']]
            assert tray['mode']=='empty' and tray['edge_to']<0 and tray['node']==supply['node']
            assert supply['earliest']==supply['estimate']==row['now']
            assert supply['owner_id']==row['owner_id']==contracts[supply['node']]['resource_owner']
            supply_checked+=1
        gate='baseline_intents_returned' if intents else 'no_actual_available_supply' if not actual else 'forecast_would_be_called'
        gates[gate]+=1
        late.append({'sequence':count-1,'now':row['now'],'owner':row['owner_id'],
            'actual_available':[{'tray_id':s['tray_id'],'node':s['node']} for s in actual],
            'intent_count':len(intents),'gate':gate})
    assert count==recording['record_count'] and first==recording['first_at'] and last==recording['last_at']
    report={'schema':'g31.airport_layer1_opportunity_gate.v1','status':'passed_layer1_not_full_materialization',
        'wall_seconds':time.monotonic()-started,'native_sessions':0,
        'process_status':receipt['status'],'actual_clock':raw['final_physical_time'],
        'last_complete_snapshot':raw['final_result']['physical_clock'],
        'complete_requested_window':complete,'warmup_hash':raw['warmup_native_state_sha256'],
        'full_business_population':28506,'completed_business':raw['final_result']['population']['completed'],
        'source_archive_pairs_verified':len(plan['source_sha256']),
        'gzip_crc_and_every_blob_sha_verified':True,'unique_blobs':len(index),
        'all_reference_types_keys_hash_targets_and_lengths_verified':True,
        'record_count':count,'first':first,'last':last,'owners':dict(owners),
        'actual_supply_to_current_public_empty_owned_tray_checks':supply_checked,
        'late_guards':dict(gates),
        'C10_initial_guard_reachable':complete and bool(gates['forecast_would_be_called']),
        'full_materialization_audit_pending':True,'C10_launch_allowed_by_this_layer':False,
        'receiver_completeness_or_candidate_guaranteed':False,
        'scope':'Every complete gzip and content blob is validated; all record reference graphs are closed. Only decision and necessary local public tray/contract metadata are materialized for the initial guard. No global/receiver ledger feature is added.'}
    save('quick_gate_report.json',report);save('quick_gate_rows.json',late)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
