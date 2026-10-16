"""Freeze existing pure evidence and the next design; no simulation or policy run."""
import hashlib
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
PAIR=OUT/'preference_request_context_pair_001'
TEST=OUT/'preference_request_context_tests_001'
TARGET=OUT/'preference_request_context_summary_001.json'
assert not TARGET.exists()
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())
report=read(PAIR/'worker/report.json');plan=read(PAIR/'worker/plan.json')
assert report['status']=='passed_exact_pure_pair' and report['source_changed']==[] and len(report['rows'])==24
for relative,digest in plan['source_sha256'].items():
    assert sha(ROOT/relative)==digest==sha(PAIR/'worker/source'/relative)
suite=ET.parse(TEST/'worker/tests.xml').getroot().find('testsuite')
assert suite is not None and (int(suite.attrib['tests']),int(suite.attrib['errors']),int(suite.attrib['failures']),int(suite.attrib['skipped']))==(41,0,0,0)
summary={}
for name in ('reference','context'):
    values=[r['timing'][name]['wall_ns']/1e6 for r in report['rows']]
    summary[name]={'batch_count':len(values),'each_batch_candidates':32,'minimum_ms':min(values),
        'median_ms':statistics.median(values),'maximum_ms':max(values),'sum_ms':sum(values),
        'batches_below_or_equal_100ms':sum(v<=100 for v in values)}
result={'schema':'g31.preference_request_context.frozen_pure_evidence.v1',
    'status':'complete_pure_differential_positive_performance_candidate_not100ms',
    'actual_inputs':'Fixed vector00 supplied A/B bundles for each of six saved cases. Outcomes never enter either predictor.',
    'exactness':'All full ordered output fields, completion doubles, commands, events and unknown flags match for all24 paired batches.',
    'summary':summary,'sum_reduction_fraction':1-summary['context']['sum_ms']/summary['reference']['sum_ms'],
    'pure_tests':41,'runtime_source_archive_count':len(plan['source_sha256']),
    'profile_interpretation':{
        'reference_potential_calls_6x32':7248,'context_potential_calls_6x32':222,
        'context_direct_score_potential_constructions':6,
        'remaining_potential_calls':'216 arise inside the unchanged input guard scenario constructors; these were not removed or disguised.',
        'context_profile_total_seconds':4.282,'context_guard_compilation_cumulative_seconds':.8614679,
        'context_original_event_run_cumulative_seconds':2.664,
        'generated_function_profile_counts':'Repeated dynamically compiled code objects can collide in pstats textual keys; do not interpret its generated guard row count as total calls. Counter tests establish once-per-request validation.',
        'not_exclusive_subtraction':'Cumulative profile fields overlap and are diagnostic only.'},
    'limits':['Pure model batch, not complete business request or native/online authority.',
        'Both orders measured with background work uncontrolled; observed paired reduction is not an isolated machine or future latency guarantee.',
        'All24 candidate batches still exceed100ms before native source/receiver validation, commit, ACK and response costs.',
        'Closed builtin supplied-data trees only; custom containers and cycles are explicitly rejected by context preparation.',
        'Every request currently pays source hash checks, AST proof/compilation, input snapshot/deepcopy, fingerprint, all original dynamic guards and32 complete simulations.'],
    'next_design_only':{
        'static_implementation':'A separately timed process-local immutable implementation may compile the exact guard AST once. It may retain code/constants/source pins only, never bundle/action/potential/request data. Each request still rechecks source identity and executes every dynamic guard; creates private snapshot/fingerprint/potential and candidate states.',
        'cold_warm_accounting':'Report cold implementation construction plus first request without amortization, and separately declared already-initialized-host warm requests. Preserve full parent launch wall and all new setup. Do not relabel cold cost as excluded.',
        'deadline_contract':'Keep maximum32 initial/4 later candidates for every method. Start a common monotonic deadline before request observation/preprocessing; reserve actual measured commit/revalidation/codec work. All not evaluated candidates remain unknown_unexecuted, never infeasible or protected.',
        'inflight_prediction':'Initially check deadlines only between complete candidate evaluations. An evaluation overrun remains an actual overrun. Do not truncate an event loop and present a completed prediction.',
        'incumbent':'Deadline alone supplies no legality. Returning a prior installed decision requires actual current source identity/lease/permissions and declared operation completion evidence; otherwise return unknown/replan-needed, retain pending ACK/retry lineage and charge it.',
        'fairness':'Same deadline/reserve/max-domain and input facts for coordinate/plateau/pair/enumeration, preserving every failure/open root. No fitted per-method budget or outcome-selected truncation.',
        'not_implemented':True,'native_dispatch_authorized':False},
    'evidence_sha256':{},'native_executions':0,'complete_100ms_certified':False}
for path in [Path(__file__),PAIR/'worker/plan.json',PAIR/'worker/report.json',PAIR/'receipt.json',PAIR/'external_process.json',
             PAIR/'worker/reference.pstats',PAIR/'worker/context.pstats',TEST/'worker/tests.xml',TEST/'receipt.json',TEST/'external_process.json',
             ROOT/'tests/test_g31_circulation_preference_request_context.py']:
    result['evidence_sha256'][str(path)]=sha(path)
TARGET.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'status':result['status'],'summary_sha256':sha(TARGET),'source_count':len(plan['source_sha256'])}))
