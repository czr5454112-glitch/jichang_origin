from copy import deepcopy
from dataclasses import replace
import pickle
import pytest

from scripts.experiments.ics_circulation_v3.model import Bag,Edge,Network,Node,Snapshot,Tray,Reservation,Leg,RouteCandidate
from scripts.experiments.ics_circulation_v3.runtime import INFINITY,ExecutionValidator
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.network_role_labels import BudgetGenerator,SearchAccounting,SearchBudget
from scripts.experiments.ics_circulation_v3.terminal_capacity_screen import (
    terminal_capacity_certificate,TerminalScreenGenerator,TerminalScreenFactory,ScreenAccounting)
from scripts.experiments.ics_circulation_v3.routing_cache_contract import ReplayRegionalFactory


def state():
    return Snapshot(0,Network({n:Node(n,'z','p',1)for n in ('a','b','c')},
        {'ab':Edge('ab','a','b',1)}),{'t':Tray('t','a','loaded','bag'),'other':Tray('other','c')},
        {'bag':Bag('bag','a','b',0,100)})


def generator():
    return RegionalCandidateGenerator(horizon=10,expansion_limit=3000,deadline_ms=None,
        dynamic_local=True,local_label_limit=3,cache_contract='isolated_replay_v1')


def test_later_future_occupancy_blocks_entire_terminal_interval():
    s=state();s.reservations=(Reservation('node:b',50,INFINITY,'other'),)
    c=terminal_capacity_certificate(s,'t','b',10)
    assert c['certified']and c['conflict_at']==50 and c['cutoff']==10
    for arrive in range(1,11):
        p=RouteCandidate('x','bag','t',(Leg('ab',arrive-1,arrive),),arrive+s.module.unload_ticks,
            arrive+s.module.unload_ticks+s.module.hold_ticks('b'),s.version,'x',True)
        assert not ExecutionValidator().validate(s,p).accepted


def test_half_open_release_at_horizon_is_not_certificate():
    s=state();s.reservations=(Reservation('node:b',2,10,'other'),)
    assert not terminal_capacity_certificate(s,'t','b',10)['certified']
    s.reservations=(Reservation('node:b',10,20,'other'),)
    assert terminal_capacity_certificate(s,'t','b',10)['certified']


def test_own_and_duplicate_reservations_do_not_inflate_occupancy():
    s=state();s.network.nodes['b']=replace(s.network.nodes['b'],capacity=2)
    s.reservations=(Reservation('node:b',0,INFINITY,'other'),Reservation('node:b',3,INFINITY,'other'),
                    Reservation('node:b',2,INFINITY,'t'))
    assert not terminal_capacity_certificate(s,'t','b',10)['certified']


@pytest.mark.parametrize('horizon',[-1,True,INFINITY,INFINITY+1])
def test_unsupported_horizon_does_not_certify(horizon):
    s=state();s.reservations=(Reservation('node:b',0,INFINITY,'other'),)
    c=terminal_capacity_certificate(s,'t','b',horizon)
    assert not c['certified']and c['status']=='unsupported_or_invalid_delegate'


def test_screen_record_cap_delegates_without_claiming_infeasibility():
    s=state();s.reservations=(Reservation('node:b',0,INFINITY,'other'),)
    c=terminal_capacity_certificate(s,'t','b',10,max_records=1)
    assert not c['certified']and c['status']=='screen_record_budget_unknown_delegate'


def test_unblocked_raw_candidate_pool_is_exact_and_original_object_returned():
    s=state();plain=generator();expected=plain.generate(s,'bag','t',4)
    wrapped=TerminalScreenGenerator(generator());actual=wrapped.generate(s,'bag','t',4)
    assert actual==expected and wrapped.last_expansions==plain.last_expansions
    assert wrapped.last_search_status==plain.last_search_status
    assert not wrapped.accounting.rows[0]['certificate']['certified']


def test_certified_empty_query_still_counts_one_search_call_and_extra_screen_work():
    s=state();s.reservations=(Reservation('node:b',0,INFINITY,'other'),)
    wrapped=TerminalScreenGenerator(generator());owner=SearchAccounting(SearchBudget())
    counted=BudgetGenerator(wrapped,owner)
    assert counted.generate(s,'bag','t',4)==()
    assert len(owner.rows)==1 and owner.work==0
    assert owner.rows[0]['status']=='terminal_capacity_certificate'
    assert wrapped.accounting.screen_work>0 and wrapped.last_diagnostics['terminal_screen']['certified']


def test_copy_pickle_share_only_copied_accounting_and_preserve_live_cache():
    account=ScreenAccounting();g=generator();wrapper=TerminalScreenGenerator(g,account)
    factory=TerminalScreenFactory(ReplayRegionalFactory.from_generator(g),account)
    wrapper.generate(state(),'bag','t',4)
    for clone in (deepcopy((wrapper,factory)),pickle.loads(pickle.dumps((wrapper,factory)))):
        assert clone[0].accounting is clone[1].accounting
        assert clone[0].accounting is not account
        clone[1]().generate(state(),'bag','t',4)
        assert len(clone[0].accounting.rows)==2 and len(account.rows)==1


def test_invalid_own_irrevocable_request_delegates_to_original():
    s=state();s.trays['t']=replace(s.trays['t'],available_at=5)
    s.reservations=(Reservation('node:b',0,INFINITY,'other'),)
    wrapped=TerminalScreenGenerator(generator())
    assert wrapped.generate(s,'bag','t',4)==()and wrapped.last_search_status=='invalid_request'
    assert not wrapped.accounting.rows[0]['certificate']['certified']


def test_unknown_bag_preserves_original_empty_invalid_request():
    wrapped=TerminalScreenGenerator(generator())
    assert wrapped.generate(state(),'unknown','t',4)==()
    assert wrapped.last_search_status=='invalid_request'and wrapped.last_expansions==0


def test_delegate_failure_keeps_paid_screen_and_partial_search_work(monkeypatch):
    original=generator();wrapped=TerminalScreenGenerator(original)
    def fail(*args,**kwargs):
        original.last_expansions=17;original.last_search_status='injected_partial'
        original.last_diagnostics={'work_units_by_stage':{'partial':17}}
        raise RuntimeError('injected delegate failure')
    monkeypatch.setattr(original,'generate',fail)
    with pytest.raises(RuntimeError,match='delegate failure'):wrapped.generate(state(),'bag','t',4)
    row=wrapped.accounting.rows[0]
    assert row['phase']=='error'and row['search_work']==17
    assert wrapped.accounting.screen_work>0 and row['certificate']['screen_work']>0


def test_record_binds_actual_public_query_snapshot_before_generation():
    from scripts.experiments.ics_circulation_v3.same_zone_query_coverage import public_sha
    s=state();expected=public_sha(s);wrapped=TerminalScreenGenerator(generator())
    wrapped.generate(s,'bag','t',4)
    row=wrapped.accounting.rows[0]
    assert row['public_snapshot_sha256']==expected and row['observation_cpu_seconds']>=0
    s.reservations=(Reservation('node:b',50,INFINITY,'other'),)
    wrapped.generate(s,'bag','t',4)
    assert wrapped.accounting.rows[-1]['public_snapshot_sha256']!=expected
