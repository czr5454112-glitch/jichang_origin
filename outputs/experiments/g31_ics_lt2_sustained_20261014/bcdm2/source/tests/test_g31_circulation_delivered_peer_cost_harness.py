import pytest
from scripts.experiments.g31_ics_circulation import measure_delivered_peer_cost as m


def records():
    rows=[]
    for ordinal in (27212,27215):
        for batch,arm in enumerate(m.ARMS):
            for repeat in range(4):
                start=len(rows)*100
                metrics={'started_ns':start,'finished_ns':start+50,'validator_ns':50,
                    'digest_entered':1 if arm=='B' else None,'digest_completed':1 if arm=='B' else None,
                    'digest_raised':0 if arm=='B' else None,'digest_ns':20 if arm=='B' else None,
                    'validator_outside_digest_ns':30 if arm=='B' else None}
                rows.append({'ordinal':ordinal,'batch':batch,'arm':arm,'repeat':repeat,'metrics':metrics,
                    'outcome_sha256':str(ordinal),'disposition':'absent',
                    'outcome_file':f'outcome_{ordinal}_{batch}_{repeat}.json'})
    return rows


def test_complete_synthetic_order_and_nested_conservation():
    result=m.audit_records(records())
    assert result['27212']['B']['median_nested_digest_ms']==.00002
    assert result['27215']['A']['median_nested_digest_ms'] is None
    assert result['27215']['B']['median_outside_digest_ms']==.00003


@pytest.mark.parametrize('change',['drop','swap','clock','count','child','outcome','A_counts','filename'])
def test_denominator_timing_and_output_corruption_rejected(change):
    rows=records()
    if change=='drop':rows.pop()
    elif change=='swap':rows[0],rows[1]=rows[1],rows[0]
    elif change=='clock':rows[0]['metrics']['validator_ns']=-1
    elif change=='count':rows[4]['metrics']['digest_entered']=2
    elif change=='child':rows[4]['metrics']['digest_ns']=51
    elif change=='outcome':rows[0]['outcome_sha256']='different'
    elif change=='A_counts':rows[0]['metrics']['digest_ns']=0
    elif change=='filename':rows[0]['outcome_file']='other.json'
    with pytest.raises(ValueError):m.audit_records(rows)
