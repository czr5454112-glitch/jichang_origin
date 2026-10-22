"""Admit the fixed eight-run source006 science audit only after native closure."""
from pathlib import Path
import copy
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'

def main():
    path=ROOT/'outputs/terminal_flow_horizon_offline006.py'
    loader=importlib.util.spec_from_file_location('horizon_register_budget',path)
    w=importlib.util.module_from_spec(loader);loader.loader.exec_module(w)
    spec=copy.deepcopy(w.read(DATA/'offline_budget_spec_005_ready_004.json'));spec.pop('template',None)
    workflow=w.bind(w.CYCLE/'terminal_flow/workflow_006/registration.json')
    completion=w.bind(w.CYCLE/'terminal_flow/workflow_006/completion.json')
    spec.update(wrapper=w.bind(path),registration_driver=w.bind(__file__),workflow=workflow,workflow_completion=completion,
        horizon_registration=workflow,horizon_completion=completion,
        source_manifest=w.bind(w.CYCLE/'sources/terminal_flow_runtime_006/source_manifest.json'),
        remaining_work_reserved_seconds=0,remaining_work_reserved_bytes=0,
        reason_pending='Fixed four-parent same-source 600 versus1800 projection audit; no fitting or native starts.')
    output=DATA/'horizon_science_006_001';producer=DATA/'horizon_science_006.py'
    spec['tasks']=[dict(id='horizon_science',kind='horizon_science',argv=[spec['python']['path'],'-B',str(producer),
        '--source-manifest',spec['source_manifest']['path'],'--workflow',spec['workflow']['path'],
        '--execute','--output-dir',str(output)],output=str(output),hard_seconds=6000,
        estimated_evidence_bytes=256*1024**2,required_outputs=['COMPLETE.json','horizon_science_report.json'])]
    spec['producer_bindings']+=[w.bind(producer)]
    limits,holdback=w.validate_spec(spec);preflight=w.checked_preflight(spec,limits,holdback)
    w.save(DATA/'horizon_science_preflight_006_001.json',dict(preflight=preflight,ledger_mutated=False))
    ref=w.save(DATA/'horizon_science_spec_006_001.json',spec)
    print(json.dumps(dict(spec=ref,preflight=preflight),indent=2))

if __name__=='__main__':main()
