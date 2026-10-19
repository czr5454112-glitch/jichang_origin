"""Source-shaped CONDITIONAL future data from a pure physical projection.

These messages are forecasts, never native receipts or delivery credentials.
The ordinary pure endpoint validators can test their consistency. Source rows
are constructed solely from simulated observations already processed, never
by looking at a future event heap or a saved native outcome.
"""
from __future__ import annotations
import copy
from . import planning_capture_v2_contract as v2
from . import planning_capture_v3_contract as v3
from . import live_obligation_domain_guard as domain


class CaptureWorld:
    def __init__(self, engine, initial_validated):
        self.e=engine
        self.static=initial_validated['envelopes']['A']['capture']['static_contract_sha256']
        self.semantics=copy.deepcopy(initial_validated['envelopes']['A']['capture']['semantics'])
        self.contracts={k:{f:v[f] for f in domain.CONTRACT_FIELDS} for k,v in engine.jobs.items()}
        self.entries={}
        self.completions=[]
        self.active={k: k=='L' for k in engine.trays}
        self.in_service={k:k=='L' for k in engine.trays}
        self.prefix={k:list(t['committed_prefix']) for k,t in engine.trays.items()}
        self.started={'P':0.}

    def owner(self,node): return self.e.nodes[node]['resource_owner']

    def tray(self,key,*,captured):
        e,t=self.e,self.e.trays[key]; job=t['job']
        value={f:copy.deepcopy(t[f]) for f in ('tray_id','node','mode','edge_from','edge_to','generation','traversal_id')}
        value.update(business_bag_id=job or '',reception_node=t['lease'] if t['lease'] is not None else -1,
            available_at=t['available_at'],committed_prefix=copy.deepcopy(self.prefix[key]))
        mode=t['mode']; bound=-1.;known=False;kind='unknown';load=-1.
        if t['edge_to']>=0:
            entry=self.entries.get(key)
            if entry is not None:value['edge_exit_at']=entry['derived_edge_exit_at']
        elif mode=='empty':bound=t['available_at'];known=True;kind='empty_available_at'
        elif mode=='hold':bound=t['available_at'];known=True;kind='observed_hold_completion'
        elif mode=='storage':
            j=e.jobs[job];bound=max(e.time,j['storage_release_at'],j['storage_entered_at']+j['storage_min_dwell'])
            known=True;kind='observed_storage_release_bound'
        elif mode in ('loading','unloading'):
            bound=self.started[key]+e.jobs[job]['load_seconds' if mode=='loading' else 'unload_seconds']
            value['available_at']=bound;known=True;kind='observed_load_completion' if mode=='loading' else 'observed_unload_completion'
            if mode=='loading':load=bound
        elif mode=='loaded' and self.active[key] and self.in_service[key]:
            # Accepted027 goal service has no calendar reservation, so its
            # task_service_end observation is clamped to capture time. Keep
            # this raw limitation; historical entry facts may support it.
            bound=e.time if t['node']==t['goal'] else t['ready']
            known=True;kind='committed_local_service_end'
        if captured:
            value.update(service_ready_at=bound,service_ready_known=known,ready_kind=kind,load_complete_at=load)
            value.pop('edge_exit_at',None)
        return value

    def owned_trays(self,owner,*,captured):
        return [self.tray(k,captured=captured) for k,t in self.e.trays.items() if self.owner(t['node'])==owner]

    def owned_jobs(self,owner,*,capture):
        carried={t['job'] for t in self.e.trays.values() if self.owner(t['node'])==owner and t['job'] is not None}
        return [copy.deepcopy(j) for key,j in self.e.jobs.items() if key in carried or
            (self.owner(j['origin'])==owner and (not capture or j['status']=='waiting_for_tray'))]

    def nodes(self,owner,*,capture):
        out=[]
        for node,n in self.e.nodes.items():
            if capture and self.owner(node)!=owner:continue
            row={'node':node} if capture else copy.deepcopy(n)
            if self.owner(node)==owner:
                occupancy=self.e.occupancy(node)
                available=sum(t['node']==node and t['edge_to']<0 and t['mode']=='empty'
                    and t['available_at']<=self.e.time+1e-9 for t in self.e.trays.values())
                row.update(occupancy=occupancy,actual_available=available)
                if capture:
                    represented=sum((t['node']==node if t['edge_to']<0 else t['edge_to']==node) or t['lease']==node
                        for t in self.e.trays.values() if self.owner(t['node'])==owner)
                    row['unrepresented_occupancy']=occupancy-represented
            out.append(row)
        return out

    def view(self,owner):
        e=self.e
        requests=[e.endpoint(r) for r in e.client_rows.values() if r['owner']==owner and r['kind']=='transfer']
        commands=[e.endpoint(r) for r in e.client_rows.values() if r['owner']==owner and r['kind']!='transfer']
        return {'schema':'g31.protocol_view.v1','now':e.time,'owner_id':owner,
            **{k:copy.deepcopy(e.b['contract'][k]) for k in ('node_records','edge_records','edge_contracts')},
            'node_contracts':self.nodes(owner,capture=False),'trays':self.owned_trays(owner,captured=False),
            'jobs':self.owned_jobs(owner,capture=False),'known_faults':[],
            'client_requests':requests,'client_commands':commands}

    def retained(self,owner):
        return {'owner':owner,'retained_at':.11,'contracts':copy.deepcopy(self.contracts),
            'static_contract_sha256':self.static}

    def capture(self,row):
        e=self.e;owner=row['owner'];peer=e.peer(owner);now=e.time
        trays=self.owned_trays(owner,captured=True);jobs=self.owned_jobs(owner,capture=True);nodes=self.nodes(owner,capture=True)
        e.channel_sequence[owner]+=1;seq=e.channel_sequence[owner]
        local={'schema':'g31.planning_capture.v1','source_owner':owner,'target_owner':peer,
            'message_id':f'planning-v3:1:{owner}:1:{peer}:{seq}','publication_sequence':seq,
            'captured_at':now,'valid_until':row['request']['expiry'],'static_contract_sha256':self.static,
            'semantics':copy.deepcopy(self.semantics),'trays':trays,'jobs':jobs,'nodes':nodes,'known_faults':[],
            'coverage':{'scope':'source_waiting_or_locally_carried_released_jobs_and_local_trays',
                'complete_for_declared_local_scope':True,'local_node_ids':[n['node'] for n in nodes],
                'tray_ids':[t['tray_id'] for t in trays],'business_bag_ids':[j['business_bag_id'] for j in jobs],
                'unrepresented_occupancy':sum(n['unrepresented_occupancy'] for n in nodes),'future_arrivals_included':False}}
        completed=[]
        for done in self.completions:
            if self.owner(done['destination'])!=owner:continue
            seq=len(completed)+1
            completed.append({**copy.deepcopy(done),'source_owner':owner,'source_local_sequence':seq,
                              'receipt_id':f'completion:1:{owner}:{seq}'})
        actions=[]
        for key,r in sorted(e.client_rows.items()):
            if r['owner']!=owner or r['kind'] not in v2.PHYSICAL_KINDS:continue
            ack=r.get('ack')
            actions.append({'request_id':key,'kind':r['kind'],'source_owner':owner,
                'last_delivered_ack':None if ack is None else {k:ack[k] for k in ('sequence','delivered_at','status')}})
        ext={'schema':v2.SCHEMA,'source_owner':owner,'captured_at':now,'terminal_receipts':completed,
            'completion_coverage':{'scope':v2.COMPLETION_SCOPE,'complete_for_declared_scope':True,'through':now,
                'source_owned_destination_nodes':sorted(n['node'] for n in nodes),'future_events_included':False,
                'completed_business_bag_ids':[r['business_bag_id'] for r in completed]},
            'submitted_physical_actions':actions,'action_coverage':{'scope':v2.ACTION_SCOPE,'through':now,
                'complete_for_declared_scope':True,'includes_unsubmitted_python_plans':False,'uses_hidden_execution_truth':False,
                'submitted_request_ids':[r['request_id'] for r in actions],
                'unresolved_request_ids':[r['request_id'] for r in actions if r['last_delivered_ack'] is None or
                    r['last_delivered_ack']['status'] not in v2.TERMINAL_BY_KIND[r['kind']]]}}
        inflight=[];unmatched=[];moving=[]
        for t in trays:
            if t['edge_to']<0:continue
            key=t['tray_id'];moving.append(key);entry=self.entries.get(key)
            if entry is None or any(entry[f]!=t[f] for f in ('generation','traversal_id','edge_from','edge_to')):
                unmatched.append(key)
            else:inflight.append(copy.deepcopy(entry))
        body={'schema':v3.SCHEMA,'capture_v2':{'schema':'g31.planning_capture.v2','local_capture':local,'extension':ext},
            'extension':{'schema':v3.EXTENSION,'source_owner':owner,'captured_at':now,'source_observed_inflight':inflight,
                'coverage':{'scope':v3.SCOPE,'source_owned_inflight_tray_ids':moving,'capture_cutoff':now,
                    'complete_for_declared_source_inflight':not unmatched,'unmatched_tray_ids':unmatched,
                    'uses_future_event_heap':False}}}
        return {'schema':'g31.planning_snapshot.v3','kind':'planning_snapshot_v3','capture':body,
            'payload_sha256':v3.capture_digest_v3(body),'digest_format':'g31.planning_capture_digest.v3',
            'delivered_at':now+.01,'status':'conditional'}

    def begin_leg(self,key):
        self.active[key]=True;self.in_service[key]=True
        self.prefix[key]=[self.e.trays[key]['node']]

    def complete_leg(self,key):
        t=self.e.trays[key];t['generation']+=1
        self.active[key]=False;self.in_service[key]=False;self.prefix[key]=[t['node']]

    def entry(self,key,source,target):
        t=self.e.trays[key]
        self.entries[key]={'source_owner':self.owner(source),'receipt_event':'EDGE_ENTER','tray_id':key,
            'business_bag_id':t['job'] or '','generation':t['generation'],'traversal_id':t['traversal_id'],
            'edge_from':source,'edge_to':target,'entered_at':self.e.time,
            'static_edge_travel_seconds':self.e.travel[source,target],
            'derived_edge_exit_at':self.e.time+self.e.travel[source,target]}
