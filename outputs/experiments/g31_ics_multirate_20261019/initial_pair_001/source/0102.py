"""Count old policy reads after each lawful cap proof; terminal tapes only."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path

from . import research_original_low_wip_repeat as p
from .review_original_low_wip_repeat_saved import terminal_inventory, require


class ProofCounter:
    def __init__(self, cap, token):
        self.cap, self.token = cap, token
        self.views, self.peers, self.first, self.reads = {}, {}, {}, []

    def read(self, endpoint, owner, at, ordinal, result):
        if endpoint not in {'observe_protocol_control_policy_recent','protocol_planning_snapshots_v2'}: return
        row = {'endpoint':endpoint, 'owner':owner, 'at':at, 'ordinal':ordinal, 'result':result}
        (self.views if endpoint == 'observe_protocol_control_policy_recent' else self.peers)[owner] = row
        self.reads.append({k:v for k,v in row.items() if k != 'result'})

    def barrier(self, owner, proof):
        if proof is None or proof['known_supply_count'] < self.cap or owner in self.first: return
        view, peer = self.views[owner], self.peers[owner]
        require(view['at'] == peer['at'] == view['result']['now'] and view['ordinal'] < peer['ordinal'], 'counter_current_reads')
        self.first[owner] = {'at':view['at'], 'after_api_ordinal':peer['ordinal'],
            'current_token_locally_empty':p.reuse.current_empty(view['result'],self.token),
            'physical_barrier':deepcopy(proof)}

    def summary(self):
        return {owner:{**proof, 'subsequent_reads':{endpoint:sum(r['owner']==owner and r['endpoint']==endpoint
            and r['ordinal'] > proof['after_api_ordinal'] for r in self.reads)
            for endpoint in ('observe_protocol_control_policy_recent','protocol_planning_snapshots_v2')}}
            for owner,proof in self.first.items()}


def diagnose_case(directory):
    plan=p.base.read(directory/'preregistered_protocol.json'); p.verify_pins(directory,plan)
    raw=p.base.gzread(directory/'raw_final.json.gz')
    counter=ProofCounter(plan['supply_cap'],plan['parking_plan']['token_tray_id'])
    class Tape(p.base.ReplayTape):
        def __getattr__(self,name):
            original=super().__getattr__(name)
            def call(*args,**kwargs):
                at=self.physical_time; ordinal=self.index; result=original(*args,**kwargs)
                if name in {'observe_protocol_control_policy_recent','protocol_planning_snapshots_v2'}:
                    counter.read(name,args[0],at,ordinal,result)
                return result
            return call
    tape=Tape(directory/'api'); original=p.physical_barrier
    def observed(outbox,owner,peer,parking):
        result=original(outbox,owner,peer,parking); counter.barrier(owner,result); return result
    try:
        p.physical_barrier=observed
        owners,status,tick=p.run_policy(tape,plan)
    finally:
        p.physical_barrier=original
    require(tape.index==len(tape.manifest) and status==raw['status'] and tick==raw['tick']
        and tape.physical_time==raw['physical_time']
        and p.base.normalized_owners([o.summary() for o in owners])==p.base.normalized_owners(raw['owners']),
        'counter_changed_saved_policy')
    return {'status':'passed_identical_saved_policy_with_read_counter','api_rows':tape.index,
        'first_cap_proofs_and_later_reads':counter.summary(), 'horizon':tape.physical_time,
        'producer_status':status,'native_executions':0,'seconds_saved':None,
        'scope':'Counts only. No actual API wall clocks exist in this tape for these reads; no predicted speedup, native phase exclusion, changed retry or100ms result.'}


def diagnose(output):
    _,ledger=terminal_inventory(output); p.verify_campaign(output)
    return {'schema':'g31.repeat_postcap.saved_diagnostic.v1','cases':{
        name:diagnose_case(output/name) if entry.get('status')=='completed_saved_case'
        else {'status':'unknown_incomplete_case','ledger':entry} for name,entry in ledger.items()},
        'source_sha256':p.base.sha(__file__),'native_executions':0,'active_files_read':False}
