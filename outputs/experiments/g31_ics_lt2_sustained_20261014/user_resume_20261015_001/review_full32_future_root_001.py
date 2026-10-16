from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DEST=OUT/'full32_future_suffix_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='c48367f67be44aea409369d72f632228d28839fe1580fcda6bdacdabbdf7d811'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==162
for p,d in plan['source_sha256'].items():assert sha(ROOT/p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['hard_application_seconds']==360 and plan['maximum_initial_engines']==48 and plan['maximum_future_suffixes']==96
assert len(plan['order'])==len(plan['rows'])==96 and len(plan['group_order'])==len(plan['groups'])==48
xml=ET.parse(OUT/'full32_future_suffix_pure_001/tests.xml');assert len(xml.findall('.//testcase'))==60
assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
assert not any((DEST/n).exists() for n in ('execution_claim.json','external_application_wall.json'))
body=(HERE/'invoke_future_paired_six_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'future_later_paired_six_prepare_001':'full32_future_suffix_prepare_001',
 '5628a1262101d3a8bdcb21733d2185a538f752e81df12c26f207ebbb62ad9fbd':expected,
 'ready_for_one_fixed_future_paired_six_attempt':'ready_for_one_full32_future_suffix_conformance',
 'validate_future_later_paired_suffix --execute':'validate_full32_future_suffix --execute',
 'g31.future_later_paired_six.external_wall.v1':'g31.full32_future_suffix.external_wall.v1',
 'whole_python_within_120_seconds=($taskWall -le 120)':'whole_python_within_360_seconds=($taskWall -le 360)',
 'shared_owned_seconds=120;fixed_rows=6;maximum_initial_engines=6;maximum_prefix_cutpoints=14;expected_suffixes=12;expected_prefix_same_resumes=8;expected_future_resumes=12;expected_graph_forks=12;native_calls=0':'shared_owned_seconds=360;fixed_rows=96;fixed_cases=3;maximum_initial_engines=48;maximum_prefix_cutpoints_per_group=4;maximum_suffixes=96;maximum_future_resumes=96;maximum_graph_forks=96;native_calls=0',
 'Fixed6 original initial contexts, at most14 prefix cuts,8 same-action prefix resumes,12 future forks and12 suffix resumes. Both later choices cloned from same unconsumed first knownB cut before either suffix. Strict wire/current/past-action guards; unsupported firstB remains unknown with fixed6/12 denominator. Full returned predictions saved before frozen target reads; exact bytes/types/order/floathex/chronology, graph only allowed action change, parent/sibling alias isolation.156source/current/archive/runtime guards. All imports/setup/clones/model/audit/export/exit within120. No native authority, actual opaque-ID relation, hidden-state coverage, online utility or100ms claim.':'Complete original3cases times32 Cartesian actions.16prefixes percase include earlier return_delay coordinate;48fresh A/B initial context pairs,atmost48engines96futureforks/resumes. Eachpair initial endpoints exact,only initial suppliedcontext/action enter model. Both laterchoices cloned from same unconsumed firstknownB before any suffix; strictwire/current/pastaction guards,unsupported firstcut retainsbothunknown,noadaptive replacement/restart. Complete returnedoutputs saved before targets; fullbytes/types/order/floathex/chronology andgraph/alias/count audits.162source/current/archive/evidence/runtime guards. All imports,48contextpairs,model/clones/96targets/export/exit within360;225s prior linear reference only. No scopedmodel optimization, nativeauthority,opaqueID relation,hiddenstatecoverage,onlineutility or100ms claim.',
 "if ($taskWall -gt 120) {throw 'Whole Python future paired six-input budget exceeded'}":"if ($taskWall -gt 360) {throw 'Whole Python full32 future suffix budget exceeded'}"}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_full32_future_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.full32_future.root_review.v1','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':162,'focused_pure_tests':60,'model_calls':0,'raw_decodes':0,
 'notes':['Root read complete partition/evaluator/full96driver/runner and38new+22retained tests, rechecked originalpaired run_case/audit_case. Domain2x4x2x2 means16prefix/32suffix;return_delay consumed beforeB so no8prefix shortcut.',
 'Directgroup validation exactindex/pastcoordinates/defaultrepresentative. FirstknownB strictcut only; bothchildrenbeforeeitherresume, oldfourframes/fork guards unchanged. All96denominator/48groupspersistincluding unsupported,timeout andpartialsave.',
 'Prepared96minimal initialinputs only,eachpair entireinitialendpointbytes same. Executionconstructs newA+B contexts and checksindependentjobs/trays/contract/now pergroup; no savedtarget/modeloutput input andnoopaqueID parsing.',
 'Complete suffixsave precedes targetdecode; oldpaired completebytes/types/order/floathex/fullchronology andalias/countchecks retained. Source/current/archive/runtime guards allinside360.',
 'Accept only exact_full96_future_suffixes with96exact0unknown48exactgroups48contexts48engines48advances96forks96resumes,unchangedpins andouterexit0whole<=360. Prefixresumes auditedpergroup. Exit0alone mayretainunknowns; notcompletecertificate.',
 'No v2scope/initialcontext optimization combined. Offline fullactiondomain conformance only,not hiddenstate/onlineprotection/fullrequest100ms.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_full32_future_suffix_conformance','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
