"""Root review of current gate002 complete-evidence ABBA, no sampling here."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_complete_root_evidence_codec as m
c=m.c;here=Path(__file__).resolve().parent
out=c.OUT/'complete_root_evidence_codec_pair_prepare_001'
expected='11451e03fd2ff9ccda080b82a5fa2497b55f37463f0c30b07fd7467fda31d9ff'
plan=m.verify_pins(out,expected)
assert c.sha(out/'preparation.json')=='53d5266189bb2d672c697c3d4a09f8db9ed5577c408ae413a9a0ed691c84f49e'
assert len(plan['source_sha256'])==135 and len(plan['row_order'])==72 and len(plan['input_raw'])==18
assert plan['hard_timeout_seconds']==240 and plan['calls_per_arm']==36
loaded=c.check_loaded_sources(plan)
counts={}
for prefix,total in (('codec',68),('harness',18)):
    ref=plan[prefix+'_pure_XML']
    value={k:sum(int(s.get(k,0)) for s in ET.parse(ref['path']).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert value==dict(tests=total,failures=0,errors=0,skipped=0)
    counts[prefix]=value
assert c.sha(m.candidate.codec.__file__)=='7e05b5c16ac305ba13024c9787306f5f7ced7b349c938a8c544ab022696fd3cb'
assert c.sha(m.candidate.__file__)=='94cfb9f16a36d6dfb02c95eb62517285fc2a0d48c18a5c83732bddc537283c20'
assert m.bindings('A')[0].__code__ is m.candidate.frozen.EVIDENCE.__code__
assert m.bindings('B')[0].__code__ is m.candidate.EVIDENCE.__code__
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_complete_codec_pair_001_measured.ps1'
text=(here/'invoke_single_root_evidence_002_measured.ps1').read_text(encoding='utf8')
for before,after in {
 'single_root_evidence_pair_prepare_002':'complete_root_evidence_codec_pair_prepare_001',
 '086dd891c9b60a2700045c5c75da0cd9d67776f541e1c8c9eb215f82d8ba36cf':expected,
 'measure_single_root_evidence':'measure_complete_root_evidence_codec',
 'g31.single_root_evidence.external_application_wall.v1':'g31.complete_root_evidence_codec.external_application_wall.v1',
 'owned ABBA72 full evidence/return mock':'owned ABBA72 currentgate002 complete-query-proof evidence/return mock',
 'Dispatched only after the bridge owned process and independent heavy readback close; all agents confirm no active heavy tests/native/compile/benchmark during this comparison.':'Dispatched only after previous native and saved audit jobs close; all agents confirm no active heavy tests/native/compile/benchmark during this comparison.',
}.items():
    assert before in text;text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(text)
report={'schema':'g31.complete_root_evidence_codec.root_review.v1',
 'status':'passed_fixed_saved18_mock_gate_ready','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'plan_sha256':expected,'preparation':c.reference(out/'preparation.json'),
 'live_archive_source_count':135,'loaded_sources_verified':len(loaded),'pure_counts':counts,
 'rules':[
  'A is current actualgate002 complete root evidence, not an older inflated baseline. Exactly18 fixed roots, everyunknown retained, ABBA4perroot/72total/36perarm.',
  'Original normalize makes one fresh exact builtin ordered tree, with identical depth/node/key/scalar restrictions. Only its already-redundant artifact_encode _tree call is removed by exact reversibleAST proof.',
  'Original strict decoder, duplicate-key/finite/builtin/size checks remain. On this closed finite builtin strictUTF8 ensure_asciiFalse domain, same original compact JSON encoding distinguishes ordered keys, exact scalar types and all finitefloatbits including signedzero. Surrogate failures remain; ensure_asciiTrue collision is explicitly excluded and tested.',
  'Decoded output is C JSON reencoded and compared to original bytes before normalized evidence escapes. No caller-supplied trust bit, shared normalized alias or dynamic native capability is created.',
  'Original body timestamp remains immediately after firstencoding; all checkwork is still within complete evidence call and outerrootclock. Original methodidentity guard, hash/ledger/returncodec/publisher append and caller tail remain.',
  'One originalraw decoded at a time during setup; complete roots retained, not summarized. Complete outbox/query proof comes from the same saved fixture in both arms. Sourceevent/deadline clocks remain data; all regenerated clockfields/formulas and full result topology validated.',
  'All72 gzip outputs hashed and read back with full ordered/type comparisons; input fingerprints before/after detect mutation. Loading/setup/exports/hash/readback/sourcechecks/cleanup allinside fixed240 or fullouterPythoninterval.',
  'No native/predictor, firsthop, scheduler or online policy execution. Samples represent complete data-only evidenceconstruction, never complete newrequest100ms.',
 ],
 'source_proof':m.candidate.source_proof(),
 'limits':['No guaranteed performance improvement before results.','Agentexclusive dispatch required; unrelated systemload uncontrolled.',
           'Finite2/full32 complete100ms and originaldaybusiness goals remain open.'],
 'producer':c.reference(__file__),'wrapper':c.reference(wrapper),
 'native_calls':0,'new_predictions':0,'benchmark_calls_in_review':0}
review=out/'root_source_review_001.json';ready=out/'root_ready_001.json'
with review.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
with ready.open('x',encoding='utf8') as f:json.dump({'status':'ready_for_one_bounded_mock_attempt',
 'plan_sha256':expected,'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
 'benchmark_dispatched':False,'fixed_calls':72,'owned_seconds':240},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper)}))
