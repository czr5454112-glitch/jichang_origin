"""Closed96 declaration and saved-native comparisons; never an online oracle."""
import copy
import math
from . import public_live_obligation_projection as model
from . import live_obligation_projection_protocol as prior

CASE_ORDER=list(model.construction.CASE_IDS)
ORDER=[case+f'/vector_{i:02d}' for case in CASE_ORDER for i in range(32)]
JOB_ORDER=tuple(sorted(model.JOBS))

def rows():
    actions=model.actions()
    return {key:{'case':key.split('/')[0],'vector':copy.deepcopy(actions[int(key[-2:])]),
        'method':'fixed_feasibility','fault':None,'status':'unknown_unexecuted'} for key in ORDER}

def validate_rows(actual):
    expected=rows()
    if list(actual)!=ORDER:raise ValueError('native96:missing_reordered_or_extra_rows')
    if any(any(actual[k].get(f)!=r[f] for f in ('case','vector','method','fault')) for k,r in expected.items()):
        raise ValueError('native96:misbound_action_or_case')

def known(row):
    s=row.get('summary',{});c=s.get('completion',{})
    return (row.get('status')==s.get('status')=='assessed' and s.get('business_complete') is True
        and s.get('all_required_inputs_verified') is True and s.get('selected_actions_executed') is True
        and set(c)==model.JOBS and all(type(t) in (int,float) and math.isfinite(t) and 0<=t<=40. for t in c.values()))

def compare_one(row,base):
    if not known(row) or not known(base):return {'status':'unknown','strict_protected':None,'delta':None}
    c,b=row['summary']['completion'],base['summary']['completion']
    return {'status':'assessed','strict_protected':all(c[j]<=b[j] for j in JOB_ORDER),
        'delta':{j:c[j]-b[j] for j in JOB_ORDER}}

def score(row):return sum(row['summary']['completion'][j] for j in JOB_ORDER)

def compare(actual, frozen_model_comparisons):
    validate_rows(actual);result={}
    for case in CASE_ORDER:
        group={k:r for k,r in actual.items() if r['case']==case}
        basekey=next(k for k,r in group.items() if r['vector']==prior.incumbent_action());base=group[basekey]
        references={}
        for name,keep in (('fixed_initial_native_default',lambda a:a['initial_action']=='native_default'),
                          ('later_native_default',lambda a:a['later_action']=='native_default')):
            family={k:r for k,r in group.items() if keep(r['vector'])}
            if len(family)!=16:raise ValueError('native96:reference_denominator')
            complete=known(base) and all(known(r) for r in family.values())
            eligible=[k for k,r in family.items() if complete and compare_one(r,base)['strict_protected'] is True]
            best=min(eligible,key=lambda k:(score(family[k]),k),default=None)
            references[name]={'status':'complete_native_finite_reference' if complete else 'unknown_incomplete_reference',
                'members':list(family),'member_count':16,'assessed_members':sum(known(r) for r in family.values()),
                'best_key':best,'best_sum':score(family[best]) if best else None}
        methods={}
        declared=frozen_model_comparisons['cases'][case]['methods']
        if set(declared)!=set(prior.METHODS):raise ValueError('native96:method_domain')
        for method,selection in declared.items():
            if selection.get('budget')!=32 or not 0<=selection['evaluations']<=32:
                raise ValueError('native96:method_budget')
            action=selection['selected_action'];keys=[k for k,r in group.items() if r['vector']==action]
            if action is not None and len(keys)!=1:raise ValueError('native96:method_action_binding')
            key=keys[0] if keys else None
            methods[method]={'selection':copy.deepcopy(selection),'selected_native_key':key,
                'native_outcome_vs_incumbent':compare_one(group[key],base) if key else {'status':'unknown','strict_protected':None,'delta':None},
                'native_vs_complete_references':{name:compare_one(group[key],group[ref['best_key']]) if key and ref['best_key'] else
                    {'status':'unknown','strict_protected':None,'delta':None} for name,ref in references.items()},
                'scope':'Prior saved public-model same32-budget selection mapped to this actual fixed candidate; not an executed online solver and native results did not choose the action.'}
        eligible=[k for k,r in group.items() if all(known(x) for x in group.values()) and compare_one(r,base)['strict_protected'] is True]
        best=min(eligible,key=lambda k:(score(group[k]),k),default=None)
        result[case]={'incumbent_key':basekey,'assessed':sum(known(r) for r in group.values()),
            'unknown':sum(not known(r) for r in group.values()),'references':references,'methods':methods,
            'full32_finite_optimum':best,'rows_vs_incumbent':{k:compare_one(r,base) for k,r in group.items()}}
    return {'status':'complete96_denominator_not_necessarily_assessed','row_count':96,'cases':result,
        'objective':'sum completion times in sorted business ID order; exact per-job <=0 protection, no tolerance',
        'online_solver_executed':False,'native_oracle_policy_input':False,'full_reference_claim_requires_complete_family':True}
