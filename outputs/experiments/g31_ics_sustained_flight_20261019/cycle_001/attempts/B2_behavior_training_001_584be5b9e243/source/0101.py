"""Per-process, finite native028 admission; never inherits native027 timing certification."""
from __future__ import annotations
import copy
import os
from pathlib import Path
from . import native028_receiver_gate as gate

SCHEMA='g31.native028_receiver_admission_contract.v1'
_TOKEN=object()


def accept(gate_directory,output):
    directory=Path(gate_directory).resolve();verified=gate.validate_saved(directory)
    contract={'schema':SCHEMA,'status':'accepted_finite_receiver_semantics',
        'binary':verified['binary']['path'],'binary_sha256':verified['binary']['sha256'],
        'build_receipt':verified['build_receipt'], 'semantic_gate':gate.ref(directory/'receipt.json'),
        'policy_version':verified['policy_version'], 'native_constructor_attempts':9,
        'legacy44plus21_reexecuted':False,'complete_request_100ms_certified':False,
        'global_deadlock_freedom_established':False}
    gate.write(output,contract);return contract


def verify(contract_reference,semantic_reference):
    gate.require(gate.ref(contract_reference['path'])==contract_reference,'contract_bytes')
    contract=gate.read(contract_reference['path'])
    gate.require(contract['schema']==SCHEMA and contract['status']=='accepted_finite_receiver_semantics'
        and contract['semantic_gate']==semantic_reference,'contract_semantic_binding')
    gate.require(gate.ref(semantic_reference['path'])==semantic_reference,'semantic_bytes')
    verified=gate.validate_saved(Path(semantic_reference['path']).parent)
    gate.require(contract['binary']==verified['binary']['path']
        and contract['binary_sha256']==verified['binary']['sha256']
        and contract['build_receipt']==verified['build_receipt']
        and contract['policy_version']==verified['policy_version']
        and contract['complete_request_100ms_certified'] is False,'contract_identity')
    pins=dict(verified['evidence_sha256'])
    pins[contract_reference['path']]=contract_reference['sha256']
    pins[semantic_reference['path']]=semantic_reference['sha256']
    return contract,pins


def inventory(contract_reference,semantic_reference,campaign_reference):
    contract,pins=verify(contract_reference,semantic_reference)
    gate.require(gate.ref(campaign_reference['path'])==campaign_reference,'campaign_bytes')
    plan=gate.read(campaign_reference['path']);directory=Path(campaign_reference['path']).parent
    pins[campaign_reference['path']]=campaign_reference['sha256']
    gate.require(plan['binary']=={'path':contract['binary'],'sha256':contract['binary_sha256']},'campaign_binary')
    gate.require(set(plan['source_sha256'])==set(plan['source_archive']),'campaign_archive_domain')
    for source,digest in plan['source_sha256'].items():
        archive=(directory/plan['source_archive'][source]).resolve()
        gate.require(archive.is_relative_to(directory/'source') and gate.sha(source)==gate.sha(archive)==digest,'campaign_source')
        pins[source]=digest;pins[str(archive)]=digest
    for name,digest in plan['input_file_sha256'].items():
        path=directory/'inputs'/(name+'.json');gate.require(gate.sha(path)==digest,'campaign_input');pins[str(path)]=digest
    return contract,pins,plan


class RunAcceptance:
    def __init__(self,token,contract_reference,semantic_reference,campaign_reference):
        gate.require(token is _TOKEN,'factory_required')
        self.pid=os.getpid();self.token=token
        self.references=copy.deepcopy((contract_reference,semantic_reference,campaign_reference))
        self.contract,self.pins,self.plan=inventory(*self.references)
        self.branch=None;self.used=[];self.closed=False;self.invalid=[]
    def __reduce__(self):raise TypeError('native028_acceptance:not_serializable')
    def check(self):
        gate.require(self.token is _TOKEN and self.pid==os.getpid() and not self.closed,'process_scope')
        gate.require(all(gate.sha(path)==digest for path,digest in self.pins.items()),'run_pins_changed')
    def enter_branch(self,key,campaign_reference):
        self.check();gate.require(self.branch is None and key not in self.used
            and key in self.plan['rows'] and campaign_reference==self.references[2],'branch_scope')
        self.branch=key;self.used.append(key)
    def finish_branch(self,key):
        self.check();gate.require(self.branch==key,'branch_end');self.branch=None
    def close(self):
        try:
            self.check();gate.require(self.branch is None,'unfinished_branch')
            contract,pins,plan=inventory(*self.references)
            gate.require(contract==self.contract and pins==self.pins and plan==self.plan,'exit_inventory')
        except Exception as error:self.invalid.append(str(error))
        self.closed=True
        return {'schema':'g31.native028_closed_run.v1','status':'invalidated_acceptance_evidence'if self.invalid else'closed_run_acceptance_passed',
            'run_reference':self.references[2],'contract_reference':self.references[0],'semantic_reference':self.references[1],
            'evidence_sha256':self.pins,'branch_keys':self.used,'active':False,'invalid':self.invalid,'pid':self.pid,
            'finite_semantic_scope':gate.SCHEMA,'complete_request_100ms_certified':False,'native_calls':0}


def open_run(contract_reference,semantic_reference,campaign_reference):
    return RunAcceptance(_TOKEN,contract_reference,semantic_reference,campaign_reference)
