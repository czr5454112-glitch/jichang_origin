"""Pure preparation tests only; deliberately never loads a native artifact."""
from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation import native028_receiver_fixture as fixture
from scripts.experiments.g31_ics_circulation import native028_receiver_gate as gate
from scripts.experiments.g31_ics_circulation import foundation_airport_admission_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_domain as domain


def test_fixture_domain_and_non_authorizing_policy_fields():
    old=fixture.scene();zero=fixture.scene(0);reserve=fixture.scene(1)
    assert fixture.FIELD not in old['node_contracts'][1]
    for data in (zero,reserve):
        rebuilt=deepcopy(data);rebuilt['node_contracts'][1].pop(fixture.FIELD)
        assert rebuilt==old
    assert old['node_contracts'][1]['capacity']==reserve['node_contracts'][1]['capacity']==4
    assert old['owner_protocol']==reserve['owner_protocol']
    assert len(old['jobs'])==1 and len(old['trays'])==5
    assert fixture.tape()[0]==fixture.tape()[1]
    assert fixture.tape()[-2]['endpoint']=='protocol_command'
    assert fixture.tape()[-1]['args']==[20.]


def test_budget_declares_invalid_constructors_and_serial_arms():
    assert sum(map(len,gate.ARMS.values()))+len(gate.INVALID)==9
    assert len(gate.ARMS['native027'])==1
    assert len(gate.ARMS['native028'])+len(gate.INVALID)==8
    assert type(gate.INVALID['boolean']) is bool
    assert type(gate.INVALID['fraction']) is float


def test_parity_removes_only_diagnostic_clocks():
    before={'wall_seconds':1.,'status':'received','received_at':5.,'outputs':[{'time':3.}]}
    after=deepcopy(before);after['wall_seconds']=10.
    assert fixture.stable(before)==fixture.stable(after)
    after['received_at']=5.001
    assert fixture.stable(before)!=fixture.stable(after)
    after=deepcopy(before);after['outputs'][0]['time']=3.001
    assert fixture.stable(before)!=fixture.stable(after)


@pytest.fixture(scope='module')
def full_input():
    return domain.build_full_input()[0]


def test_airport_overlay_preserves_entire_business_and_physics(full_input):
    prior=deepcopy(full_input);candidate=campaign.apply_policy(full_input)
    assert prior==full_input
    assert len(candidate['jobs'])==28506 and candidate['jobs']==full_input['jobs']
    assert candidate['trays']==full_input['trays'] and len(candidate['trays'])==22
    assert candidate['edge_contracts']==full_input['edge_contracts']
    assert candidate['node_records']==full_input['node_records'] and candidate['edge_records']==full_input['edge_records']
    changed=[(a,b)for a,b in zip(full_input['node_contracts'],candidate['node_contracts'])if a!=b]
    assert len(changed)==1 and changed[0][0]['node']==49
    assert changed[0][1]=={**changed[0][0],fixture.FIELD:1}
    assert domain.digest(candidate)==campaign.POLICY_INPUT_SHA
    assert domain.digest({k:v for k,v in candidate.items()if k!='jobs'})==campaign.POLICY_NONBUSINESS_SHA
    assert campaign.policy_contract()['physical_capacity_changed'] is False


def test_overlay_rejects_different_business_or_physics(full_input):
    wrong=deepcopy(full_input);wrong['jobs'][0]['arrival']+=.001
    with pytest.raises(ValueError,match='base_business_input'):campaign.apply_policy(wrong)
    wrong=deepcopy(full_input);wrong['node_contracts'][49]['capacity']+=1
    with pytest.raises(ValueError,match='base_business_input'):campaign.apply_policy(wrong)


def test_native027_contract_cannot_be_accepted_as_native028(tmp_path):
    from scripts.experiments.g31_ics_circulation import native028_run_acceptance as acceptance
    path=tmp_path/'old.json';gate.write(path,{'schema':'g31.native027_contract.v1','status':'accepted'})
    with pytest.raises(ValueError,match='contract_semantic_binding'):
        acceptance.verify(gate.ref(path),{'path':'unread','sha256':'unread'})
