"""Unchanged whole policy/physical replay plus the old complete27218 API rows.

Compare each old row when the original replay decodes the matching new row;
no second new-tape scan. All old row hashes and ordered semantic fields are
checked. This is offline evidence, never owner knowledge or policy input.
"""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
from . import research_original_bridge_serialize_once as r
from . import verify_original_cooperative_bridge as original

base,require=r.base,r.require


def semantic_api(row):
    # Same sole normalization as the accepted old verifier, without copying
    # the whole snapshot merely to remove one scalar from advance results.
    value=dict(row)
    if value['endpoint']=='advance_to':
        result=dict(value['result']);wall=result.pop('wall_seconds')
        require(original.finite(wall),'serialize_bridge_native_wall');value['result']=result
    return original.ordered(value)


class PrefixComparison:
    def __init__(self,old_directory,expected_manifest_sha,expected_count):
        self.directory=Path(old_directory);path=self.directory/'manifest.jsonl'
        require(base.sha(path)==expected_manifest_sha,'serialize_bridge_old_manifest')
        self.manifest=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
        require(len(self.manifest)==expected_count and all(item['path']==f'{i:06d}.json.gz'
            for i,item in enumerate(self.manifest)),'serialize_bridge_old_domain')
        self.index=0;self.last_after=None;self.old_manifest_sha256=expected_manifest_sha
    def consume(self,row):
        if row['ordinal']>=len(self.manifest):return
        require(row['ordinal']==self.index,'serialize_bridge_prefix_order')
        item=self.manifest[self.index];path=self.directory/item['path']
        require(base.sha(path)==item['sha256'],'serialize_bridge_old_row_changed')
        old=base.gzread(path)
        require(old['ordinal']==self.index and old['endpoint']==item['endpoint']
            and semantic_api(old)==semantic_api(row),'serialize_bridge_prefix_difference')
        self.index+=1;self.last_after=row['after']
    def finish(self):
        require(self.index==len(self.manifest),'serialize_bridge_incomplete_comparison')
        return {'status':'exact_old_complete_manifest_prefix','rows':self.index,'last_logical_time':self.last_after,
            'manifest_sha256':self.old_manifest_sha256,'only_exclusion':'advance_to.result.wall_seconds finite nonnegative',
            'truncated_old_unmanifested_row':'027218.json.gz excluded, not repaired or used',
            'cost':'Runs inside the same saved replay and shared2400 parent; no time deducted.',
            'old_full_horizon_or_final_native_seal_certified':False}


def compared_replay_type(comparison):
    def read(path):
        value=base.gzread(path);comparison.consume(value);return value
    return type('ComparedReplayTape',(base.ReplayTape,),{
        '__getattr__':r.original.clone(base.ReplayTape.__getattr__,{**base.ReplayTape.__getattr__.__globals__,'gzread':read})})


def verifier_function(replay_type):
    private_base=SimpleNamespace(**{**vars(base),'ReplayTape':replay_type})
    return r.original.clone(original.verify_case,{**original.verify_case.__globals__,
        'r':r.isolated_runner(),'base':private_base})


def verify_case(directory):
    comparison=PrefixComparison(r.REFERENCE/'bridge/api',r.MANIFEST_SHA,r.PREFIX_ROWS)
    # Original nested ObservedOwner remains the exact BridgeOwner. This clone
    # changes only r/schema/pins and the offline read observer; every original
    # lifecycle, FIFO, Storage, cap relay, clocks and alloffered check remains.
    result=verifier_function(compared_replay_type(comparison))(directory)
    result['same_policy_old001_complete_prefix']=comparison.finish()
    result['logging_only_comparison']='Same policy/control cadence. No claim old incomplete run was a fullH performance/control arm.'
    result['reference_evidence_sha256']=dict(r.EVIDENCE)
    return result
