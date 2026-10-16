"""Fixed four changed choices, read-only saved timing diagnosis, no causal ABBA claim."""
from pathlib import Path
import gzip,hashlib,json,time
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
encoded=lambda v:json.dumps(v,ensure_ascii=False,allow_nan=False).encode()
keys=['normal/block0_load1/budget_two','normal/block0_load2/budget_two',
      'normal/block1_load0/budget_two','normal/block1_load1/budget_two']
folders={'old':OUT/'initial_owner_route_entry_codec_campaign_prepare_001',
         'new':OUT/'initial_owner_route_single_capture_campaign_prepare_001'}
expected={'old':'2d948207fcd77a97dc29491c3f22e8d5c476e24c94a479759002bcece7c533dc',
          'new':'f8255ca3e9a6a989221c4c13673bebe195e9e3b1dfdee624435c9a4b1912fe6a'}
begin=time.monotonic();pins={};rows={k:{} for k in keys}
for arm,folder in folders.items():
    assert sha(folder/'verification.json')==expected[arm]
    ledger=read(folder/'branch_ledger.json')
    for name in ('campaign.json','verification.json','branch_ledger.json','receipt.json','external_application_wall.json'):
        pins[str(folder/name)]=sha(folder/name)
    for key in keys:
        ref=ledger[key]['raw'];path=Path(ref['path']);assert sha(path)==ref['sha256'];pins[str(path)]=ref['sha256']
        with gzip.open(path,'rb') as f:raw=f.read(128*1024*1024+1)
        assert len(raw)<=128*1024*1024
        value=json.loads(raw);e=value['root_records'][0]['value']['evidence'];start=e['root_started_ns']
        events=e['events'];reply=[r for r in events if r['stage']=='two_choice_reply'];assert len(reply)==1
        payload=reply[0]['value']['payload'];budget=payload['budget']
        row={'choice':e['choice'],'state':e['state'],'deadline_ms':(e['root_deadline_ns']-start)/1e6,
             'decision_cutoff_ms':(e['decision_cutoff_ns']-start)/1e6,
             'warm_ms':value['root_records'][0]['warm_caller_elapsed_ns']/1e6,
             'stage_offset_ms':{r['stage']:(r['wall_ns']-start)/1e6 for r in events if r['stage'] in
                ('actual_A_collection','two_choice_reply','RPC_attempt','final_local_and_receiver_check')},
             'selection':payload['selection'],
             'worker_budget':{k:((v-start)/1e6 if k.endswith('_ns') and type(v) is int else v) for k,v in budget.items()},
             'baseline_sha256':hashlib.sha256(encoded(payload['baseline'])).hexdigest(),
             'snapshot_sha256':payload['snapshot_sha256'],
             'prediction_statuses':[p.get('status') if type(p) is dict else type(p).__name__ for p in payload['predictions']],
             'initial_actual_next':value['outcome']['initial_actual_next']}
        rows[key][arm]=row
        assert time.monotonic()-begin<120
for key,pair in rows.items():
    pair['same_baseline_prediction']=pair['old']['baseline_sha256']==pair['new']['baseline_sha256']
    pair['same_predictor_snapshot']=pair['old']['snapshot_sha256']==pair['new']['snapshot_sha256']
assert all(sha(p)==d for p,d in pins.items())
report={'status':'saved_four_changed_choices_read','rows':rows,'pins':pins,'source_sha256':sha(__file__),
    'native_calls':0,'model_calls':0,'raw_reads':8,'source_changed':[],
    'readback_seconds_not_a_request_benchmark':time.monotonic()-begin,
    'limits':'Selected four differences only, not all18 independent replay. Historical runs are not interleaved ABBA and have deadline-dependent choices. No causal overall speedup, getter effect equivalence or complete100ms claim.'}
dest=HERE/'single_capture_changed_choices_readback_001.json'
with dest.open('x',encoding='utf8') as f:json.dump(report,f,indent=2,allow_nan=False)
print(json.dumps({'report_sha256':sha(dest),'rows':rows}))
