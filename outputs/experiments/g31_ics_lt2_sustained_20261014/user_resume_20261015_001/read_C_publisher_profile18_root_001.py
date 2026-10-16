from pathlib import Path
import hashlib,json,pstats,statistics,time
BOOT=time.monotonic();HERE=Path(__file__).resolve().parent;OUT=HERE.parent
FOLDER=OUT/'complete_C_publisher_profile_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(FOLDER/'receipt.json')=='23441df00fe81c8844d44fc44f82dbd25bf30599e8af0e8c54d8d8f2e4957708'
assert sha(FOLDER/'external_application_wall.json')=='d1fa9358b248a88c6b141a27069f7b043ab14e583c4fb30232b9a696355df126'
receipt=json.loads((FOLDER/'receipt.json').read_bytes());rows=json.loads((FOLDER/'rows.json').read_bytes())
assert receipt['counts']==dict(fixed_roots=18,profiled_publishers=18,exact=18,unknown=0)
assert len(rows)==18 and sha(FOLDER/'rows.json')==receipt['rows']['sha256']
records=[]
for row in rows:
    assert time.monotonic()-BOOT<120
    for field in ('profile','functions'):assert sha(row[field]['path'])==row[field]['sha256']
    functions=json.loads(Path(row['functions']['path']).read_bytes())
    selected=[]
    stats=pstats.Stats(row['profile']['path'])
    for f in functions:
        if f['function'] not in ('_tree','artifact_decode','_check_owned_encoding','artifact_encode','iterencode','raw_decode','normalize') and 'try_normalize' not in f['function']:continue
        item=dict(f)
        if f['function']=='_tree':
            data=stats.stats[(f['filename'],f['line'],f['function'])]
            item['nonrecursive_callers']=[dict(filename=k[0],line=k[1],function=k[2],primitive_calls=v[0],total_calls=v[1],self_seconds=v[2],cumulative_seconds=v[3]) for k,v in data[4].items() if k[2]!='_tree']
        selected.append(item)
    records.append({'key':row['key'],'instrumented_outer_ms':row['elapsed_ns']/1e6,'profile_total_seconds':stats.total_tt,'functions':selected})
tree=[next(f for f in r['functions'] if f['function']=='_tree') for r in records]
ratios=[f['cumulative_seconds']/r['profile_total_seconds'] for f,r in zip(tree,records)]
result={'schema':'g31.complete_C_publisher_profile18.root_small_readback.v1','status':'checked18_small_profile_artifacts',
 'receipt_sha256':sha(FOLDER/'receipt.json'),'rows_sha256':sha(FOLDER/'rows.json'),
 'source_script_sha256':sha(__file__),'records':records,
 'summary':{'fixed_profiles':18,'tree_cumulative_ms_range':[min(f['cumulative_seconds'] for f in tree)*1e3,max(f['cumulative_seconds'] for f in tree)*1e3],
    'tree_self_ms_range':[min(f['self_seconds'] for f in tree)*1e3,max(f['self_seconds'] for f in tree)*1e3],
    'tree_primitive_calls':sorted(set(f['primitive_calls'] for f in tree)),
    'tree_total_calls_range':[min(f['total_calls'] for f in tree),max(f['total_calls'] for f in tree)],
    'tree_share_profile_cumulative_range':[min(ratios),max(ratios)],'tree_share_profile_cumulative_median':statistics.median(ratios)},
 'limits':'Read only36small producer profile artifacts and receipts. No raw/model/C/native rerun and no independent full18 output re-audit. cProfile perturbs costs; cumulative includes recursive children and overlaps parent/other cumulative times. Two tree roots may have different work; use caller data. Not uninstrumented saving or complete100ms proof.',
 'reader_seconds':time.monotonic()-BOOT}
target=HERE/'C_publisher_profile18_small_readback_001.json'
with target.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'sha256':sha(target),'summary':result['summary'],'first_tree_callers':tree[0]['nonrecursive_callers']}))
