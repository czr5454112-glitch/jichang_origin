"""Source/saved-metadata assessment only: no repository imports or execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SRC = ROOT / 'scripts/experiments/g31_ics_circulation'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    names = ('json_prediction_worker.py', 'json_prediction_client.py',
        'public_preference_request_context.py', 'public_preference_protection_request_context.py',
        'public_preference_protection_cut.py', 'preference_wall_budget.py',
        'native_public_preference_policy.py', 'public_native_preference_search.py',
        'research_native_public_preference.py', 'native_preexisting_v3_bound_adapter.py',
        'business_update_outbox.py', 'rolling_request_lineage.py', 'native027_request_timing.py')
    files = [SRC / name for name in names]
    files += [OUT / 'native027_build_001/source/cpp/ics_core/runtime' / name for name in
        ('circulation_runtime_impl.hpp', 'circulation_protocol_impl.hpp')]
    evidence = [OUT / name for name in (
        'json_prediction_RPC_independent_actual_review_001.json',
        'preference_static_context_summary_001.json',
        'original_route_pending_ack_report_review_001.json')]
    before = {str(p.relative_to(ROOT)): sha(p) for p in files + evidence}
    review = json.loads(evidence[0].read_bytes())
    old = json.loads(evidence[1].read_bytes())
    assert review['status'] == 'passed_saved_outputs_and_cost_envelopes'
    assert (review['requests'], review['full_baselines'], review['candidate_queries']) == (24, 24, 768)
    assert all(x['finalization'] == 'unknown_no_native_final_revalidation' for x in old['budget_probes'])
    report = {
        'schema': 'g31.prediction_next_boundary_source_assessment.v1',
        'status': 'source_bound_design_only_no_implementation_or_performance_prediction',
        'reviewed_sources_and_evidence_sha256': before,
        'assessor_sha256': sha(Path(__file__)),
        'scope': 'The existing fixed-source JSON service covers supplied initial 3-tray/5-job conditional prediction. It has no NativeSession or online authority. Neither option below expands that model to the original full workload.',
        'known_costs': {
            'json_full32_complete_caller_ms': review['warm_complete_caller_ms'],
            'nested_compute_ms_not_additive': review['nested_compute_ms_not_additive'],
            'cold_worker_launch_through_first_return_ms': review['cold_launch_through_first_return_ms'],
            'close_with_reclamation_ms': review['close_with_reclamation_ms'],
            'compiled_warm_at_or_below100ms': 0,
            'compiled_warm_denominator': 12,
            'whole_python_application_seconds': review['whole_python_application_seconds'],
            'old_budget_shell': [{'case': x['case'], 'evaluated': x['evaluated'],
                'unknown_unexecuted': x['unknown_unexecuted'], 'outer_function_ms': x['outer_function_ms'],
                'finalization': x['finalization']} for x in old['budget_probes']],
            'unmeasured': ['The fixed-worker setup/full-baseline component versus individual candidate costs are not separately measured in this ABBA.',
                'Complete caller minus nested compute is an aggregate including codec, IPC, scheduling and bookkeeping; it is not an isolated codec measurement.',
                'No actual deadline-limited fixed-worker search with native final validation, distributed agreement and delivered ACK closure has been measured.',
                'Native026 original witnessed first-hop root measurements are a different input/operation and cannot be subtracted from or added as a proven native027 synthetic finalization reserve.']},
        'comparison': {
            'fixed32_process_sharding': {
                'semantic_basis': 'Stronger exact-output basis: each action creates isolated dynamic projection state; the reference completion times and public potential are read-only within one request. Full results and strict-prefix rejections can be merged by the original action ordinal without arithmetic reduction.',
                'required_contract': [
                    'A new versioned subset request carries original request/snapshot digest, source version, exact 32-action domain digest and a predeclared disjoint shard ordinal list. No arbitrary actions/code are accepted.',
                    'Every worker performs the complete fresh dynamic input guard, copy/fingerprint, potential and full same-input baseline before its subset. Baselines, action domains and snapshot identities must agree exactly; each returned candidate retains its original ordinal and full/partial label.',
                    'Caller requires exact union0..31 once each, no duplicate/missing/foreign row, then assembles in canonical order and applies the unchanged deterministic selection/ties. No supplied baseline or old result is accepted as worker authority.',
                    'Failure of any shard leaves exact32 incomplete. A partial-search fallback is a separately declared result, never exact enumeration. All child errors and costs remain in the denominator.',
                    'Each competing method gets the same process/core and total wall/query budget. Adaptive coordinate searches cannot precompute unused neighborhoods for free or change their query order without a new method contract.',
                    'Caller launch/admission, input serialization, concurrent dispatch, slowest reply, full merge/codec, teardown and native finalization remain charged. Cold startup and duplicated guard/baseline work are reported without averaging.'],
                'cost_condition_not_prediction': 'Warm wall would need caller_dispatch + max_i(fresh_guard_potential_full_baseline_i + sum(candidate_costs_in_shard_i)) + caller_merge_codec + actual_finalization <100ms. Sum CPU includes every duplicated worker baseline/guard; it is not this critical-path wall.',
                'limits': 'No shard cost profile, concurrent run or performance bound exists. Dividing116-160ms by worker count is unjustified. Cold cost already exceeds100ms before native integration. This option preserves32 semantics but alone does not complete a business request.'},
            'deadline_limited_native_request': {
                'goal_alignment': 'More directly addresses a complete operation/request, but currently has larger unclosed authority, deadline and multiowner coordination gaps. It changes evaluated candidate count and cannot be labeled full32.',
                'existing_pieces': [
                    'preference_wall_budget.run admits before setup, retains unknown unexecuted rows and reports atomic overrun, but finalize is a supplied callback and native permission is explicitly false.',
                    'NativeCollectedV3 and initial ledger collectors bind actual native027 owner/session, own command/self-ACK, selected delivered peer message, current owned actions and freshness. Serialized JSON does not retain these process-local authority handles.',
                    'owner_first_action performs a fresh own view before submitting route/transfer; native route execution validates identity, generation, traversal, local owner, reroute permission, current stage goal and can_enter. The updated ACK is explicitly a preference result, not a hard reservation or evidence of actual edge entry.',
                    'BusinessUpdateOutbox admits before observation and requires actual delivered ACK handling, mandatory complete native drain and codec. It supports only a fresh exclusive client; transfer business attribution is declared-label-only, not established by its empty tray payload.'],
                'integration_gaps': [
                    'Current JSON Engine evaluates all32 atomically and Protocol accepts only predict/close. It has no per-request deadline, finite search continuation or partial status; the existing watchdog bounds worker lifetime, not a complete native request.',
                    'The caller must own the root and absolute wall deadline before actual collection/serialization. Queue, RPC, full fresh baseline, selection, current-source/receiver checks, submission, actual ACK/retry/fallback, required physical proof, same-time drain and output all retain that root. Wall deadlines must not be equated with native physical time.',
                    'Baseline/guard/potential are atomic and may consume the entire budget before one candidate. Candidate checks can stop only between complete calls unless a separately verified resumable model is built. Reserve20ms in the old pure shell is no proven finalization or ACK bound; overrun and timeout remain explicit.',
                    'A predictor response is a proposal only. Caller retains the session-bound collected object and verifies response version/request/snapshot/action identity, then rereads actual owner facts and follows native source/receiver admission. Stale generation/traversal, expired latest message, new pending action or changed stage requires withholding/replanning under the same root, not freshening old data.',
                    'Current joint runner independently predicts at A and B, then requires their selected vectors equal. Different wall cutoffs can produce different evaluated sets and selections. They cannot submit independently and compare afterward. A predeclared real agreement protocol or a narrower explicitly single-owner first-action request is required; any negotiation is charged and cannot read remote private truth.',
                    'Route updated/rejected ACK and transfer received/rejected have different terminal meanings. A first-hop contract additionally needs actual edge-entry/post-exit evidence. Terminal failure needs a real delivered ACK; absent ACK remains open/unknown. Long-term route maintenance/reuse is not discharged by a finite first-hop result.',
                    'Keeping native physics/background advancement identical is part of the contract. Do not invent an atomic global cut by equal timestamps or stop background work only to keep a returned proposal fresh. Actual scheduler response/target and same-time drain must be retained.',
                    'If no fully evaluated safe incumbent remains, native-default/withhold is not automatically a validated fallback. Its actual local preconditions, expected continuation and complete request accounting must be explicit. Failed or unqueried predictions remain unknown; strict protection uses delta<=0 with no tolerance.',
                    'Accepted native027 instrumentation can retain nested phases and unclassified remainder, but broad phase names do not prove pure physics. Shared and unclassified work remain fully charged; elapsed ACK/message wait, continuous service bursts and exclusive computation are separate outputs. No subtraction or100ms proof follows from a proposal callback.'],
                'limits': 'No implementation or performance claim. Cold source/worker startup is additional; a warm finite result cannot establish cold100ms, all-flow protection, model error bounds or complete32 enumeration.'}},
        'recommendation': {
            'stronger_proven_basis': 'Exact32 process sharding has the stronger source-level semantic decomposition; neither option has a proven under100ms timing bound.',
            'closer_to_user_goal': 'A truly caller-admitted finite native request is closer to the complete computation/validation goal, but first requires an explicit operation scope and distributed agreement or single-owner contract. Reusing the old callback shell alone is insufficient.',
            'next_allowed_action': 'No automatic experiment or implementation. If an experiment is later authorized, predeclare one scope, exact denominator/failure gates and complete cold/warm costs. Do not mix sharding, finite truncation, receiver-bound changes and diagnostic-writer changes in one comparison.',
            'stop_rule': 'Do not run codec microbenchmarks or claim that warm savings can overcome the already observed116-160ms full32 nested kernel. Preserve all prior negative factory/prefix/quiet/spool results.'},
        'new_predictor_calls': 0, 'new_profile_calls': 0, 'new_native_calls': 0,
        'implementation_created': False, 'frozen_sources_modified': False,
        'complete_request_100ms_certified': False,
    }
    assert before == {str(p.relative_to(ROOT)): sha(p) for p in files + evidence}
    target = OUT / 'prediction_next_boundary_source_assessment_001.json'
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'path': str(target), 'sha256': sha(target), 'sources': len(files),
        'status': report['status'], 'new_native_calls': 0, 'new_predictor_calls': 0}))

if __name__ == '__main__':
    main()
