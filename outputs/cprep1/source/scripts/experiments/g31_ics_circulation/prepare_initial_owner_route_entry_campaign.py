"""Freeze separate first-entry actual18 proposal; never execute native here."""
from __future__ import annotations
import argparse,copy,hashlib,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from . import initial_owner_route_entry_campaign as c
from . import initial_owner_route_entry_integration as integration
from . import run_initial_owner_route_entry_pure as pure_runner
from . import prepare_initial_owner_route_gate_campaign_v2 as previous


def prepare(output,pure_receipt):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    try:
        pure_receipt=Path(pure_receipt).resolve();pure=c.read(pure_receipt);xml=pure_receipt.parent/'tests.xml'
        tests=ET.parse(xml).getroot().findall('.//testcase')
        c.require(pure['status']=='passed' and pure['source_changed']==[] and pure['native_calls']==0
            and pure['predictor_evaluations']==0 and pure['performance_runs']==0
            and pure['XML_sha256']==c.sha(xml) and len(tests)==pure['tests']==186
            and not any(n.tag in ('failure','error','skipped') for row in tests for n in row),'unclosed_entry_pure')
        for name,digest in pure['source_sha256'].items():
            c.require(c.sha(c.ROOT/name)==digest and c.sha(pure_receipt.parent/'source'/name)==digest,
                      'entry_pure_source_changed:'+name)
        old_dir=c.OUT/'initial_owner_route_gate_campaign_prepare_002'
        old_plan=c.read(old_dir/'campaign.json');previous.verify_frozen(old_dir,old_plan)
        files=c.image.source_closure(c.ROOT,pure_runner.modules())
        sources,archive={},{}
        for name,data in files.items():
            path=c.ROOT/name;target=output/'source'/name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            sources[str(path)]=hashlib.sha256(data).hexdigest();archive[str(path)]=str(target.relative_to(output))
        c.require(all(sources.get(k)==v for k,v in old_plan['source_sha256'].items()),'old141_not_preserved')
        plan=copy.deepcopy(old_plan)
        plan.update(schema=c.SCHEMA,source_sha256=sources,source_archive=archive,
            pure_reference=c.reference(pure_receipt),pure_XML=c.reference(xml),entry_pure_reference=c.reference(pure_receipt),
            frozen_gate_v2_campaign=c.reference(old_dir/'campaign.json'),
            entry_source_proof=integration.integration_proof(),
            environment={'interpreter':sys.executable,'interpreter_sha256':c.sha(sys.executable),'version':sys.version},
            status='prepared_for_review_no_execution')
        inputs={}
        for key,row in plan['rows'].items():
            path=output/'inputs'/(key+'.json');c.write(path,c.scene(row));inputs[key]=c.sha(path)
        c.require(inputs==old_plan['input_file_sha256'],'all18_input_bytes_changed')
        plan['input_file_sha256']=inputs
        plan['amendment']={
            'prior_preparation':c.reference(old_dir/'campaign.json'),
            'reason':'Native027 committed_prefix still has only source0 at real first EDGE_ENTER. The old predicate requires two prefix nodes and therefore waits for exit despite already delivered actual entry evidence.',
            'correction':'Extend only that strict source-bound initial prefix[0] observation with actual current matching traversal EDGE_ENTER-derived edge_exit_at. Both root observer and post-drain observer share it. Original post-exit outputs and ACK/actual-drain closure unchanged.',
            'not_inferred':'Reservation edge fields or elapsed scheduled time do not prove entry. No future state is read and no native capability comes from saved JSON.',
            'effects':'Earlier root closure removes later root admissions and may change request IDs. All later controller statements and .05 cadence remain, but tape/ID/final outcome equality is not assumed.',
            'scope':'Same18 inputs, faults, finite2 choices, fullH40/all5 business audit and shared600. Complete100ms still required; no full32 or universal latency certificate.',
            'costs':'New identity checks, actual queries/drains/ACKs, complete trace proof and new observation-contract marker are inside the charged root. Cold startup/setup/cleanup and full campaign retained without amortization.'}
        plan['scope']['new_mechanisms']={
            'inherited':'Exact gatev2 complete outbox/query evidence and one-build strict roundtrip remain.',
            'entry':'Only the two source-bound root first-hop observation callsites use the new strict predicate.',
            'original_closure':'Same actual complete drain and terminal delivered routeACK rules; missing or malformed evidence stays unknown.',
            'comparison':'Same18 inputs; compare actual branch outcomes and exact five-job protection. No oldtape/ID equality claim; separate rounds are not paired performance attribution.',
            'costs':'All guards/observations/new marker/complete proof/encoding/strictreadback/caller tail and cold work retained.'}
        c.write(output/'campaign.json',plan)
        c.write(output/'branch_ledger.json',{k:{**v,'status':'unknown_unexecuted'} for k,v in plan['rows'].items()})
        expected=c.sha(output/'campaign.json');c.verify_plan(output,expected)
        receipt={'schema':c.SCHEMA,'status':'prepared_source_review_pending','campaign':c.reference(output/'campaign.json'),
            'sources':len(sources),'compiled_sources':len(plan['compiled_source_archive_sha256']),
            'pure_tests':len(tests),'native_calls':0,'predictor_evaluations':0,'not_dispatched':True,
            'execute_command':[sys.executable,'-m',__package__+'.launch_initial_owner_route_entry_campaign',
                '--output',str(output),'--campaign-sha256',expected],
            'external_measured_launch_wrapper_required':True}
        c.write(output/'source_preparation.json',receipt);return receipt
    except BaseException as error:
        c.write(output/'preparation_failure.json',{'status':'failed_preparation','error':repr(error),'native_calls':0})
        raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pure-receipt',type=Path,required=True);args=parser.parse_args()
    print(prepare(args.output,args.pure_receipt));return 0


if __name__=='__main__':raise SystemExit(main())
