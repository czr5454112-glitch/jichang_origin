"""Freeze one new actual18 package; never construct native or predictor objects."""
from __future__ import annotations
import argparse
import copy
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import initial_owner_route_gate_campaign_v2 as c
from . import initial_owner_route_gated_evidence_v2 as integration
from . import run_initial_owner_route_gate_pure_v2 as pure_runner


def verify_frozen(output,plan):
    c.require(set(plan['source_sha256'])==set(plan['source_archive']),'old_source_domain')
    for path,digest in plan['source_sha256'].items():
        c.require(c.sha(path)==digest and c.sha(output/plan['source_archive'][path])==digest,
            'old_frozen_source_changed:'+path)


def prepare(output,pure_receipt):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    try:
        pure_receipt=Path(pure_receipt).resolve();pure=c.read(pure_receipt);xml=pure_receipt.parent/'tests.xml'
        tests=ET.parse(xml).getroot().findall('.//testcase')
        c.require(pure['status']=='passed' and pure['source_changed']==[] and pure['native_calls']==0
            and pure['predictor_evaluations']==0 and pure['performance_runs']==0
            and pure['XML_sha256']==c.sha(xml) and len(tests)==pure['tests']==130
            and not any(n.tag in ('failure','error','skipped') for row in tests for n in row),'unclosed_gate_pure')
        names={row.attrib['name'].split('[')[0] for row in tests}
        c.require({'test_equal_intermediate_representation_and_restoration_are_all_preserved',
            'test_signed_zero_and_integer_zero_restore_without_handler_change',
            'test_old_v1_loses_middle_order_even_when_final_representation_restores',
            'test_complete_saved_v2_keeps_equal_middle_ACK_and_handler_denominator',
            'test_compiled_integrated_scheduler_keeps_IDs_and_replays_every_actual_refresh'}<=names,
            'missing_representation_or_actual_scheduler_gate')
        for name,digest in pure['source_sha256'].items():
            c.require(c.sha(c.ROOT/name)==digest and c.sha(pure_receipt.parent/'source'/name)==digest,
                'gate_pure_source_changed:'+name)
        old_dir=c.OUT/'initial_owner_route_campaign_v3_prepare_001'
        old_plan=c.read(old_dir/'campaign.json');verify_frozen(old_dir,old_plan)
        evidence_dir=c.OUT/'single_root_evidence_pair_prepare_002'
        evidence_plan=c.read(evidence_dir/'plan.json')
        verify_frozen(evidence_dir,evidence_plan)
        gate_v1_dir=c.OUT/'initial_owner_route_gate_campaign_prepare_001'
        gate_v1_plan=c.read(gate_v1_dir/'campaign.json');verify_frozen(gate_v1_dir,gate_v1_plan)
        files=c.image.source_closure(c.ROOT,pure_runner.modules())
        sources,archive={},{}
        for name,data in files.items():
            path=c.ROOT/name;target=output/'source'/name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            sources[str(path)]=hashlib.sha256(data).hexdigest();archive[str(path)]=str(target.relative_to(output))
        plan=copy.deepcopy(old_plan)
        plan.update(schema=c.SCHEMA,source_sha256=sources,source_archive=archive,
            pure_reference=c.reference(pure_receipt),pure_XML=c.reference(xml),gate_pure_reference=c.reference(pure_receipt),
            frozen_v3_campaign=c.reference(old_dir/'campaign.json'),
            frozen_single_evidence_plan=c.reference(evidence_dir/'plan.json'),
            frozen_gate_v1_campaign=c.reference(gate_v1_dir/'campaign.json'),
            gate_source_proof=integration.integration_proof(),
            environment={'interpreter':sys.executable,'interpreter_sha256':c.sha(sys.executable),'version':sys.version},
            status='prepared_for_review_no_execution')
        inputs={}
        for key,row in plan['rows'].items():
            path=output/'inputs'/(key+'.json');c.write(path,c.scene(row));inputs[key]=c.sha(path)
        c.require(inputs==old_plan['input_file_sha256'],'all18_input_bytes_changed')
        plan['input_file_sha256']=inputs
        plan['amendment']={
            'prior_preparation':c.reference(gate_v1_dir/'campaign.json'),
            'prior_native_execution':False,
            'reason':'V1 body reuse followed Python ACK equality, which does not preserve key order, integer/float types or signed zero. Intermediate representations could be lost even if final state restored.',
            'correction':'Original ACK handler predicate remains unchanged. Independent body_is_new records each strictly ordered/type/float-exact new representation. Replay consumes bodies by body_is_new, not ack_changed.',
            'costs':'Every strict comparison and necessary body copy is inside the original caller accounting; no work or time is removed.',
            'unchanged':'No first-hop, scheduler, client admission, native physical, input, horizon or budget change; v1 evidence and all139 frozen sources retained.'}
        plan['scope']['new_mechanisms']={
            'evidence':'One fresh complete JSON tree/encoding and original strict readback/ledger; required runtime query proof is included before the root body and outside-return stamps.',
            'gate':'Only source-proven complete all-owner notification chains, unchanged protocol calls, no A change and no A retry due may omit root read/drain. Original A activation and last boundary assignment remain at the exact old position.',
            'outbox':'Actual original client query/ACK-change loop records every consumed ACK and immutable retry; linear saved replay reconstructs complete rows at all gate prefixes and final H. No caller-supplied JSON Boolean grants runtime permission.',
            'source_binding':'Actual NativeSession and LocalTransport exact types; private source-restored functions only. No session proxy, imported-global monkeypatch, physical-state or callback changes.',
            'unchanged':'Original firsthop detection, fixed B .11 action, both owner policies, .05 periodic ticks, cursor updates, ID/admission sequence, all18 faults/input/horizons and 600 shared wall cap.',
            'comparison':'No assumed elapsed speed or old final-seal equality when actual deadline-dependent preference differs. Per-arm endpoint/physical/RPC audit and all gates remain required.',
            'costs':'Constructor/guards/chain logging/query proof normalization/full encoding/strict readback/native drains/retries/caller tail all retained; startup and whole campaign are separate full-charge sensitivities, not divided.'}
        c.write(output/'campaign.json',plan)
        c.write(output/'branch_ledger.json',{k:{**v,'status':'unknown_unexecuted'} for k,v in plan['rows'].items()})
        expected=c.sha(output/'campaign.json');c.verify_plan(output,expected)
        receipt={'schema':c.SCHEMA,'status':'prepared_source_review_pending','campaign':c.reference(output/'campaign.json'),
            'sources':len(sources),'compiled_sources':len(plan['compiled_source_archive_sha256']),
            'pure_tests':len(tests),'native_calls':0,'predictor_evaluations':0,'not_dispatched':True,
            'execute_command':[sys.executable,'-m',__package__+'.launch_initial_owner_route_gate_campaign_v2',
                '--output',str(output),'--campaign-sha256',expected],
            'external_measured_launch_wrapper_required':True}
        c.write(output/'source_preparation.json',receipt);return receipt
    except BaseException as error:
        c.write(output/'preparation_failure.json',{'status':'failed_preparation','error':repr(error),'native_calls':0})
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pure-receipt',type=Path,required=True);a=p.parse_args()
    print(prepare(a.output,a.pure_receipt));return 0


if __name__=='__main__':raise SystemExit(main())
