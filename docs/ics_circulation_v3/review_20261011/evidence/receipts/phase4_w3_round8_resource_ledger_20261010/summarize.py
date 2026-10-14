"""Round8 only: additive CPU intervals, no nested cost or parallel wall sums."""
from pathlib import Path
from hashlib import sha256
from time import process_time,perf_counter
import argparse,json

ROOT=next(p for p in Path(__file__).resolve().parents if(p/'scripts/experiments/ics_circulation_v3').is_dir())
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
HERE=Path(__file__).parent
PERF=BASE/'phase4_w3_terminal_screen_performance_20261010'
STABILITY=BASE/'phase4_w3_same_zone_stability_20261010'
REVIEW=BASE/'phase4_w3_round8_independent_review_20261010'


def main(output,required):
    cpu,wall=process_time(),perf_counter();output=Path(output)
    summarizer_bytes=Path(__file__).read_bytes();summarizer_sha=sha256(summarizer_bytes).hexdigest()
    if output.exists():raise FileExistsError(output)
    for name in required:
        if not(BASE/name).is_file():raise FileNotFoundError(name)
    rows=[];bindings={};seen=set();checks=[]
    def read(path):
        b=path.read_bytes();bindings[str(path.relative_to(ROOT))]=sha256(b).hexdigest();return json.loads(b.decode('utf-8-sig'))
    def part(scope,value,field,quality='measured_interval_lower_bound'):
        return {'scope':scope,'cpu_seconds':value,'source_field':field,'quality':'unknown'if value is None else quality}
    def add(identity,path,parts,status='complete',wall_seconds=None,notes=None,counts=None):
        if identity in {r['id']for r in rows}:raise ValueError('duplicate invocation '+identity)
        rows.append({'id':identity,'source':None if path is None else str(path.relative_to(ROOT)),
            'status':status,'cpu_components':parts,'individual_wall_seconds':wall_seconds,'notes':notes or [],'counts':counts or {}})
        if path is not None:seen.add(path)
    def failed(s):
        return any(bool(s.get(k))for k in('exit_code','failed_checks','failures','errors','failure'))or s.get('status')in('failed','failed_tests')
    def direct(path,ck='cpu_seconds',wk='wall_seconds',identity=None):
        if path in seen:return
        s=read(path)
        value=s.get(ck)
        add(identity or str(path.relative_to(BASE)),path,[part('direct invocation interval',value,ck)],
            status='failed'if failed(s)else'complete',wall_seconds=s.get(wk,s.get('tool_wall_seconds')),
            notes=[s.get('resource_scope',s.get('scope','Timing excludes unasserted bootstrap and final output writes.')),
                'Other embedded CPU values are nested metadata and are not added. Measured zero is clock resolution, not no work.'],
            counts={k:s[k]for k in('tests','passed','failed','fixture_errors','input_checks','failed_checks','physical_simulations','new_original_network_physical_calls')if k in s})
        if failed(s):rows[-1]['failure_evidence']={k:s[k]for k in('exit_code','failed_checks','error','errors','failures','cause','failure','status')if s.get(k)}
    for path,ck,wk in ((PERF/'protocol.json','prepare_cpu_seconds','prepare_wall_seconds'),
                      (STABILITY/'protocol.json','preparation_cpu_seconds','preparation_wall_seconds')):
        if path.exists():direct(path,ck,wk)
    for stage,count in(('pilot',12),('formal',108)):
        path=PERF/stage/'summary.json'
        if not path.exists():
            add('performance_'+stage,path,[part('workers and parent',None,'pending')],status='pending',counts={'planned_physical_calls':count});continue
        s=read(path);arms=[a for pair in s['pairs']for a in pair['arms'].values()]
        recorded=sum(a.get('process_cpu_seconds')or 0 for a in arms)
        checks+=[{'name':'performance_'+stage+'_cpu','okay':abs(recorded-s['worker_final_process_cpu_seconds_sum'])<1e-8},
                 {'name':'performance_'+stage+'_grid','okay':len(arms)==count==s['planned_physical_calls']}]
        parts=[part('fresh child full OS process lifetime',recorded,'worker_final_process_cpu_seconds_sum','complete_child_process_lifetimes'),
               part('coordinator measured interval',s['parent_cpu_seconds'],'parent_cpu_seconds')]
        if s['unknown_final_process_cpu_arms']:parts.append(part('unrecorded launched process CPU',None,'unknown_final_process_cpu_arms'))
        add('performance_'+stage,path,parts,status='complete'if s['all_exact']else'failed',wall_seconds=s['wall_makespan_seconds'],
            counts={k:s[k]for k in('planned_physical_calls','physical_calls_recorded','unknown_final_process_cpu_arms')},
            notes=['Algorithm/search/screen/observer/run_cycle/child invocation/import CPU is nested inside complete OS CPU. Do not add again.',
                   'Pilot and formal independently repeat identities. Two timing blocks do not create new business samples. Parent comparisons are inside coordinator CPU.',
                   'Individual child launch wall and block makespans overlap; global elapsed time is not their sum.'])
        rows[-1]['max_single_child_lifetime_peak_working_set_bytes']=max((a.get('receipt')or{}).get('memory',{}).get('peak_working_set_bytes')or 0 for a in arms)
    for stage in('bridge','pilot','full'):
        path=STABILITY/stage/'summary.json'
        if not path.exists():
            add('stability_'+stage,path,[part('workers and parent',None,'pending')],status='pending');continue
        s=read(path);worker=s['case_invocation_cpu_seconds_recorded'];results=s.get('rows',s.get('results',[]))
        if results:checks.append({'name':'stability_'+stage+'_cpu','okay':abs(sum(r.get('invocation_cpu_seconds')or 0 for r in results)-worker)<1e-8})
        checks.append({'name':'stability_'+stage+'_full_denominator','okay':
            len(results)==s['planned_unique_physical']=={'bridge':17,'pilot':24,'full':2468}[stage]and
            sum(s['status_counts'].values())==len(results)and
            sum(s['logical_status_counts'].values())==s['planned_logical_requests']and
            s['planned_logical_requests']==s['planned_unique_physical']+s['memo_aliases']})
        add('stability_'+stage,path,[part('unique physical worker intervals',worker,'case_invocation_cpu_seconds_recorded'),
            part('coordinator interval',s['parent_cpu_seconds'],'parent_cpu_seconds')],
            status='complete'if(s.get('source_input_test_unchanged')and
                set(s.get('status_counts',{}))=={'controller_quiescent'}and
                set(s.get('logical_status_counts',{}))=={'controller_quiescent'})else'failed_or_incomplete',
            wall_seconds=s['wall_makespan_seconds'],
            counts={k:s[k]for k in('planned_logical_requests','planned_unique_physical','actual_physical_calls_recorded','unknown_physical_call_statuses','complete_resource_accounting','memo_aliases','status_counts','logical_status_counts')if k in s},
            notes=[s.get('resource_scope','Worker imports/startup/initializer and final receipt output outside intervals are unknown.'),
                   'Unique physical computations only. Logical aliases are memo reuse, not new work. Bridge/pilot/formal independent invocations remain separate.',
                   'Nested cycle/search/continuation timing is never added. Concurrent stage makespans never sum to global wall.'])
        if not s.get('complete_resource_accounting',False):rows[-1]['cpu_components'].append(part('unrecorded workers',None,'incomplete_resource_accounting'))
        final_path=STABILITY/'os_cpu_monitor_final.json'
        if stage=='full'and final_path.exists():
            os_final=read(final_path);start=read(STABILITY/'os_cpu_monitor_start.json')
            requested=STABILITY/'full/requested_rows.json';protocol=STABILITY/'protocol.json'
            read(requested);read(protocol)
            monitor=STABILITY/'observe_os_cpu.py'
            bindings[str(monitor.relative_to(ROOT))]=sha256(monitor.read_bytes()).hexdigest()
            identities=os_final.get('identities',{});finals=os_final.get('final_lifetime_times',{})
            expected_pids={str(start['parent_pid']),*(str(p)for p in start['worker_pids'])}
            actual_pids={r.get('memory',{}).get('pid')for r in results}
            identity_ok=(start['full_requests_sha256']==bindings[str(requested.relative_to(ROOT))]and
                start['full_protocol_sha256']==bindings[str(protocol.relative_to(ROOT))]and
                start['script_sha256']==os_final['source_sha256']==bindings[str(monitor.relative_to(ROOT))]and
                identities==start['identities']and set(identities)==set(finals)==expected_pids and
                actual_pids==set(start['worker_pids'])and len(results)==2468 and
                all(r.get('actual_physical_call')is True for r in results)and
                all(v is not None and v['exit_code']==0 and
                    v['creation_filetime_100ns']==identities[pid]['initial_lifetime_times']['creation_filetime_100ns']
                    for pid,v in finals.items())and
                not os_final.get('failures')and not os_final.get('unexpected_child_observations'))
            replace_ok=os_final.get('complete_bound_parent_and_worker_lifetimes')and identity_ok
            checks.append({'name':'stability_full_OS_complete_identity_binding',
                'okay':identity_ok if os_final.get('complete_bound_parent_and_worker_lifetimes')else True})
            rows[-1]['OS_monitor_source']=str(final_path.relative_to(ROOT))
            rows[-1]['OS_monitor_replaces_nested_invocation_timers']=bool(replace_ok)
            if replace_ok:
                os_workers=sum(finals[str(p)]['total_cpu_seconds']for p in start['worker_pids'])
                os_parent=finals[str(start['parent_pid'])]['total_cpu_seconds']
                checks.append({'name':'stability_full_OS_sum',
                    'okay':abs(os_workers-os_final['known_worker_lifetime_cpu_seconds'])<1e-8 and
                        abs(os_parent-os_final['known_parent_lifetime_cpu_seconds'])<1e-8 and
                        abs(os_workers+os_parent-os_final['known_bound_process_cpu_seconds'])<1e-8 and
                        os_workers+1e-8>=worker and os_parent+1e-8>=s['parent_cpu_seconds']})
                rows[-1]['nested_original_intervals_excluded_from_addition']={
                    'worker_case_intervals':worker,'parent_interval':s['parent_cpu_seconds']}
                rows[-1]['cpu_components']=[
                    part('six worker complete OS process lifetimes',os_workers,'os_cpu_monitor_final.known_worker_lifetime_cpu_seconds','complete_bound_process_lifetimes'),
                    part('full coordinator complete OS process lifetime',os_parent,'os_cpu_monitor_final.known_parent_lifetime_cpu_seconds','complete_bound_process_lifetimes')]
                rows[-1]['notes'].append('Complete late-attached Windows GetProcessTimes CPU replaces both nested full worker and parent interval totals; it is not an additional experiment or physical call. Bridge/pilot/prepare and observer remain separate.')
            else:
                rows[-1]['notes'].append('OS monitor incomplete/unbound: retain original invocation lower bound. Partial overlapping OS process totals are bound but not added or silently promoted to complete coverage.')
    for path,ck,wk in ((STABILITY/'os_cpu_monitor_initial_failure.json','child_cpu_seconds','tool_wall_seconds'),
                       (STABILITY/'os_cpu_monitor_final.json','observer_cpu_seconds','observer_wall_seconds'),
                       (STABILITY/'os_cpu_monitor_binding_audit.json','audit_cpu_seconds','audit_wall_seconds')):
        if path.exists():direct(path,ck,wk,identity='stability_'+path.stem+'_own_interval')
    path=STABILITY/'os_cpu_interface_validation.json'
    if path.exists():
        v=read(path);add('stability_os_cpu_interface_validation',path,[
            part('tiny helper child OS lifetime',v.get('known_helper_child_lifetime_cpu_seconds'),'known_helper_child_lifetime_cpu_seconds','complete_child_process_lifetime'),
            part('interface validation parent interval',v.get('observer_validation_parent_cpu_seconds'),'observer_validation_parent_cpu_seconds')],
            status='complete'if v.get('all_passed')else'failed',wall_seconds=v.get('wall_seconds'),
            counts={'physical_calls':v.get('physical_simulation_calls'),'helper_child_processes':v.get('helper_child_processes')},
            notes=['OS API verification only. Tiny child and parent are separate processes; no original-network physics. Embedded initial/after_exit totals are not added again.'])
    for name in('cost_forecast.json','conditional_support_inventory.json','public_pool_inventory.json','summary_authoring_receipt.json'):
        path=STABILITY/name
        if path.exists():direct(path)
    author=BASE/'phase4_w3_round8_performance_authoring_20261010'
    for path in sorted(author.glob('*.json')):direct(path)
    author=BASE/'phase4_w3_round8_stability_authoring_20261010'
    for path in sorted(author.glob('*.json')):
        s=read(path)
        direct(path,'cpu_seconds'if'cpu_seconds'in s else'child_cpu_seconds')
        if 'inventory_prediction'in s:
            a=s['inventory_prediction'];add('stability_inventory_prediction',path,[part('pure inventory diagnostic',None,'inventory_prediction CPU unrecorded')],
                wall_seconds=a.get('tool_wall_seconds'),counts={'physical_calls':a.get('physical_calls')})
    boundary=BASE/'phase4_w3_round8_conditional_boundary_mechanism_20261010'
    for path in (boundary/'validation_meter_failure.json',boundary/'author_v2/validation.json',boundary/'validation.json'):
        if path.exists():direct(path)
    experiment=boundary/'experiment'
    if(experiment/'protocol.json').exists():
        direct(experiment/'protocol.json','preparation_cpu_seconds','preparation_wall_seconds')
        for stage in('bridge','full'):
            path=experiment/stage/'summary.json'
            if not path.exists():
                add('conditional_boundary_'+stage,path,[part('workers and parent',None,'pending')],status='pending');continue
            s=read(path);results=s['rows'];worker=s['case_invocation_cpu_seconds_recorded']
            checks.append({'name':'conditional_boundary_'+stage+'_cpu',
                'okay':abs(sum(r.get('invocation_cpu_seconds')or 0 for r in results)-worker)<1e-8})
            checks.append({'name':'conditional_boundary_'+stage+'_denominator',
                'okay':len(results)==s['planned_physical_calls']==(2 if stage=='bridge'else 24)})
            components=[part('independent physical worker invocation intervals',worker,'case_invocation_cpu_seconds_recorded'),
                part('coordinator interval',s['parent_cpu_seconds'],'parent_cpu_seconds')]
            if not s['complete_resource_accounting']:components.append(part('unrecorded workers',None,'incomplete_resource_accounting'))
            add('conditional_boundary_'+stage,path,components,
                status='complete'if(s['source_input_test_unchanged']and set(s['status_counts'])=={'controller_quiescent'})else'failed_or_incomplete',
                wall_seconds=s['wall_makespan_seconds'],
                counts={k:s[k]for k in('planned_physical_calls','actual_physical_calls_recorded','unknown_physical_call_statuses','memo_aliases','status_counts')},
                notes=[s['resource_scope'],'Separate two-state single-target conditional mechanism supplement; not part of original 4352 logical stability grid.',
                    'Both original bridges and all 24 candidates/support outcomes are separate physical work. No memo or bridge deduction. Nested cycle CPU excluded.'])
        for path in sorted(experiment.glob('*_driver_failure.json')):direct(path)
    candidates=set(REVIEW.glob('*.json'))|set(REVIEW.glob('*/result.json'))
    # Explicit analysis paths avoid recursively counting author fixture JSON or
    # raw records, and prefer analysis over a manifest copying the same clock.
    for folder in BASE.glob('phase4_w3_round8_*_20261010'):
        if folder in(HERE,REVIEW)or'authoring'in folder.name:continue
        for sub in(folder,folder/'results',folder/'pilot',folder/'formal',folder/'visuals',folder/'report',folder/'pipeline',folder/'service_tradeoffs',folder/'projection_domains'):
            primary=sub/'analysis.json'
            metered=False
            if primary.exists():
                candidates.add(primary);a=read(primary)
                metered=any(k in a for k in('cpu_seconds','analysis_cpu_seconds','cpu_seconds_after_imports'))or(
                    isinstance(a.get('resources'),dict)and'analysis_cpu_seconds'in a['resources'])
            if not metered:
                for name in('resource.json','resources.json','metadata.json','manifest.json'):
                    if(sub/name).exists():candidates.add(sub/name);break
        for name in('statistics_validation.json','mechanisms.json','adapter_validation.json',
                    'future_support.json','support_set_validation.json','closure_validation.json',
                    'supplement_source_extraction.json','path_resolution_diagnostic.json','final_closure.json','failure.json',
                    'closeout_validation.json','finalization_failure.json','return_reachability.json'):
            if(folder/name).exists():candidates.add(folder/name)
        candidates.update(folder.glob('extraction_*.json'))
        candidates.update(folder.glob('interim_*.json'))
    for path in sorted(candidates):
        if path in seen:continue
        s=read(path)
        if 'cpu_seconds'in s:direct(path)
        elif 'analysis_cpu_seconds'in s:direct(path,'analysis_cpu_seconds','analysis_wall_seconds')
        elif isinstance(s.get('resources'),dict)and'analysis_cpu_seconds'in s['resources']:
            r=s['resources'];add(str(path.relative_to(BASE)),path,[part('direct pure-file analysis interval',r['analysis_cpu_seconds'],'resources.analysis_cpu_seconds')],
                wall_seconds=r.get('analysis_wall_seconds'),notes=[r.get('scope','Final serialization excluded; embedded experiments are not repeated work.')])
        elif 'cpu_seconds_after_imports'in s:direct(path,'cpu_seconds_after_imports','wall_seconds_after_imports')
        elif path.parent.name=='pipeline'and'parent_cpu_seconds'in s:
            direct(path,'parent_cpu_seconds','wall_including_overlapping_wait_seconds')
    for path in sorted(HERE.glob('preview*/ledger.json')):
        if path.parent==output:continue
        direct(path,'ledger_cpu_seconds_separate','ledger_wall_seconds_separate',identity='resource_'+path.parent.name)
    add('unmetered_development_and_closeout',None,[part('auxiliary overhead',None,'not independently metered')],status='unmetered',notes=[
        'Includes source edits, small structure reads, tool polling, hashes outside recorded intervals, documentation, Git read/check operations, plot visual QA and process bootstrap not covered by a direct receipt.',
        'Author unit tests include a tiny child used to validate Windows full-process CPU extraction. Its returned CPU is asserted but not separately persisted as a resource receipt; unmetered auxiliary, not original-network physics.',
        'No guessed CPU from tool wall or budget limits. This ledger is a known lower bound for Round8, not complete development CPU. Round7 totals are intentionally excluded.'])
    known=sum(p['cpu_seconds']or 0 for r in rows for p in r['cpu_components'])
    physical_ids={'performance_pilot':12,'performance_formal':108,'stability_bridge':17,
        'stability_pilot':24,'stability_full':2468,'conditional_boundary_bridge':2,'conditional_boundary_full':24}
    physical_rows=[r for r in rows if r['id']in physical_ids]
    physical_recorded=sum(r['counts'].get('physical_calls_recorded',r['counts'].get('actual_physical_calls_recorded',0))for r in physical_rows)
    physical_unknown=sum(r['counts'].get('unknown_physical_call_statuses',0)for r in physical_rows)
    physical_pending=sum(physical_ids[r['id']]for r in physical_rows if r['status']=='pending')
    physical_summary={'planned_original_network_invocations':sum(physical_ids.values()),
        'recorded_original_network_invocations':physical_recorded,'unknown_physical_call_statuses':physical_unknown,
        'pending_planned_invocations':physical_pending,'memo_aliases_excluded':sum(r['counts'].get('memo_aliases',0)for r in physical_rows),
        'scope':'Seven independently charged physical stages; pilot/bridge repeats remain work. Business identities are reused. Unit fixtures, OS API helper, file audits and metadata extraction are not original-network physical invocations.'}
    if physical_pending==0:
        checks.append({'name':'round8_physical_full_denominator','okay':physical_recorded==sum(physical_ids.values())and physical_unknown==0})
    checks.append({'name':'resource_source_unchanged','okay':sha256(Path(__file__).read_bytes()).hexdigest()==summarizer_sha})
    checks.append({'name':'bound_receipt_files_unchanged','okay':all(sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in bindings.items())})
    result={'schema':'ics_round8_resource_ledger_v1','rows':rows,'known_cpu_seconds_lower_bound':known,
        'unknown_cpu_components':sum(p['cpu_seconds']is None for r in rows for p in r['cpu_components']),
        'pending_rows':sum(r['status']=='pending'for r in rows),'global_wall_seconds':None,
        'checks':checks,'failed_checks':sum(not c['okay']for c in checks),'bound_inputs':bindings,'physical_summary':physical_summary,'source_sha256':summarizer_sha,
        'ledger_cpu_seconds_separate':process_time()-cpu,'ledger_wall_seconds_separate':perf_counter()-wall,
        'scope':'Round8 only. Known nonoverlapping measured CPU intervals and full child process lifetimes; nested times and memo aliases excluded. Ledger own interval separate. Parallel wall not added.'}
    output.mkdir(parents=True)
    (output/'ledger.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    lines=['# Round8 resource ledger','',f"Known nonoverlapping CPU lower bound: **{known:.6f}s**. Unknown components: {result['unknown_cpu_components']}; pending rows: {result['pending_rows']}. Global elapsed time is unknown and is not a sum of overlapping runners.",'',
        f"Original-network physical invocations: {physical_recorded}/{sum(physical_ids.values())}; physical-status unknown {physical_unknown}; pending planned {physical_pending}. Memo aliases {physical_summary['memo_aliases_excluded']} are excluded from physical work.",'',
        '| Invocation | Status | Known CPU seconds | Measurement |','|---|---|---:|---|']
    for r in rows:
        value=sum(p['cpu_seconds']or 0 for p in r['cpu_components'])
        src='unmetered'if r['source']is None else r['source']
        lines.append(f"| {r['id']} | {r['status']} | {value:.6f}"+(' + unknown'if any(p['cpu_seconds']is None for p in r['cpu_components'])else'')+f" | {src} |")
    lines+=['','Full scopes, source fields, failures, duplicate-work distinctions, memory and hashes are in ledger.json. Query/search/screen/simulation/import timings are nested inside performance child OS CPU; stability memo aliases are not physical work. Pilot repeats are charged separately.','',
        f"Ledger construction interval {result['ledger_cpu_seconds_separate']:.6f}s CPU / {result['ledger_wall_seconds_separate']:.6f}s wall is separately measured and not recursively added to the headline."]
    (output/'RESOURCE_LEDGER.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (output/'summarize.py').write_bytes(summarizer_bytes)
    (output/'manifest.json').write_text(json.dumps({'bound_inputs':bindings,'source_sha256':summarizer_sha,
        'outputs':{name:sha256((output/name).read_bytes()).hexdigest()for name in('ledger.json','RESOURCE_LEDGER.md','summarize.py')}},indent=2),encoding='utf8')
    print(json.dumps({k:result[k]for k in('known_cpu_seconds_lower_bound','unknown_cpu_components','pending_rows','failed_checks','ledger_cpu_seconds_separate')}))
    if result['failed_checks']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--require-file',action='append',default=[]);a=p.parse_args();main(a.output,a.require_file)
