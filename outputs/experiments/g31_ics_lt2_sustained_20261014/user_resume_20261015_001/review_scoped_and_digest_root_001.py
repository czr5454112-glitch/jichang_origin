from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
template=(HERE/'invoke_C_publisher_saved_root_001_measured.ps1').read_text(encoding='utf8')
old_scope='Independent saved-only72 complete publisher records against18 original fixtures. Original145/169/135source and6124toolchain/raw/runtime guards; strict types/order/floathex and regenerated clocks; original event/deadline fields retained;36samples perarm and all18paired outcomes recomputed. Producer direct18C support and alias facts remain producer observations. No C loading/model/native/performance or complete100ms claim.'
configs=[
 ('scoped_public_inputs_six_cost_prepare_001','d4c69fe70c5c6bd567677f9a04c2b024b47f1a6e25a9e671a932ef8e938b6d04',
  'scoped_inputs_six_cost','measure_scoped_public_inputs_six --execute --output $taskFolder --expected-plan $taskPlanSha',
  'shared_owned_seconds=120;fixed_inputs=6;model_calls=24;C_extension_loads=0;native_simulation_calls=0',
  'Fixed6ABBA24 conditional model calls; same complete predictions and chronology as frozen originals. Every B includes one fresh public-input construction/private binding and all unchanged guards/model calls, every input read deepcopies. Initial contexts/setup, exports, full checks, source pins and process exit in whole120. DefaultGC; scope-cycle reclamation may occur after sample return, so no fullcleanup-per-sample or complete request100ms claim.',
  ['Root authored driver and candidate; independent legal review994bdd2a74c10bbae7388b9116af8f3be164110ac2757d7de35b02d4a92951ad read/retained.',
   '16candidate functional cases pass. Read strict fixed6ABBA24,fullsavedpredictions and original107+new151 closure; no native/C.',
   'Explicit serial pinned builder scope; concurrent configuration mutation and changed allocation failure timing not equivalent. All unknowns remain24 denominator.',
   'Accept only passed_fixed_six_ABBA24_complete_prediction,exact24unknown0,unchangedpins,defaultGC,externalexit0 andwhole<=120. Speed only conditional model component.']),
 ('planning_v2_digest_prepare_002','f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187',
  'planning_v2_digest_diagnostic','launch_planning_v2_digest_v2 --execute --output $taskFolder --plan-sha256 $taskPlanSha',
  'shared_owned_seconds=120;fixed_query_rows=2;digest_calls=32;C_extension_loads=0;model_calls=0;native_simulation_calls=0',
  'Fixed two historical v2 query rows,new27212/new27215,allone-envelope denominators.32 original digest calls in8ABBA batches,A16 original and B16 same original under cProfile,not optimization. Same saved native payload digest,complete original compressed/raw hashes and all bounded builtin/schema guards. Four profiles verified against original function counts. All source/input/guard/hash/export/readback/exit inside120. No fullpolicy or600 attribution and no100ms claim.',
  ['Root read complete v2driver/ownedlauncher and58functional tests. Exact real extension schema correction preserved failed001 and its sources.',
   'Two saved actual queries bounded decode32MiB,one envelope each,32calls exact; no extra digestreference or native/model/C.',
   'A/B changes only profiler instrumenting original callable. Direct hashes remain required; everycall guard/fingerprint and outputcheck insidewhole, isolatedspan labels nested.',
   'Accept completed_original_digest_attribution and passed_saved_attribution,32records8batches4profiles,unchangedpins,defaultGC,externalexit0 andwhole<=120.'])]
for folder,expected,label,command,counts,scope,notes in configs:
    dest=OUT/folder;assert sha(dest/'plan.json')==expected
    plan=json.loads((dest/'plan.json').read_bytes())
    if 'source_sha256' in plan:
        for path,digest in plan['source_sha256'].items():assert sha(path)==digest==sha(dest/plan['source_archive'][path]),path
        assert sha(dest/'independent_narrow_review_legal_001.json')=='994bdd2a74c10bbae7388b9116af8f3be164110ac2757d7de35b02d4a92951ad'
    else:
        for rel,digest in plan['sources'].items():assert sha(ROOT/rel)==digest==sha(dest/'source'/rel),rel
    assert not any((dest/name).exists() for name in ('execution_claim','execution_claim.json','external_application_wall.json','campaign_outer_claim.json'))
    replacements={
      'C_publisher_saved_review_prepare_001':folder,
      '510ee1590e4c871eff6f25dd2ef5bf69262850575aaf50fb42e5cb1b086ce1d9':expected,
      'ready_for_one_independent_C_publisher_saved_review':'ready_for_one_'+label,
      'review_complete_root_c_publisher_saved --execute --output $taskFolder --expected-plan $taskPlanSha':command,
      'g31.C_publisher.independent_saved.external_wall.v1':'g31.'+label+'.external_wall.v1',
      'shared_owned_seconds=120;fixed_inputs=18;saved_publisher_rows=72;C_extension_loads=0;model_calls=0;native_simulation_calls=0':counts,
      old_scope:scope,
      'Whole Python independent C publisher saved review budget exceeded':'Whole Python '+label+' budget exceeded'}
    if label=='planning_v2_digest_diagnostic':replacements["'execution_claim'"]="'execution_claim.json'"
    body=template
    for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
    wrapper=HERE/('invoke_'+label+'_root_001_measured.ps1')
    with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
    review={'schema':'g31.'+label+'.root_review.v1','plan_sha256':expected,'root_review_script_sha256':sha(__file__),
        'wrapper_sha256':sha(wrapper),'notes':notes,'dispatched':False,'raw_reads_in_this_root_review':0}
    with (dest/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
    ready={'status':'ready_for_one_'+label,'plan_sha256':expected,'wrapper_sha256':sha(wrapper),
        'root_review':{'path':str(dest/'root_source_review_001.json'),'sha256':sha(dest/'root_source_review_001.json')}}
    with (dest/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
    print(json.dumps({'label':label,'review_sha256':sha(dest/'root_source_review_001.json'),
        'ready_sha256':sha(dest/'root_ready_001.json'),'wrapper_sha256':sha(wrapper)}))
