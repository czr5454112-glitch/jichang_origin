"""Report every boundary-slice branch; do not alter the frozen selection."""
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from time import process_time,perf_counter
from collections import Counter
import gzip,json,traceback

HERE=Path(__file__).parent
EXPERIMENT=HERE/'experiment'
OUTPUT=HERE/'results'


def main():
    cpu,wall=process_time(),perf_counter()
    if OUTPUT.exists():raise FileExistsError(OUTPUT)
    OUTPUT.mkdir()
    bindings={};checks=[]
    def read(path,expected=None):
        raw=path.read_bytes();actual=sha256(raw).hexdigest()
        if expected is not None and actual!=expected:raise ValueError('SHA mismatch '+str(path))
        bindings[str(path.resolve())]=actual
        return json.loads((gzip.decompress(raw) if path.suffix=='.gz' else raw).decode('utf-8-sig'))
    def check(name,good):
        checks.append({'name':name,'okay':bool(good)})
        if not good:raise ValueError(name)
    try:
        prep=read(EXPERIMENT/'preparation_manifest.json')
        protocol=read(EXPERIMENT/'protocol.json',prep['protocol.json'])
        full_rows=read(EXPERIMENT/'full_rows.json',prep['full_rows.json'])
        summaries={};raws={}
        for stage,count in(('bridge',2),('full',24)):
            manifest=read(EXPERIMENT/stage/'manifest.json')
            for name,expected in manifest.items():
                path=EXPERIMENT/name
                raw=path.read_bytes();check('manifest:'+name,sha256(raw).hexdigest()==expected)
                bindings[str(path.resolve())]=expected
            summary=read(EXPERIMENT/stage/'summary.json',manifest[str(Path(stage)/'summary.json')])
            summaries[stage]=summary
            check(stage+':full_denominator',len(summary['rows'])==summary['planned_physical_calls']==count)
            check(stage+':immutable',summary['source_input_test_unchanged'])
            check(stage+':no_memo',summary['memo_aliases']==0)
            for receipt in summary['rows']:
                check(receipt['request_key']+':quiet',receipt['status']=='controller_quiescent')
                raw=read(EXPERIMENT/receipt['file'],receipt['sha256'])
                check(receipt['request_key']+':unmodified_nonfuture',all(raw['future_replacement_binding']['unchanged'].values()))
                check(receipt['request_key']+':instant_trace',bool(raw['instant_physical_tick_trace']))
                check(receipt['request_key']+':complete_tasks',all(r['observed'] and r['completed_at'] is not None for r in raw['evaluation_ledger']))
                if stage=='full':raws[receipt['request_key']]=raw
        check('exact_full_identity',set(raws)=={r['request_key'] for r in full_rows})
        states=[]
        for selected in protocol['selected_details']:
            key=selected['state_key'];subset=[r for r in full_rows if r['state_key']==key]
            check(key+':12_grid',len(subset)==12 and {(r['future_index'],r['candidate']) for r in subset}=={(f,c) for f in range(3) for c in range(4)})
            futures=[];weighted=[Fraction(0) for _ in range(4)]
            for future in range(3):
                candidates=[]
                for request in sorted((r for r in subset if r['future_index']==future),key=lambda r:r['candidate']):
                    raw=raws[request['request_key']];ledger=raw['evaluation_ledger'];cost=raw['result']['total_cost']
                    weighted[request['candidate']]+=Fraction(str(cost))*Fraction(request['support_mass'],17)
                    candidates.append({'candidate':request['candidate'],'total_cost':cost,
                        'cost_components':raw['result']['cost_components'],'stopped_at':raw['stopped_at'],
                        'task_count':len(ledger),'on_time':sum(r['completed_at']<=r['deadline'] for r in ledger),
                        'protected_count':sum(r['protected'] for r in ledger),
                        'protected_on_time':sum(r['protected'] and r['completed_at']<=r['deadline'] for r in ledger),
                        'search_calls':raw['search_calls'],'search_work':raw['search_work'],
                        'raw_file':str(EXPERIMENT/'full'/(request['physical_key']+'.json.gz'))})
                best=min(c['total_cost'] for c in candidates)
                futures.append({'future_index':future,'name':('cancel','j0','j+2')[future],
                    'probability_fraction':('3/17','7/17','7/17')[future],
                    'candidates':candidates,'optimal_candidates':[c['candidate'] for c in candidates if abs(c['total_cost']-best)<=1e-9],
                    'actual_choice_gap':candidates[selected['actual_chosen_index']]['total_cost']-best})
            best=min(weighted)
            states.append({'state_key':key,'time':selected['time'],'target':selected['target'],
                'actual_chosen_index':selected['actual_chosen_index'],'candidate_count':4,'futures':futures,
                'weighted_costs':[float(v) for v in weighted],'weighted_cost_fractions':[str(v) for v in weighted],
                'weighted_optimal_candidates':[i for i,v in enumerate(weighted) if abs(float(v-best))<=1e-9],
                'weighted_actual_choice_gap':float(weighted[selected['actual_chosen_index']]-best)})
        for path,expected in bindings.items():check('unchanged:'+path,sha256(Path(path).read_bytes()).hexdigest()==expected)
        result={'schema':'ics_boundary_slice_all24_analysis_v1','states':states,'missing_cells':protocol['missing_cells'],
            'counts':{'bridges':2,'full_physical':24,'selected_states':2,'missing_cells':4,'memo':0},
            'checks':checks,'failed_checks':sum(not r['okay'] for r in checks),'bound_inputs':bindings,
            'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
            'resource_scope':'Pure raw read/hash/check/finite weighted arithmetic after imports, before report/JSON/manifest writes; embedded physical costs are not additional work.',
            'physical_calls':0,'scope':'Exact finite one-target conditional slice with all other pending tasks fixed; separate from main joint future law; statewise gaps are not additive deployment gains.'}
        (OUTPUT/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        lines=['# Conditional-boundary mechanism supplement','',
            'Both original-future actual-choice bridges reproduced the frozen Round7 branches exactly. All 24 separately executed support × candidate branches reached controller quiescence with every task observed and complete. No memo reuse or bridge deduction.',
            '', '| State | Support | Mass | c0 J | c1 J | c2 J | c3 J | Optimal candidates | Actual-choice gap |',
            '|---|---|---|---:|---:|---:|---:|---|---:|']
        for state in states:
            for future in state['futures']:
                lines.append('| '+' | '.join(map(str,[state['state_key'],future['name'],future['probability_fraction'],
                    *[c['total_cost'] for c in future['candidates']],future['optimal_candidates'],future['actual_choice_gap']]))+' |')
            lines.append('| '+' | '.join(map(str,[state['state_key'],'finite weighted mean','1',*state['weighted_costs'],
                state['weighted_optimal_candidates'],state['weighted_actual_choice_gap']]))+' |')
        lines+=['','The only varying task has original arrival-now 1 or 2, so jitter −2 is inconsistent with its absence at the real loaded cursor. Cancellation, unchanged and +2 carry exact masses 3/17, 7/17 and 7/17. Deadline shifts with arrival. All other pending tasks, protected entries, public state, original forecasts/publications, controller, cursor and slow clock remain fixed.',
            '', 'This is an exhaustive finite single-task mechanism slice over two real states; four scene × role cells remain missing. It does not extend the main 64-draw future law, add independent business samples, calibrate uncertainty or establish deployment gains. Costs from different states must not be summed as regret savings.',
            '',f"Pure analysis CPU {result['cpu_seconds']:.6f}s / wall {result['wall_seconds']:.6f}s; {len(checks)} checks / {result['failed_checks']} errors. Full per-branch service/protection/search metrics and file SHA bindings are in analysis.json."]
        (OUTPUT/'MECHANISM.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
        (OUTPUT/'analyze.py').write_bytes(Path(__file__).read_bytes())
        (OUTPUT/'manifest.json').write_text(json.dumps({p.name:sha256(p.read_bytes()).hexdigest() for p in OUTPUT.iterdir() if p.is_file()},indent=2),encoding='utf8')
        print(json.dumps({'states':[{k:s[k] for k in('state_key','weighted_costs','weighted_optimal_candidates','weighted_actual_choice_gap')} for s in states],
            'checks':len(checks),'failed_checks':result['failed_checks'],'cpu_seconds':result['cpu_seconds']}))
    except Exception as error:
        (OUTPUT/'failure.json').write_text(json.dumps({'failure':{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()},
            'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,'physical_calls':0,'checks':checks},indent=2),encoding='utf8')
        raise


if __name__=='__main__':main()
