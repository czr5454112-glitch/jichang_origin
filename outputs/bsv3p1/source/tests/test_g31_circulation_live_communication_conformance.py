import copy
from scripts.experiments.g31_ics_circulation import validate_live_communication_projection as m

def values():return dict(loaded=1.,receiver=2.,reuse1=3.,reuse2=4.,blocker=5.)

def test_exact_endpoint_count_and_types():
    a=values();assert m.exact_completion(a,copy.deepcopy(a))
    for bad in (None,{},dict(loaded=1.),dict(a,extra=1.),dict(a,loaded=True),dict(a,loaded=1),dict(a,receiver=float('nan'))):
        assert not m.exact_completion(a,bad)

def test_no_ulp_or_business_epsilon():
    a=values();b=values();b['loaded']=1.0000000000000002
    assert not m.exact_completion(a,b)

def test_fixed_denominator_order():
    assert len(m.ORDER)==len(set(m.ORDER))==96
    assert m.ORDER[0]=='mechanism/vector_00' and m.ORDER[-1]=='insufficient_advance/vector_31'
    assert m.ORDER[32]=='no_overlap/vector_00'

def test_initial_extractor_does_not_pass_future_data():
    ep={'view':{'owner_id':'A'},'command':{'request_id':'id'},'received':[]}
    raw={'initial_owners':{'A':{'raw_endpoints':ep}},'result':{'secret':'outcome'},
        'specification':{'case':'secret'},'calls':[{'at':.05,'retry':False,'request':{'owner_id':'A','request_id':'id'}},
            {'at':99.,'retry':False,'request':{'owner_id':'A','request_id':'later','future':True}}]}
    got=m.public_initial(raw,'A')
    assert set(got)=={'view','command','received','own_request'} and 'future' not in repr(got) and 'secret' not in repr(got)
