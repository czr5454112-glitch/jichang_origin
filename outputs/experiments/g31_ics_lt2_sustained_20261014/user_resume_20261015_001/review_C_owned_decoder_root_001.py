from pathlib import Path
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_complete_root_owned_decode_c as a
HERE=Path(__file__).resolve().parent
DEST=a.OUT/'complete_root_owned_decode_C_pair_prepare_001'
expected='947f7c33f012f4b4b3248cbbfe1cc037537340c3da89971160ec732d91bae00d'
assert a.sha(DEST/'plan.json')==expected
plan=a.read(DEST/'plan.json')
assert len(plan['source_sha256'])==153 and len(plan['input_raw'])==18
assert plan['row_order']==a.declarations(plan['input_raw']) and len(plan['row_order'])==72
assert plan['hard_timeout_seconds']==240 and plan['binding_source_proof']==a.binding.source_proof()
assert plan['worker_source_proof']==a.worker_source_proof()
for path,digest in plan['source_sha256'].items():assert a.sha(path)==a.sha(DEST/plan['source_archive'][path])==digest
pure=[]
for label,count in (('harness_pure',131),('binding_pure',8),('owned_pure',105)):
    ref=plan[label];path=Path(ref['path']);assert a.sha(path)==ref['sha256']
    xml=path.parent/'tests.xml';cases=ET.parse(xml).getroot().findall('.//testcase')
    assert len(cases)==count and not any(c.tag in ('failure','error','skipped') for t in cases for c in t)
    pure.append({'label':label,'receipt':ref,'XML_sha256':a.sha(xml),'count':count})
independent=DEST/'independent_narrow_source_review_legal_001.json'
assert a.sha(independent)=='2743b6fd8e0fd0becd490919c5c0cc01afa8e4b4694e55d739e1e6dba80b1968'
assert not any((DEST/n).exists() for n in ('execution_claim','external_application_wall.json','stdout.log'))
body=(HERE/'invoke_C_publisher_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'C_publisher_pair_prepare_001':'complete_root_owned_decode_C_pair_prepare_001',
 '840329a5c7eaf928f92b7c6d9a4bbfaf08bdf12260141e41f2863746e2df4072':expected,
 'ready_for_one_bounded_full_publisher_cost_attempt':'ready_for_one_same_C_owned_decoder_ABBA72',
 'measure_complete_root_c_normalizer --execute':'measure_complete_root_owned_decode_c --execute',
 'g31.C_publisher.ABBA72.external_wall.v1':'g31.C_owned_decoder.ABBA72.external_wall.v1',
 'publisher_calls=72':'declared_publisher_calls=72',
 'Fixed actual entrycodec18 x ABBA72 complete data publisher A originalPython normalization B verifiedC normalization. Complete originalcodec strictdecode hashledger publisherreturn and originaldeadline/eventclocks retained. Require18 directC fullargument preflights and72 complete saved readbacks. Imports,6124tools,145+169/135sources,18raws,runtime,load,binding,allpreflight/export/teardown/exit included in240. Mock component costs only, no actual native100ms or business effect.':'Fixedactual18xABBA72 fullpublisher A=currentverifiedC B=sameexactCprovider+owneddecode only. Fresh boundednormalization, strictUTF8/size/duplicate/nonfinite parse, canonical reencode, hashledger/publicledger_tree/fullreturn retained. No externalbytes decoder fastpath. Originalworker code/fullglobals except5explicit bindings, direct18support preflights, full72savedchecks unchanged. All153+169/135sources/6124toolchain/runtime/18rawload/Cbindings/18preflight/72samples/export/readback/cleanup/exit in240. Unknown historical2 included. Resourcefailurepoints not assertedidentical. Componentmock costs only, not newnative100ms/all-day/protection success.',
 'Whole Python complete C publisher cost budget exceeded':'Whole Python same C owned decoder cost budget exceeded'}
for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
wrapper=HERE/'invoke_C_owned_decoder_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.C_owned_decoder.root_review.v1','plan_sha256':expected,'sources':153,
 'pure':pure,'independent_narrow_source_review':{'path':str(independent),'sha256':a.sha(independent)},
 'raw_fixture_reads':0,'C_loads':0,'native_calls':0,'notes':[
 'Root fully read owned core87tests, Cbinding18tests, full72driver26tests and original C worker/verify/preflight. Independent legal source-only review no concrete blocker.',
 'A andB same original verified C facade; only B internal owneddecode _tree removed afterfresh boundednormalization+encode. Publicdecoder/ledger_tree and strictJSONcanonical checks retained; ASTsource/provenance prerequisites required.',
 'Whole original worker/launcher code reused, fullglobals only5changes; original direct_support18 unchanged and returns complete builtin support proof. C binding validated beforemocktime/proof injection; all72actualfixtures strictchecked.',
 'All72 fulloutputs andclock formulas/order/scalars/unknowns saved/readback. Historical18includes16closed2unknown. Entire startup/toolchain/source/runtime/Cload/setup/exports/exit in240. No forcedGC orclaimedpersample cyclecleanup.',
 '131combinedpure passes and prepare nowexact131,105ownedbinding+original8separate gates retained. No performance test beforethisdispatch.',
 'Accept receiptcompleted_fixed_entry_codec_C_mock_ABBA/source[] and reportpassed_exact_complete_entry18_same_C_owned_decode_ABBA72/72samples36each/direct18/GCtrue/whole<=240, not nativecomplete100ms.'],
 'wrapper_sha256':a.sha(wrapper),'root_review_script_sha256':a.sha(__file__)}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump({
 'status':'ready_for_one_same_C_owned_decoder_ABBA72','plan_sha256':expected,
 'root_review':{'path':str(path),'sha256':a.sha(path)},'wrapper_sha256':a.sha(wrapper)},f,indent=2)
print(json.dumps({'review':a.sha(path),'ready':a.sha(DEST/'root_ready_001.json'),'wrapper':a.sha(wrapper)}))
