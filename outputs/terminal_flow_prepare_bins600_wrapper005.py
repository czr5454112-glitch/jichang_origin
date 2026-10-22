"""Prepare a dedicated one-task science supervisor; never launch a child."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'outputs/terminal_flow_offline_budget.py').read_text(encoding='utf8')
begin=source.index('HELPERS = {');end=source.index('\nFIGURES = ',begin)
source=source[:begin]+"HELPERS = {'bins600': ROOTDATA/'bins600_science_005.py'}\n"+source[end:]
begin=source.index('def validate_task_roster(tasks):');end=source.index('\ndef validate_spec(',begin)
source=source[:begin]+'''def validate_task_roster(tasks):
    need(len(tasks) == 1 and tasks[0]['kind'] == 'bins600' and tasks[0]['id'] == 'bins600', 'single_bins600_science_task')


def validate_bins600_inputs(spec):
    registration = read(checked(spec['bins600_registration']))
    completion = read(checked(spec['bins600_completion']))
    need(registration['schema'] == 'g31.terminal_flow.bins600_extension.v1'
         and registration['source_bundle'] == spec['source_manifest']
         and registration['parents'] == [2201,2202,2203,2204], 'bins600_registered_matrix')
    need(completion['registration'] == spec['bins600_registration'] and completion['status'] == 'closed'
         and completion['full_window_native_runs'] == 4, 'bins600_native_closed')
    need(len(registration['task_plans']) == len(completion['receipts']) == 4, 'bins600_exact_four_receipts')
    for ref, receipt_ref in zip(registration['task_plans'],completion['receipts']):
        plan = read(checked(ref)); receipt = read(checked(receipt_ref))
        need(Path(receipt_ref['path']).resolve() == Path(ref['path']).resolve().parent/'receipt.json'
             and receipt['plan_sha256'] == ref['sha256'] and receipt['process']['exitcode'] == 0
             and receipt['worker']['scientific_status'] == 'closed'
             and receipt['worker']['final_physical_time'] == 59400.
             and plan['method'] == 'TF-B1-600', 'bins600_receipt_contract')
    intent = read(checked(registration['intent']))
    checked(intent['baseline_science']); checked(spec['registration_driver'])

''' + source[end:]
source=source.replace("def validate_spec(spec, *, require_closed=True):\n", "def validate_spec(spec, *, require_closed=True):\n    validate_bins600_inputs(spec)\n")
source=source.replace("def verify_exit_bindings(spec, spec_ref, producer):\n", "def verify_exit_bindings(spec, spec_ref, producer):\n    validate_bins600_inputs(spec)\n")
target=ROOT/'outputs/terminal_flow_bins600_offline005.py'
with target.open('x',encoding='utf8',newline='\n') as stream: stream.write(source)
print(target)
