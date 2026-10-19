"""Freeze source and synthetic ownership proof only; no model execution."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from . import public_live_obligation_owned_bundle as candidate
from . import measure_scoped_public_inputs_v2_six as utility

ROOT, OUT = utility.ROOT, utility.OUT
MODULE = 'scripts.experiments.g31_ics_circulation.prepare_live_obligation_owned_bundle'
PURE = OUT/'owned_initial_bundle_pure_001'
PREVIOUS = OUT/'live_communication_initial_scoped_inputs_prepare_001'
PREVIOUS_PLAN = '8036d19b2f397551df1fe593f45b17097ef6cf314a6521319ad33b772cfb491c'
PREVIOUS_FINAL = '34bba02fd695b81383ac94d0e81baf279cff1c5702e04d5c4c09f6f1ff5aea2a'
sha, read, write, ref, require = utility.sha, utility.read, utility.write, utility.ref, utility.require


def pure_receipt():
    receipt=read(PURE/'receipt.json')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[]
        and receipt['tests']==len(cases)==26 and receipt['native_calls']==receipt['model_engine_runs']==0
        and receipt['performance_runs']==receipt['real_saved_input_decodes']==0
        and not any(n.tag in ('failure','error','skipped') for case in cases for n in case), 'owned26_pure')
    require(receipt['XML_sha256']==sha(PURE/'tests.xml'), 'owned26_XML')
    outer=read(PURE/'external_application_wall.json')
    require(outer['exitcode']==0 and outer['status']=='closed0'
        and 0<outer['whole_python_wall_seconds']<=120
        and outer['fixed_owned_limit_seconds']==120 and outer['test_count']==26,
        'owned26_outer_wall')
    for name,digest in receipt['source_sha256'].items():
        require(sha(ROOT/name)==digest==sha(PURE/'source'/name),'owned26_source')
    return receipt


def prepare(output):
    utility.frozen.base.no_execution_extensions(); pure=pure_receipt()
    require(sha(PREVIOUS/'plan.json')==PREVIOUS_PLAN
        and sha(PREVIOUS/'final_receipt.json')==PREVIOUS_FINAL,'original_initial96_identity')
    old=read(PREVIOUS/'plan.json'); final=read(PREVIOUS/'final_receipt.json')
    require(len(old['source_sha256'])==174 and final['status']=='exact_all96_original_checks_and_full_outputs'
        and final['full_output_exact']==96 and final['unknown_or_difference']==0
        and final['actual_collection_data_checks']==226 and final['actual_known_collection_data']==192
        and final['early_invocations']==96 and final['early_ordinal_mapping_certified']
        and final['early_unbound_invocations']==0 and final['source_changed']==[] and final['GC_enabled'],
        'original_initial96_result')
    files=utility.frozen.image.source_closure(ROOT,(MODULE,
        'scripts.experiments.g31_ics_circulation.run_live_obligation_owned_bundle_pure',
        'tests.test_g31_circulation_live_obligation_owned_bundle'))
    for path,digest in old['source_sha256'].items():
        require(sha(path)==digest==sha(PREVIOUS/old['source_archive'][path]),'frozen174_sources')
        files[str(Path(path).relative_to(ROOT))]=Path(path).read_bytes()
    for name,digest in pure['source_sha256'].items():
        require(hashlib.sha256(files[name]).hexdigest()==digest,'tested_sources')
    output.mkdir(exist_ok=False); pins={}; archives={}
    for name,data in sorted(files.items()):
        path=output/'source'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        pins[str(ROOT/name)]=hashlib.sha256(data).hexdigest(); archives[str(ROOT/name)]=str(path.relative_to(output))
    evidence={}
    for folder,names in ((PURE,('receipt.json','tests.xml','external_application_wall.json')),
        (PREVIOUS,('plan.json','final_receipt.json','receipt.json','bounded_execution.json','external_application_wall.json'))):
        for name in names: evidence[str(folder/name)]=sha(folder/name)
    design=OUT/'owned_initial_bundle_design_001.json'; evidence[str(design)]=sha(design)
    plan={'schema':candidate.SCHEMA,'status':'prepared_source_only_unexecuted_model',
        'source_sha256':pins,'source_archive':archives,'evidence_sha256':evidence,
        'source_proof':candidate.source_proof(),'candidate':ref(candidate.__file__),
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'pure_tests':26,'preparation_model_calls':0,'preparation_raw_decodes':0,'native_calls':0,
        'future_cost_boundary':'A current initial_scope.predict; B owned_bundle.predict. Both fresh scope plus exact same A/B construction/guards/facts and model. Whole includes every source/hash/load/export/readback/cleanup cost.',
        'retained_revalidate_deepcopy':True,'retained_protocol_deepcopy':True,
        'allocation_failure_timing_equivalent':False,'sample_cleanup_certified':False,
        'complete_request_100ms_certified':False}
    write(output/'plan.json',plan)
    write(output/'source_preparation.json',{'status':plan['status'],'plan':ref(output/'plan.json'),
        'source_count':len(pins),'pure_tests':26,'source_changed':[],'model_calls':0,'native_calls':0})


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); prepare(args.output.resolve())


if __name__=='__main__': main()
