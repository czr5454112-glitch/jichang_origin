import copy
import pytest
from scripts.experiments.g31_ics_circulation import prepare_cooperative_bridge_policy as p


def actual_parking():
    prior=p.OUT/'original_low_wip_prepare_005'
    plan=p.policy.base.read(prior/'preregistered_protocol.json')
    data=p.policy.base.gzread(prior/'input.json.gz')
    public={k:data[k] for k in ('node_records','node_contracts','edge_records','edge_contracts')}
    return p.policy.base.parking_plan(public,data['trays']),plan['parking_plan']


def test_actual_frozen_parking_tuple_list_boundary_is_exact():
    computed,persisted=actual_parking()
    assert computed!=persisted
    assert p.same_json_structure(computed,persisted)


@pytest.mark.parametrize('change',['path_order','identity','number_type','number_value'])
def test_persisted_parking_differences_are_not_normalized_away(change):
    computed,persisted=actual_parking();value=copy.deepcopy(persisted)
    row=value['parking'][0]
    if change=='path_order':row['positive_path'].reverse()
    elif change=='identity':row['request_id']+=':changed'
    elif change=='number_type':row['source']=float(row['source'])
    else:row['free_flow_seconds']+=.001
    assert not p.same_json_structure(computed,value)


def test_nonfinite_preparation_data_fails_closed():
    with pytest.raises(ValueError):p.same_json_structure({'x':float('nan')},{'x':float('nan')})


def test_source_closure_contains_absolute_eval_dependency_and_self_tests():
    names={str(path.relative_to(p.ROOT)).replace('\\','/') for path in p.source_paths()}
    assert 'scripts/eval/run_g4irsf28_service_potential.py' in names
    assert 'src/czr005/io/legacy_map.py' in names
    assert 'tests/test_g31_circulation_bridge_prepare.py' in names
