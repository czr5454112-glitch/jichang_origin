from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'complete_C_publisher_profile_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='5b9ff4bd5f643bf64c47fb9e5f55afc6914af5eee1bbfe8ca11f6bd51f3c0c85'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/'source'/Path(p).relative_to(ROOT))
for key in ('pure','pure_XML'):assert sha(plan[key]['path'])==plan[key]['sha256']
assert sha(plan['python'])==plan['python_sha256']
xml=ET.parse(plan['pure_XML']['path']);assert len(xml.findall('.//testcase'))==8
assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
assert len(plan['order'])==18 and plan['hard_seconds']==120
assert not any((DEST/n).exists() for n in ('execution_claim.json','external_application_wall.json'))
body=(HERE/'invoke_planning_v2_digest_diagnostic_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'planning_v2_digest_prepare_002':'complete_C_publisher_profile_prepare_001',
 'f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187':expected,
 'ready_for_one_planning_v2_digest_diagnostic':'ready_for_one_complete_C_publisher_profile18',
 'launch_planning_v2_digest_v2 --execute --output $taskFolder --plan-sha256 $taskPlanSha':'profile_complete_c_publisher_saved18 --execute --output $taskFolder --expected-plan $taskPlanSha',
 'g31.planning_v2_digest_diagnostic.external_wall.v1':'g31.complete_C_publisher_profile18.external_wall.v1',
 'fixed_query_rows=2;digest_calls=32;C_extension_loads=0':'fixed_historical_roots=18;profiled_publishers=18;direct_support_preflight_publishers=18;C_extension_loads=1',
 'Fixed two historical v2 query rows,new27212/new27215,allone-envelope denominators.32 original digest calls in8ABBA batches,A16 original and B16 same original under cProfile,not optimization. Same saved native payload digest,complete original compressed/raw hashes and all bounded builtin/schema guards. Four profiles verified against original function counts. All source/input/guard/hash/export/readback/exit inside120. No fullpolicy or600 attribution and no100ms claim.':'Fixed18 historical complete entry-codec records,including16closed2unknown. Accepted C-normalizer complete publisher unchanged;18directsupport preflights and18cProfiles enclosing fresh root construction through append/return. Full output saves precede comparison, exact all fields/order/types/floathex and regenerated clocks checked, saved full records reread. All old source/toolchain6124/runtime/binary/raw guards plus new sources preserved. Setup,C load,all36publisher calls,profiles/exports/readback/cleanup/exit within120. Instrumented diagnostic only; overlapping cumulative times, no uninstrumented speedup/native100ms/full32 or online utility claim.',
 'Whole Python planning_v2_digest_diagnostic budget exceeded':'Whole Python complete C publisher profile18 budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_C_publisher_profile_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.complete_C_publisher_profile18.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':len(plan['sources']),'pure_tests':8,'real_raw_decodes':0,
 'notes':['Root authored/read new fixed18 profile driver,8 synthetic controls andowned120 pure runner;8passed internal10.764999999999418s, no exterior pure clock claimed.',
 'Accepted original C publisher callable and original18fixtures/toolchain guards remain; source union includes original145 plus new3. All model/native calls0, Cdata provider loaded explicitly only at actual worker.',
 'Each model-free profile begins before root construction, includes publication/appendidentity; full result saved first, semantic fields/clock intervals checked and full saved record reread.18originalunknown labels unchanged data.',
 'Additional18directsupports rerun withinwhole; defaultGC, no profile cost presented as uninstrumented speed or complete native latency.',
 'Accept exact_all18_profiled_diagnostic,18exact0profileunknown,unchangedsource/runtime andexit0whole<=120. Historical2unknown roots remain unknown; diagnostic exactness does not certify those roots.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_complete_C_publisher_profile18','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper),'source_count':len(plan['sources'])}))
