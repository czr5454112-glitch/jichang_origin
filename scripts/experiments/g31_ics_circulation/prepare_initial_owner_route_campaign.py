"""Prepare the finite native campaign, without starting native or predictors."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import initial_owner_route_campaign as c
from . import initial_owner_route_image as image


def prepare(output, pure_receipt):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        pure_receipt = Path(pure_receipt).resolve()
        pure = c.read(pure_receipt)
        xml = pure_receipt.parent / 'tests.xml'
        tests = ET.parse(xml).getroot().findall('.//testcase')
        c.require(pure['status'] == 'passed' and pure['native_calls'] == 0 and
            pure['source_changed'] == [] and pure['XML_sha256'] == c.sha(xml) and
            len(tests) == pure['tests'] and len(tests) >= 30 and
            not any(n.tag in ('failure','error','skipped') for t in tests for n in t), 'unclosed_pure_gate')
        for name, digest in pure['source_sha256'].items():
            c.require(c.sha(c.ROOT/name) == digest and c.sha(pure_receipt.parent/'source'/name) == digest,
                      'pure_source_drift:' + name)
        source_prepare = c.OUT / 'initial_owner_route_source_prepare_002'
        prior = c.read(source_prepare/'plan.json')
        for name,digest in prior['source_sha256'].items():
            c.require(c.sha(c.ROOT/name) == digest and c.sha(source_prepare/'source'/name) == digest,
                      'original_source_package_changed:' + name)
        image.verify_image(prior['image']['path'], prior['image']['version'])
        startup_path=pure_receipt.parent/'image_startup.json'
        startup=c.read(startup_path)
        c.require(pure['startup_sha256']==c.sha(startup_path) and startup['image']==prior['image'] and
            startup['status']=='passed_functional_startup_zero_predictions' and
            startup['close']['reply']['requests']==0 and startup['close']['process_exit_code']==0,
            'missing_functional_image_startup')
        files = image.source_closure(c.ROOT, (__package__+'.prepare_initial_owner_route_campaign',
            __package__+'.initial_owner_route_campaign', __package__+'.verify_initial_owner_route_campaign',
            __package__+'.launch_initial_owner_route_campaign', __package__+'.run_initial_owner_route_campaign_pure',
            'tests.test_g31_circulation_initial_owner_route_campaign'))
        sources, archive = {}, {}
        for name,data in files.items():
            original = c.ROOT/name
            target = output/'source'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
            sources[str(original)] = hashlib.sha256(data).hexdigest()
            archive[str(original)] = str(target.relative_to(output))
        rows = c.declarations()
        inputs = {}
        for key,row in rows.items():
            path = output/'inputs'/(key+'.json')
            c.write(path,c.scene(row))
            inputs[key] = c.sha(path)
        contract = c.read(c.OUT/'native027_accepted_reference_001.json')
        native_contract = c.read(contract['path'])
        build = c.read(native_contract['build_receipt'])
        c.require(build['source_changed'] == [] and c.sha(native_contract['binary']) == native_contract['binary_sha256'],
                  'compiled_native_authority')
        compiled = {}
        for name,digest in build['source_after'].items():
            path = Path(native_contract['source_archive'])/name
            c.require(c.sha(path) == digest, 'compiled_archive')
            compiled[str(path)] = digest
        plan = {'schema':c.SCHEMA,'rows':rows,'row_order':list(rows),'native_branch_budget':18,
            'source_sha256':sources,'source_archive':archive,'input_file_sha256':inputs,
            'native_contract_reference':contract,
            'semantic_gate_reference':c.reference(c.OUT/'native027_semantic_native_002/receipt.json'),
            'native_binary':c.reference(native_contract['binary']),'compiled_source_archive_sha256':compiled,
            'source_preparation':c.reference(source_prepare/'source_preparation.json'),
            'pure_reference':c.reference(pure_receipt),'pure_XML':c.reference(xml),
            'startup_reference':c.reference(startup_path),
            'expected_READY':{k:startup['ready'][k] for k in ('version','mode','loaded_sources','proof','limits','native_authority')},
            'image':prior['image'],'participation_contract':c.contract.participation_contract(),
            'participation_contract_sha256':c.contract.contract_sha256(),
            'hard_timeout_seconds':c.LIMIT,'max_native_workers':1,'predictor_workers':1,
            'environment':{'interpreter':sys.executable,'interpreter_sha256':c.sha(sys.executable),'version':sys.version},
            'scope':{'model':'Unchanged original initial 3tray/5job six-case domain; no live-obligation/later model substitution.',
                'timed_arm':'At most full default baseline plus one prefer2 simulation; actual caller admission before all collection. Unknown baseline is not an incumbent.',
                'fixed_control':'Separate no-solver default physical counterpart; not a timed full-baseline arm or the new solver executing default.',
                'fixed_future':'B independent E5->1 at.11 before any subsequent advance; both FixedContinuationOwner actors retain actual collection/replies/retry/recovery and fixed0/default first reuse, explicit3 second reuse.',
                'evidence_amendment':'Sourceplan002 proposed full API tape. This campaign instead retains real NativeSession authority and endpoint replay/all immutable transport calls/all explicit boundaries/full5job physical audit. It does not claim every internal query was taped. All unlogged query work remains charged to the actual root wall.',
                'entry_capture':'Private FunctionType retains original method bytecode and only records each real initial collector result plus immediate owner-only endpoint rereads, including successful final reread. No session proxy or supplied-data authority.',
                'faults':'drop3 applies independently to every immutable request and tests initial readiness. OwnerA/B outages .115..2 gate source execution/recipient publication, not ACK delivery. No lawful route-only ACK-drop capability exists in027; it is unavailable, not simulated by a mislabeled outage.',
                'conditional_predictions':'Future fault rows are outside normal-delivery point prediction assumptions; actual endpoint/root status and all-five-job outcomes are retained, never upgraded to a model certificate.',
                'timing':'100ms root allocation/60ms decision/40ms finalization reserve are experimental, not WCET. Actual atomic overruns, no baseline, delayed ACK and censor retained. Actual firsthop+deliveredACK+complete drain required; default no-command does not promise next1.',
                'cold':'Worker startup/import/44+21 gates/native setup/predictor compilation/shutdown and final export+saved verification retained. External whole campaign is a conservative full-charge sensitivity, never divided by roots.',
                'budget_rationale':'One serial18-branch H40 campaign; prior closed44+21 entry/exit cost about18s and small native three-branch campaigns about20s.600s includes every worker, predictor, all native branches and saved verification; this is a finite cap, not a predicted runtime.',
                'not_claimed':['full32 solver result','joint optimizer breakthrough','unconditional protection','cold100ms','all internal native query replay','pure physics subtraction']},
            'status':'prepared_for_review_no_execution'}
        c.write(output/'campaign.json',plan)
        c.write(output/'branch_ledger.json',{k:{**v,'status':'unknown_unexecuted'} for k,v in rows.items()})
        c.verify_plan(output,c.sha(output/'campaign.json'))
        receipt={'schema':c.SCHEMA,'status':'prepared_source_review_pending','campaign':c.reference(output/'campaign.json'),
            'sources':len(sources),'compiled_sources':len(compiled),'pure_tests':len(tests),'native_calls':0,
            'predictor_executions':0,'execute_command':[sys.executable,'-m',__package__+'.launch_initial_owner_route_campaign',
                '--output',str(output),'--campaign-sha256',c.sha(output/'campaign.json')],
            'not_dispatched':True,'external_measured_launch_wrapper_required':True}
        c.write(output/'source_preparation.json',receipt)
        return receipt
    except BaseException as error:
        c.write(output/'failure.json',{'status':'failed_preparation','error':repr(error),'native_calls':0})
        raise


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--pure-receipt',required=True,type=Path)
    a=p.parse_args()
    prepare(a.output,a.pure_receipt)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
