from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=HERE.parents[3]
DEST=OUT/'delivered_peer_cost_prepare_004'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='904afc076ef0d94d5a55356715473cedf9469715358debb473b2721b64e4cd62'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['sources'])==78
for name,digest in plan['sources'].items():assert sha(ROOT/name)==digest==sha(DEST/'source'/name)
for item in plan['files']:assert sha(item['source'])==item['sha256']==sha(DEST/'fixtures'/item['file'])
assert sha('C:/PROGRAMING/python3.11.9/python.exe')==plan['python_sha256']
for ref in plan['pure'].values():assert sha(ref['path'])==ref['sha256']
xml=ET.parse(plan['pure']['xml']['path']);assert len(xml.findall('.//testcase'))==57
assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert plan['calls']==32 and plan['arms']==['A','B','B','A'] and plan['shared_seconds']==120
assert not any((DEST/n).exists() for n in ('execution_claim.json','external_application_wall.json'))
body=(HERE/'invoke_planning_v2_digest_diagnostic_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'planning_v2_digest_prepare_002':'delivered_peer_cost_prepare_004',
 'f9b74d4f92b247a228fa891d000bae1bd00f8d038253562adec31e9e272e1187':expected,
 'ready_for_one_planning_v2_digest_diagnostic':'ready_for_one_delivered_peer_actual32_attribution',
 'launch_planning_v2_digest_v2 --execute --output $taskFolder --plan-sha256 $taskPlanSha':'measure_delivered_peer_cost_v4 --execute --output $taskFolder --admission $taskPlanSha',
 'g31.planning_v2_digest_diagnostic.external_wall.v1':'g31.delivered_peer_actual32.external_wall.v4',
 'fixed_query_rows=2;digest_calls=32;C_extension_loads=0;model_calls=0':'fixed_query_rows=2;validator_calls=32;maximum_digest_calls=32;C_extension_loads=0;model_calls=0',
 'Fixed two historical v2 query rows,new27212/new27215,allone-envelope denominators.32 original digest calls in8ABBA batches,A16 original and B16 same original under cProfile,not optimization. Same saved native payload digest,complete original compressed/raw hashes and all bounded builtin/schema guards. Four profiles verified against original function counts. All source/input/guard/hash/export/readback/exit inside120. No fullpolicy or600 attribution and no100ms claim.':'Fixed2 original queries27212/27215 with exact owner/queryclock/all envelopes and original005 static node contract.32 complete originaldelivered_peer calls ABBA, A16unchanged/B16same code fullglobals with only originaldigest nestedtimer. All accepted/absent/rejected fulloutcomes saved; resourceerrors unknown. Strict clock/count/index types and closedmetrics added in v2 afterindependentreview, original38pure/prepare001 preserved unexecuted. All78source/current/archive/runtime, inputhash/decode/metadata/canonicalmutationguards,32outcomes/export/readback/exit inside120. B timer overhead retained, no optimization/per-activationfrequency/fullpolicy/full-day/100msclaim.',
 'Whole Python planning_v2_digest_diagnostic budget exceeded':'Whole Python delivered_peer attribution budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_delivered_peer_root_003_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.delivered_peer_actual32.root_review.v4','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review_script_sha256':sha(__file__),'source_count':78,'pure_tests':57,'actual_validator_calls':0,'raw_decodes':0,
 'prior_independent_findings':{'path':str(OUT/'delivered_peer_cost_source_review_control_timers_001.json'),
    'sha256':'3106547bdabe2f2c95da2a2a5ad91bdbb0e79f4cc9d43d69eac01373d74ea82f'},
 'notes':['Originalvalidator code and allglobals preserved except timed originaldigest. No batchedwriter or policy checkpoint. Original ordinary rejects remain fulloutcomes; resourceerrors failunknown.',
 'Fixedstatic contract is pinned original005 public graph from same original28506 input; peer derives declaredtwoowners, not untrustedcapture; now exact querybefore==after. These are offline arguments, not a new actual policy invocation.',
 'All32 completeoutputs, source/runtime pins, rawfullhash metadata, inputnonmutation and savedorderedoutputchecks inwhole120. Timerstart/end callable interval distinct from metadata/setup. B inclusivechild subtracted once; wrapperoverhead remains.',
 'Independent source review identified bool/float/negative savedclock/count weakness beforeactual; v1 immutable38pure/prepare preserved. v2 exactclosedmetrics/nonnegativeint/index guards and52purepassed. Private prepare/execute/saved audit allboundnewchecker. Root first prelaunch source-count check then found bare reused test import absent from v2 archive; no actual run. V3 explicitly includes that source, re-passed all52 tests,76 sources; v1/v2 frozen plans and failed root review retained. V3 actual failed before child launch because preparation stdout.log already existed;0validatorcalls. V4 gives each prepare/pure/execute stage distinct exclusive logs, five additional fake stage-flow tests,57pure passed. Full original checker/worker and source pins unchanged; prior failed003 and all earlier files retained.',
 'Accept completed_original_delivered_peer_attribution/calls32/complete saved hashes and same fulloutcome perinput/source[]/outer0whole<=120; dispositions may berejected/absent and mustremain. Noactualfrequency/600completion/native100msclaim.']}
assert sha(review['prior_independent_findings']['path'])==review['prior_independent_findings']['sha256']
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_delivered_peer_actual32_attribution','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
