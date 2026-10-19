"""Source/image preparation only. Deliberately no native execute command."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from . import initial_owner_route_image as image
from . import initial_owner_route_contract as contract
from . import run_initial_owner_route_pure as pure

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf8')


def prepare(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    pure_dir=OUT/'initial_owner_route_pure_003'
    receipt=json.loads((pure_dir/'receipt.json').read_text())
    xml=pure_dir/'tests.xml';rows=ET.parse(xml).getroot().findall('.//testcase')
    if (receipt['status']!='passed' or receipt['tests']!=48 or len(rows)!=48
            or any(child.tag in ('failure','error','skipped') for row in rows for child in row)
            or receipt['source_changed'] or receipt['native_calls']!=0
            or receipt['XML_sha256']!=sha(xml)):
        raise ValueError('source_prepare:unclosed_pure_gate')
    for name,digest in receipt['source_sha256'].items():
        if sha(ROOT/name)!=digest or sha(pure_dir/'source'/name)!=digest:
            raise ValueError('source_prepare:pure_source_changed:'+name)
    # Verify old accepted32 closure remained untouched; no old model is rerun.
    old=OUT/'json_prediction_RPC_prepare_002'
    old_plan=json.loads((old/'preregistered_protocol.json').read_text())
    for name,digest in old_plan['source_sha256'].items():
        if sha(ROOT/name)!=digest or sha(old/'source'/name)!=digest:
            raise ValueError('source_prepare:old_32_source_changed:'+name)
    files=image.source_closure(ROOT,(__package__+'.prepare_initial_owner_route',image.ENTRY,
        __package__+'.initial_owner_route_request','tests.test_g31_circulation_initial_owner_route'))
    before={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    for name,data in files.items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    version=image.build_image(ROOT,output/'image')
    image.verify_image(output/'image',version)
    accepted=OUT/'native027_accepted_reference_001.json'
    accepted_ref=json.loads(accepted.read_text())
    if sha(accepted_ref['path'])!=accepted_ref['sha256']:
        raise ValueError('source_prepare:accepted_reference_changed')
    # Actual capability construction will rerun the closed accepted run gates;
    # these references are provenance pins, not a newly executed acceptance.
    plan={
        'schema':'g31.initial_owner_route_source_plan.v1',
        'status':'source_and_pure_ready_for_review','native_dispatch_ready':False,
        'native_calls_executed':0,'benchmark_executed':False,
        'source_sha256':before,'image':{'path':str(output/'image'),'version':version},
        'pure':ref(pure_dir/'receipt.json'),'pure_XML':ref(xml),
        'preserved_pure001':ref(OUT/'initial_owner_route_pure_001/receipt.json'),
        'preserved_pure002':ref(OUT/'initial_owner_route_pure_002/receipt.json'),
        'pure_history':'001 synthetic command fixture wrongly included response owner_id; actual saved027 shape corrected in002.003 also explicitly includes the pure-gate entry in its own source closure. All old receipts remain unchanged.',
        'old_32_plan':ref(old/'preregistered_protocol.json'),
        'old_32_sources_unchanged':len(old_plan['source_sha256']),
        'old_32_saved_payloads':ref(old/'1.compiled.json.gz'),
        'actual_command_shape_fixture':ref(OUT/'native027_fixture_diagnostic_002/raw.json'),
        'native027_accepted_reference':ref(accepted),'native027_contract':accepted_ref,
        'participation_contract':contract.participation_contract(),
        'participation_contract_sha256':contract.contract_sha256(),
        'finite_domain':{'logical_choices':2,'same_input_full_baseline_default':1,
            'additional_prefer2_queries_maximum':1,'original_32_search':False,
            'early_stop':'Before starting a new atomic candidate only. A completed default baseline is reused as the default output; no snapshot/result/label survives Engine.predict.',
            'known_rule':'Strict all-five-job predicted <= baseline, then lower canonical job-order sum; exact ties keep default. Unknown/partial/overrun never selects prefer2.'},
        'time_contract':{'root_ms':100,'decision_allocation_ms':60,'finalization_allocation_ms':40,
            'allocation_is_proven_WCET':False,'root_admitted_physical':.05,'initial_decision_physical':.11,
            'wire_seconds':.01,'immutable_retry_seconds':.5,'finite_observation_censor':40.,
            'atomic_overrun':'Preserve actual elapsed and unknown unevaluated candidates; no newly chosen preference after the root budget. Issued commands stay pending until real terminal evidence or explicit censor.',
            'cold':'Record full acceptance/native setup, worker process imports/compile/READY, root, shutdown/reclamation and evidence verification without amortization.',
            'root':'Before collection publication/freshview: capture/communication/native advance, JSON/RPC, fullbaseline/candidate, final local and own-receiver validation, native source/shield/admission, immutable submit/retry, actual delivered ACK, actual first-hop, complete drain, codecs and outside-return ledger tail.',
            'sum_cpu_vs_wall':'No worker wall is relabeled CPU. All shared native/control work remains fully charged; native unclassified remainder is not physics-exempt.'},
        'api_sequence':[
            'Create accepted NativeSession/RunAcceptance and fixed predictor image/client with complete cold records; advance only native setup to .05.',
            'Construct InitialOwnerRequest before any publication/capture/freshview for this stage; it admits the root before validation.',
            'collect(): fixed A/B demand+v1 publications, actual complete advance to .11, A owner-local accepted collection. No peer view enters A prediction.',
            'choose(): strict JSON RPC, full dynamic initial guards/full same-input default + at most prefer2. No independent B optimization or whole-vector-equality trick.',
            'final_revalidate_and_submit(): actual A selfACK/peer capture reread and own source/receiver2 fresh view; native default emits nothing, preference has exact generation/traversal and unchanged expiry5/wire.01.',
            'Invoke fixed_B_first_action at .11 before any subsequent advance, independent of A choice; retain its actual readiness/submit/ACK, or mark participation unverified.',
            'Instantiate FixedContinuationOwner for A and B using their own actual ledgers/channels, reuse real notification/tick/collection boundaries, with fixed0/default continuation. Caller must enforce this; InitialOwnerRequest alone is not an autonomous runner.',
            'After each real complete boundary use observe_after_boundary then drain_and_finish_if_closed. Updated ACK/reservation alone is insufficient. Default never promises next1.',
            'Retain every unknown/open input, pre-submit failure and actual missingACK at H40; never silently omit roots. Continue fixed background to commonH40 separately for outcome/parity diagnostics.',
            'evidence() includes serialization; external caller must timestamp after return/ledger and shutdown. Independent verifier must bind full API tape, source/input/authority and commonH seal.'
        ],
        'draft_fixed_cohort':{
            'normal_inputs':'All six original supplied initial cases in accepted JSON002 order, no new live-obligation/later model.',
            'collection_negative_inputs':'Original first declared case with the existing missing_peer, expired_capture, lost_self_ack configurations; these are readiness failures, not post-submit ACK evidence.',
            'submitted_ACK_negative':'Pure actual-shaped query/step/drain guards are implemented. Actual post-submit ACK fault specification must be source-validated and preregistered before a native harness is ready; do not relabel a pre-collection drop as a submitted-request test.',
            'native_campaign_budget':'Not assigned/executable in this source plan; parent review before actual campaign. No native command is emitted.'},
        'integration_remaining':[
            'One owned bounded native campaign with exact fixed-B-before-advance sequencing and both FixedContinuationOwner instances; no separate owner wall-clock choices.',
            'Actual functional image startup/READY loaded-closure proof and shutdown; image is only byte-verified here.',
            'Source-validated post-submit source/receiver or ACK fault rows and preservation of initial model normal-delivery conditional scope.',
            'Full same-input public/native API replay, actual edge/ACK/query-owner and drain validation, complete all-root denominators/cold/output costs, source unchanged checks and commonH40 seal.',
            'No actual100ms or physical protection conclusion until complete real request evidence.'
        ]}
    write(output/'plan.json',plan)
    write(output/'source_preparation.json',{'schema':'g31.initial_owner_route_source_preparation.v1',
        'plan':ref(output/'plan.json'),'sources':len(before),'image_files':len(json.loads((output/'image/manifest.json').read_text())['files']),
        'pure_tests':48,'native_calls':0,'performance_runs':0,
        'source_unchanged':all(sha(ROOT/name)==digest for name,digest in before.items()),
        'status':'source_and_pure_ready_for_review','native_dispatch_ready':False})
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();prepare(args.output);return 0


if __name__=='__main__':raise SystemExit(main())
