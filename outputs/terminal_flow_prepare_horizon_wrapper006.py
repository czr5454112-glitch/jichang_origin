"""Prepare a separate source006 supervisor, preserving the tested resource core."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'outputs/terminal_flow_horizon_offline006.py'
assert not target.exists()
text=(ROOT/'outputs/terminal_flow_bins600_offline005.py').read_text(encoding='utf8')

def replace(old,new):
    global text
    assert text.count(old)==1,(old,text.count(old));text=text.replace(old,new)

replace("HELPERS = {'bins600': ROOTDATA/'bins600_science_005.py'}",
    "HELPERS = {'horizon_science': ROOTDATA/'horizon_science_006.py'}")
replace("need(Path(manifest['root']).name == 'terminal_flow_runtime_005', 'source005_only')",
    "need(Path(manifest['root']).name == 'terminal_flow_runtime_006', 'source006_only')")
text=text.replace('validate_bins600_inputs','validate_horizon_inputs')
replace("for ref in completion['blocks']+[completion['training_fit'], completion['evaluation']]:",
    "for ref in completion['blocks']+completion['receipts']:")
replace("need(len(tasks) == 1 and tasks[0]['kind'] == 'bins600' and tasks[0]['id'] == 'bins600', 'single_bins600_science_task')",
    "need(len(tasks) == 1 and tasks[0]['kind'] == 'horizon_science' and tasks[0]['id'] == 'horizon_science', 'single_horizon_science_task')")
start=text.index('def validate_horizon_inputs(spec):')
end=text.index('\n\ndef validate_spec(',start)
text=text[:start]+'''def validate_horizon_inputs(spec):
    registration = read(checked(spec['horizon_registration']))
    completion = read(checked(spec['horizon_completion']))
    need(spec['horizon_registration'] == spec['workflow'] and spec['horizon_completion'] == spec['workflow_completion'],
         'same_horizon_workflow_bindings')
    need(registration['schema'] == 'g31.terminal_flow.projection_horizon_workflow.v1'
         and registration['source_bundle'] == spec['source_manifest'] and registration['new_native_starts'] == 8,
         'registered_eight_horizon_runs')
    block = read(checked(registration['block']))
    need(block['parents'] == [2201,2202,2203,2204] and block['methods'] == ['TF-B1-60','TF-B1-60-H1800']
         and block['source_bundle'] == spec['source_manifest'], 'fixed_horizon_matrix')
    need(completion['registration'] == spec['workflow'] and completion['status'] == 'closed'
         and completion['all_registered_development_tasks_closed'] is True
         and len(block['task_plans']) == len(completion['receipts']) == 8, 'horizon_native_closed')
    for i,(ref,receipt_ref) in enumerate(zip(block['task_plans'],completion['receipts'])):
        plan = read(checked(ref)); receipt = read(checked(receipt_ref))
        need(Path(receipt_ref['path']).resolve() == Path(ref['path']).resolve().parent/'receipt.json'
             and receipt['plan_sha256'] == ref['sha256'] and receipt['process']['exitcode'] == 0
             and receipt['worker']['scientific_status'] == 'closed'
             and receipt['worker']['final_physical_time'] == 59400.
             and plan['method'] == block['methods'][i%2]
             and plan['parent']['parent_seed'] == block['parents'][i//2]
             and plan['parent']['split'] == 'dev' and plan['source_bundle'] == spec['source_manifest'],
             'horizon_receipt_identity_contract')
    for ref in registration['dependencies'].values(): checked(ref)
    checked(registration['driver']); checked(spec['registration_driver'])
'''+text[end:]
start=text.index("        evaluation = read(checked(completion['evaluation']))")
end=text.index("    tasks = spec['tasks']",start)
text=text[:start]+"        for ref in completion['blocks']+completion['receipts']:\n            checked(ref)\n"+text[end:]
compile(text,str(target),'exec');target.write_text(text,encoding='utf8')
print(target)
