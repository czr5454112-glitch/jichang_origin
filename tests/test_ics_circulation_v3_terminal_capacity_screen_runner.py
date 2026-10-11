from copy import deepcopy
from scripts.experiments.ics_circulation_v3.run_terminal_capacity_screen import compare_physical


def outcome():
    value={k:[]for k in ('opportunities','actual_slow_trigger_times','physical_tick_trace','event_trace_suffix',
        'evaluation_ledger','selector_history_suffix')}
    value.update(status='controller_quiescent',stopped_at=30,initial_state={},initial_cursor={},milestones={},
        last_cycle_state={},result={'total_cost':1,'policy_stats':{}},original_endpoint={'result':{'total_cost':1,'policy_stats':{}}},
        slow_history_suffix=[{'trigger_time':3,'proposals':[{'tray_id':'t','target':'b'}],'diagnostics':{'search':'budget'}}])
    return value


def test_search_diagnostic_change_is_explicitly_excluded_from_physical_comparison():
    old=outcome();new=deepcopy(old)
    new['slow_history_suffix'][0]['diagnostics']={'search':'certificate','extra_screen_work':10}
    assert all(compare_physical(old,new).values())


def test_actual_slow_action_or_physical_trace_change_cannot_hide_in_diagnostics():
    old=outcome();new=deepcopy(old)
    new['slow_history_suffix'][0]['proposals'][0]['target']='c'
    assert not compare_physical(old,new)['slow_triggers_and_proposals']
    new=deepcopy(old);new['physical_tick_trace']=[{'time':8,'node':'c'}]
    assert not compare_physical(old,new)['physical_tick_trace']
