"""Conditional historical+one-fresh-pair communication/physical projection.

New source candidate, not yet accepted conformance or an online solver. Future
messages come from projected source observations only. Saved completion data,
branch keys, native sessions and native forks are not inputs to this module.
"""
from __future__ import annotations
import ast
import copy
import heapq
import inspect
import math
import textwrap
from . import public_live_obligation_event_projection_v2 as physics
from . import live_obligation_delivered_context as context
from . import live_obligation_projected_captures as captures
from . import live_obligation_unloading_policy as policy
from . import domain_guard_historical_service as guard
from . import research_native_preexisting_v3_bound as source_policy

VERSION='g31.live_obligation.communication_projection.v1'
WIRE=.01
ACK=.02


class Projection(physics.Projection):
    """Model world is separate from each owner's delayed knowledge state."""
    def __init__(self,bundle,action,initial):
        super().__init__(bundle,action)
        self.world=captures.CaptureWorld(self,initial)
        self.channel_sequence={'A':2,'B':2}
        self.client_rows={};self.request_sequence=0;self.ack_sequence=0
        self.inbox={'A':None,'B':None};self.demand_inbox={};self.demand_channel={}
        self.owner_state={o:{'pending':None,'quiet':-1.,'seen':set(),'started':set(),
            'reply_budget':policy.PhaseReplyBudget(),'pending_reply':None} for o in ('A','B')}
        self.communication_trace=[];self.collection_trace=[];self.unknown_phases=[]
        self.activated_boundaries=set()
        self.future_data_authority='conditional_projection_only'
        # The closed declared initial fixture has all three tray availability
        # epochs0. Capture loading.available_at is a different typed field:
        # observed LOAD_START + duration. Never retain that future bound as the
        # underlying empty-availability epoch after loading finishes.
        for t in self.trays.values():t['available_at']=0.
        for owner in ('A','B'):
            signature=self.waiting_signature(owner)
            self.demand_channel[owner]={'terminal':True,'captured':signature}
            self.demand_inbox[self.peer(owner)]=signature

    @staticmethod
    def peer(owner):return 'B' if owner=='A' else 'A'

    def schedule(self,when,kind,*args):
        if kind.startswith('projected_'):
            self.sequence+=1
            heapq.heappush(self.events,(when,6,self.sequence,kind,args))
        elif kind=='owner_activation':
            # Actual fixed runner forms a set from drained notifications and
            # the due periodic tick, then invokes owners in sorted order.
            self.sequence+=1
            heapq.heappush(self.events,(when,99 if args[0]=='A' else 100,self.sequence,kind,args))
        else:super().schedule(when,kind,*args)

    def new_row(self,owner,kind,**request):
        self.request_sequence+=1;key=f'projection:{owner}:{self.request_sequence}'
        request={'owner_id':owner,'request_id':key,'kind':kind,**request}
        row={'owner':owner,'kind':kind,'request':request,'ack':None,'terminal':False,
             'attempt':1,'issued_at':self.time}
        self.client_rows[key]=row
        return row

    def endpoint(self,row):
        return {'request_id':row['request']['request_id'],'kind':row['kind'],'attempt':row['attempt'],
            'status':'acknowledged' if row['ack'] is not None else 'submitted',
            'last_delivered_ack':copy.deepcopy(row['ack'])}

    def acknowledge(self,row,status,**extra):
        self.ack_sequence+=1
        row['ack']={'sequence':self.ack_sequence,'attempt':row['attempt'],'status':status,
                    'delivered_at':self.time,**extra}
        row['terminal']=row['terminal'] or status in ('received','rejected','updated','delivered','expired','failed')
        self.notify_owner(row['owner'],'delivered_'+row['kind']+'_ack')

    def publish(self,owner,label):
        row=self.new_row(owner,'planning_snapshot_v3',target_owner=self.peer(owner),
            message_delay=WIRE,publication_delay=WIRE,expiry=self.time+.2)
        row['label']=label
        self.schedule(self.time+WIRE,'projected_capture',row)
        self.communication_trace.append({'at':self.time,'phase':'publication_submitted','owner':owner,
            'label':label,'request_id':row['request']['request_id']})
        return row

    def waiting_signature(self,owner):
        return tuple(sorted(key for key,j in self.jobs.items()
            if self.world.owner(j['origin'])==owner and j['status']=='waiting_for_tray'))

    def publish_demand(self,owner):
        row=self.new_row(owner,'demand',target_owner=self.peer(owner),message_delay=WIRE,publication_delay=WIRE)
        self.demand_channel[owner]=row
        self.schedule(self.time+WIRE,'projected_demand_capture',row)

    def begin_leg(self,key,goal,*,ready=None):
        super().begin_leg(key,goal,ready=ready)
        if hasattr(self,'world'):self.world.begin_leg(key)

    def complete_leg(self,key):
        t=self.trays[key];job=t['job'];empty=t['mode']=='empty_transit'
        self.world.complete_leg(key)
        if empty:t['available_at']=self.time
        super().complete_leg(key)
        if not empty:
            self.jobs[job]['status']=t['mode']
            if t['mode']=='storage':self.jobs[job]['storage_entered_at']=self.time
            elif t['mode']=='unloading':self.world.started[key]=self.time

    def load_waiting(self,key):
        super().load_waiting(key)
        t=self.trays[key]
        if t['mode']=='loading':
            t['generation']+=1;self.world.started[key]=self.time
            self.jobs[t['job']]['status']='loading'
            self.world.prefix[key]=[t['node']]

    def commit(self,key,target):
        t=self.trays[key];old=t['edge_to']
        super().commit(key,target)
        if old<0 and t['edge_to']>=0:
            t['traversal_id']+=1;self.world.entries.pop(key,None)

    def request(self,key,destination,earliest):
        super().request(key,destination,earliest)
        r=self.requests[-1]
        row=self.new_row('B' if key=='E' else 'A','transfer',tray_id=key,source=self.trays[key]['node'],
            destination=destination,earliest_departure=r['earliest'],expiry=39.,message_delay=WIRE)
        r['client_row']=row;row['physical_request']=r

    def submit_preference(self,key,target,*,expiry=None):
        super().submit_preference(key,target,expiry=expiry)
        tray=self.trays[key];owner=self.world.owner(tray['node'])
        row=self.new_row(owner,'route',tray_id=key,business_bag_id=tray['job'],
            **{'from':tray['node'],'next':target},expected_generation=tray['generation'],
            expected_traversal=tray['traversal_id'],message_delay=WIRE,
            expiry=self.time+5. if expiry is None else expiry)
        row['command_serial']=self.serial

    def execute_preference(self,record):
        super().execute_preference(record)
        row=next(r for r in self.client_rows.values() if r.get('command_serial')==record['id'])
        outcome=self.commands[-1]
        self.schedule(self.time+ACK,'projected_route_ack',row,outcome['status'])

    def notify_local_lifecycle(self,key):
        # Actual policy acts at owner boundaries after the native timestamp
        # drains. It never observes inside a load/hold completion handler.
        pass

    def own_rows(self,owner):
        return {key:{'request':copy.deepcopy(row['request']),'kind':row['kind'],
                    'terminal':row['terminal'],'ack':copy.deepcopy(row['ack'] or {})}
                for key,row in self.client_rows.items() if row['owner']==owner}

    def begin_collection(self,owner,phase,trigger):
        s=self.owner_state[owner];s['started'].add(phase)
        row=self.publish(owner,phase)
        s['pending']={'phase':phase,'at':self.time,'deadline':self.time+.08,
            'request_id':row['request']['request_id'],'root':'projected_phase:'+phase,
            'trigger_tray':copy.deepcopy(trigger),'peer_message':None,'recollection_index':0,
            'policy_quiet_since':self.time}
        self.schedule(s['pending']['deadline'],'projected_collection_deadline',owner)

    def exchange(self,owner):
        s=self.owner_state[owner];envelope=self.inbox[owner]
        if envelope is None:return
        local=envelope['capture']['capture_v2']['local_capture'];identity=local['message_id']
        if identity in s['seen']:return
        s['seen'].add(identity)
        if s['pending'] is not None:
            if local['captured_at']>=s['pending']['at']:s['pending']['peer_message']=identity
            return
        phase=source_policy.invitation_phase(envelope,owner,self.time)
        if not s['reply_budget'].admit(phase,local):return
        refresh=[]
        if phase=='reuse1_loading_ack_refresh' and owner=='A':
            for r in self.requests:
                if r['tray']=='L' and not r['client_row']['terminal']:
                    r['next_retry']=self.time+.5;r['client_row']['attempt']+=1
                    self.schedule(self.time+WIRE,'request_delivery',r);refresh.append(r)
        if refresh:s['pending_reply']={'phase':phase,'requests':refresh}
        else:self.reply(owner,phase)

    def reply(self,owner,phase):
        self.publish(owner,'reply:'+phase)
        if phase in ('first_return','first_reuse_route'):
            self.owner_state[owner]['quiet']=max(self.owner_state[owner]['quiet'],self.time+.08)

    def collect(self,owner,pending):
        own=self.client_rows[pending['request_id']]
        view=self.world.view(owner)
        received=[] if self.inbox[owner] is None else [copy.deepcopy(self.inbox[owner])]
        own_rows=self.own_rows(owner)
        actions=sorted((k,r['kind']) for k,r in own_rows.items() if r['kind'] in policy.PHYSICAL_KINDS)
        publications={k:r['request'] for k,r in own_rows.items() if r['kind']=='planning_snapshot_v3'}
        information=guard.validate_collected_endpoints(view,self.endpoint(own),received,
            retained=self.world.retained(owner),own_actions=actions,phase=pending['phase'],
            own_request_id=pending['request_id'],peer_message_id=pending['peer_message'],
            collection_started_at=pending['at'],policy_quiet_since=pending['policy_quiet_since'],
            own_request=own['request'],own_publication_requests=publications)
        screen={'status':'not_admitted','reason':'no_failed_read'}
        if information.get('status')=='unknown':screen=policy.retry_admission(information,pending,view,own_rows)
        return information,screen,view

    def decide(self,owner):
        s=self.owner_state[owner];p=s['pending']
        if p is None or self.time<s['quiet']:return
        ack=self.client_rows[p['request_id']]['ack'] or {}
        if not(ack.get('status')=='delivered' and p['peer_message'] is not None) and self.time<p['deadline']:return
        info,screen,view=self.collect(owner,p)
        record={'at':self.time,'owner':owner,'phase':p['phase'],'recollection_index':p['recollection_index'],
            'collection_started_at':p['at'],'information_status':info['status'],
            'reasons':copy.deepcopy(info.get('reasons',[])),
            'bundle_reasons':copy.deepcopy(info.get('bundle',{}).get('reasons',[])),
            'retry_admission':copy.deepcopy(screen),'conditional_projected_data_only':True}
        self.collection_trace.append(record)
        if screen['status']=='conditional_retry_admissible':
            row=self.publish(owner,'recollect:'+p['phase'])
            deadline=self.time+.08
            if screen['retained_own_service_bound'] is not None:deadline=min(deadline,screen['retained_own_service_bound'])
            s['pending']={**copy.deepcopy(p),'at':self.time,'deadline':deadline,
                'request_id':row['request']['request_id'],'peer_message':None,'recollection_index':1}
            self.schedule(deadline,'projected_collection_deadline',owner)
            record['disposition']='one_fresh_pair_requested';return
        known=info.get('status')=='conditional_validated_later_v3_data'
        if not known:self.unknown_phases.append(copy.deepcopy(record))
        tray=next((t for t in view['trays'] if t['tray_id']=='L'),None)
        try:
            policy.local_target(view,p['trigger_tray'],p['phase'])
            if p['phase']=='first_return':
                if not any(self.jobs[j]['origin']==7 for j in self.demand_inbox.get(owner,())):
                    raise ValueError('missing_delivered_reuse_demand')
                self.returns+=1
                # Inherited typed request implements the fixed absolute7.84
                # alternative. Unknown input uses the common immediate rule.
                original=self.action['return_delay']
                if not known:self.action['return_delay']=0.
                try:self.request('L',7,self.time)
                finally:self.action['return_delay']=original
            else:
                if known and not self.time+WIRE<info['bundle']['trays']['L']['service_ready_at']:
                    raise ValueError('final_route_wire_outside_service_window')
                if known and self.action['later_action']=='prefer_8':
                    if self.occupancy(8)>=self.nodes[8]['capacity']:raise ValueError('local_receiving_precondition')
                    self.submit_preference('L',8)
                self.choice_jobs.add('reuse1')
        except (KeyError,TypeError,ValueError) as exc:
            record['final_local_guard_reason']=str(exc);self.unknown_phases.append(copy.deepcopy(record))
        record['disposition']='final_decision_no_more_recollection';s['pending']=None

    def tick(self,owner=None):
        for o in ('A','B') if owner is None else (owner,):self.activate(o)

    def activate(self,owner):
        identity=(self.time,owner)
        if identity in self.activated_boundaries:return
        self.activated_boundaries.add(identity)
        s=self.owner_state[owner]
        # All immutable retries run even when new physical admission is held.
        for r in self.requests[:]:
            row=r['client_row']
            if row['owner']==owner and not row['terminal'] and self.time>=r['next_retry']:
                r['next_retry']=self.time+.5;row['attempt']+=1
                self.schedule(self.time+WIRE,'request_delivery',r)
        channel=self.demand_channel[owner]
        if channel['terminal'] and channel.get('captured')!=self.waiting_signature(owner):self.publish_demand(owner)
        self.exchange(owner)
        reply=s['pending_reply']
        if reply and all(r['client_row']['terminal'] and (r['client_row']['ack'] or {}).get('status')=='received'
                         for r in reply['requests']):
            self.reply(owner,reply['phase']);s['pending_reply']=None
        self.decide(owner)
        if s['pending'] is not None or self.time<s['quiet']:return
        t=self.trays['L'];view=self.world.view(owner)
        if owner=='A':
            if (t['node']==6 and t['mode']=='empty' and t['edge_to']<0 and t['available_at']<=self.time
                    and self.returns<2 and not self.return_pending
                    and any(self.jobs[j]['origin']==7 for j in self.demand_inbox.get(owner,()))):
                if 'first_return' not in s['started']:
                    self.begin_collection(owner,'first_return',next(x for x in view['trays'] if x['tray_id']=='L'))
                elif self.returns:self.returns+=1;self.request('L',7,self.time)
        else:
            r=self.last_supply;e=self.trays['E']
            if (r and r['client_row']['terminal'] and (r['client_row']['ack'] or {}).get('status')=='rejected'
                    and self.time>=r['client_row']['ack']['delivered_at']+.5
                    and len([x for x in self.requests if x['tray']=='E'])<16 and e['mode']=='empty' and e['node']==5):
                self.request('E',1,self.time)
            if t['node']==7 and t['edge_to']<0:
                if t['mode']=='loading' and t['job']=='reuse1' and 'preflight' not in s['started']:
                    s['started'].add('preflight');self.publish(owner,'preflight')
                if t['mode']=='loaded' and t['job'] not in self.choice_jobs:
                    if t['job']=='reuse1' and 'first_reuse_route' not in s['started']:
                        self.begin_collection(owner,'first_reuse_route',next(x for x in view['trays'] if x['tray_id']=='L'))
                    elif t['job']=='reuse2':self.choice_jobs.add('reuse2');self.submit_preference('L',3)

    def protocol_event(self,kind,args):
        if not kind.startswith('projected_'):return False
        if kind=='projected_collection_deadline':self.notify_owner(args[0],'collection_deadline');return True
        row=args[0]
        if kind=='projected_capture':
            row['envelope']=self.world.capture(row);row['executed_at']=self.time
            self.communication_trace.append({'at':self.time,'phase':'source_capture','owner':row['owner'],
                'request_id':row['request']['request_id'],'envelope':copy.deepcopy(row['envelope'])})
            self.schedule(self.time+WIRE,'projected_message_delivery',row)
        elif kind=='projected_demand_capture':
            row['captured']=self.waiting_signature(row['owner']);row['executed_at']=self.time
            self.channel_sequence[row['owner']]+=1
            self.schedule(self.time+WIRE,'projected_message_delivery',row)
        elif kind=='projected_message_delivery':
            row['completed_at']=self.time;peer=self.peer(row['owner'])
            if row['kind']=='planning_snapshot_v3':self.inbox[peer]=copy.deepcopy(row['envelope'])
            else:self.demand_inbox[peer]=row['captured']
            self.schedule(self.time+ACK,'projected_message_ack',row)
            self.notify_owner(peer,'delivered_'+row['kind'])
        elif kind=='projected_message_ack':
            extra={'executed_at':row['executed_at'],'completed_at':row['completed_at']}
            if row['kind']=='planning_snapshot_v3':
                envelope=copy.deepcopy(row['envelope'])
                extra.update(planning_snapshot_v3=envelope,result_id=envelope['capture']['capture_v2']['local_capture']['message_id'])
            self.acknowledge(row,'delivered',**extra)
        elif kind=='projected_route_ack':self.acknowledge(row,args[1])
        else:raise ValueError('unsupported_projected_protocol_event:'+kind)
        return True

    def before_event(self,kind,args):
        if kind=='service_ready':self.world.in_service[args[0]]=False
        elif kind=='edge_enter':self.world.entry(*args)
        elif kind=='arrive':self.world.prefix[args[0]].append(args[1]);self.world.in_service[args[0]]=True
        elif kind=='load_end':
            t=self.trays[args[0]];self.jobs[t['job']]['status']='in_transit';self.jobs[t['job']]['loaded_at']=self.time
        elif kind=='storage_release':
            t=self.trays[args[0]];self.jobs[t['job']]['status']='in_transit';self.jobs[t['job']]['storage_released_at']=self.time
        elif kind=='unload':
            t=self.trays[args[0]];job=t['job'];self.jobs[job]['status']='completed'
            t['available_at']=self.time+self.jobs[job]['hold_seconds']
            self.world.completions.append({'event':'UNLOAD_COMPLETE','status':'completed','business_bag_id':job,
                'destination':t['node'],'tray_id':args[0],'completed_at':self.time})

    def after_event(self,kind,args):
        if kind=='ack':
            r,status=args;self.acknowledge(r['client_row'],status)

    def finish(self,result):
        result.update(model_version=VERSION,projected_collections=self.collection_trace,
            projected_communication=self.communication_trace,unknown_information_phases=self.unknown_phases,
            native_protection_certified=False,native_execution_certified=False,online_information_delivered=False,
            complete_request_100ms_certified=False,comparison_scope='retrospective_conformance_not_heldout_validation')
        if self.unknown_phases:result['status']='unknown_projected_information'
        elif sum(r['disposition']=='final_decision_no_more_recollection' for r in self.collection_trace)!=2:
            result['status']='unknown_missing_projected_collection'
        return result


def make_run():
    """Retain the pinned physical event-loop statements; add explicit hooks.

The obsolete normal-exchange shortcut handlers remain but are never scheduled
by this subclass. Every original heap pop/count/horizon/tick remains present.
"""
    physics.check_sources()
    old=physics.previous.original.Projection.run
    tree=ast.parse(textwrap.dedent(inspect.getsource(old)))
    function=tree.body[0];loop=next(n for n in function.body if isinstance(n,ast.While))
    index=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.If) and ast.unparse(n.test)=="kind == 'tick'")
    physical=loop.body[index]
    before=ast.parse('self.before_event(kind,args)').body[0]
    after=ast.parse('self.after_event(kind,args)').body[0]
    wrapper=ast.If(test=ast.parse('self.protocol_event(kind,args)',mode='eval').body,
                  body=[ast.Pass()],orelse=[physical])
    loop.body[index:index+1]=[before,wrapper,after]
    final=function.body[-1]
    if not isinstance(final,ast.Return):raise ValueError('unreviewed_physical_loop_return')
    final.value=ast.Call(func=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),attr='finish',ctx=ast.Load()),
                         args=[final.value],keywords=[])
    ast.fix_missing_locations(tree);namespace=dict(old.__globals__)
    exec(compile(tree,'<conditional_communication_physical_loop>','exec'),namespace)
    return namespace['run']


Projection.run=make_run()


def predict(supplied_context,action):
    """No actual outcome/branch argument; future messages remain conditional."""
    try:
        initial=context.revalidate(supplied_context)
        if initial.get('status')!='conditional_validated_data':return context.unknown('unsupported_initial_context')
        context.encoded(action)
        if (set(action)!={'initial_action','empty_departure','return_delay','later_action'} or
                any(type(action.get(k)) not in (int,float) or not math.isfinite(action[k])
                    for k in ('empty_departure','return_delay')) or
                action not in physics.previous.actions()):return context.unknown('undeclared_action')
        bundle=context.initial_projection_bundle(supplied_context)
        engine=Projection(bundle,copy.deepcopy(action),initial)
        return engine.run()
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
        return context.unknown('conditional_projection:'+str(exc))
