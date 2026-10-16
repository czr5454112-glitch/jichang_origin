"""Source-only integration findings; no import of project code or dispatch."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
NAMES = (
    'research_live_obligation_native_domain.py',
    'research_live_obligation_historical.py',
    'live_obligation_historical_policy.py',
    'live_obligation_recollection_policy.py',
    'live_obligation_same_information_search.py',
    'live_obligation_owned_same_information_search.py',
    'live_obligation_initial_decision_adapter_v2.py',
    'live_obligation_initial_decision_adapter.py',
)
paths = [ROOT / 'scripts/experiments/g31_ics_circulation' / name for name in NAMES]
assert all(p.is_file() for p in paths)
record = {
    'schema': 'g31.online21.source_callsite_review.v1',
    'status': 'source_review_only_new_online_runner_not_implemented',
    'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    'findings': [
        {
            'source': NAMES[0], 'function': '_run_branch',
            'observed': 'After both first actions, the fixed-vector runner stops continuation when selections[A] != selections[B], and otherwise supplies row[vector] to both OwnerPolicy instances.',
            'why_currently_valid': 'The old fixed96 experiment preregisters one vector per branch. This is an experiment consistency check, not a distributed agreement protocol.',
            'online_requirement': 'Do not transplant that global equality condition into online control. Each owner must retain and execute only its own lawful proposal; disagreement is an after-the-fact diagnostic. Peer private proposal contents must not authorize or stop its local policy.',
        },
        {
            'source': NAMES[3], 'functions': ['fixed_choice', 'OwnerPolicy.decide_pending'],
            'observed': 'The historical policy consumes self.method as a fixed vector and labels causal records predeclared_counterfactual_vector and future_proposal_component_executed_without_replan=False.',
            'online_requirement': 'A version that retains an initially selected suffix must label it as a retained initial estimate, reapply all unchanged actual history/current/wire/union guards, and report that no later model re-estimation occurred. Do not retain the old no-replan=False metadata for that implementation.',
        },
        {
            'source': NAMES[0], 'function': 'completed_summary',
            'observed': 'The fixed96 assessment accepts a single vector representing both owners.',
            'online_requirement': 'Derive the executed specification from actual A initial route and return and B empty transfer and later route. Preserve each independent proposal and all failures. Neither owner receives this retrospective combined specification as an input.',
        },
        {
            'source': NAMES[4], 'function': 'propose_initial',
            'observed': 'The existing seam evaluates all32, selects using the declared method, and returns a current local proposal; it does not submit.',
            'online_requirement': 'The new dispatcher must recheck the same real InitialDecision immediately before submission, bind immutable command fields and creation lineage, retain no-command/unknown distinctions, and charge collection, full32, proof binding, selection, revalidation, serialization, submit and ACK descendants. Equal model cost for all7 arms remains explicit.',
        },
    ],
    'unchanged_acceptance': {
        'arms': 7, 'cases': 3, 'branches': 21, 'candidate_denominator_per_owner': 32,
        'strict_five_job_protection_tolerance': 0,
        'complete_request_milliseconds': 100,
        'global_goal_met': False,
        'initial_only_online_stage_proves_joint_rolling_effectiveness': False,
        'missing_or_failed_actions_may_be_removed_from_denominator': False,
    },
    'activity': {'project_imports': 0, 'tests': 0, 'model': 0, 'native': 0, 'C_load': 0},
}
target = HERE / 'online21_callsite_review_001.json'
with target.open('x', encoding='utf8', newline='\n') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'findings': len(record['findings']), 'sources': len(paths)}))
