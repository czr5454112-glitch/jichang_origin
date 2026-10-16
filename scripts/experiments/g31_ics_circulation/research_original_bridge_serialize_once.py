"""Fresh bridge campaign: only its diagnostic Tape implementation changes.

Original policy/native/worker/clock code is reused in private namespaces. No
old module globals are changed. Full saved policy/physical replay and exact
old complete API prefix comparison share the same2400s owned parent budget.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
from . import research_original_cooperative_bridge as original
from . import serialize_once_low_wip_tape as tape_candidate

base,policy=original.base,original.policy
ROOT,OUT=original.ROOT,original.OUT
SCHEMA='g31.original_bridge.serialize_once.campaign.v1'
MODULE='scripts.experiments.g31_ics_circulation.research_original_bridge_serialize_once'
LAUNCH_MODULE='scripts.experiments.g31_ics_circulation.launch_original_bridge_serialize_once'
LIMIT=2400.
CASE='bridge'
REFERENCE=OUT/'original_cooperative_bridge_prepare_001'
OLD_PLAN_SHA='a8c51ab4062940da0919733b59072f6a9897e69c99d66a7b83423d15aea68d28'
MANIFEST_SHA='53093badec00132dd4c4373bb157b874c63f85171d027209356a971d5a368093'
PREFIX_ROWS=27218
EVIDENCE={
    str(REFERENCE/'bridge/preregistered_protocol.json'):OLD_PLAN_SHA,
    str(REFERENCE/'bridge/api/manifest.jsonl'):MANIFEST_SHA,
    str(REFERENCE/'external_launch_receipt.json'):'6792cd004c3f5af9e11af701d4198fe918dd840709c6ffa16526e99dbfd53ba2',
    str(REFERENCE/'external_application_wall.json'):'341218e11f25ae4bce6d6a1714bb4df028b4d25e3b8fab5678ee22fa6ea073d3',
    str(OUT/'bridge001_terminal_partial_review_001/review.json'):'0bd6bf3faf488b1fb0e488c6bf2c7f31d1c1e3419d707461bfe6df0bc4c3cbc2',
    str(OUT/'serialize_once_tape_prepare_001/result.json'):'7efe2da12e641372f2995777be3f7a3f5529501512597e8cfe879f84d898b021',
    str(OUT/'serialize_once_tape_independent_readback_001/review.json'):'d0da53e99de8b4e81d55ac3b1287821caef3345772ce3eacc2cbbcd360c79349'}
require=base.require


class MeasuredSerializedTape(original.MeasuredTape,tape_candidate.SerializedOnceTape):
    """Exact original measurement methods; super dispatch selects new Tape."""
    pass


def source_paths():
    found=set(original.source_paths())
    for entry in (Path(__file__),Path(__file__).with_name('verify_original_bridge_serialize_once.py'),
                  Path(__file__).with_name('launch_original_bridge_serialize_once.py'),
                  ROOT/'tests/test_g31_circulation_bridge_serialize_once.py',
                  ROOT/'tests/test_g31_circulation_serialize_once_tape.py'):
        function=original.clone(base.source_paths,{**base.source_paths.__globals__,'__file__':str(entry)})
        found.update(function())
    return sorted(found)


def reference_pins():
    for path,digest in EVIDENCE.items():require(base.sha(path)==digest,'serialize_bridge_evidence_changed')
    old=base.read(REFERENCE/'bridge/preregistered_protocol.json')
    require(old['horizon']==86400 and old['max_physical_requests']==100
        and old['bridge_contract']['max_actual_token_completions']==39,'serialize_bridge_old_scope')
    for path,digest in old['source_before'].items():
        require(base.sha(path)==base.sha(REFERENCE/'bridge/source_archive'/Path(path).relative_to(ROOT))==digest,
                'serialize_bridge_frozen_policy_changed')
    return old


def contract():
    return {**original.contract(),
        'logging_only_amendment':{
            'policy':'Original cooperative_bridge_policy.py and all original76 sources remain exact. Only the explicit Tape class is replaced; MeasuredTape clock methods/coverage are inherited unchanged.',
            'failed_reference':'Old001 timed out2400.2173068s; latest complete API prefix27218 rows reachesH41700. Heartbeat26completed is only a lower bound; no old fullH/native-seal/physical-completion certificate.',
            'reference':str(REFERENCE),'reference_evidence_sha256':dict(EVIDENCE),'complete_prefix_rows':PREFIX_ROWS,
            'normalization':'Only advance_to.result.wall_seconds, validated finite nonnegative. Every other ordered field/argument/result/clock logical value remains exact. Unmanifested truncated027218 is excluded, never repaired.',
            'budget':'Single fresh026 worker plus full saved policy/physical audit and old complete-prefix comparison inside one2400s ownedJob. No budget increase or excluded prefix audit work.',
            'scope':'Same28506 jobs,22trays,21noncirculating parked after startup,39completion/78postparking/100physical caps,86400 horizon. All failure/open states remain unknown.',
            'performance':'Saved fixed8 mock logging ratio3.1362 is not native/application speedup. Larger later payloads and full replay may still exhaust2400. No fullH or100ms promise.'}}


def runner_namespace():
    namespace=dict(vars(original))
    for name,value in vars(original).items():
        if isinstance(value,FunctionType) and value.__globals__ is vars(original):
            namespace[name]=original.clone(value,namespace)
    namespace.update(SCHEMA=SCHEMA,MODULE=MODULE,source_paths=source_paths,contract=contract,
                     MeasuredTape=MeasuredSerializedTape,verify_pins=verify_pins)
    return namespace


def isolated_runner():return SimpleNamespace(**runner_namespace())


def verify_pins(output,plan,runtime=False):
    namespace=runner_namespace()
    original.clone(original.verify_pins,namespace)(output,plan,runtime)
    reference_pins()


def prepare(output,tests_xml):
    require(not output.exists(),'serialize_bridge_preserve_output')
    reference_pins();r=isolated_runner();campaign=r.prepare(output,tests_xml)
    case=output/CASE;plan=base.read(case/'preregistered_protocol.json')
    plan['execution_amendment']='Preserve old bridge0012400s timeout. Fresh same-policy original026 campaign changes only Tape encoding; every remaining policy/native/measurement method is exact. Prefix audit and full saved replay share2400.'
    base.write(case/'preregistered_protocol.json',plan);campaign['case_plans'][CASE]=base.sha(case/'preregistered_protocol.json')
    base.write(output/'campaign.json',campaign);r.verify_campaign(output)
    ready={'schema':'g31.original_bridge.serialize_once.ready.v1','status':'prepared_unexecuted','output':str(output),
        'campaign_sha256':base.sha(output/'campaign.json'),'source_count':len(campaign['source_before']),
        'pure':campaign['tests'],'native_dispatch_ready_requires_root_review':True,'native_executions':0,
        'execute_command':[campaign['interpreter']['path'],'-m',LAUNCH_MODULE,'--output',str(output),
                           '--campaign-sha256',base.sha(output/'campaign.json')],
        'external_full_python_stopwatch_required':True,'shared_seconds':LIMIT}
    base.write(output/'ready.json',ready);return ready


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--tests-xml',type=Path)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--verify',action='store_true')
    parser.add_argument('--campaign',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    require(sum((args.prepare,args.worker,args.verify,args.campaign))==1,'serialize_bridge_mode')
    if args.prepare:print(json.dumps(prepare(output,args.tests_xml)));return
    r=isolated_runner()
    if args.campaign:raise SystemExit(r.campaign_worker(output,args.admission))
    if args.worker:r.worker(output/CASE);return
    from .verify_original_bridge_serialize_once import verify_case
    result=verify_case(output/CASE);target=output/CASE/'independent_verification.json'
    require(not target.exists(),'serialize_bridge_verification_exists');base.write(target,result)


if __name__=='__main__':main()
