"""Register one bounded 600-bin audit only after all four native runs close."""
from pathlib import Path
import copy
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
def main():
    path=ROOT/'outputs/terminal_flow_bins600_offline005.py'
    loader=importlib.util.spec_from_file_location('bins600_register_budget',path)
    w=importlib.util.module_from_spec(loader);loader.loader.exec_module(w)
    prior_path=DATA/'offline_budget_spec_005_ready_004.json'
    prior=w.read(prior_path);spec=copy.deepcopy(prior)
    spec.pop('template',None)
    spec.update(wrapper=w.bind(path),registration_driver=w.bind(__file__),
        bins600_registration=w.bind(w.CYCLE/'terminal_flow/bins600_full_005/registration.json'),
        bins600_completion=w.bind(w.CYCLE/'terminal_flow/bins600_full_005/NATIVE_COMPLETE.json'),
        remaining_work_reserved_seconds=0,remaining_work_reserved_bytes=0,
        reason_pending='Explicit four-parent 600-bin closed-native audit; original budget and source remain unchanged')
    output=DATA/'bins600_science_005_001'
    producer=DATA/'bins600_science_005.py'
    spec['tasks']=[dict(id='bins600',kind='bins600',argv=[spec['python']['path'],'-B',str(producer),
        '--source-manifest',spec['source_manifest']['path'],'--workflow',spec['workflow']['path'],
        '--execute','--output-dir',str(output)],output=str(output),hard_seconds=3600,
        estimated_evidence_bytes=128*1024**2,required_outputs=['COMPLETE.json','bins600_science_report.json'])]
    spec['producer_bindings']+=[w.bind(producer)]
    limits,holdback=w.validate_spec(spec);preflight=w.checked_preflight(spec,limits,holdback)
    w.save(DATA/'bins600_science_preflight_005_001.json',dict(preflight=preflight,ledger_mutated=False))
    ref=w.save(DATA/'bins600_science_spec_005_001.json',spec)
    print(json.dumps(dict(spec=ref,preflight=preflight),indent=2))

if __name__=='__main__': main()
