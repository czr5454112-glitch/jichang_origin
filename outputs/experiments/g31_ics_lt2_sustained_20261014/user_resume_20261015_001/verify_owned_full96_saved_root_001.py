from pathlib import Path
from collections import Counter
import hashlib,json,gzip
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=HERE.parents[3];DEST=OUT/'owned_full32_runtime_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
encode=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
pins={'plan.json':'6f4434bcf87d8e35d709eabfed5561b6461adde71389b92c8042072a9e6c4bc5',
 'root_review_001.json':'05a8502fabb9ce7436571e4f6675b957e8f0074fd30125d0f179a727264cd312',
 'receipt.json':'a6cebda0a1321415bc5ccdf4ebd1d8889a96adf73e62e3f5af973b2b350e94ed',
 'rows.json':'54a76c29d90f182cbc96d5d5ac3c239d373e57f592e30480c3985d33c0eb6279',
 'groups.json':'1b43df223a2093cd4066a61fed73f41398e454bf6645dc8d0341a85715f9b9c5',
 'bounded_execution.json':'1725b9c3edb75e42cbcac7372bcacef845a69cfb14026462e8d197923aa32f98',
 'external_application_wall.json':'60129533dd298c95b451c8421d46823ba29933073461e8c8f4f6e12c37fc0d2e'}
for name,digest in pins.items():assert sha(DEST/name)==digest
plan=read(DEST/'plan.json');receipt=read(DEST/'receipt.json');rows=read(DEST/'rows.json');groups=read(DEST/'groups.json')
outer=read(DEST/'external_application_wall.json');bounded=read(DEST/'bounded_execution.json');review=read(DEST/'root_review_001.json')
assert outer['exitcode']==0 and 0<outer['external_application_seconds']<=360 and outer['command']==review['command']
assert sha(outer['wrapper_path'])==outer['wrapper_sha256'] and outer['bounded_execution_sha256']==pins['bounded_execution.json']
assert outer['plan_sha256']==outer['plan_after_sha256']==pins['plan.json'] and outer['root_review_sha256']==pins['root_review_001.json']
assert outer['ready_sha256']==outer['ready_after_sha256']==sha(DEST/'ready.json')
assert bounded['status']=='bounded_worker_completed' and bounded['process']['exitcode']==0
assert receipt['status']=='exact_full96_future_suffixes' and receipt['source_changed']==[]
for key in ('plan','rows','groups','entry_pins','exit_pins','loaded_entry','loaded_exit'):
    item=receipt[key];assert sha(item['path'])==item['sha256']
entry=read(DEST/'entry_pins.json');exit_pins=read(DEST/'exit_pins.json');assert entry==exit_pins
assert read(DEST/'loaded_entry.json')==read(DEST/'loaded_exit.json')
expected={str(ROOT/n):d for n,d in plan['source_sha256'].items()};expected.update(plan['evidence_sha256'])
expected.update({str(DEST/plan['source_archive'][n]):d for n,d in plan['source_sha256'].items()})
assert expected==entry
for name,digest in expected.items():assert sha(name)==digest
assert tuple(rows)==tuple(plan['order']) and len(rows)==96 and tuple(groups)==tuple(plan['group_order']) and len(groups)==48
byte_pairs=0
for key,row in rows.items():
    assert row['status']=='exact_conformance' and encode(row['action'])==encode(plan['rows'][key]['action'])
    actual=row['prediction'];target=plan['rows'][key]['comparison_only_prediction']
    assert sha(actual['path'])==actual['sha256'] and sha(target['path'])==target['sha256']
    assert gzip.decompress(Path(actual['path']).read_bytes())==gzip.decompress(Path(target['path']).read_bytes())
    byte_pairs+=1
def drop(v):
    assert 'graph_sha256' in v and 'graph_encoded_bytes' in v
    return {k:x for k,x in v.items() if k not in ('graph_sha256','graph_encoded_bytes')}
counts=Counter();point_count=0;contexts=0
for key,group in groups.items():
    assert group['status']=='exact_two_future_suffixes'
    ref=plan['groups'][key]['comparison_only_group'];assert sha(ref['path'])==ref['sha256']
    result=group['result'];old=read(ref['path'])['result'];inner=result['detail'];prior=old['detail']
    assert result['status']=='exact_two_future_suffixes' and result['diagnostic_graphs_remeasured'] is False
    assert result['prior_graph_audit_is_saved_reference_only'] is True and result['context_constructions']==1
    assert encode(inner['counts'])==encode(prior['counts'])
    assert encode(inner['points'])==encode([drop(p) for p in prior['points']])
    assert encode(inner['prefix']['point'])==encode(drop(prior['prefix']['point']))
    assert inner['prefix']['diagnostic_graphs_computed'] is False and inner['prefix']['parent_unconsumed'] is True
    assert not any(k in inner['prefix'] for k in ('parent_graph_sha256','three_mutable_graphs_disjoint','complete_graph_only_future_action_changed'))
    assert tuple(inner['suffixes'])==tuple(prior['suffixes'])
    for choice,suffix in inner['suffixes'].items():
        assert suffix['status']=='returned' and 'parent_and_unconsumed_sibling_isolated' not in suffix
        assert encode(suffix['terminal_state'])==encode(drop(prior['suffixes'][choice]['terminal_state']))
        assert encode(suffix['initial_cut_action'])==encode(prior['suffixes'][choice]['initial_cut_action'])
    counts.update(inner['counts']);point_count+=len(inner['points']);contexts+=result['context_constructions']
assert dict(counts)==receipt['counts'] and contexts==48 and byte_pairs==96
assert receipt['exact_rows']==96 and receipt['unknown_rows']==0 and receipt['exact_groups']==48 and receipt['unknown_groups']==0
result={'schema':'g31.owned_full96.independent_saved_root_review.v1','status':'accepted_complete_saved_conformance',
 'review_script_sha256':sha(__file__),'evidence_sha256':pins,'independent_full_prediction_byte_pairs':byte_pairs,
 'groups_verified':48,'retained_points_verified':point_count,'contexts':contexts,'execution_counts':dict(counts),
 'current_archived_and_evidence_files_rehashed':len(expected),'source_count':191,
 'actual_run_external_seconds':outer['external_application_seconds'],
 'scope':['Root independently compared all96 decompressed complete prediction byte strings and all48 groups retained semantic points, terminal states, future actions and counts against pinned historical outputs.','Only saved data read; no model/native/C rerun. Historical graph metrics remain historical; current run has no fabricated graph flags.','Not a paired performance comparison, native hidden-state coverage, online efficacy/protection or complete100ms certification.']}
path=DEST/'root_saved_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'root_saved_review_sha256':sha(path),'pairs':byte_pairs,'groups':48,'points':point_count,'pins':len(expected)}))
