"""Draft shape tests only; intentionally not yet executed/prepared."""
import copy
import itertools
import pytest
from scripts.experiments.g31_ics_circulation import live_obligation_full32_suffix_partition as p


def actions():
    # Synthetic vocabulary solely for the partition parser; not real inputs.
    return [dict(zip(p.FIELDS,row)) for row in itertools.product(p.INITIAL,(.11,1.,2.,3.),p.RETURN,p.LATER)]


def test_cartesian_gives_sixteen_prefixes_and_all_thirtytwo_suffixes():
    result=p.partition(actions())
    assert (result['logical_candidates'],result['prefixes'],result['future_suffixes'])==(32,16,32)
    assert [i for g in result['groups'] for i in g['candidate_indices']]==list(range(32))
    assert all(g['representative_action']['later_action']=='native_default' for g in result['groups'])
    assert all(o['status']=='unknown_unexecuted' for g in result['groups'] for o in g['outcomes'])


def test_return_coordinate_cannot_be_silently_merged_into_eight_prefixes():
    result=p.partition(actions());first,second=result['groups'][:2]
    assert first['prefix_key']['initial_action']==second['prefix_key']['initial_action']
    assert first['prefix_key']['empty_departure']==second['prefix_key']['empty_departure']
    assert first['prefix_key']['return_delay']==0. and second['prefix_key']['return_delay']==.5
    assert first['prefix_key']!=second['prefix_key']


@pytest.mark.parametrize('kind',['missing','duplicate','reorder','past_field','later_field','extra_field','field_order','bool','int','nan','fifth_window'])
def test_wrong_or_ambiguous_action_domain_fails_closed(kind):
    rows=actions()
    if kind=='missing':rows.pop()
    elif kind=='duplicate':rows[1]=copy.deepcopy(rows[0])
    elif kind=='reorder':rows[0],rows[1]=rows[1],rows[0]
    elif kind=='past_field':rows[1]['return_delay']=.25
    elif kind=='later_field':rows[1]['later_action']='prefer_3'
    elif kind=='extra_field':rows[0]['lookahead']=True
    elif kind=='field_order':rows[0]=dict(reversed(list(rows[0].items())))
    elif kind=='bool':rows[0]['return_delay']=False
    elif kind=='int':rows[0]['return_delay']=0
    elif kind=='nan':rows[0]['empty_departure']=float('nan')
    else:rows[1]['empty_departure']=4.
    with pytest.raises(ValueError):p.partition(rows)


def test_result_mutations_do_not_change_input_or_other_group():
    rows=actions();old=copy.deepcopy(rows);result=p.partition(rows)
    result['groups'][0]['actions'][0]['return_delay']=99.
    result['groups'][0]['prefix_key']['return_delay']=55.
    result['public_windows'][0]=100.
    assert rows==old and result['groups'][1]['actions'][0]['return_delay']==.5


def test_float_tokens_preserve_negative_zero():
    assert p.token(-0.)!=p.token(0.)
