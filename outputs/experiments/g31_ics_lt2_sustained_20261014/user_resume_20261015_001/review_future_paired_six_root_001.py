from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
OUT=HERE.parent
DEST=OUT/'future_later_paired_six_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected='5628a1262101d3a8bdcb21733d2185a538f752e81df12c26f207ebbb62ad9fbd'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256'])==156
for p,d in plan['source_sha256'].items():assert sha(p)==d==sha(DEST/plan['source_archive'][p])
for p,d in plan['evidence_sha256'].items():assert sha(p)==d
assert sha(plan['environment']['python'])==plan['environment']['sha256']
assert plan['counts']==dict(initial_engines=6,initial_advances=6,prefix_same_resumes=8,future_forks=12,future_resumes=12)
assert plan['maximum_prefix_cuts']==14 and plan['hard_application_seconds']==120
assert len(plan['order'])==6 and len(plan['rows'])==6
for folder,n in [('future_later_fork_pure_002',62),('future_later_paired_driver_pure_001',22)]:
    xml=ET.parse(OUT/folder/'tests.xml')
    assert len(xml.findall('.//testcase'))==n
    assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
assert not any((DEST/n).exists() for n in ('execution_claim.json','external_application_wall.json'))
template=(HERE/'invoke_continuation_six_root_001_measured.ps1').read_text(encoding='utf8')
replacements={
 'conditional_continuation_six_prepare_001':'future_later_paired_six_prepare_001',
 'dd91512a60cc6ef336842ab93a5341a47ebd90276470116b24e8cb4e90917c56':expected,
 'ready_for_one_bounded_conformance_attempt':'ready_for_one_fixed_future_paired_six_attempt',
 'validate_live_conditional_continuation --execute':'validate_future_later_paired_suffix --execute',
 'g31.same_action_continuation_six.external_wall.v1':'g31.future_later_paired_six.external_wall.v1',
 'expected_cutpoints=14;expected_suffixes=14;expected_resume_calls=39;expected_graph_forks=28':'maximum_prefix_cutpoints=14;expected_suffixes=12;expected_prefix_same_resumes=8;expected_future_resumes=12;expected_graph_forks=12',
 'Fixed6 initial model engines and14 independently forked same-action suffixes from four explicit call frames;39 resumes and28 forks, no prefix reinitialization. All20 terminal output bytes match frozen lazy; each reached cut graph and terminal graph exact to mainline, original retained cuts mutation-isolated. All imports/pins/model/forks/outputchecks/exports/exit within120. Factory-made model states only, no native authority, actualopaqueID relation, hiddenstatecoverage, onlineefficacy or100ms.':'Fixed6 original initial contexts, at most14 prefix cuts,8 same-action prefix resumes,12 future forks and12 suffix resumes. Both later choices cloned from same unconsumed first knownB cut before either suffix. Strict wire/current/past-action guards; unsupported firstB remains unknown with fixed6/12 denominator. Full returned predictions saved before frozen target reads; exact bytes/types/order/floathex/chronology, graph only allowed action change, parent/sibling alias isolation.156source/current/archive/runtime guards. All imports/setup/clones/model/audit/export/exit within120. No native authority, actual opaque-ID relation, hidden-state coverage, online utility or100ms claim.',
 'Whole Python continuation six-input budget exceeded':'Whole Python future paired six-input budget exceeded'}
for old,new in replacements.items():assert template.count(old)==1,old;template=template.replace(old,new)
wrapper=HERE/'invoke_future_paired_six_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(template)
review={'schema':'g31.future_later_paired_six.root_review.v1','plan_sha256':expected,
 'root_review_script_sha256':sha(__file__),'wrapper_sha256':sha(wrapper),'source_count':156,
 'new_fork_pure_tests':62,'new_driver_pure_tests':22,'model_calls':0,'raw_decodes':0,
 'notes':['Root read complete future fork source,43 new fork tests with19 retained core tests, complete driver and22 tests. Final scalar-to-dict encoding correction reviewed; failed pure001 preserved.',
 'Effective later-action consumers source-inventoried; collect occurs before decision read; obsolete scheduled later read unreachable under unchanged lifecycle noop. Existing four frames kept; no physical handlers edited.',
 'Only known firstB postcollect/predecision may fork; first unsupported cut stays unknown. No adaptive replacement, prefix restart, second collect or extra retry.',
 'Both choice children cloned before suffixes; fresh graph identities disjoint, parent/sibling unchanged; only later_action changed, all past action fields fixed. Complete predictions saved before target reads.',
 'Fixed6/12 full denominator and declared6start/6advance/8prefixresume/12fork/12suffixresume with maximum14cuts; source/input/runtime/exit guards included in120.',
 'Accept exact_six_paired_future_suffixes only with6exact0unknown and all counts exact; outer exit0 and whole<=120 independently required. Retrospective comparison cannot prove hidden-state coverage, actual-ID relation, online effectiveness or full32/100ms.']}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_fixed_future_paired_six_attempt','plan_sha256':expected,'wrapper_sha256':sha(wrapper),
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')}}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review':sha(DEST/'root_source_review_001.json'),'ready':sha(DEST/'root_ready_001.json'),'wrapper':sha(wrapper)}))
