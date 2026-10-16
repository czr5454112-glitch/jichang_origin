"""Saved-only root readback. No project imports, repeated tests or C calls."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import xml.etree.ElementTree as ET
START=time.perf_counter()
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/bcdp2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(n):return json.loads((OUT/n).read_bytes())
def require(ok,why):
    if not ok:raise ValueError('bcdp2_root:'+why)
pins={'plan.json':'3cec8d06031be2dc7b41af3f5fca6c9e7e3ec43399ef0bda071e7d8ac0ee4c22',
 'receipt.json':'f4f880adc9d659a2f0cc9f96ab40fac6b85b554ac837fe86fd6c4cd1918ef285',
 'worker.json':'e5a1bf5cb9f1d6768f9ddc710d25ee26fda0148f7073119e52fafb6933a527a9',
 'tests.xml':'8af4bb8722c07cc4b8946965eff3f66395310125423d7cab9b677d4d618fe180',
 'bounded_execution.json':'5c4978d4a3f6e7da216b2ad8f6b5eeb80ce892110f3fe9b9c562d165976526d8',
 'external_application_wall.json':'143ace300e68d8f9e6a8f4fe2a0b5f6dd438229a6d1ea4668508af5cdf9f66bd',
 'parent_stages.jsonl':'0874531d2ca74f9a33f1c8dbb8b9fb9d59f4f2fd047bb8c8b4ab99916e04d537',
 'worker_stages.jsonl':'dd07b05b164e191118267415713fa175591271396e630b18c82823fb940b2bf3'}
for n,d in pins.items():require(sha(OUT/n)==d,'pin:'+n)
p,r,w,b,e=map(read,('plan.json','receipt.json','worker.json','bounded_execution.json','external_application_wall.json'))
require(p['schema']==r['schema']=='g31.bridge.saved_C_digest.driver_pure.v2','schema')
require(p['tests']==r['tests']==r['expected_tests']==27 and p['limit_seconds']==120,'denominator')
require(r['status']=='passed_synthetic_routing' and r['bad_tests']==[] and r['error'] is None,'result')
require(type(w['pytest_exitcode']) is int and w['pytest_exitcode']==0 and w['source_entry_exit_exact'] is True,'worker')
require(r['process']==b and b['status']=='exited' and type(b['exitcode']) is int and b['exitcode']==0
    and b['windows_job_kill_on_close'] is True and b['child_released_only_after_job_assignment'] is True,'owned')
require(r['XML_sha256']==pins['tests.xml'] and r['worker_sha256']==pins['worker.json'],'inner_refs')
cases=ET.parse(OUT/'tests.xml').getroot().findall('.//testcase')
require(len(cases)==27 and not any(n.tag in ('failure','error','skipped') for c in cases for n in c),'XML27')
for record in (r,w):require(all(type(record[k]) is int and record[k]==0 for k in ('native_calls','extension_loads','actual_fixture_reads')),'no_actual_declaration')
require(r['benchmark_executed'] is False and e['expected_tests']==27,'no_benchmark')
require(e['schema']=='g31.bridge.saved_C_digest.driver_pure_external.v1' and e['started'] is True
    and e['accepted_launch_and_clock'] is True and type(e['exit_code']) is int and e['exit_code']==0
    and e['outer_timeout'] is False and e['exception'] is None and e['cleanup_errors']==[]
    and e['source_changed']==e['missing_outputs']==[],'external')
f,t=e['tick_frequency'],e['elapsed_ticks']
require(type(f) is int and f>0 and type(t) is int and 0<=t<=120*f==e['budget_ticks']
    and e['end_ticks']-e['start_ticks']==t and e['whole_python_seconds']==t/f,'typed_clock')
command=[e['python']['path'],'-m','scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_driver_pure_v2','--output',str(OUT)]
require(e['command']==command and p['command']==command+['--worker','--admission',p['admission']]
    and e['working_directory']==str(ROOT),'commands')
require(e['environment_explicit']=={'PYTHONPATH':'src;.;tests','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8'},'env')
for kind in ('python','wrapper'):require(sha(e[kind]['path'])==e[kind]['sha256'],'identity:'+kind)
require(e['python']['sha256']=='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
    and e['wrapper']['sha256']=='1943b29c396375d216d7885fb68080136b836a66df9b56938f3cba1e0c9f480e','fixed_launch')
for name,digest in e['output_sha256'].items():require(sha(OUT/name)==digest,'external_output')
sources=p['source_sha256'];require(len(sources)==138 and sources==r['source_sha256'],'sources138')
targets=set();maxpath=0
for n,d in sources.items():
    rel=PurePosixPath(n);current=(ROOT/n).resolve();saved=(OUT/'source'/n).resolve()
    require(not rel.is_absolute() and rel.as_posix()==n and '..' not in rel.parts,'canonical')
    require(current.is_relative_to(ROOT) and saved.is_relative_to(OUT/'source') and current!=saved
        and saved not in targets and len(str(saved))<260,'archive')
    targets.add(saved);maxpath=max(maxpath,len(str(saved)))
    require(sha(current)==sha(saved)==d,'current_archive:'+n)
for n,d in e['source_sha256'].items():require(sources[n]==d,'outer_source')
for loaded in (r['loaded_parent_exit'],w['loaded_entry'],w['loaded_exit']):
    require(len(loaded)==len(set(loaded)) and set(loaded)<=set(sources),'loaded')
journals={};source_spans=[]
for name,count in (('parent_stages.jsonl',20),('worker_stages.jsonl',10)):
    raw=(OUT/name).read_bytes();require(raw.endswith(b'\n'),'complete_lines')
    rows=[json.loads(line) for line in raw.splitlines()];require(len(rows)==count,'stage_count')
    stack=[];last=-1
    for i,row in enumerate(rows):
        require(set(row)=={'sequence','phase','event','at_ns'} and type(row['sequence']) is int
            and row['sequence']==i and type(row['at_ns']) is int and row['at_ns']>=last,'stage_typed')
        last=row['at_ns']
        if row['event']=='started':stack.append(row)
        else:
            require(row['event']=='completed' and stack and stack[-1]['phase']==row['phase'],'balanced_stage')
            start=stack.pop()
            if row['phase']=='source_union':source_spans.append((row['at_ns']-start['at_ns'])/1e9)
    require(not stack,'complete_stage');journals[name]=count
require(len(source_spans)==5,'five_collection_calls')
record={'schema':'g31.bcdp2.root_saved_review.v1','status':'passed_saved_only_readback','pins':pins,
    'tests':27,'sources':138,'whole_python_seconds':t/f,'max_archive_path':maxpath,
    'journals':journals,'five_source_collection_nested_wall_seconds':source_spans,
    'scope':'Complete saved XML/owned/outer/source/archive/loaded/journal bindings. Stage spans are nested wall, not CPU. No test rerun, C/native/raw/model or all-day/100ms acceptance.',
    'saved_review_seconds':time.perf_counter()-START}
target=OUT/'root_saved_review_001.json'
with target.open('x',encoding='utf8') as stream:json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'tests':27,'sources':138,'whole_seconds':t/f}))
