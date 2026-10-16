import cProfile
import pytest
from scripts.experiments.g31_ics_circulation import profile_complete_c_publisher_saved18 as p

def test_profile_covers_root_construction_and_publish():
    events=[];value={'complete':[1,2]}
    def factory(record,method):events.append(('root',record,method));return record
    def publish(root,holder):events.append(('publish',root));holder.append(root);return root
    result,profiler,start,end=p.profile_call(value,'method',publish,factory)
    assert result is value and events==[('root',value,'method'),('publish',value)] and start<=end
    rows=p.profile_rows(profiler);functions={r['function'] for r in rows}
    assert 'factory' in functions and 'publish' in functions

def test_append_identity_is_not_relaxed():
    with pytest.raises(ValueError):p.profile_call({},None,lambda root,holder:{},lambda r,m:r)

def test_publication_exception_preserved():
    error=RuntimeError('original')
    def fail(root,holder):raise error
    with pytest.raises(RuntimeError) as caught:p.profile_call({},None,fail,lambda r,m:r)
    assert caught.value is error

def rows():
    return [{'key':str(n),'status':'exact_profiled','started_ns':n*10,'finished_ns':n*10+5,'elapsed_ns':5} for n in range(18)]

def test_exact_fixed18_inventory():
    r=rows();assert p.validate_inventory(r,[x['key'] for x in r])==dict(fixed_roots=18,profiled_publishers=18,exact=18,unknown=0)

@pytest.mark.parametrize('defect',['missing','unknown','bool_clock','overlap'])
def test_inventory_rejects_incomplete_or_bad_clocks(defect):
    r=rows();order=[x['key'] for x in r]
    if defect=='missing':r.pop()
    elif defect=='unknown':r[5]['status']='unknown_error'
    elif defect=='bool_clock':r[0]['started_ns']=False
    else:r[1]['started_ns']=1;r[1]['elapsed_ns']=14
    with pytest.raises(ValueError):p.validate_inventory(r,order)
