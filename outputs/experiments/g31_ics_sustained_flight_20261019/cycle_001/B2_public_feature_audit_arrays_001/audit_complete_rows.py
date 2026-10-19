"""Independent stdlib-only result audit; no prediction, fit, or native calls."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def require(ok, reason):
    if not ok: raise ValueError('complete_public_rows:' + reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_bytes())


def main():
    start=time.perf_counter();deadline=start+30.
    receipt=read(HERE/'receipt.json');plan=read(HERE/'plan.json')
    require(receipt['status']=='completed_public_feature_audit' and receipt['source_exit_pins_passed'] is True,'completed_source_pinned_run')
    require(receipt['plan']['sha256']==sha(HERE/'plan.json'),'closed_plan_bytes')
    for path,expected in {**plan['source_sha256'],**plan['historical_collection_sources']}.items():
        require(sha(path)==expected,'source_bytes')
    for item in [*plan['inputs'].values(),receipt['feature_rows'],receipt['samples']]:
        require(sha(item['path'])==item['sha256'],'input_and_output_bytes')
    require(receipt['native_branches']==receipt['fit_calls']==receipt['outcome_labels_created']==0,'public_only_scope')
    require(receipt['actual_training_ready'] is False and receipt['native_action_consumption_tested'] is False,'no_training_or_execution_claim')
    owners=Counter();counts=Counter();feature_sizes=Counter();previous=-float('inf');lines=[]
    with gzip.open(receipt['feature_rows']['path'],'rt',encoding='utf8') as stream:
        for sequence,line in enumerate(stream):
            require(time.perf_counter()<deadline,'bounded_result_audit')
            row=json.loads(line);lines.append(line)
            require(row['sequence']==sequence and 43200.<=row['now']<=59400. and row['now']>=previous,'complete_ordered_sequence')
            require(row['status']=='public_features_verified_no_labels'
                and row['label_status']=='no_actual_candidate_outcome_label' and row['target_value'] is None,'row_without_outcome_labels')
            previous=row['now'];owners[row['owner']]+=1;counts['records']+=1
            a=row['accounts_audit']
            require(a['owner']==row['owner'] and a['now']==row['now'] and a['observation_sha256']==row['observation_sha256'],'public_account_scope')
            require(a['unknown_inbound_not_zero'] is True and a['unknown_outbound_generation_not_inferred'] is True
                and a['observed_counts_for_flight_model'] is None and a['private_lookup_used'] is False
                and a['native_execution_authority'] is False and a['label_status']=='no_outcome_labels_created','unknown_and_no_private_labels')
            c=row['forecast_information_cutoffs']
            require(c=={'training_labels_closed_at':43200.,'model_frozen_at':43200.,'plan_received_at':0.,'observed_arrivals_through':None},'original_frozen_public_cutoffs')
            for candidate in row['candidates']:
                action=candidate['action'];features=candidate['features']
                require(action['enabled'] is None and action['outcome_label'] is None
                    and action['status']=='proposal_only_requires_current_native_guard_and_execution_binding','proposal_not_execution_or_label')
                require(action['semantic']['earliest_legal_arrival']>=row['now'],'future_static_arrival_estimate')
                require(all(type(v) in (float,int) and math.isfinite(v) for v in features.values()),'finite_feature_vector')
                feature_sizes[len(features)]+=1;counts['feature_vectors']+=1
    expected={'records':946,'recorded_proposals':463,'B1_forward_attempts':946,'B1_forward_calls':946,
        'valid_records':946,'feature_vectors':463,'records_with_current_free':296}
    require(receipt['counts']==expected and not receipt['failures'],'complete_success_counts')
    observation_receipt=read(plan['inputs']['observation_receipt']['path'])
    require(counts=={'records':946,'feature_vectors':463} and set(owners)==set(observation_receipt['owners'])
        and feature_sizes=={88:463},'independently_recounted_coverage')
    require(json.loads(lines[0])['now']==43200. and json.loads(lines[-1])['now']==59400.,'full_registered_time_range')
    prior=HERE.parent/'B2_public_feature_audit_002/public_feature_rows.jsonl.gz'
    with gzip.open(prior,'rt',encoding='utf8') as stream:prefix=list(stream)
    require(len(prefix)==202 and prefix==lines[:202],'all_previous_202_rows_exact_serialized_bytes')
    report={'status':'complete_public_rows_independently_verified','native_branches':0,'fit_calls':0,'forecast_forward_calls':0,
        'source_sha256':sha(__file__),'receipt_sha256':sha(HERE/'receipt.json'),'plan_sha256':sha(HERE/'plan.json'),
        'full_feature_artifact_sha256':sha(receipt['feature_rows']['path']),
        'recounted_records':946,'recounted_vectors':463,'features_per_vector':88,'owners':dict(owners),
        'all_targets_and_action_outcomes_none':True,'all_action_enabled_unknown':True,'all_account_unknown_flags_preserved':True,
        'all_202_previous_record_serialized_lines_exact':True,'prior_partial_feature_artifact_sha256':sha(prior),
        'all_source_input_output_hashes_match':True,'native_control_benefit_established':False,
        'standalone_training_readiness_established':False,'receipt_inner_wall_seconds':receipt['wall_seconds'],
        'reviewer_correction':'An initial reviewer-only assertion incorrectly assumed equal owner counts. Actual callbacks include residual calls; the corrected check binds the recorded owner set and reports 567/379 without imposing balance. No producer or artifact changed.',
        'parent_reported_outer_wall_seconds':196.312,'audit_wall_seconds':time.perf_counter()-start,
        'scope':'Complete saved-output recount and source/input/byte binding; no forecast/features recomputed and no actual-label or native guard claim.'}
    with (HERE/'independent_complete_rows_audit_001.json').open('x',encoding='utf8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
