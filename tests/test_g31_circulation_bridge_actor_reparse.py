import ast
import builtins
from copy import deepcopy
import gzip
import inspect
import io
import json
import pytest
from scripts.experiments.g31_ics_circulation import measure_bridge_actor_reparse as m


def text_row(value):
    return json.dumps({'ordinal':27210,'endpoint':'observe_protocol','args':['A'],
        'kwargs':{},'result':value}, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize('value', [None, True, 1, 1.0, -0.0, '汉字🌍',
    {'b':[1.25,False,None],'a':[]}, [[], {'x':-0.0}, 1e-200]])
def test_full_typed_result_and_isolation(value):
    text=text_row(value); row=m.decoded_text(text); before=deepcopy(row)
    a=m.actor_copy(row,text); b=m.actor_reparse(row,text)
    assert m.frozen.exact(a,b) and m.frozen.exact(row,before)
    assert m.frozen.decoded_tree(a).isdisjoint(m.frozen.decoded_tree(row))
    assert m.frozen.decoded_tree(b).isdisjoint(m.frozen.decoded_tree(row))


@pytest.mark.parametrize('a,b', [(True,1),(1,1.0),(0.0,-0.0),
    ({'a':1,'b':2},{'b':2,'a':1}),([1,2],[2,1])])
def test_oracle_cannot_hide_type_order_or_float_bits(a,b):
    row=m.decoded_text(text_row(a)); other=m.actor_reparse(row,text_row(b))
    assert not m.frozen.exact(row['result'],other)


@pytest.mark.parametrize('text', ['{"result":NaN}', '{"result":Infinity}',
    '{"result":"\\ud800"}', '{"result":{"\\udfff":0}}', '[]', '{"error":"x","result":0}'])
def test_finite_builtin_success_domain_only(text):
    with pytest.raises(ValueError):m.decoded_text(text)


def test_default_decoder_duplicate_keys_not_silently_redefined():
    text='{"ordinal":27210,"endpoint":"x","result":{"a":1,"b":0,"a":2}}'
    row=m.decoded_text(text)
    original=json.load(io.StringIO(text))
    assert m.frozen.exact(row,original)
    assert list(row['result'])==['a','b'] and row['result']['a']==2


def test_text_bound_and_exact_builtin(monkeypatch):
    text=text_row(0); monkeypatch.setattr(m,'MAX_TEXT',len(text)-1)
    with pytest.raises(ValueError,match='actor_text_domain'):m.decoded_text(text)
    class Text(str):pass
    with pytest.raises(ValueError,match='actor_text_domain'):m.decoded_text(Text('x'))


def test_same_default_gzip_text_and_load_semantics(tmp_path):
    path=tmp_path/'row.gz'
    raw=b'{\r\n"ordinal":27210,"endpoint":"x","result":{"n":-0.0,"s":"\\ud83c\\udf0d"}\r\n}'
    with gzip.open(path,'wb') as f:f.write(raw)
    with gzip.open(path,'rt',encoding='utf8') as f:original=json.load(f)
    row,text=m.load_fixture(path,{'ordinal':27210,'endpoint':'x'})
    assert '\r' not in text
    assert m.frozen.exact(row,original)
    assert m.frozen.exact(m.actor_reparse(row,text),original['result'])


@pytest.mark.parametrize('changed', [{'ordinal':True,'endpoint':'x'}, {'ordinal':27210,'endpoint':'foreign'}])
def test_first_identity_rejects_wrong_row(tmp_path,changed):
    path=tmp_path/'row.gz'
    with gzip.open(path,'wt',encoding='utf8') as f:json.dump({**changed,'result':{}},f)
    with pytest.raises(ValueError,match='actor_first_identity'):
        m.load_fixture(path,{'ordinal':27210,'endpoint':'x'})


def test_second_parse_uses_only_existing_text_without_encode_or_reads(monkeypatch):
    text=text_row({'x':[1]}); row=m.decoded_text(text)
    def forbidden(*a,**kw):raise AssertionError('new read/encode forbidden')
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(gzip,'open',forbidden)
    monkeypatch.setattr(json,'dumps',forbidden)
    assert m.actor_reparse(row,text)=={'x':[1]}


def test_multiple_actor_results_do_not_share_containers():
    text=text_row({'x':[{'y':[]}]} ); row=m.decoded_text(text)
    a=m.actor_reparse(row,text); b=m.actor_reparse(row,text)
    ids=[m.frozen.decoded_tree(x) for x in (row,a,b)]
    assert all(ids[i].isdisjoint(ids[j]) for i in range(3) for j in range(i))
    a['x'][0]['y'].append(9)
    assert b['x'][0]['y']==row['result']['x'][0]['y']==[]


@pytest.mark.parametrize('kind',['alias','cycle','custom'])
def test_nondecoded_domain_is_not_an_alias_graph_equivalence(kind):
    shared=[]
    if kind=='alias':value=[shared,shared]
    elif kind=='cycle':shared.append(shared);value=shared
    else:
        class Custom(dict):pass
        value=Custom()
    with pytest.raises(ValueError):m.frozen.decoded_tree(value)


def records():
    result=[]
    for batch,arm in enumerate(m.ARMS):
        for index in range(16):
            start=len(result)*20
            result.append({'batch':batch,'arm':arm,'index':index,'ordinal':27210+index%8,
                'side':'old' if index<8 else 'new','started_ns':start,'finished_ns':start+10,
                'wall_ns':10,'cpu_ns':2,'result_sha256':'a'*64,'mutable_disjoint':True})
    return result


def test_exact_denominator_64_and_baseline_counts():
    result=m.check_records(records(),['a'*64]*16)
    assert result['A']['batch_ms']==[.00016,.00016]
    assert result['B']['batch_ms']==[.00016,.00016]
    assert m.COUNTS=={'input_files':16,'batches':4,'actor_copies':64,
        'A_deepcopies':32,'B_second_parses':32,'first_observer_parses':16}


@pytest.mark.parametrize('case',['omission','reorder','boolclock','floatclock','clockoverlap',
    'wronghash','alias','side','extra'])
def test_record_counterexamples_fail_closed(case):
    rows=records()
    if case=='omission':rows.pop()
    elif case=='reorder':rows[0],rows[1]=rows[1],rows[0]
    elif case=='boolclock':rows[0]['started_ns']=False
    elif case=='floatclock':rows[0]['cpu_ns']=2.0
    elif case=='clockoverlap':rows[1]['started_ns']=0;rows[1]['wall_ns']=30
    elif case=='wronghash':rows[0]['result_sha256']='b'*64
    elif case=='alias':rows[0]['mutable_disjoint']=False
    elif case=='side':rows[0]['side']='new'
    else:rows[0]['status']='complete'
    with pytest.raises(ValueError):m.check_records(rows,['a'*64]*16)


def saved():
    files=[{'side':'old' if i<8 else 'new','ordinal':27210+i%8,'sha256':'c'*64} for i in range(16)]
    rows=records();digest=['a'*64]*16
    value={'schema':m.SCHEMA,'status':'passed_fixed_saved_actor_parse_diagnostic_only',
        'plan_sha256':'d'*64,'counts':dict(m.COUNTS),'source_changed':[],
        'native_calls':0,'policy_replays':0,'full_audit_accepted':False,
        'first_decompression_parse_domain_ns':12,'worker_before_final_export_ns':9999,
        'records':rows,'result_digests':digest,'summary':m.check_records(rows,digest),
        'input_texts':[{'side':x['side'],'ordinal':x['ordinal'],'gzip_sha256':x['sha256'],
            'decoded_text_sha256':'e'*64,'decoded_characters':10} for x in files]}
    return value,{'files':files}


@pytest.mark.parametrize('case',['firstclockbool','countbool','textomit','textordinalbool','texthash','falseaudit'])
def test_saved_scope_cannot_omit_first_decode_or_upgrade_audit(case):
    value,plan=saved()
    if case=='firstclockbool':value['first_decompression_parse_domain_ns']=True
    elif case=='countbool':value['counts']['input_files']=True
    elif case=='textomit':value['input_texts'].pop()
    elif case=='textordinalbool':value['input_texts'][0]['ordinal']=True
    elif case=='texthash':value['input_texts'][0]['decoded_text_sha256']='z'*64
    else:value['full_audit_accepted']=True
    with pytest.raises(ValueError):m.check_saved_result(value,plan,'d'*64)


def test_saved_positive_is_only_kernel_evidence():
    value,plan=saved();m.check_saved_result(value,plan,'d'*64)
    assert value['full_audit_accepted'] is False


@pytest.mark.parametrize('digests',[['a'*64]*15,['z'*64]*16])
def test_missing_or_malformed_digest_denominator(digests):
    with pytest.raises(ValueError,match='actor_digest_domain'):m.check_records(records(),digests)


def test_second_parser_exact_standard_expression_no_hooks():
    tree=ast.parse(inspect.getsource(m.actor_reparse))
    expression=tree.body[0].body[-1].value
    assert ast.dump(expression)==ast.dump(ast.parse("json.loads(text)['result']",mode='eval').body)
    assert m._LOADS is json.loads and m._LOAD is json.load


def test_second_parse_exception_does_not_mutate_observer():
    row=m.decoded_text(text_row({'a':[1]}));before=deepcopy(row)
    with pytest.raises(json.JSONDecodeError):m.actor_reparse(row,'{"result":')
    assert m.frozen.exact(row,before)
