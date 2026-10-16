from pathlib import Path
import json
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture_campaign as c

HERE = Path(__file__).resolve().parent
DEST = HERE.parent/'initial_owner_route_single_capture_campaign_prepare_001'
EXPECTED = '5ac870bdd01f09eefdf4b5e552238abc3a730745daeb04590acbb6ac3a539ddc'
assert c.sha(DEST/'source_preparation.json') == '88625ec5c1082aa5a393ad03b2db94aaa78ba9e49e7a6a80d04efdbc18a2e136'
assert c.sha(DEST/'readiness_r1_001.json') == 'cbc5d5629d25f4bd370db4c83d4e09e8857e824c8d8df44209345347d1ecd684'
assert not any((DEST/name).exists() for name in ('campaign_outer_claim.json', 'execution_claim.json', 'external_application_wall.json', 'receipt.json'))
plan = c.verify_plan(DEST, EXPECTED)
assert len(plan['source_sha256']) == 190
for path, digest in plan['source_sha256'].items():
    assert c.sha(path) == c.sha(DEST/plan['source_archive'][path]) == digest, path
c.source_reference(plan['single_capture_verifier_source'], 156, plan['source_sha256'])
assert len(plan['compiled_source_archive_sha256']) == 67
for path, digest in plan['compiled_source_archive_sha256'].items():
    assert c.sha(path) == digest, path
for pure_key, xml_key, count in [('single_capture_campaign_pure','pure_XML',27), ('single_capture_verifier_pure','single_capture_verifier_XML',117)]:
    ref, xr = plan[pure_key], plan[xml_key]
    assert c.sha(ref['path']) == ref['sha256'] and c.sha(xr['path']) == xr['sha256']
    pure = c.read(ref['path']); rows = ET.parse(xr['path']).getroot().findall('.//testcase')
    assert pure['status'] == 'passed' and pure['source_changed'] == [] and pure['tests'] == count
    assert len(rows) == count and not any(n.tag in ('failure','error','skipped') for r in rows for n in r)
    assert pure['XML_sha256'] == xr['sha256']
    for path,digest in pure['source_sha256'].items():
        assert c.sha(c.ROOT/path) == c.sha(Path(ref['path']).parent/'source'/path) == digest
base = c.read(plan['frozen_entry_codec_campaign']['path'])
for key in ('image','expected_READY','row_order','rows','input_file_sha256','compiled_source_archive_sha256'):
    assert plan[key] == base[key], key
for name,digest in plan['input_file_sha256'].items():
    assert c.sha(DEST/'inputs'/(name+'.json')) == digest
assert c.sha(plan['native_binary']['path']) == plan['native_binary']['sha256'] == '845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be'
assert c.sha(plan['environment']['interpreter']) == plan['environment']['interpreter_sha256'] == '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
for folder, expected in [
    ('initial_single_capture_verifier_source_prepare_001','d96fbc473c34973f6148f275baa4b34147889708f6ecd7cef5442c3bedd191d7'),
    ('initial_single_capture_integration_source_prepare_001','af960a559c9e09e7762ddbbfc5285c9f57133e29533d2786115b2b55a08210f4')]:
    assert c.sha(HERE.parent/folder/'independent_narrow_review_control_timers_001.json') == expected
template = (HERE/'invoke_entry_codec_actual18_001_measured.ps1').read_text(encoding='utf8')
replacements = {
    'initial_owner_route_entry_codec_campaign_prepare_001':'initial_owner_route_single_capture_campaign_prepare_001',
    '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a':EXPECTED,
    'launch_initial_owner_route_entry_codec_campaign':'launch_initial_owner_route_single_capture_campaign',
    'f3710fce799768f22b707346a3309b73734dc4bc6a17c3ccd08673e5b62ed9f9':'1f81e00299f1db4b9b1f69928c1358d300bb432e05b9691feb6bebcc2aaeefba',
    'g31.initial_owner_entry_complete_codec.external_wall.v1':'g31.initial_owner_single_capture.external_wall.v1',
    'All prior native/saved jobs closed. Offline communication conformance002 ended at its hard cap and is preserved. Fixed bridge kernel diagnostic completed before this fresh native dispatch. All agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this exclusive performance window closes. Unrelated user/system load is not controlled.':'Prior model ABBA24 and original digest32 diagnostics closed. Agents have no active child runs and are restricted to light source/report work; no new pure, native, compile, benchmark or heavy I/O during this performance window. Unrelated user/system load is not controlled.',
    'Full Python parent launch through exit: imports/prechecks, owned600s tree, native027 entry/exit acceptance,18 fresh H40 branches, actual fixed or finite2 initial-A roots, one pure JSON predictor startup/RPC/close, all policy/codec/complete required outbox proof/endpoint and physical export, saved full refresh/outbox/endpoint/RPC/physical verification with actual entry predicate in both root replay layers, repaired complete verifier globals and full strict evidence codec, parent final receipts. Root walls and cold costs remain separate; nothing divided by18 and no physical/shared cost subtraction.':'Full Python parent launch through exit: imports/prechecks, owned600s tree, native027 entry/exit acceptance,18 fresh H40 branches and all5 physical jobs, actual fixed or finite2 initial-A roots, one pure JSON predictor startup/RPC/close. Every A initial/A final/B collection uses the same fresh single getter triplet; unchanged policy, codec, complete outbox proof and actual source predicates. Failure-aware saved verifier keeps all18 branches and three endpoint slots, reported physical facts separate from certified roots, checker errors saved before completion gate. Root walls and cold costs remain separate; nothing divided by18 or subtracted. No C normalizer added.'
}
for old,new in replacements.items():
    assert old in template, old
    template = template.replace(old,new)
template = template.replace("if (Test-Path -LiteralPath $taskDestination) {throw 'Preserve prior external measurement'}", "if ((Test-Path -LiteralPath $taskDestination) -or (Test-Path -LiteralPath (Join-Path $taskFolder 'campaign_outer_claim.json'))) {throw 'Preserve prior external measurement or attempt'}")
template = template.replace("$taskDestination=Join-Path $taskFolder 'external_application_wall.json'", "if ((Get-FileHash -LiteralPath $taskReady.root_review.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReady.root_review.sha256) {throw 'Root review changed'}\n$taskDestination=Join-Path $taskFolder 'external_application_wall.json'")
template += "\nif ($taskWall -gt 600) {throw 'Whole Python single capture campaign budget exceeded'}\n"
wrapper = HERE/'invoke_single_capture_actual18_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f: f.write(template)
review = {
    'schema':'g31.single_capture.actual18.root_review.v1','campaign_sha256':EXPECTED,
    'root_review_script_sha256':c.sha(__file__),'wrapper_sha256':c.sha(wrapper),
    'source_current_and_archive_count':190,'compiled_archive_count':67,'pure_tests':[27,117],
    'native_calls':0,'predictor_evaluations':0,'C_extension_loads':0,'raw_saved_reads':0,
    'notes':[
        'Root read final campaign, launcher, preparation and 27 tests; full failure-aware verifier and its28 new tests plus original checker dependencies already reviewed.',
        'Only four concrete branch bindings and schema change. Exact inverse AST worker verifier import and status gate after saved verification; original complete namespace retained.',
        'Original169/135 and integration153/endpoint131/verifier156 current/archive sources retained; 190 source union and67 compiled archives checked.',
        'Source-only narrow independent integration and verifier reviews checked; these do not establish actual getter side-effect equivalence.',
        'All18 inputs/image/READY unchanged. One native worker, shared600 cap, fullH40/all5 physical audit, no C normalization or scoped public-model optimization combined.',
        'Verified unknown roots may remain in cohort; invalid or audit-error reports prevent completed receipt. All endpoint slots and RPC denominators retained.',
        'Acceptance requires complete saved verification with unchanged sources and outer exit0/whole<=600; no automatic overall goal or100ms/full32 claim.'
    ]}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready = {'status':'ready_for_one_bounded_actual_attempt','campaign_sha256':EXPECTED,
    'wrapper_sha256':c.sha(wrapper),'root_review':c.reference(DEST/'root_source_review_001.json')}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'status':ready['status'],'review_sha256':c.sha(DEST/'root_source_review_001.json'),
    'ready_sha256':c.sha(DEST/'root_ready_001.json'),'wrapper_sha256':c.sha(wrapper)}))
