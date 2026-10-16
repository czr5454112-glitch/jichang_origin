from pathlib import Path
import json, hashlib, statistics, time
BEGIN=time.perf_counter(); HERE=Path(__file__).resolve().parent; ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'dpc_prepare_001'; sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda n:json.loads((DEST/n).read_bytes())
assert sha(DEST/'plan.json')=='cb22099c23037b14a53dd98e1ffaa7e71003c1e55913e54e0754a2d71911b1a9'
assert sha(DEST/'result.json')=='729c3a240538c8ef8aa8d0714402840d133ee36ad50b0a52e64c0b36d33632d1'
assert sha(DEST/'actual_external_application_wall.json')=='93bb690984a194d8a89770791515ad9e5263fed1f602bfbb928ba8d6a627ec59'
plan,report,outer=read('plan.json'),read('result.json'),read('actual_external_application_wall.json')
assert outer['exit_code']==0 and outer['exception'] is None and outer['outer_timeout'] is False
assert outer['source_changed']==outer['missing_required_outputs']==[]
assert type(outer['elapsed_ticks']) is int and type(outer['tick_frequency']) is int
assert 0<outer['elapsed_ticks']<=120*outer['tick_frequency'] and outer['whole_python_seconds']==outer['elapsed_ticks']/outer['tick_frequency']
for key in ('plan','ready','root_review','runner','interpreter','wrapper'):
    item=outer[key]; assert sha(item['path'])==item['sha256']
for name,digest in outer['output_sha256'].items():assert sha(DEST/name)==digest
assert len(plan['sources'])==95
for name,digest in plan['sources'].items():assert sha(ROOT/name)==sha(DEST/'source'/name)==digest
records=[json.loads(line) for line in (DEST/'measurements.jsonl').read_bytes().splitlines()]
assert records==report['records'] and len(records)==report['calls']==32 and report['source_changed']==[]
order=[(o,b,a,i) for o in (27212,27215) for b,a in enumerate(('A','B','B','A')) for i in range(4)]
assert [(r['ordinal'],r['batch'],r['arm'],r['repeat']) for r in records]==order
previous=-1; summary={}; digest_by_query={}
for row in records:
    m=row['metrics']; start,end,elapsed=(m[k] for k in ('started_ns','finished_ns','validator_ns'))
    assert all(type(x) is int for x in (start,end,elapsed)) and previous<=start<=end and end-start==elapsed;previous=end
    assert row['disposition']=='absent' and read(row['outcome_file'])=={'status':'absent'}
    assert sha(DEST/row['outcome_file'])==row['outcome_sha256']
    if row['arm']=='A':assert m['digest_events'] is None
    else:
        assert len(m['digest_events'])==1; event=m['digest_events'][0]
        assert event['ordinal']==0 and event['classification']=='direct_C_bytes' and event['returned'] is True
        digest_by_query.setdefault(row['ordinal'],set()).add(event['sha256'])
for ordinal in (27212,27215):
    summary[str(ordinal)]={}
    for arm in ('A','B'):
        selected=[r for r in records if r['ordinal']==ordinal and r['arm']==arm]; assert len(selected)==8
        ms=statistics.median(r['metrics']['validator_ns'] for r in selected)/1e6
        assert ms==report['summary'][str(ordinal)][arm]['median_validator_ms']
        summary[str(ordinal)][arm]={'calls':8,'median_validator_ms':ms}
oracles=read('byte_oracle.json');assert len(oracles)==report['C_oracle_attempts']==2
assert [r['ordinal'] for r in oracles]==[27212,27215]
byte_counts=[]
for row in oracles:
    expected,actual=bytes.fromhex(row['expected_hex']),bytes.fromhex(row['actual_hex'])
    assert expected==actual and hashlib.sha256(actual).hexdigest()==row['sha256']
    assert row['classification']=='direct_C_bytes' and row['C_attempts']==row['original_byte_writer_calls']==1
    assert digest_by_query[row['ordinal']]=={row['sha256']} and row['matches_declared_payload'] is True
    byte_counts.append(len(actual))
batches=read('batches.json');assert batches==report['batches'] and len(batches)==8
assert [(r['ordinal'],r['batch'],r['arm']) for r in batches]==[(o,b,a) for o in (27212,27215) for b,a in enumerate(('A','B','B','A'))]
for batch in batches:
    assert batch['finished_ns']-batch['started_ns']==batch['whole_batch_ns']
    members=[r for r in records if all(r[k]==batch[k] for k in ('ordinal','batch','arm'))]
    assert len(members)==4 and all(batch['started_ns']<=r['metrics']['started_ns']<=r['metrics']['finished_ns']<=batch['finished_ns'] for r in members)
stages=[json.loads(line) for line in (DEST/'stages.jsonl').read_bytes().splitlines()]
assert len(stages)==26 and [r['ordinal'] for r in stages]==list(range(26))
assert all(type(r['at_ns']) is int for r in stages) and [r['at_ns'] for r in stages]==sorted(r['at_ns'] for r in stages)
spans={}
for a,b in zip(stages[::2],stages[1::2],strict=True):
    assert a['event']=='started' and b['event']=='completed' and a['stage']==b['stage']
    spans[a['stage']]=(b['at_ns']-a['at_ns'])/1e9
entry,exit_=read('C_entry.json'),read('C_exit.json')
functional=OUT/'planning_v2_C_encoder_functional_002/receipt.json'
assert sha(functional)=='3116ddf66830d8f3f70cb6dc6651a29ecf539bf328db4ae1e28906edc49212cd'
assert entry['actual_extension']==exit_['actual_extension']==json.loads(functional.read_bytes())['actual_extension']
assert entry['complete_toolchain_and_runtime_entry_check'] is True and exit_['complete_toolchain_and_runtime_exit_check'] is True
saved=read('saved_verification.json');assert saved['status']=='passed_fixed_two_C_validator_saved' and saved['calls']==32
result={'schema':'g31.delivered_peer_C32.root_saved.v1','status':'passed_independent_saved32_bytes_and_metrics',
 'script_sha256':sha(__file__),'plan_sha256':sha(DEST/'plan.json'),'actual_outer_sha256':sha(DEST/'actual_external_application_wall.json'),
 'whole_python_seconds':outer['whole_python_seconds'],'summary':summary,'oracle_full_byte_lengths':byte_counts,
 'calls':32,'absent':32,'direct_C_measurements':16,'fallback_measurements':0,'stages_seconds':spans,
 'source_current_archive_count':95,'root_saved_review_seconds_before_export':time.perf_counter()-BEGIN,
 'limits':['No C/model/native load or actual validator rerun. Complete saved byte oracles and all32 results, typed timing/order/batches independently recomputed.',
 'Two historical absent queries only. Successful guard path, full-stream activation frequency and full-day benefit remain unmeasured.',
 'Full7779/3082 entryexit checks were producer measurements, not repeated here. Their costs retained in111.8239422s whole; local validator intervals are not full-request100ms.']}
with (DEST/'root_saved_review_001.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'status':result['status'],'sha256':sha(DEST/'root_saved_review_001.json'),'summary':summary,'whole_saved_review_seconds':time.perf_counter()-BEGIN}))
