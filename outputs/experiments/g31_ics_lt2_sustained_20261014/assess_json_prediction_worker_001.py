"""Source/profile-only feasibility note; never constructs a predictor/worker."""
from pathlib import Path
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
CODE = ROOT/'scripts/experiments/g31_ics_circulation'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())

static_summary = OUT/'preference_static_context_summary_001.json'
static_report = OUT/'preference_static_context_pair_001/worker/report.json'
static_plan = OUT/'preference_static_context_pair_001/worker/plan.json'
quiet_folder = OUT/'preference_quiet_profile_001'
quiet_report = quiet_folder/'report.json'; quiet_plan = quiet_folder/'plan.json'
quiet_pair = OUT/'preference_quiet_pair_001/receipt.json'
s = read(static_summary); r = read(static_report); qp = read(quiet_plan); q = read(quiet_report); pair = read(quiet_pair)
assert sha(static_report) == s['evidence_sha256']['preference_static_context_pair_001\\worker\\report.json']
assert sha(static_plan) == s['evidence_sha256']['preference_static_context_pair_001\\worker\\plan.json']
assert r['status'] == 'passed_exact_pure_static_context_pair' and r['source_changed'] == []
assert q['status'] == 'completed_pure_quiet_diagnosis' and q['source_changed'] == [] and q['native_calls'] == 0
assert q['plan_sha256'] == sha(quiet_plan) and q['full_output_pairs_exact'] == 32
for path, entry in qp['sources'].items():
    assert sha(quiet_folder/'source'/entry['archive']) == entry['sha256']
for profile in q['profiles']:
    assert sha(quiet_folder/(profile['arm']+'.prof')) == profile['profile_sha256']
assert pair['status'] == 'completed_exact_pure_quiet_pair' and pair['source_changed'] == []

def function(arm, name, suffix):
    profile = next(row for row in q['profiles'] if row['arm'] == arm)
    matches = [row for row in profile['functions'] if row['function'] == name and row['file'].endswith(suffix)]
    assert len(matches) == 1
    return matches[0]

rows = r['paired_rows']; assert len(rows) == 24 and len(r['cold_full32_rows']) == 12
old = [row['timings']['reference_context']['wall_ns']/1e6 for row in rows]
warm = [row['timings']['static_warm']['wall_ns']/1e6 for row in rows]
cold = [row['wall_ns']/1e6 for row in r['cold_full32_rows']]
compile_rows = {arm:function(arm,'compile_guards','public_preference_request_context.py') for arm in ('A','B')}
evidence = [static_summary,static_report,static_plan,quiet_report,quiet_plan,quiet_folder/'diagnosis.json',
    quiet_folder/'A.prof',quiet_folder/'B.prof',quiet_pair,Path(__file__)]
sources = [CODE/name for name in ('public_preference_static_context.py','public_preference_request_context.py',
    'public_native_preference_projection.py','public_reuse_model.py','public_preference_quiet_context.py','profile_public_preference_quiet.py')]
result = {
 'schema':'g31.json_prediction_worker.source_feasibility.v1',
 'status':'conditionally_feasible_unimplemented_hypothesis_no_speed_claim',
 'new_native_calls':0,'new_projection_calls':0,'new_service_or_benchmark_implemented':False,
 'source_sha256':{str(path):sha(path) for path in sources},
 'evidence_sha256':{str(path):sha(path) for path in evidence},
 'history':{
   'static_factory_already_reuses_compiled_guards':True,
   'difference':'StaticImplementation.__checked_compiler invokes verify_implementation on every new RequestContext. That rereads/hashes all source files and recursively inventories live functions/defaults/constants/module aliases. Proposed dedicated process removes this repeated implementation-inventory path only by adopting a closed, versioned process contract.',
   'static_pair_reference_sum_ms':sum(old),'static_pair_warm_sum_ms':sum(warm),
   'static_pair_warm_change_fraction':sum(warm)/sum(old)-1,
   'static_pair_reference_median_ms':statistics.median(old),'static_pair_warm_median_ms':statistics.median(warm),
   'static_cold_full32_range_ms':[min(cold),max(cold)],'factory_cold_build_ms':r['factory_cold_build']['wall_ns']/1e6,
   'separate_per_request_inventory_cost_measured':False,
   'attribution':'The aggregate regression is measured. It does not isolate how much source rehash, binding checks, copies or host variation caused it.',
   'dedicated_json_once_startup_trial_found':False,
   'search_scope':'Current static/request-context source and saved static/quiet experiments; collaborator who implemented static factory confirms no dedicated JSON-only once-startup trial. Not a proof of absence outside this workspace history.',
   'quiet_pair_median_A_ms':pair['median_all_A_ns']/1e6,'quiet_pair_median_B_ms':pair['median_all_B_ns']/1e6,
   'quiet_not_recommended':'Even ignoring its extra code generation, quiet evaluate is slower under the same profile; do not combine the new process hypothesis with this rejected event-loop variant.'},
 'measured_relocatable_category':{
   'compile_guards_cumulative_ms_under_profiler':{arm:row['cumulative_seconds']*1000 for arm,row in compile_rows.items()},
   'A_profile_total_wall_ms':q['profiles'][0]['wall_with_profiler_seconds']*1000,
   'A_context_init_cumulative_ms':function('A','__init__','public_preference_request_context.py')['cumulative_seconds']*1000,
   'A_32_evaluate_cumulative_ms':function('A','evaluate','public_preference_request_context.py')['cumulative_seconds']*1000,
   'A_32_event_run_cumulative_ms':function('A','run','public_native_preference_projection.py')['cumulative_seconds']*1000,
   'A_dynamic_guard_cumulative_ms':function('A','_validate_supplied_snapshot','public_preference_request_context.py:exact_guard_split')['cumulative_seconds']*1000,
   'interpretation':'117.274–126.223ms is the previously measured profiled compile_guards envelope in two related arms of one case. It includes overlapping nested source/AST/copy/compile work; never add these nested categories again. It identifies work that could move to cold startup, not a measured service saving, confidence interval, or unprofiled runtime bound.',
   'net_warm_gain_lower_bound_ms':None,'net_warm_gain_upper_bound_ms':None,
   'why_no_net_range':'JSON framing, queue/IPC/copies/codec and the new fixed-version guard are unmeasured. A net regression remains possible. No subtraction from236.769ms unprofiled median or any original native request is justified.',
   'scope_mismatch':'Quiet profile is context plus32 predictions only. It excludes a separately required full baseline, external JSON request/response RPC and native source/receiver final validation; these must remain charged when the service contract requires them.'},
 'conditional_process_contract':[
   'Launch a new worker per exact source/ABI/guard-version identity from an archived source image; verify the complete source closure and loaded project modules against that image before READY. Compile exact guard AST once in this startup. No mutable live checkout imports after READY, stale pyc reliance or late extension discovery.',
   'Expose only a bounded JSON request/JSON response channel. No pickle loads, eval, callable objects, arbitrary import/module names, file execution, debug console, extension hooks, reload or mutation endpoint. Internal startup compilation is not a caller-accessible execution API. This is an operational closed-process contract, not a Python sandbox against administrator/code-injection attacks.',
   'A request carries the expected worker version plus unique caller/request identity. A mismatch requires a new worker, never a silent fallback to old compiled guards. Code-version changes always terminate/retire the old instance before the dispatcher uses the new version. Failure/crash/capacity overflow leaves affected requests unknown.',
   'Preserve JSON numeric types, negative zero and insertion order. Reject duplicate keys/nonfinite numbers/unsupported schema and oversized/deep frames. The declared comparison domain is the same JSON-decoded input on both reference and candidate; an arbitrary Python-object input is not silently declared equivalent to a JSON round trip.',
   'For every admitted request decode a fresh tree, validate the full dynamic snapshot and typed action domain, deepcopy/isolate it, compute its fingerprint and public potential, derive the same candidate sequence and fresh full baseline, simulate each admitted candidate with isolated calendars and state, and encode the complete result/status. Do not cache observations, job labels, completion values, predictions, potentials or a preceding request context across requests.',
   'Only implementation objects persist: pinned source/version evidence, compiled validate/action functions and immutable proof metadata. Compiled functions must not close over a request tree; per-request closures/potential/projections are released after response. Request A/B/A order, changed facts, changed insertion order, malformed then valid, timeout then valid, and output mutation must have the same outcomes as fresh contexts.',
   'The JSON prediction service grants no online/native authority. Delivered-message authenticity, owner scope, freshness, source/receiver revalidation, physical admission, commit/ACK/retry/drain and mandatory fallback still belong to the actual business request and cannot be bypassed by a service-version token.'
 ],
 'cost_contract':[
   'Warm request begins at caller admission before creating/encoding its service input. Retain caller acquisition/guards, input encoding, copying, IPC send, queue delay, receive/decode, dynamic validation, isolation/fingerprint/potential/baseline/candidates, output encoding, IPC return, caller decode and any final validation. Report exclusive computation, maximum continuous service and elapsed queue/message latency separately; do not silently subtract shared or unclassified work.',
   'Cold sensitivity additionally retains process launch/import, source-image hash/loaded-closure checks, exact AST compilation and READY handshake. Charge this actual startup to a request requiring a new worker; do not call a warmed worker cold or amortize it away from a strict per-request requirement.',
   'Single sequential ownership is the smallest defensible scope. Any later multi-client concurrency needs explicit admission/order/queue and shared-cost accounting; code reuse alone does not justify a throughput or100ms certificate.'
 ],
 'decision':'Do not repeat the failed same-process static factory or quiet wrapper. A dedicated fixed-version JSON worker is a distinct, source-supported hypothesis because it could remove repeated implementation self-checks as well as guard codegen. It is not yet an accepted optimization; no service/benchmark/native was built or run in this assessment. Existing evidence does not establish a route to complete100ms.',
 'stop_conditions':['If closed-worker code immutability cannot be justified without reinstating the same full inventory on every request, this collapses back to the failed static-factory design; stop rather than relabel it.',
   'If future exact-output/equal-domain tests require cached prior snapshots/labels or relaxed guards, reject the design.',
   'If complete request including RPC and cold sensitivities has no material measured benefit, retain the negative result and stop; do not count only the new warm predictor core.'],
 'complete_100ms_certified':False
}
target=OUT/'json_prediction_worker_feasibility_001.json'
with target.open('x',encoding='utf8') as stream: json.dump(result,stream,ensure_ascii=False,allow_nan=False,indent=2)
print(json.dumps({'path':str(target),'sha256':sha(target),'static_warm_change_fraction':result['history']['static_pair_warm_change_fraction'],
    'profiled_compile_ms':result['measured_relocatable_category']['compile_guards_cumulative_ms_under_profiler']}))
