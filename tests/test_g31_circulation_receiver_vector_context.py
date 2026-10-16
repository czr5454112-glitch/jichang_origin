from copy import deepcopy
import ast
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import textwrap
import pytest
from test_g31_circulation_preference_request_context import bundle,ordered
from scripts.experiments.g31_ics_circulation import public_preference_receiver_vector_context as new

ROOT=Path(__file__).resolve().parents[1]
SAVED=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/preference_receiver_bound_pair_001'
ROWS=[]


def test_exact_predict_ast_except_dispatch_binding_and_reference_lookup():
    original=ast.parse(textwrap.dedent(inspect.getsource(new.old.ReceiverBoundRequestContext.predict))).body[0]
    candidate=ast.parse(textwrap.dedent(inspect.getsource(new.ReceiverVectorRequestContext.predict))).body[0]
    class Restore(ast.NodeTransformer):
        counts={'reference':0,'dispatch':0,'exception':0,'private':0}
        def visit_Call(self,node):
            text=ast.unparse(node)
            if text=='dict(self.__completion_vector)':
                self.counts['reference']+=1;return ast.parse("self.baseline()['completion']",mode='eval').body
            if text=='old.combined.ProtectionRequestContext.predict(self, action)':
                self.counts['dispatch']+=1;return ast.parse('super().predict(action)',mode='eval').body
            return self.generic_visit(node)
        def visit_Attribute(self,node):
            if ast.unparse(node)=='old._LowerBoundRejected':
                self.counts['exception']+=1;return ast.Name(id='_LowerBoundRejected',ctx=ast.Load())
            if isinstance(node.value,ast.Name) and node.value.id=='self' and node.attr.startswith('_ReceiverBoundRequestContext__'):
                self.counts['private']+=1;return ast.Attribute(value=node.value,attr='__'+node.attr.split('__',1)[1],ctx=node.ctx)
            return self.generic_visit(node)
    restore=Restore();restored=restore.visit(candidate)
    assert restore.counts=={'reference':1,'dispatch':1,'exception':1,'private':3}
    assert ast.dump(original,include_attributes=False)==ast.dump(restored,include_attributes=False)


@pytest.mark.parametrize('index',range(6))
def test_fixed192_every_output_exact_saved_actual_and_counts(index):
    plan=json.loads((SAVED/'preregistered_protocol.json').read_bytes());case=plan['cases'][index]
    path=SAVED/case['input'];assert hashlib.sha256(path.read_bytes()).hexdigest()==case['input_sha256']
    value=json.loads(path.read_bytes());ctx=new.ReceiverVectorRequestContext(value)
    ledger=json.loads((SAVED/'ledger.json').read_bytes());row=ledger[4*index+1];raw=SAVED/row['raw']
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==row['raw_sha256']
    saved=json.loads(gzip.decompress(raw.read_bytes()))
    assert ordered(ctx.baseline())==ordered(saved['baseline']) and ordered(ctx.actions())==ordered(saved['actions'])
    for action,expected in zip(ctx.actions(),saved['predictions'],strict=True):assert ordered(ctx.predict(action))==ordered(expected)
    counts=ctx.describe()['counts'];assert counts['candidate_queries']==32 and counts['baseline_full_simulations']==1
    assert sum(counts[k] for k in ('candidate_full_predictions','candidate_prefix_rejections','candidate_lower_bound_rejections','candidate_unknowns'))==32
    ROWS.append({'case':case['case'],'exact_predictions':32,'counts':counts})


def test_no_full_baseline_copy_during_early_certificates(monkeypatch):
    calls=[];source=new.old.combined.ProtectionRequestContext.baseline
    def counted(self):calls.append(type(self).__name__);return source(self)
    monkeypatch.setattr(new.old.combined.ProtectionRequestContext,'baseline',counted)
    ctx=new.ReceiverVectorRequestContext(bundle());assert calls==[]
    action=ctx.actions()[8]
    result=ctx.predict(action);assert result['status']=='conditional_protection_rejected_lower_bound' and calls==[]
    assert ctx.baseline()['status']=='conditional_prediction' and len(calls)==1
    assert ctx.predict(action)==result and len(calls)==1


def test_private_vector_immutable_ordered_and_public_full_baseline_isolated():
    value=bundle();ctx=new.ReceiverVectorRequestContext(value);action=ctx.actions()[8]
    vector=object.__getattribute__(ctx,'_ReceiverVectorRequestContext__completion_vector')
    assert type(vector) is tuple and len(vector)==5 and all(type(pair) is tuple and len(pair)==2 for pair in vector)
    expected=ctx.predict(action);full=ctx.baseline();assert list(dict(vector))==list(full['completion'])
    full['completion']['receiver']=-1;full['events'].clear() if 'events' in full else None
    expected_copy=deepcopy(expected);expected['baseline_completion']['receiver']=-1
    value['trays']['E']['node']=1
    assert ordered(ctx.predict(action))==ordered(expected_copy)
    other=new.ReceiverVectorRequestContext(bundle(3));assert other.baseline()['completion']!=ctx.baseline()['completion']
    assert ordered(ctx.predict(action))==ordered(expected_copy)


@pytest.mark.parametrize('defect',['extra_empty','P_returns','new_edge','permission','age','pending','receiver','extra_job','custom'])
def test_bad_or_alternative_inputs_keep_exact_unknown(defect):
    value=bundle();action=new.old.ReceiverBoundRequestContext(value).actions()[8]
    if defect=='extra_empty':value['trays']['X']={**value['trays']['E'],'tray_id':'X'}
    elif defect=='P_returns':value['jobs']['blocker']['destination']=1
    elif defect=='new_edge':value['contract']['edge_records'].append([9,1,.01,1.])
    elif defect=='permission':value['contract']['node_contracts'][0]['allow_export']=not value['contract']['node_contracts'][0]['allow_export']
    elif defect=='age':value['now']+=.01
    elif defect=='pending':value['owner_pending_tray_requests']=['request']
    elif defect=='receiver':value['jobs']['receiver']['origin']=7
    elif defect=='extra_job':value['jobs']['other']=deepcopy(value['jobs']['receiver'])
    else:
        class Custom(dict):pass
        value=Custom(value)
    if defect=='custom':
        with pytest.raises(TypeError):new.ReceiverVectorRequestContext(value)
        return
    a=new.old.ReceiverBoundRequestContext(value);b=new.ReceiverVectorRequestContext(value)
    assert ordered(a.baseline())==ordered(b.baseline())
    assert ordered(a.predict(action))==ordered(b.predict(action))
    assert b.describe()['counts']['candidate_lower_bound_rejections']==0


@pytest.mark.parametrize('defect',['bool','extra','missing','window','nan'])
def test_candidate_guard_unchanged(defect):
    a=new.old.ReceiverBoundRequestContext(bundle());b=new.ReceiverVectorRequestContext(bundle());action=a.actions()[8]
    if defect=='bool':action['empty_departure']=True
    elif defect=='extra':action['extra']=1
    elif defect=='missing':action.pop('initial_action')
    elif defect=='window':action['empty_departure']+=.001
    else:action['return_delay']=float('nan')
    assert ordered(a.predict(action))==ordered(b.predict(action))
    assert b.describe()['counts']['candidate_lower_bound_rejections']==0


def test_unknown_baseline_cannot_gain_reference(monkeypatch):
    monkeypatch.setattr(new.old.combined.proof,'_reference_times',lambda result:None)
    a=new.old.ReceiverBoundRequestContext(bundle());b=new.ReceiverVectorRequestContext(bundle())
    assert object.__getattribute__(b,'_ReceiverVectorRequestContext__completion_vector') is None
    assert ordered(a.predict(a.actions()[8]))==ordered(b.predict(b.actions()[8]))


def test_source_and_callable_identity_guards(monkeypatch):
    monkeypatch.setattr(new,'EXPECTED_OLD','0'*64)
    with pytest.raises(ValueError,match='unreviewed_source'):new.ReceiverVectorRequestContext(bundle())
    monkeypatch.undo()
    monkeypatch.setattr(new.old.ReceiverBoundRequestContext,'predict',lambda *args:None)
    with pytest.raises(ValueError,match='unreviewed_source'):new.ReceiverVectorRequestContext(bundle())
