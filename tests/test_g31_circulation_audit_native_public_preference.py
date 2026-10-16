from copy import deepcopy
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import audit_native_public_preference as audit


def proposal():
    return {'status':'conditional_model_proposal','proposal_wall_seconds':.2,
        'selected_action':{'return_delay':0.},'selected_prediction':{'completion':{'loaded':2.}},
        'rows':[{'model_call_wall_seconds':.01,'prediction':{'physical_projection':[{'at':1.1}]}}]}


def test_replay_ignores_only_valid_measured_durations_without_mutating_original_costs():
    a=proposal();b=deepcopy(a);b['proposal_wall_seconds']=2.;b['rows'][0]['model_call_wall_seconds']=1.
    before=deepcopy(a)
    assert audit.semantic_proposal(a)==audit.semantic_proposal(b) and a==before
    b['rows'][0]['prediction']['physical_projection'][0]['at']+=.001
    assert audit.semantic_proposal(a)!=audit.semantic_proposal(b)


@pytest.mark.parametrize('value',[True,-.1,float('nan'),float('inf'),'0.1'])
def test_invalid_timing_cannot_hide_a_saved_proposal_mismatch(value):
    a=proposal();a['rows'][0]['model_call_wall_seconds']=value
    with pytest.raises(ValueError,match='invalid_measured_duration'):audit.semantic_proposal(a)


@pytest.fixture(scope='module')
def old_raw():
    # One existing immutable native192 row checks the actual saved endpoint
    # representation. This does not inspect a running/new60 campaign.
    root=Path(__file__).resolve().parents[1]
    path=root/'outputs/experiments/g31_ics_lt2_sustained_20261014/native_preference_matrix_native_001_independent_audit.json'
    evidence=json.loads(path.read_bytes());row=next(iter(evidence['rows'].values()))
    raw=Path(row['raw_artifact']);assert audit.runner.sha(raw)==row['raw_sha256']
    return json.loads(gzip.decompress(raw.read_bytes()))


def test_existing_actual_endpoint_shape_replays_owned_transport_and_retained_contracts(old_raw):
    audit.verify_transport(old_raw);audit.verify_retained_ledgers(old_raw)


@pytest.mark.parametrize('defect',['changed_retry','missing_outbox','ack_future','unprocessed_final_ack','undrained_boundary'])
def test_saved_transport_requires_complete_immutable_causal_evidence(old_raw,defect):
    raw=deepcopy(old_raw)
    if defect=='changed_retry':
        retry=next(row for row in raw['calls'] if row['retry']);retry['request']['message_delay']=99.
    elif defect=='missing_outbox':raw['outbox'].pop(next(iter(raw['outbox'])))
    elif defect=='ack_future':raw['ack_handling'][0]['ack']['delivered_at']=41.
    elif defect=='unprocessed_final_ack':
        row=next(r for r in raw['outbox'].values() if r.get('ack'));row['ack']['sequence']+=1
    else:raw['native_batches'][0]['response']['timestamp_complete']=False
    with pytest.raises(ValueError):audit.verify_transport(raw)


def test_changed_completed_prefix_contract_is_not_reconstructed_from_later_absence(old_raw):
    raw=deepcopy(old_raw);raw['retained_ledgers']['A']['contracts']['loaded']['destination']=9
    with pytest.raises(ValueError,match='retained_ledger'):audit.verify_retained_ledgers(raw)


def test_audit_refuses_an_active_or_censored_parent_before_any_raw_scan(tmp_path):
    (tmp_path/'bounded_parent_receipt.json').write_text(json.dumps({'status':'hard_timeout','exitcode':1}))
    (tmp_path/'receipt.json').write_text('{}')
    with pytest.raises(ValueError,match='campaign_not_terminal'):audit.audit(tmp_path)
