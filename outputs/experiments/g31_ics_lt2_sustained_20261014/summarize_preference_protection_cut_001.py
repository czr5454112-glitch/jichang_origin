from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
TARGET=OUT/'preference_protection_cut_tests_003'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
report=read(TARGET/'worker/report.json');plan=read(TARGET/'worker/plan.json')
assert report['status']=='passed_pure_cut_guard_tests' and report['source_changed']==report['input_changed']==[]
for name,digest in plan['source_sha256'].items():
    assert sha(ROOT/name)==digest==sha(TARGET/'worker/source'/name),name
for name,digest in plan['input_sha256'].items():assert sha(name)==digest,name
suites=ET.parse(TARGET/'worker/tests.xml').getroot().findall('testsuite')
counts={k:sum(int(s.attrib[k]) for s in suites) for k in ('tests','failures','errors','skipped')}
assert counts=={'tests':40,'failures':0,'errors':0,'skipped':0}
rows=report['six_actual_supplied_input_rows'];methods=report['six_cases_four_method_rows']
assert len(rows)==6 and len(methods)==24 and all(r['exact_query_sequence_and_selected_full_output'] for r in methods)
value={'status':'passed_conditional_prefix_protection_cut_logic_only','native_executions':0,
 'source_sha256':{name:digest for name,digest in plan['source_sha256'].items() if 'protection_cut' in name},
 'full_executed_source_archive_count':len(plan['source_sha256']),
 'tests':counts,'external_wall':read(TARGET/'external_wall.json'),
 'actual_supplied_data_cases':[{'case':r['case'],**r['counts'],
    'first_violating_jobs':sorted({w['job'] for w in r['witnesses']})} for r in rows],
 'candidate_count':192,'conditional_prefix_rejections':sum(r['counts']['candidate_prefix_rejections'] for r in rows),
 'nonpruned_full_outputs_exact':sum(r['counts']['candidate_full_predictions'] for r in rows),
 'all_rejections_have_exact_full_run_strict_violation':True,
 'method_comparisons':24,'all_method_query_orders_evaluation_counts_selected_actions_and_full_selected_outputs_exact':True,
 'candidate_budget':32,'cut_consumes_candidate_evaluation':True,
 'failure_history':{'001':'33 passed/1 failed: test read prior plan inputs_sha256 rather than its actual singular input_sha256. Production cut unchanged; evidence retained.',
                    '002':'34 passed, then source identity wrapper and method-query differential tests added for003.'},
 'scope':['Only source-pinned restricted initial supplied-data model with isolated same-bundle complete5job reference.',
          'Strict > without epsilon; missing/unknown/nonfinite reference disables cut; original dynamic/action guards remain.',
          'Cut returns empty completion and unknown_unexecuted suffix plus a model counterexample, not a full prediction.',
          'Current old search keeps partial prediction eligibility unknown; it is never selected and query/choice parity is tested.',
          'No prefix sharing, cross-request cache, native call, changed physical contract, performance measurement or100ms certificate.'],
 'structural_initialization_note':'Repeated inspect/AST proof is algorithm-build/evidence work, not fresh owner information. A future explicitly initialized source-pinned process may build code once, keep all dynamic guards per request, and report cold-total and warm-service separately. Existing measured costs cannot be subtracted retroactively; the prior whole-closure-per-request factory remains a measured negative.',
 'evidence_sha256':{str(p.relative_to(OUT)):sha(p) for p in (TARGET/'worker/report.json',TARGET/'worker/plan.json',TARGET/'worker/tests.xml',TARGET/'receipt.json',TARGET/'external_wall.json')},
 'summary_source_sha256':sha(__file__)}
path=OUT/'preference_protection_cut_summary_001.json'
with path.open('x',encoding='utf8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'path':str(path),'sha256':sha(path),'cuts':value['conditional_prefix_rejections'],'exact_full':value['nonpruned_full_outputs_exact']}))
