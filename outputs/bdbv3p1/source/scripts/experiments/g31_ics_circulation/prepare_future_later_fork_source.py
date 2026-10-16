"""Freeze source/pure proof and proposed six pairs; never run model/native."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
PURE=OUT/'future_later_fork_pure_002'
SIX=OUT/'conditional_continuation_six_prepare_001'
LAZY=OUT/'live_communication_lazy_prepare_001'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(value,reason):
    if not value:raise ValueError('future_prepare:'+reason)
def ref(path):return {'path':str(path),'sha256':sha(path)}


def main():
    require(sha(PURE/'receipt.json')=='0fbe25a205aabe20664878c6cb5aa85306eba706450657d7999cb2f9398936f9','pure_receipt')
    require(sha(SIX/'plan.json')=='dd91512a60cc6ef336842ab93a5341a47ebd90276470116b24e8cb4e90917c56','six_plan')
    require(sha(LAZY/'plan.json')=='afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497','lazy_plan')
    require(sha(LAZY/'rows.json')=='7753bc2c9731ded83300435814f5b9c033197237cbaaa0c33721fe09c1a74a3e','lazy_rows')
    pure=read(PURE/'receipt.json');pp=read(PURE/'plan.json');bound=read(PURE/'bounded_parent_receipt.json')
    outer=read(PURE/'external_application_wall.json');six=read(SIX/'plan.json')
    lazy_plan=read(LAZY/'plan.json');lazy_rows=read(LAZY/'rows.json')
    require(pure['status']==bound['status']=='passed' and pure['tests']==62
        and pure['source_changed']==pure['final_source_changed']==[] and pure['proof_unchanged'] is True,'pure_failed')
    require(bound['process']['status']=='exited' and bound['process']['exitcode']==0
        and outer['exitcode']==0 and outer['whole_python_wall_seconds']<120.,'pure_process')
    require(pure['plan_sha256']==sha(PURE/'plan.json') and pure['XML_sha256']==sha(PURE/'tests.xml')
        and pure['source_proof_sha256']==sha(PURE/'source_proof.json'),'pure_artifacts')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases)==62 and not any(n.tag in ('failure','error','skipped') for row in cases for n in row),'pure_XML')
    proposed=pp['future_experiment'];order=proposed['order'];counterparts=proposed['counterpart_order']
    require(len(order)==len(counterparts)==6 and order==six['order'],'fixed_six_order')
    pairs={}
    for key,other in zip(order,counterparts,strict=True):
        left=lazy_plan['rows'][key]['action'];right=lazy_plan['rows'][other]['action']
        require({k:v for k,v in left.items() if k!='later_action'}=={k:v for k,v in right.items() if k!='later_action'}
            and {left['later_action'],right['later_action']}=={'native_default','prefer_8'},'only_future_choice')
        require(left==six['rows'][key]['action'],'same_old_action')
        require(lazy_rows[key]['status']==lazy_rows[other]['status']=='exact_conformance','saved_comparands_unknown')
        initial=six['rows'][key]['input'];same=lazy_rows[key]['prediction'];different=lazy_rows[other]['prediction']
        for item in (initial,same,different):require(sha(item['path'])==item['sha256'],'frozen_file_changed')
        require(same==six['rows'][key]['comparison_only_saved_prediction'],'same_target_binding')
        expected=[row for row in six['rows'][key]['expected_collections'] if row['owner']=='B'
            and row['phase']=='first_reuse_route' and row['information_status']=='conditional_validated_later_v3_data']
        require(len(expected)==1,'one_known_B_cut')
        pairs[key]={'status':'unknown_unexecuted','initial_context':initial,'original_action':left,
            'counterpart_key':other,'counterpart_action':right,
            'same_choice_comparison_only':same,'changed_choice_comparison_only':different,
            'expected_B_chronology_label_not_filter_authority':expected[0],
            'past_fields_fixed':['initial_action','empty_departure','return_delay']}
    sources={}
    for name,digest in pp['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(PURE/pp['source_archive'][name])==digest,'pure_source_drift:'+name)
        sources[name]=(ROOT/name).read_bytes()
    sources[Path(__file__).resolve().relative_to(ROOT).as_posix()]=Path(__file__).read_bytes()
    output=OUT/'future_later_fork_source_prepare_001';output.mkdir(exist_ok=False)
    for name,data in sources.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    plan={'schema':'g31.future_later_fork.source_preparation.v1',
        'status':'source_pure_ready_real_six_driver_not_implemented_or_dispatched',
        'source_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in sources.items()},
        'source_archive':{name:'source/'+name for name in sources},'order':order,'pairs':pairs,
        'pure_plan':ref(PURE/'plan.json'),'pure_receipt':ref(PURE/'receipt.json'),
        'pure_XML':ref(PURE/'tests.xml'),'pure_bounded':ref(PURE/'bounded_parent_receipt.json'),
        'pure_external':ref(PURE/'external_application_wall.json'),'source_proof':ref(PURE/'source_proof.json'),
        'same_action_six_plan':ref(SIX/'plan.json'),'saved_lazy_plan':ref(LAZY/'plan.json'),
        'saved_lazy_rows':ref(LAZY/'rows.json'),'proposed_experiment':proposed,
        'failed_pure001_preserved':ref(OUT/'future_later_fork_pure_001/receipt.json'),
        'source_scope':'The frozen known model source has no live later_action consumer before phase B tail. A constructor copies it without branching; a dormant legacy event consumer is unreachable under the effective no-op scheduler and additionally rejected in the current heap. Loaded methods/parts/code identities are checked. Private Python state is not advertised as arbitrary-tamper-proof or native authority.',
        'new_interface':['fork_later_action(existing_conditional_cut, declared_later_action)',
            'resume_future_later(factory_branch)'],
        'semantic_limits':['Only known B first_reuse_route post-collect/pre-action cuts with current uncommitted L, finite unexpired collection and strict wire-before-service are supported.',
            'One entire engine/frames graph copy preserves aliases and current popped event/owner cursor; prior action fields and the parent are unchanged.',
            'The new fixed action identity is explicit. Old same-action validation/code remain unchanged; no second collect or prefix reinitialization.',
            'Comparands are retrospective semantic regression records. No new physical protection, online authority, hidden-state/opaque-ID coverage or speed claim.'],
        'native_calls':0,'real_model_predictions_executed_for_this_preparation':0}
    write(output/'plan.json',plan)
    print(json.dumps({'output':str(output),'plan_sha256':sha(output/'plan.json'),'sources':len(sources),
        'tests':62,'pairs':6,'suffix_budget':12,'real_model_predictions':0,'native_calls':0}))


if __name__=='__main__':main()
