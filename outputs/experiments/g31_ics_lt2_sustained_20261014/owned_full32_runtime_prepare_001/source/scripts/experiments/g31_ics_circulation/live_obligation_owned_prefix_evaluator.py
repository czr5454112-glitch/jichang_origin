"""Source candidate: owned model execution separated from graph diagnostics.

No native authority, actual hidden-state coverage, speed or protection claim.
This deliberately retains the accepted future API, repeated source inventories,
all initial/dynamic guards and one whole graph clone per suffix. The old paired
diagnostic remains unchanged and is the proposed independent comparison path.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import json
import textwrap
from types import FunctionType
from . import validate_future_later_paired_suffix as previous
from . import live_obligation_future_later_fork as future
from . import live_obligation_full32_suffix_evaluator as evaluator
from . import live_obligation_full32_suffix_partition as domain

VERSION='g31.owned_model_future_suffix_execution.v1'
OWNERSHIP='private_factory_complete_graph_clone_v1'


def require(ok,reason):
    if not ok:raise ValueError('owned_prefix_candidate:'+reason)


def _dump(value):return ast.dump(value,include_attributes=False)
def _stmt(text):return ast.parse(text).body[0]


def _rewrite(function,replacements,*,drop_return_keys=()):
    """Closed exact statement substitutions with an executable inverse map."""
    original=ast.parse(textwrap.dedent(inspect.getsource(function)))
    pairs=[(_stmt(left),_stmt(right)) for left,right in replacements]
    counts=[0]*len(pairs);inverse_counts=[0]*len(pairs)
    def replace(tree,pairs,counts):
        class Change(ast.NodeTransformer):
            def visit(self,node):
                for index,(left,right) in enumerate(pairs):
                    if _dump(node)==_dump(left):
                        counts[index]+=1;return ast.copy_location(copy.deepcopy(right),node)
                return super().visit(node)
        return Change().visit(copy.deepcopy(tree))
    changed=replace(original,pairs,counts)
    require(counts==[1]*len(pairs),'one_exact_statement_each:'+function.__name__)
    dropped=[]
    if drop_return_keys:
        returns=[node for node in ast.walk(changed) if isinstance(node,ast.Return) and isinstance(node.value,ast.Dict)]
        require(len(returns)==1,'single_metadata_return:'+function.__name__)
        value=returns[0].value
        for index,(key,item) in reversed(list(enumerate(zip(value.keys,value.values,strict=True)))):
            if isinstance(key,ast.Constant) and key.value in drop_return_keys:
                dropped.append((index,copy.deepcopy(key),copy.deepcopy(item)));del value.keys[index];del value.values[index]
        require({key.value for _,key,_ in dropped}==set(drop_return_keys),'exact_metadata_keys')
    restored=copy.deepcopy(changed)
    if dropped:
        value=next(n.value for n in ast.walk(restored) if isinstance(n,ast.Return) and isinstance(n.value,ast.Dict))
        for index,key,item in sorted(dropped,key=lambda x:x[0]):value.keys.insert(index,key);value.values.insert(index,item)
    restored=replace(restored,[(b,a) for a,b in pairs],inverse_counts)
    require(inverse_counts==[1]*len(pairs) and _dump(restored)==_dump(original),'inverse_AST:'+function.__name__)
    namespace={};exec(compile(ast.fix_missing_locations(changed),__file__,'exec'),namespace)
    proof={'function':function.__name__,'original_AST_sha256':hashlib.sha256(_dump(original).encode()).hexdigest(),
        'candidate_AST_sha256':hashlib.sha256(_dump(changed).encode()).hexdigest(),
        'inverse_AST_exact':True,'exact_statement_count':len(pairs),'removed_metadata_keys':list(drop_return_keys)}
    return namespace[function.__name__].__code__,proof


_POINT_REPLACEMENTS=[("encoded = graph(state, model)","'diagnostic_only_graph_encoding_removed_at_point'")]
_TERMINAL_REPLACEMENTS=[("value = graph(state, model)","'diagnostic_only_graph_encoding_removed_at_terminal'")]
_RUN_REPLACEMENTS=[
    ("before = graph(parent, model)","'diagnostic_only_parent_graph_encoding_removed'"),
    ("encoded = graph(child, model)","'diagnostic_only_child_graph_encoding_removed'"),
    ("action_graph_only(before, encoded, action['later_action'], choice)","'diagnostic_only_whole_graph_action_comparison_removed'"),
    ("require(graph(parent,model)==before,'parent_changed_by_fork')", "require(parent._consumed is False,'parent_consumed_by_fork')"),
    ("child_graphs[choice] = encoded", "'diagnostic_only_child_graph_retention_removed'"),
    ("ids={key:mutable_ids(branch._state,model) for key,branch in children.items()}","'diagnostic_only_child_mutable_walks_removed'"),
    ("pids=mutable_ids(parent,model)","'diagnostic_only_parent_mutable_walk_removed'"),
    ("require(not(ids[CHOICES[0]]&ids[CHOICES[1]]) and all(not(pids&v) for v in ids.values()),'shared_mutable_fork_state')",
     "'diagnostic_only_three_graph_intersection_removed'"),
    ("result['prefix'].update(parent_graph_sha256=hashlib.sha256(before).hexdigest(),complete_graph_only_future_action_changed=True,three_mutable_graphs_disjoint=True)",
     "result['prefix'].update(isolation_basis=_OWNERSHIP,diagnostic_graphs_computed=False,native_hidden_state_coverage=False)"),
    ("require(graph(parent,model)==before and graph(child,model)==child_graphs[choice],'pre_suffix_changed')",
     "require(parent._consumed is False and child is branch._state,'pre_suffix_owned_state')"),
    ("require(graph(parent,model)==before,'parent_changed_by_suffix')","require(parent._consumed is False,'parent_consumed_by_suffix')"),
    ("waiting=[other for other in CHOICES if other!=choice and not children[other]._consumed]",
     "'diagnostic_only_waiting_graph_list_removed'"),
    ("require(all(graph(children[other]._state,model)==child_graphs[other] for other in waiting),'sibling_changed_by_suffix')",
     "'diagnostic_only_waiting_graph_comparison_removed'"),
    ("previous.mutate_finished_copy(child)","'diagnostic_only_destructive_completed_probe_removed'"),
    ("require(graph(parent,model)==before and all(graph(children[other]._state,model)==child_graphs[other] for other in waiting),'finished_mutation_leaked')",
     "require(parent._consumed is False,'parent_consumed_after_return')"),
    ("row['parent_and_unconsumed_sibling_isolated']=True","row['isolation_basis']=_OWNERSHIP")]

_POINT_CODE,_POINT_PROOF=_rewrite(previous.point_description,_POINT_REPLACEMENTS,
    drop_return_keys=('graph_sha256','graph_encoded_bytes'))
_TERMINAL_CODE,_TERMINAL_PROOF=_rewrite(previous.terminal_description,_TERMINAL_REPLACEMENTS,
    drop_return_keys=('graph_sha256','graph_encoded_bytes'))
_RUN_CODE,_RUN_PROOF=_rewrite(previous.run_case,_RUN_REPLACEMENTS)
_GROUP_CODE,_GROUP_PROOF=_rewrite(evaluator.execute_group,[
    ('detail=paired.run_case(context,copy.deepcopy(group[\'representative_action\']),MAXIMUM_CUTS,model,future,save_prediction)',
     'detail=_owned_run(context,copy.deepcopy(group[\'representative_action\']),MAXIMUM_CUTS,model,future,save_prediction)')])


def _clone(function,namespace,code):
    result=FunctionType(code,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__;return result


_point=_clone(previous.point_description,dict(previous.point_description.__globals__),_POINT_CODE)
_terminal=_clone(previous.terminal_description,dict(previous.terminal_description.__globals__),_TERMINAL_CODE)
_RUN_GLOBALS={**previous.run_case.__globals__,'point_description':_point,'terminal_description':_terminal,'_OWNERSHIP':OWNERSHIP}
_run=_clone(previous.run_case,_RUN_GLOBALS,_RUN_CODE)
_GROUP_GLOBALS={**evaluator.execute_group.__globals__,'_owned_run':_run}
_group=_clone(evaluator.execute_group,_GROUP_GLOBALS,_GROUP_CODE)
_FUNCTIONS={name:getattr(future.core,name) for name in
    ('start_conditional','advance_to_collection_or_terminal','resume_same_action','fork_conditional','validate')}
_FUTURE={name:getattr(future,name) for name in ('fork_later_action','resume_future_later','_cut','source_proof')}
_CODES={function:function.__code__ for function in (*_FUNCTIONS.values(),*_FUTURE.values())}
_PRIVATE_CODES={_point:_POINT_CODE,_terminal:_TERMINAL_CODE,_run:_RUN_CODE,_group:_GROUP_CODE}


def source_proof():
    require(all(function.__code__ is code for function,code in _PRIVATE_CODES.items()),'private_code_identity')
    require(all(getattr(future.core,k) is v for k,v in _FUNCTIONS.items())
        and all(getattr(future,k) is v for k,v in _FUTURE.items())
        and all(function.__code__ is code for function,code in _CODES.items()),'factory_and_dynamic_guard_identity')
    for function,original in ((_point,previous.point_description),(_terminal,previous.terminal_description)):
        require(set(function.__globals__)==set(original.__globals__)
            and all(function.__globals__[k] is v for k,v in original.__globals__.items()),'point_terminal_defining_globals')
    require(set(_RUN_GLOBALS)==set(previous.run_case.__globals__)|{'_OWNERSHIP'}
        and all(_RUN_GLOBALS[k] is v for k,v in previous.run_case.__globals__.items()
            if k not in ('point_description','terminal_description')),'run_defining_globals')
    require(_RUN_GLOBALS['point_description'] is _point and _RUN_GLOBALS['terminal_description'] is _terminal
        and _RUN_GLOBALS['_OWNERSHIP']==OWNERSHIP,'runtime_helper_bindings')
    require(set(_GROUP_GLOBALS)==set(evaluator.execute_group.__globals__)|{'_owned_run'}
        and all(_GROUP_GLOBALS[k] is v for k,v in evaluator.execute_group.__globals__.items())
        and _GROUP_GLOBALS['_owned_run'] is _run,'group_defining_globals')
    # The existing source proof and each original fork/resume still run; no
    # source-inventory cache is introduced by this diagnostic-only revision.
    old=future.source_proof()
    return {'schema':VERSION,'point':copy.deepcopy(_POINT_PROOF),'terminal':copy.deepcopy(_TERMINAL_PROOF),
        'run':copy.deepcopy(_RUN_PROOF),'group':copy.deepcopy(_GROUP_PROOF),'unchanged_future_source_proof':old,
        'original_initial_and_cut_guards_retained':True,'same_whole_dynamic_graph_clone':True,
        'both_children_before_either_resume':True,'source_inventory_memoization':False,
        'initial_context_cache':False,'offline_diagnostic_path_unchanged':True,
        'isolation_basis':OWNERSHIP,'closed_domain':'Exact source-owned factories and serial private state; no arbitrary reflection, callbacks receiving state or concurrent mutation.',
        'arbitrary_tamper_resistance':False,'native_authority':False,'100ms_certified':False}


def execute_group(group,context):
    """One fresh supplied context, private two-child model state, full outputs.

No target/native endpoint/case label or external save callback is accepted.
The helper retains all semantic point/terminal checks; diagnostic graph hashes
are deliberately absent and must not be inferred by a caller.
"""
    expected=domain.partition(future.core.lazy.original.physics.previous.actions())['groups']
    require(type(group) is dict and type(group.get('prefix_index')) is int and 0<=group['prefix_index']<16
        and previous.bytes_of(group)==previous.bytes_of(expected[group['prefix_index']]),'fixed_prefix_group')
    predictions={}
    def save(label,value):
        raw=previous.bytes_of(value)
        predictions[label]=json.loads(raw)
        return {'memory_label':label,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    # Original group exception handling and complete two-candidate denominator
    # remain unchanged. The only callback is private and receives a prediction,
    # never an engine/frame. The context callback exposes no state either.
    detail=_group(group,lambda index,action:context,save,model=future.core,future=future)
    require(tuple(detail['rows'])==tuple(f'vector_{i:02d}' for i in group['candidate_indices']),
        'two_suffix_denominator')
    return {'schema':VERSION,'prefix_index':group['prefix_index'],'candidate_indices':copy.deepcopy(group['candidate_indices']),
        'detail':detail,'predictions':predictions,'isolation_basis':OWNERSHIP,
        'diagnostic_graphs_computed':False,'native_authority':False,'hidden_state_coverage':False}
