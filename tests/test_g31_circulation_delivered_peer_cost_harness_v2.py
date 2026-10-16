"""Original nine checks retained, plus exact-type/closed-domain counterexamples."""
from test_g31_circulation_delivered_peer_cost_harness import *
from scripts.experiments.g31_ics_circulation import measure_delivered_peer_cost_v2 as v2


@pytest.mark.parametrize('change',[
    'start_bool','end_float','duration_float','enter_bool','complete_bool','raised_bool',
    'negative_counts','digest_float','outside_float','extra_metric','missing_metric',
    'batch_bool','repeat_bool','negative_clock'])
def test_v2_strict_saved_types_and_closed_metrics(change):
    rows=records();m=rows[0]['metrics'];b=rows[4]['metrics']
    if change=='start_bool':m['started_ns']=False
    elif change=='end_float':m['finished_ns']=50.0
    elif change=='duration_float':m['validator_ns']=50.0
    elif change=='enter_bool':b['digest_entered']=True
    elif change=='complete_bool':b['digest_completed']=True
    elif change=='raised_bool':b['digest_raised']=False
    elif change=='negative_counts':b.update(digest_entered=-1,digest_completed=-1)
    elif change=='digest_float':b['digest_ns']=20.0
    elif change=='outside_float':b['validator_outside_digest_ns']=30.0
    elif change=='extra_metric':m['extra']=0
    elif change=='missing_metric':del m['digest_ns']
    elif change=='batch_bool':rows[0]['batch']=False
    elif change=='repeat_bool':rows[0]['repeat']=False
    else:m['started_ns']=-1;m['validator_ns']=51
    with pytest.raises(ValueError):v2.audit_records(rows)
