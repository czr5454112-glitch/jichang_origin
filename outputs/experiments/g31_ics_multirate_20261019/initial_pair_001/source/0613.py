"""Full96 initial+prediction scope conformance, separate from frozen v2.

Only the original inline initial-context block uses a fresh per-row provider.
Every original statement and comparison remains; future actual-context checks
retain their original defining globals. One original SaveBeforeReturn owns the
entire96 journal. A private data-only carrier joins an initial validated context
to its scope without passing raw targets, restoring authority, or caching data.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
import ast
import copy
import hashlib
import inspect
from pathlib import Path
import sys
import textwrap
from types import FunctionType,SimpleNamespace
from . import validate_live_communication_scoped_inputs_v2 as previous
from . import measure_initial_scoped_public_inputs_six as cost
from . import public_live_obligation_initial_scoped_inputs as component

frozen=previous.frozen
original=frozen.original
scoped=component.scoped
ROOT,OUT,ORDER=previous.ROOT,previous.OUT,previous.ORDER
MODULE='scripts.experiments.g31_ics_circulation.validate_live_communication_initial_scoped_inputs'
TEST='tests/test_g31_circulation_live_communication_initial_scoped_inputs.py'
PURE_MODULE='scripts.experiments.g31_ics_circulation.run_live_communication_initial_scoped_inputs_pure'
PURE=OUT/'live_communication_initial_scoped_inputs_pure_002'
PREVIOUS=OUT/'live_communication_scoped_inputs_v2_prepare_001'
PREVIOUS_PLAN='d64ab44189e5c7cb3d79b109072a6f29d22c9004cd8da872ceffc65dbc8a9fe9'
COST=OUT/'initial_scoped_inputs_six_cost_prepare_001'
COST_PLAN='20522f420b69367c2cd09ebc1d9a6774b5b4853970cdde363ac637b3cfe3bf31'
COST_REPORT='b1b043f9df91ae0dbc1fa16c7d9bd6490c82316bc51707850747dbb0fed92898'
SCHEMA='g31.live_communication_initial_scoped_inputs_conformance.v1'
LIMIT=360.
PURE_COUNT=29
sha,read,ref,write,require=previous.sha,previous.read,previous.ref,previous.write,previous.require
private=previous.private
SaveBeforeReturn=frozen.SaveBeforeReturn
no_execution_extensions=frozen.no_execution_extensions
_SCOPE=scoped.PublicInputScope
_SCOPE_INIT=_SCOPE.__init__


class _ScopeInput:
    """Private call-lifetime references only; not serialized or native authority."""
    __slots__=('scope','supplied')
    def __init__(self,scope,supplied):self.scope=scope;self.supplied=supplied


def _new_scope():return scoped.PublicInputScope()


def _predict(value,action):
    require(type(value) is _ScopeInput and type(value.scope) is _SCOPE,'private_scope_input')
    require(type(value.supplied) is value.scope.context.SuppliedContext,'validated_initial_type')
    return value.scope.predict(value.supplied,action)


def _dump(node):return ast.dump(node,include_attributes=False)


def _inner_code():
    source=ast.parse(textwrap.dedent(inspect.getsource(original.worker)))
    oldblock=ast.parse("""contexts={o:context.initial_context(**public_initial(raw,o)) for o in ('A','B')}
require(all(type(v) is context.SuppliedContext for v in contexts.values()),'actual_initial_context')
facts={o:context.initial_projection_bundle(v) for o,v in contexts.items()}
require(all(context.encoded({'value':facts['A'][f]})==context.encoded({'value':facts['B'][f]})
    for f in ('jobs','trays','contract','now')),'independent_owner_initial_facts')
""").body
    class ContextProvider(ast.NodeTransformer):
        def visit_Name(self,node):
            if node.id=='context':return ast.copy_location(ast.Attribute(ast.Name('_initial_scope',ast.Load()),'context',ast.Load()),node)
            return node
    newblock=[ast.parse('_initial_scope=_new_scope()').body[0]]+[ContextProvider().visit(copy.deepcopy(n)) for n in oldblock]
    oldcall=ast.parse("model.predict(contexts['A'],action)",mode='eval').body
    newcall=ast.parse("model.predict(_ScopeInput(_initial_scope,contexts['A']),action)",mode='eval').body
    class Change(ast.NodeTransformer):
        def __init__(self,inverse=False):self.inverse=inverse;self.blocks=0;self.calls=0
        def visit_Try(self,node):
            before,after=(newblock,oldblock) if self.inverse else (oldblock,newblock)
            found=[i for i in range(len(node.body)-len(before)+1)
                if [_dump(n) for n in node.body[i:i+len(before)]]==[_dump(n) for n in before]]
            require(len(found)<=1,'unique_inline_block')
            if found:
                self.blocks+=1;index=found[0];node.body[index:index+len(before)]=copy.deepcopy(after)
            return self.generic_visit(node)
        def visit_Call(self,node):
            before,after=(newcall,oldcall) if self.inverse else (oldcall,newcall)
            if _dump(node)==_dump(before):self.calls+=1;return copy.deepcopy(after)
            return self.generic_visit(node)
    changer=Change();changed=changer.visit(copy.deepcopy(source))
    require((changer.blocks,changer.calls)==(1,1),'one_initial_block_and_predict_context')
    inverse=Change(True);restored=inverse.visit(copy.deepcopy(changed))
    require((inverse.blocks,inverse.calls)==(1,1) and _dump(restored)==_dump(source),'inline_inverse_AST')
    namespace={};exec(compile(ast.fix_missing_locations(changed),str(Path(__file__)),'exec'),namespace)
    return namespace['worker'].__code__,hashlib.sha256(_dump(source).encode()).hexdigest()


_INNER_CODE,_INNER_AST=_inner_code()


def bind_worker(saver):
    namespace={**original.worker.__globals__,'model':SimpleNamespace(physics=original.model.physics,predict=saver),
        '_new_scope':_new_scope,'_ScopeInput':_ScopeInput}
    function=FunctionType(_INNER_CODE,namespace,original.worker.__name__,original.worker.__defaults__,original.worker.__closure__)
    function.__kwdefaults__=original.worker.__kwdefaults__;return function


run_original=private(frozen.run_original,{'bind_worker':bind_worker})


def worker_function():
    return private(frozen.worker,{'candidate':SimpleNamespace(predict=_predict),'run_original':run_original,
        'SCHEMA':SCHEMA,'source_proof':source_proof,'pure_gate':pure_gate})


def source_proof():
    component.source_proof()
    require(scoped.PublicInputScope is _SCOPE and _SCOPE.__init__ is _SCOPE_INIT,'scope_identity')
    code,digest=_inner_code();require(digest==_INNER_AST and code==_INNER_CODE,'inner_code_source')
    sentinel=object();inner=bind_worker(sentinel);inner_old=original.worker.__globals__
    require(set(inner.__globals__)==set(inner_old)|{'_new_scope','_ScopeInput'}
        and all(inner.__globals__[k] is v for k,v in inner_old.items() if k!='model'),'inner_complete_globals')
    require(inner.__globals__['model'].predict is sentinel and inner.__globals__['model'].physics is original.model.physics
        and inner.__globals__['context'] is original.context
        and inner.__globals__['future_context'] is original.future_context
        and original.future_context.__globals__['context'] is original.context,'initial_only_provider')
    outer=worker_function();allowed={'candidate','run_original','SCHEMA','source_proof','pure_gate'}
    require(outer.__code__ is frozen.worker.__code__ and outer.__closure__ is frozen.worker.__closure__
        and outer.__defaults__ is frozen.worker.__defaults__ and outer.__kwdefaults__ is frozen.worker.__kwdefaults__
        and set(outer.__globals__)==set(frozen.worker.__globals__)
        and all(outer.__globals__[k] is v for k,v in frozen.worker.__globals__.items() if k not in allowed),'outer_complete_globals')
    require(run_original.__code__ is frozen.run_original.__code__
        and set(run_original.__globals__)==set(frozen.run_original.__globals__)
        and all(run_original.__globals__[k] is v for k,v in frozen.run_original.__globals__.items() if k!='bind_worker'),
        'original_cleanup_and_single_saver')
    return {'schema':SCHEMA,'original_inner_AST_sha256':_INNER_AST,'inline_inverse_AST':True,
        'initial_statements_and_fact_comparisons_unchanged':True,'one_fresh_scope_per_initial_attempt':True,
        'same_scope_initial_and_predict':True,'original_future_actual_guard_globals_unchanged':True,
        'one_original_SaveBeforeReturn_for_all96':True,'ordinal_late_binding_unchanged':True,
        'original226_192_fulloutput_chronology_checks_unchanged':True,
        'private_carrier_contains_only_scope_and_validated_initial_context':True,
        'no_actual_raw_target_in_scope_or_predictor':True,
        'initial_scope_and_guards_in_whole360_not_old_model_wall':True,
        'old_modelspan_includes_early_export_hash_journal':True,'component_ABBA_speed_comparison':False,
        'default_GC_required':True,'sample_cleanup_certified':False,'native_calls':0,
        'online_authority':False,'complete_request100ms_certified':False}


def pure_gate():
    check=private(previous.pure_gate,{'PURE':PURE,'PURE_COUNT':PURE_COUNT})
    return check()


def source_union():
    files=frozen.image.source_closure(ROOT,(MODULE,PURE_MODULE,TEST[:-3].replace('/','.')))
    for folder,expected,count in ((PREVIOUS,PREVIOUS_PLAN,164),(COST,COST_PLAN,171)):
        require(sha(folder/'plan.json')==expected,'initial_full96_prior_identity')
        plan=read(folder/'plan.json');require(len(plan['source_sha256'])==count,'initial_full96_prior_count')
        for path,digest in plan['source_sha256'].items():
            require(sha(path)==digest==sha(folder/plan['source_archive'][path]),'initial_full96_frozen_sources')
            files[str(Path(path).relative_to(ROOT))]=Path(path).read_bytes()
    return files


def prepare(output):
    no_execution_extensions();pure=pure_gate();files=source_union()
    previous_plan=read(PREVIOUS/'plan.json');final=read(PREVIOUS/'final_receipt.json')
    require(final['status']=='exact_all96_original_checks_and_full_outputs' and final['full_output_exact']==96
        and final['unknown_or_difference']==0 and final['actual_collection_data_checks']==226
        and final['actual_known_collection_data']==192 and final['early_ordinal_mapping_certified']
        and final['source_changed']==[],'v2_full96_exact')
    require(sha(COST/'report.json')==COST_REPORT,'initial_ABBA_actual_identity')
    report=read(COST/'report.json')
    require(report['status']=='passed_fixed_six_ABBA24_complete_prediction' and report['exact']==24
        and report['unknown']==0 and report['source_changed']==[],'initial_ABBA_actual_exact')
    output.mkdir(exist_ok=False);pins,archives=cost.prior._archive(output,files)
    for name,digest in pure['source_sha256'].items():require(pins[str(ROOT/name)]==digest,'pure_in_plan')
    fixed={**previous_plan['fixed_evidence_sha256'],**read(COST/'plan.json')['evidence_sha256']}
    for folder,names in ((PREVIOUS,('plan.json','receipt.json','rows.json','final_receipt.json','equivalence96.json',
        'early_prediction_inventory.json','bounded_execution.json','external_application_wall.json')),
        (COST,('plan.json','report.json','receipt.json','ledger.json','bounded_execution.json','external_application_wall.json')),
        (PURE,('receipt.json','tests.xml','external_application_wall.json'))):
        for name in names:fixed[str(folder/name)]=sha(folder/name)
    for folder in (PREVIOUS,COST):
        plan=read(folder/'plan.json')
        for path,digest in plan['source_sha256'].items():fixed[str(folder/plan['source_archive'][path])]=digest
    plan={**copy.deepcopy(previous_plan),'schema':SCHEMA,'source_sha256':pins,'source_archive':archives,
        'fixed_evidence_sha256':fixed,'source_proof':source_proof(),
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'model_variant':'same_fresh_scoped_v2_initial_and_prediction_per_row',
        'inherited_rule_text_reference_only':previous_plan['rules'],
        'rules':[
            'Only original inline initial four statements use one new row-local scope.context; all their operations/comparisons remain.',
            'Original future_context defining globals are unchanged; actual future data remain targets only.',
            'Single original SaveBeforeReturn for all96; carrier holds only scope and validated initial context; all old ordinal and fulloutput guards remain.',
            'Old model span excludes initial construction but includes early export. Whole360 includes all; no comparison with wholecomponent ABBA samples.',
            'Every failed row retained; no cached validation/observation/result, altered action or extra retry.'],
        'initial_ABBA_reference':ref(COST/'report.json'),'v2_full96_reference':ref(PREVIOUS/'final_receipt.json'),
        'budget':{**previous_plan['budget'],'fixed_application_seconds':LIMIT,
            'basis':'Keep prior360 whole bound, including source/hash, initial guards,96 models,226 checks,all exports/comparisons and process cleanup.'},
        'preparation_model_calls':0,'preparation_raw_decodes':0}
    write(output/'plan.json',plan);write(output/'rows.json',copy.deepcopy(plan['rows']))
    write(output/'ready.json',{'status':'prepared_source_review_pending','plan':ref(output/'plan.json'),
        'source_count':len(pins),'focused_pure_tests':PURE_COUNT,'retained_v1_pure_tests':53,
        'fixed_application_seconds':LIMIT,'native_calls':0,'model_calls':0,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def worker(output,expected):
    worker_function()(output,expected)
    require(read(output/'final_receipt.json')['status']=='exact_all96_original_checks_and_full_outputs','initial_complete_gate')


main=private(previous.main,{'BOOT':BOOT,'MODULE':MODULE,'prepare':prepare,'worker':worker,'__file__':__file__})


if __name__=='__main__':raise SystemExit(main())
