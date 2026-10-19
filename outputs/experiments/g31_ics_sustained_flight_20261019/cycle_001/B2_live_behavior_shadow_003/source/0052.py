"""At most two posthoc-selected live callback diagnostics; no action authority."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import time
import traceback

SCHEMA = 'g31.foundation.airport_shadow_callback.v1'


def encoded(value):
    return json.dumps(value,separators=(',',':'),allow_nan=False).encode()


class ShadowPlanner:
    def __init__(self, baseline, scorer, *, selections, branch, business_version, path,
                 clock=time.perf_counter):
        if not 1 <= len(selections) <= 2:
            raise ValueError('shadow_planner:one_or_two_targets_required')
        targets={}
        for row in selections:
            if set(row)!={'callback'} or set(row['callback'])!={'owner_id','now','sequence','residual_index','request_prefix'}:
                raise ValueError('shadow_planner:runtime_identity_only_no_reference_outcomes_or_payload')
            identity=row['callback']
            key=(identity['owner_id'],identity['now'],identity['residual_index'])
            if key in targets or identity['now'] < 57660 or type(identity['sequence']) is not int:
                raise ValueError('shadow_planner:invalid_target_identity')
            targets[key]=copy.deepcopy(row)
        self.baseline,self.scorer=baseline,scorer
        self.targets=targets;self.seen=set();self.ordinals={};self.sequence=0
        self.branch,self.business_version=branch,business_version
        self.path=Path(path);self.stream=self.path.open('x',encoding='utf-8',newline='\n')
        self.clock=clock;self.results=[];self.recording_errors=[]

    def __call__(self,observation,**options):
        started=self.clock()
        now,owner=observation['now'],observation['owner_id']
        pair=(owner,now);ordinal=self.ordinals.get(pair,0);self.ordinals[pair]=ordinal+1
        sequence=self.sequence
        if 43200<=now<=59400:self.sequence+=1
        key=(owner,now,ordinal)
        target=self.targets.get(key) if key not in self.seen else None
        capture_error=None;record=None
        if target is not None:
            # Reserve the hit before any fallible work: failures are retained,
            # never converted into another attempt at a later callback.
            self.seen.add(key)
            try:
                record={'schema':'g31.foundation.airport_policy_observation.v2',
                    'sequence':sequence,'branch':self.branch,
                    'business_contract_version':self.business_version,'owner_id':owner,'now':now,
                    'readonly':True,'scope':'actual owner policy callback arguments and returned decision, including residual calls',
                    'observation':copy.deepcopy(observation),'policy_options':copy.deepcopy(options),
                    'native_execution_authority':False,'candidate_conditional_labels':None}
            except Exception:
                capture_error=traceback.format_exc()
        # Baseline exceptions retain their original behavior. Only passive
        # diagnostic failures are contained; the original objects reach policy.
        decision=self.baseline(observation,**options)
        if target is None:return decision
        event={'schema':SCHEMA,'status':'failed','identity':copy.deepcopy(target['callback']),
            'actual_sequence':sequence,'actual_owner':owner,'actual_now':now,'actual_residual_index':ordinal,
            'score_selects_action':False,'original_decision_object_returned':True,
            'posthoc_reference_selected_mechanism_only':True,'heldout_or_policy_gain':False}
        try:
            if capture_error:raise ValueError('shadow_planner:capture_failed:'+capture_error)
            identity=target['callback']
            if sequence!=identity['sequence'] or options.get('request_prefix')!=identity['request_prefix']:
                raise ValueError('shadow_planner:callback_sequence_or_prefix_mismatch')
            record['decision']=copy.deepcopy(decision)
            before=hashlib.sha256(encoded(record)).hexdigest()
            event['public_record_sha256']=before
            event['first_proposal_index']=0
            event['scorer']=self.scorer(record)
            if hashlib.sha256(encoded(record)).hexdigest()!=before:
                raise ValueError('shadow_planner:scorer_mutated_detached_record')
            if not isinstance(event['scorer'],dict) or event['scorer'].get('status')!='completed_public_shadow_scoring':
                raise ValueError('shadow_planner:scorer_did_not_complete')
            event['status']='completed_shadow_scoring_only'
        except Exception:
            event['exception']=traceback.format_exc()
        event['wall_seconds_before_event_storage']=self.clock()-started
        try:
            self.stream.write(json.dumps(event,separators=(',',':'),allow_nan=False)+'\n')
            self.stream.flush()
        except Exception:
            event['status']='failed';error=traceback.format_exc()
            self.recording_errors.append(error);event['recording_error']=error
        # The following measurement includes baseline, detached capture,
        # scoring and event storage. Persist it in the post-run summary rather
        # than adding another timed write inside the measured callback.
        event['callback_elapsed_before_return_seconds_including_storage']=self.clock()-started
        event['complete_request_100ms_certified']=False
        self.results.append(event)
        return decision

    def close(self):
        self.stream.close()

    def summary(self):
        if not self.stream.closed:raise ValueError('shadow_planner:close_before_summary')
        return {'schema':SCHEMA,'scope':'posthoc-selected train-trajectory mechanism diagnostic; no scores select or change actions',
            'registered_targets':len(self.targets),'actual_hits':len(self.seen),'maximum_hits':2,
            'all_targets_hit':len(self.seen)==len(self.targets),'recording_errors':self.recording_errors,
            'results':self.results,'event_artifact':{'path':str(self.path.resolve()),
                'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()},
            'all_shadow_scores_completed':len(self.results)==len(self.targets) and all(r['status']=='completed_shadow_scoring_only' for r in self.results),
            'native_consumption_closed':False,'request_ACK_edge_join_pending':True,
            'complete_request_100ms_certified':False,'policy_gain_established':False}
