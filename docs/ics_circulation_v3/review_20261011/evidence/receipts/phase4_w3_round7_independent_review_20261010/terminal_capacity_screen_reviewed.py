"""Opt-in sufficient terminal-capacity rejection for an unchanged witness domain.

Every original full witness ends in a node reservation [arrival, INFINITY),
with arrival <= now + horizon. Conflict on its subinterval [now+H, INFINITY)
therefore rules out this query domain in the current public Snapshot. This is
not a forecast of future task infeasibility. No default generator is modified.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from time import process_time,perf_counter

from .runtime import INFINITY,effective_reservations


def terminal_capacity_certificate(snapshot,tray_id,destination,horizon,*,max_records=200000):
    """Return a conservative certificate or delegate verdict, with explicit work.

The cap bounds a conservative input/materialization record count, not CPU.
`screen_work` counts inspected input records, merged effective slots, target
event insertions and sorted event visits; internal Python sorting comparisons
are covered by CPU but not claimed as primitive work units.
"""
    cpu,wall=process_time(),perf_counter()
    result={'certified':False,'status':'not_certified','screen_work':0,
        'work_by_stage':{},'destination':destination,'tray_id':tray_id,
        'horizon':horizon,'cutoff':None,'conflict_at':None,'other_occupancy':None,
        'capacity':None,'witness_slots':[],
        'scope':'Current public Snapshot, original finite-horizon full-witness terminal node reservation only; not future task infeasibility.'}
    def finish(status):
        result['status']=status;result['screen_cpu_seconds']=process_time()-cpu
        result['screen_wall_seconds']=perf_counter()-wall;return result
    if(type(horizon)is not int or horizon<0 or type(max_records)is not int or max_records<1
       or snapshot.now+horizon>=INFINITY or tray_id not in snapshot.trays
       or destination not in snapshot.network.nodes):return finish('unsupported_or_invalid_delegate')
    cutoff=snapshot.now+horizon;result['cutoff']=cutoff
    estimate=len(snapshot.reservations)+3*len(snapshot.old_in_transit)+2*len(snapshot.trays)
    result['input_materialization_record_upper_bound']=estimate
    if estimate>max_records:return finish('screen_record_budget_unknown_delegate')
    work={'input_records':len(snapshot.reservations)+len(snapshot.old_in_transit)+len(snapshot.trays),
          'effective_slots':0,'target_event_insertions':0,'event_visits':0}
    slots=effective_reservations(snapshot);work['effective_slots']=len(slots)
    if len(slots)>max_records:
        result['work_by_stage']=work;result['screen_work']=sum(work.values())
        return finish('screen_record_budget_unknown_delegate')
    target='node:'+destination;events={};evidence=[]
    for slot in slots:
        if slot.tray_id==tray_id or slot.resource!=target:continue
        left,right=max(cutoff,slot.start),min(INFINITY,slot.end)
        if left>=right:continue
        events[left]=events.get(left,0)+1;events[right]=events.get(right,0)-1
        work['target_event_insertions']+=2
        evidence.append({'tray_id':slot.tray_id,'start':slot.start,'end':slot.end})
    capacity=snapshot.network.nodes[destination].capacity;result['capacity']=capacity
    occupancy=0
    for tick,delta in sorted(events.items()):
        work['event_visits']+=1;occupancy+=delta
        if tick<INFINITY and occupancy>=capacity:
            result.update(certified=True,conflict_at=tick,other_occupancy=occupancy,
                witness_slots=[s for s in evidence if s['start']<=tick<s['end']]);break
    if capacity<=0:
        result.update(certified=True,conflict_at=cutoff,other_occupancy=0,witness_slots=[])
    result['work_by_stage']=work;result['screen_work']=sum(work.values())
    return finish('terminal_capacity_certificate'if result['certified']else'not_certified')


@dataclass
class ScreenAccounting:
    rows:list=field(default_factory=list)
    screen_work:int=0
    screen_cpu_seconds:float=0.


class TerminalScreenGenerator:
    def __init__(self,generator,accounting=None,*,max_records=200000):
        from .routing import RegionalCandidateGenerator
        self.generator=generator;self.accounting=ScreenAccounting()if accounting is None else accounting
        self.max_records=max_records;self.last_expansions=0;self.last_search_status='not_started';self.last_diagnostics={}
        if type(generator)is not RegionalCandidateGenerator or getattr(generator,'deadline_ms',None)is not None or getattr(generator,'cache_contract',None)!='isolated_replay_v1':
            raise ValueError('terminal screen requires deterministic regional replay contract')

    def __getattr__(self,name):return getattr(object.__getattribute__(self,'generator'),name)

    def generate(self,state,bag_id,tray_id,k=4):
        bag=state.bags.get(bag_id)
        return self._call(state,bag_id,tray_id,None if bag is None else bag.destination,k)

    def generate_empty(self,state,tray_id,destination,k=1):
        return self._call(state,None,tray_id,destination,k)

    def _call(self,state,bag_id,tray_id,destination,k):
        tray=state.trays.get(tray_id)
        eligible=(type(k)is int and k>0 and tray is not None and tray.node is not None
            and tray_id not in state.plans and tray.available_at<=state.now
            and destination in state.network.nodes
            and not any(f.tray_id==tray_id and f.arrive>state.now for f in state.old_in_transit)
            and ((bag_id is None and tray.mode=='empty'and tray.bag_id is None)
                 or(bag_id is not None and tray.mode=='loaded'and tray.bag_id==bag_id)))
        certificate=terminal_capacity_certificate(state,tray_id,destination,self.generator.horizon,
            max_records=self.max_records)if eligible else {'certified':False,'status':'invalid_request_delegate',
                'screen_work':0,'screen_cpu_seconds':0.,'scope':'Original generator handles invalid request.'}
        if certificate['certified']:
            options=();self.last_expansions=0;self.last_search_status='terminal_capacity_certificate'
            self.last_diagnostics={'work_units_by_stage':{},'candidate_count':0,'expansions':0,
                'search_skipped_with_sufficient_certificate':True,'missing_candidate_is_not_future_task_infeasibility':True,
                'cache_accounting':None}
        else:
            try:
                options=(self.generator.generate(state,bag_id,tray_id,k)if bag_id is not None
                         else self.generator.generate_empty(state,tray_id,destination,k))
            except BaseException as error:
                self.last_expansions=self.generator.last_expansions
                self.last_search_status=self.generator.last_search_status
                self.last_diagnostics=deepcopy(self.generator.last_diagnostics)
                self.last_diagnostics['terminal_screen']=certificate
                self._record(state,bag_id,tray_id,destination,k,certificate,(),
                    phase='error',error={'type':type(error).__name__,'message':str(error)})
                raise
            self.last_expansions=self.generator.last_expansions
            self.last_search_status=self.generator.last_search_status
            self.last_diagnostics=deepcopy(self.generator.last_diagnostics)
        self.last_diagnostics['terminal_screen']=certificate
        self._record(state,bag_id,tray_id,destination,k,certificate,options)
        return options

    def _record(self,state,bag_id,tray_id,destination,k,certificate,options,*,phase='returned',error=None):
        self.accounting.screen_work+=certificate['screen_work']
        self.accounting.screen_cpu_seconds+=certificate['screen_cpu_seconds']
        self.accounting.rows.append({'time':state.now,'version':state.version,'bag_id':bag_id,
            'tray_id':tray_id,'destination':destination,'requested_k':k,'certificate':certificate,
            'search_work':self.last_expansions,'search_status':self.last_search_status,
            'options':deepcopy(options),'phase':phase,'error':error})


class TerminalScreenFactory:
    def __init__(self,inner_factory,accounting,*,max_records=200000):
        self.inner_factory=inner_factory;self.accounting=accounting;self.max_records=max_records
    def __call__(self,horizon=None):
        return TerminalScreenGenerator(self.inner_factory(horizon),self.accounting,max_records=self.max_records)
    def __getattr__(self,name):return getattr(object.__getattribute__(self,'inner_factory'),name)


def install_terminal_screen(engine,*,max_records=200000):
    """After enable_replay_cache and before bind_accounting; returns extra ledger.

The original BudgetGenerator remains outside this wrapper so query calls are
counted, including certified empty returns. Search work and screen work are
different recorded axes. Skipped searches do not warm the private cache; later
cold-equivalent logical search and actual candidate equality must be audited.
"""
    from .network_role_labels import BudgetGenerator,BudgetFactory
    if isinstance(engine._generator,(TerminalScreenGenerator,BudgetGenerator))or isinstance(engine.generator_factory,(TerminalScreenFactory,BudgetFactory)):
        raise ValueError('install once before accounting')
    inner=None if engine.slow_controller is None else engine.slow_controller.controller
    if inner is not None and isinstance(inner.generator_factory,(TerminalScreenFactory,BudgetFactory)):
        raise ValueError('install once before slow accounting')
    accounting=ScreenAccounting()
    engine._generator=TerminalScreenGenerator(engine._generator,accounting,max_records=max_records)
    engine.generator_factory=TerminalScreenFactory(engine.generator_factory,accounting,max_records=max_records)
    if engine.slow_controller is not None:
        inner.generator_factory=TerminalScreenFactory(inner.generator_factory,accounting,max_records=max_records)
    return accounting
