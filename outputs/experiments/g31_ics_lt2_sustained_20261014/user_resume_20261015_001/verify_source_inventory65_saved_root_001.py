from pathlib import Path
import hashlib,json,math,pstats,statistics,time
BEGIN=time.perf_counter();HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];DEST=ROOT/'outputs/si65d1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda n:json.loads((DEST/n).read_bytes())
assert sha(DEST/'plan.json')=='cc6432f563f1b447ebac5c8058f93cc6e721f6711ba33e2c1dbe6baa60bec0c6'
assert sha(DEST/'external_application_wall.json')=='79d98ac99373a88d60f4b3ccc132eba2aff0749ee192b44004e3e18a8eb3d519'
assert sha(DEST/'receipt.json')=='6f921d8be061073e95b410c21557308a36e49ff40245dd419da2a55edc38cb1c'
assert sha(DEST/'report.json')=='7f919ed5e699c90dad78c78d0fc6859a83a2f90457d260c3a9f85e812e9c406f'
plan,outer,receipt,report=read('plan.json'),read('external_application_wall.json'),read('receipt.json'),read('report.json')
assert outer['status']=='exact65_producer_result_with_external_bound' and outer['exitcode']==outer['wrapper_exitcode']==0 and outer['error'] is None
assert type(outer['elapsed_ticks']) is int and type(outer['stopwatch_frequency']) is int and 0<outer['elapsed_ticks']<=120*outer['stopwatch_frequency']
assert outer['external_application_seconds']==outer['elapsed_ticks']/outer['stopwatch_frequency']
assert outer['expected_pins']==outer['pins_before']==outer['pins_after']
for path,digest in outer['expected_pins'].items():assert sha(path)==digest
for group in ('outputs','proof_outputs'):
    for item in outer[group].values():assert item is not None and sha(item['path'])==item['sha256']
assert len(plan['source_sha256'])==196 and len(plan['evidence_sha256'])==12
for name,digest in plan['source_sha256'].items():
    live,archive=(ROOT/name).resolve(),(DEST/plan['source_archive'][name]).resolve()
    assert live.is_relative_to(ROOT) and archive.is_relative_to(DEST/'source') and live!=archive
    assert sha(live)==sha(archive)==digest
for path,digest in plan['evidence_sha256'].items():assert sha(path)==digest
assert read('entry_pins.json')==read('exit_pins.json')==plan['source_sha256']
assert read('loaded_entry.json')==read('loaded_exit.json')
assert report['status']==receipt['status']=='exact65_original_source_proofs_profiled'
assert all(report[k]==65 for k in ('planned_calls','actual_calls','exact_proofs','profile_original_calls'))
assert all(report[k]==0 for k in ('unknown_rows','unexecuted_rows','model_predictions','native_calls','custom_data_C_loads'))
assert report['source_changed']==receipt['source_changed']==[] and report['failure'] is None
assert report['cache_used'] is report['runtime_globals_replaced'] is report['default_GC_changed'] is False
assert report['original_function_identity_unchanged'] is True
rows=read('rows.json');assert rows==report['rows'] and len(rows)==65 and [r['ordinal'] for r in rows]==list(range(65))
target=Path(plan['comparison_proof']['path']).read_bytes();assert sha(plan['comparison_proof']['path'])==plan['comparison_proof']['sha256']
previous=-1;clocks=[]
for row in rows:
    raw=Path(row['saved_return']['path']).read_bytes()
    assert raw==target and len(raw)==row['returned_bytes'] and sha(row['saved_return']['path'])==row['returned_sha256']==row['saved_return']['sha256']
    assert row['status']=='exact_proof' and row['invoked'] is True and row['full_bytes_exact'] is True
    m=row['timing'];start,end,elapsed=(m[k] for k in ('started_ns','finished_ns','elapsed_ns'))
    assert all(type(v) is int for v in (start,end,elapsed)) and previous<=start<=end and end-start==elapsed
    previous=end;clocks.append(elapsed)
assert sum(clocks)==report['clocks']['profile_original_call_ns']
assert sha(report['pstats']['path'])==report['pstats']['sha256']; stats=pstats.Stats(report['pstats']['path'])
for row in report['statistics']['watched']:
    key=(row['file'],row['line'],row['function']); actual=stats.stats[key]
    assert (row['primitive_calls'],row['total_calls'],row['self_seconds'],row['cumulative_seconds'])==actual[:4]
original=[v for k,v in stats.stats.items() if k[0].endswith('live_obligation_future_later_fork.py') and k[2]=='source_proof']
inventory=[v for k,v in stats.stats.items() if k[0].endswith('live_obligation_future_later_fork.py') and k[2]=='_source_inventory']
assert len(original)==len(inventory)==1 and original[0][1]==inventory[0][1]==65
assert math.isclose(sum(v[2] for v in stats.stats.values()), report['statistics']['total_self_seconds'],abs_tol=1e-8)
result={'schema':'g31.source_inventory65.root_saved.v1','status':'passed_independent65_fullbytes_clocks_profile_counts',
 'script_sha256':sha(__file__),'plan_sha256':sha(DEST/'plan.json'),'whole_python_seconds':outer['external_application_seconds'],
 'full_proof_pairs':65,'proof_bytes_each':len(target),'exact_rows':65,'unknown_rows':0,
 'profiled_original_seconds':sum(clocks)/1e9,'profiled_median_call_seconds':statistics.median(clocks)/1e9,
 'source_proof_cumulative_seconds':original[0][3],'source_inventory_cumulative_seconds':inventory[0][3],
 'source_current_archive_count':196,'evidence_references':12,'root_saved_review_seconds_before_export':time.perf_counter()-BEGIN,
 'limits':['Saved bytes/clocks/pstats independently verified without calling source_proof or models/native/C.',
 'cProfile is enabled; timings include its overhead. Nested cumulative times overlap and must not be added. This does not establish unprofiled savings or percentage of full96/complete request.',
 'Supports testing reusable static analysis with byte/source and loaded dependency invalidation; dynamic current/cut/ACK/deadline checks are not static proof.']}
with (DEST/'root_saved_review_001.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'status':result['status'],'sha256':sha(DEST/'root_saved_review_001.json'),'proof_pairs':65,'profiled_total_seconds':result['profiled_original_seconds']}))
