"""Source-bound next-step assessment. No predictor, benchmark or native."""
from pathlib import Path
import hashlib
import json
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PREFIX='scripts/experiments/g31_ics_circulation/'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path):return {'path':str(path),'sha256':sha(path)}
saved=OUT/'json_prediction_shards_independent_actual_review_002.json'
assert sha(saved)=='ac9ba3840225c1cb48d5d1efd43ab2a56a5e45da370085e93aee1ba83317903b'
actual=json.loads(saved.read_bytes())
names=('json_prediction_shard_client.py','json_prediction_client.py','json_prediction_worker.py',
       'json_prediction_shard_worker.py','json_prediction_image.py','public_preference_protection_request_context.py',
       'preference_wall_budget.py','native_public_preference_policy.py','research_native_public_preference.py')
report={
 'schema':'g31.after_json_shards.structural_source_assessment.v1',
 'status':'design_only_no_new_experiment',
 'evidence':ref(saved),
 'sources':{name:ref(ROOT/PREFIX/name) for name in names},
 'observed_costs':{
   'fullcaller_ms':actual['warm_fullcaller_ms'],
   'postreply_merge_codec_ledger_ms':{arm:actual['partition_statistics_ms'][arm]['merge_whole_output_codec_and_ledger'] for arm in ('single','split')},
   'nested_max_worker_compute_ms':actual['nested_max_worker_compute_ms'],
   'duplicated_worker_compute_WALL_change_fraction':actual['nested_sum_worker_compute_change_fraction'],
   'cold_ms':actual['cold_all_workers_launch_through_first_return_ms'],
   'warning':'Stage intervals are actual envelopes, not a profile attributing each memcpy/JSON pass. Removing the whole stage is impossible; no observed duration is subtracted or promised as savings.'},
 'direction1_lossless_wire_ownership':{
   'source_basis':'LogicalClient.predict deepcopies reply payload (or merge deepcopies it), JSON encode/decode roundtrips the whole result, then separately deepcopies last worker sample(s) and merged payload. Original Client already retains decoded response in its ledger. These are real repeated passes over the same current request, not history-cache misses.',
   'minimal_new_contract':'A separate private client may retain exact immutable response UTF8 bytes as audit authority, decode each response once for strict validation and transfer sole mutable ownership into one fresh caller result. Ledger retains immutable bytes plus immutable scalar identity/clocks; no caller-returned object aliases mutable evidence. Merge must still compare both complete baselines/action domains and preserve all32 ordered full/partial candidate fields.',
   'mandatory_hot_work':['Strict bounded UTF8/JSON parsing and duplicate-key/nonfinite/identity guards.',
     'All required output encoding, immutable capture append, complete merge checks and caller return bookkeeping.',
     'Unknown on allocation/capacity/codec/write errors; preserve captured prefix. No result before mandatory evidence capture succeeds.'],
   'do_not_do':['Do not simply exclude existing ledger/codec costs from old timings.',
     'Do not share mutable response dicts with caller, diagnostic records or another request.',
     'Do not omit partial suffix-unknown labels or large candidate fields.',
     'Do not move required live logging to uncharged post-root work. Any deferred artifact serialization remains in full child/campaign cost.'],
   'gate_if_later_authorized':'A new version would need complete current single/split request envelope equality, exact old outputs and immutable evidence after arbitrary caller mutations; missing/extra frame, failed capture/close and timeout negatives; fixed full-pipeline comparison only, no codec microbenchmark.',
   'limit':'This can remove redundant passes, not required work. Even the current split worker maximum122.1045ms exceeds100ms, so representation changes alone cannot certify all tested full32 requests.'},
 'direction2_complete_single_owner_incumbent_request':{
   'recommendation':'Prioritize source-level integration of one caller-admitted owner-stage request with a finite evaluated incumbent and real native final revalidation/ACK closure. Retain immutable-wire design as a separate later representation change; do not mix it into the first native request gate.',
   'admission':'Start one parent root before its first fresh owner view, delivered-message selection, action-domain construction or solver work. Include all dynamic guards/isolation/fingerprint/potential, full same-request baseline, evaluated candidates, selection and fallback. Unqueried candidates remain unknown; never call this a full32 solve.',
   'authority':'Choose a declared single-owner physical stage whose allowed action and terminal evidence are concrete. Receiver/source native checks at actual delivery/commit must remain authoritative. Supplied model output and preference updated ACK are insufficient physical-hop evidence.',
   'finalization':'Reobserve current source identity/generation/traversal/stationarity and actual available receiver premises, then submit an immutable request. Keep actual rejection, ACK queries/retries, required fallback, complete same-timestamp drain, actual next-hop evidence when that is the declared contract, codec and output under the same root.',
   'unknown_closure':'A budget stop before submission may return no-action/unknown after required verification. After submission, missing ACK or pending physical effect stays open; a timer cannot turn it into completed100ms. Any cancellation/fallback must itself reach its declared actual terminal state.',
   'time_scope':'Compute and end-to-end queue/message wait are separately reported. Every actual required computational continuation remains charged; cold startup and full shared costs remain explicit and unamortized. Native broad source_execution/dispatch is not automatically pure physics.',
   'existing_gap':'preference_wall_budget.run accepts a supplied finalize callback and always denies native authority; its atomic candidate and20ms-style reserve provide no finalization upper bound. Initial joint runner submits each owner first action before checking equal selections, so independent owner deadline truncations cannot be substituted into that protocol.',
   'joint_limit':'Single-owner stage scope does not solve atomic joint agreement or prove all-offered business protection. A later joint request needs an actual common proposal/acceptance protocol or an equally explicit lawful coordination contract before incompatible submissions.',
   'first_bounded_gate':'Use one fixed actual owner-stage scenario and a predeclared small candidate order, including no-feasible/failed-validation and lost/missing-ACK outcomes. Finalizer must use accepted native binary/timing authority. Preserve overruns/open roots; do not claim successful fallback or100ms from a callback boolean.',
   'not_measured':'No isolated baseline/guard/candidate worst-case or native finalization reserve exists from this ABBA result. Do not infer one by dividing the measured32-query time.'},
 'decision':'No additional worker-count sweep, profile or microbenchmark is justified here. Parent decides any new implementation; current source assessment implements nothing.',
 'literature_limit':'No RTI/stability/smoothness theorem is imported into discrete FIFO/native permission behavior. The present recommendation requires actual source contracts, failures and timed finalization.',
 'new_predictor_calls':0,'new_profile_calls':0,'new_native_calls':0,
 'assessment_source_sha256':sha(__file__)}
target=OUT/'json_shards_next_structural_assessment_002.json'
with target.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'status':report['status']}))
