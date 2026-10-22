"""Register an independent horizon diagnosis after the 600-bin science closes."""
from pathlib import Path
import copy
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'

def main():
    path=ROOT/'outputs/terminal_flow_horizon_probe_offline005.py'
    loader=importlib.util.spec_from_file_location('horizon_probe_register_budget',path)
    w=importlib.util.module_from_spec(loader);loader.loader.exec_module(w)
    prior=w.read(DATA/'bins600_science_spec_005_001.json');spec=copy.deepcopy(prior)
    done=w.bind(DATA/'bins600_science_005_001/COMPLETE.json')
    w.need(w.read(w.checked(done))['status']=='complete','closed_bins600_science_required')
    spec.update(wrapper=w.bind(path),registration_driver=w.bind(__file__),
        remaining_work_reserved_seconds=30300,remaining_work_reserved_bytes=5*1024**3,
        reason_pending='Independent 600/1800 projection diagnosis after full bin audit. Reserve a possible same-source eight-run repair block and its audit; no authority to start it.')
    output=DATA/'projection_horizon_probe_005_001';producer=DATA/'projection_horizon_probe_005.py'
    spec['tasks']=[dict(id='horizon_probe',kind='horizon_probe',argv=[spec['python']['path'],'-B',str(producer),
        '--source-manifest',spec['source_manifest']['path'],'--workflow',spec['workflow']['path'],
        '--execute','--output-dir',str(output)],output=str(output),hard_seconds=1800,
        estimated_evidence_bytes=64*1024**2,required_outputs=['COMPLETE.json','projection_horizon_probe.json'])]
    spec['producer_bindings']+=[w.bind(producer),done]
    limits,holdback=w.validate_spec(spec);preflight=w.checked_preflight(spec,limits,holdback)
    w.save(DATA/'horizon_probe_preflight_005_001.json',dict(preflight=preflight,ledger_mutated=False))
    ref=w.save(DATA/'horizon_probe_spec_005_001.json',spec)
    print(json.dumps(dict(spec=ref,preflight=preflight),indent=2))

if __name__=='__main__':main()
