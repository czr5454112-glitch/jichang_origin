"""Source-only candidate and counter: no current campaign artifacts or native."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import research_original_low_wip_repeat as p
from scripts.experiments.g31_ics_circulation import repeat_quiescent_cap as q
from scripts.experiments.g31_ics_circulation.diagnose_repeat_postcap_saved import ProofCounter


def test_entire_class_ast_only_moves_existing_cap_check():
    assert q.prove_only_cap_check_moved()['all_other_class_ast_identical'] is True
    assert q.BaseOwner is p.BaseOwner
    for name in ('base','reuse','physical_barrier','invitation','local_permit','is_supply'):
        assert getattr(q,name) is getattr(p,name)


def test_ast_guard_rejects_any_other_method_change():
    source=Path(q.__file__).read_text(encoding='utf8')
    with pytest.raises(ValueError,match='other_ast_changed'):
        q.prove_only_cap_check_moved(new_source=source.replace('self.client.refresh(owner_id=self.owner)', 'self.client.refresh(owner_id=self.peer)'))


class Client:
    def __init__(self): self.state={'outbox':{}}; self.refreshed=0; self.submits=[]
    def refresh(self,**kwargs): self.refreshed+=1
    def submit(self,*args,**kwargs): self.submits.append((args,kwargs))


def owner(cls):
    value=cls.__new__(cls)
    value.halt_new_actions=False; value.quiet=True; value.failure=None; value.index=0; value.rows=[]
    value.owner='A'; value.peer='B'; value.client=Client(); value.cap_observed=False
    value.plan={'token_tray_id':'token','parking':[],'supply_cap':3}
    value.relayed=[]; value.replied=[]; value.repeat_publications=[]; value.next_publication=200
    value.publications=0; value.last_barrier=None
    value.reads=[]
    def view(*args):
        value.reads.append('view')
        return {'owner_id':'A','now':100.,'node_contracts':[],'trays':[]}
    def peer(*args): value.reads.append('peer'); return []
    value.session=SimpleNamespace(physical_time=100.,observe_protocol_control_policy_recent=view,protocol_planning_snapshots_v2=peer)
    return value


def install_proof(monkeypatch,proof):
    monkeypatch.setattr(p.BaseOwner,'activate',lambda self:self.client.refresh(owner_id=self.owner))
    for module in (p,q):
        monkeypatch.setattr(module,'physical_barrier',lambda *a:deepcopy(proof))
        monkeypatch.setattr(module,'invitation',lambda *a:None)


def test_nonlocal_token_cap_is_sticky_but_refresh_never_skipped(monkeypatch):
    install_proof(monkeypatch,{'known_supply_count':3,'received_request_ids':['opaque'],'peer_message_id':'m'})
    old,new=owner(p.RepeatOwner),owner(q.RepeatOwner)
    old.activate();new.activate()
    assert old.reads==new.reads==['view','peer']
    assert old.cap_observed is False and new.cap_observed is True
    old.activate();new.activate()
    assert old.reads==['view','peer','view','peer'] and new.reads==['view','peer']
    assert old.client.refreshed==new.client.refreshed==2 and not new.client.submits


@pytest.mark.parametrize('proof',[None,{'known_supply_count':2,'received_request_ids':['opaque'],'peer_message_id':'m'}])
def test_no_valid_exhausted_budget_means_exact_old_read_behavior(monkeypatch,proof):
    install_proof(monkeypatch,proof); old,new=owner(p.RepeatOwner),owner(q.RepeatOwner)
    for _ in range(3): old.activate();new.activate()
    assert old.reads==new.reads and old.client.refreshed==new.client.refreshed==3
    assert not old.cap_observed and not new.cap_observed


def test_halted_new_actions_still_refreshes_without_reading(monkeypatch):
    install_proof(monkeypatch,None); old,new=owner(p.RepeatOwner),owner(q.RepeatOwner)
    old.halt_new_actions=new.halt_new_actions=True
    old.activate();new.activate()
    assert old.client.refreshed==new.client.refreshed==1 and old.reads==new.reads==[]


def test_sticky_cap_keeps_new_received_ack_relay_before_early_return(monkeypatch):
    install_proof(monkeypatch,None); new=owner(q.RepeatOwner); new.cap_observed=True
    rid=p.base.owner_request_id('A','single-supply')
    new.client.state['outbox'][rid]={'kind':'transfer','terminal':True,'submission_reply':{'status':'accepted'},
        'client_view':{'last_delivered_ack':{'status':'received','delivered_at':99.}}}
    new.activate()
    assert new.client.refreshed==1 and len(new.client.submits)==1 and new.reads==[]
    assert new.repeat_publications[0]['reason']['kind']=='received_ack_relay'


def test_first_proof_counter_keeps_nonlocal_empty_fact_and_only_future_reads():
    c=ProofCounter(3,'token')
    c.read('observe_protocol_control_policy_recent','A',10.,5,{'now':10.,'trays':[]})
    c.read('protocol_planning_snapshots_v2','A',10.,6,[])
    c.barrier('A',{'known_supply_count':3,'received_request_ids':['opaque'],'peer_message_id':'m'})
    c.read('observe_protocol_control_policy_recent','A',20.,9,{'now':20.,'trays':[]})
    c.read('protocol_planning_snapshots_v2','A',20.,10,[])
    c.barrier('A',{'known_supply_count':8,'received_request_ids':['opaque'],'peer_message_id':'later'})
    result=c.summary()['A']
    assert result['at']==10 and result['current_token_locally_empty'] is False
    assert result['subsequent_reads']=={'observe_protocol_control_policy_recent':1,'protocol_planning_snapshots_v2':1}


def test_counter_rejects_stale_view_for_current_proof():
    c=ProofCounter(3,'token')
    c.read('observe_protocol_control_policy_recent','A',10.,5,{'now':9.,'trays':[]})
    c.read('protocol_planning_snapshots_v2','A',10.,6,[])
    with pytest.raises(ValueError,match='counter_current_reads'):
        c.barrier('A',{'known_supply_count':3})


def test_source_only_plan_preserves_full_domain_and_no_launch_claim():
    plan=q.comparison_contract()
    assert plan['offered_each']==28506 and plan['horizon_each']==86400 and plan['cumulative_supply_caps']==[3,8]
    assert plan['circulating_tokens_each']==1 and plan['total_trays_each']==22 and plan['other_parked_trays']==21
    assert plan['status']=='source_only_native_unexecuted' and 'No native launch command' in plan['execution']
