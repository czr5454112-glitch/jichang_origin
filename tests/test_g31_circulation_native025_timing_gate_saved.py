"""Offline adversarial replay of the saved actual025 gate; no native imports/runs."""
import gzip
import json
from pathlib import Path
import shutil
import pytest
from scripts.experiments.g31_ics_circulation import native025_timing_gate as gate

BASE=Path(__file__).resolve().parents[1]/'outputs/experiments/g31_ics_lt2_sustained_20261014'

@pytest.fixture
def saved(tmp_path):
    origin=BASE/'native025_timing_gate_001'
    if not (origin/'receipt.json').exists():pytest.skip('explicit saved native025 gate evidence absent')
    target=tmp_path/'gate';shutil.copytree(origin,target)
    contract=gate.read(BASE/'native025_timing_accepted_001/contract.json')
    return target,contract


def reset_json(path,data):
    path.write_text(json.dumps(data,indent=2))


def reset_raw(path,data):
    with gzip.open(path,'wt',encoding='utf-8') as stream:json.dump(data,stream)


def reference(path):return {'path':str(path),'sha256':gate.sha(path)}


def test_saved_actual_gate_recomputes_all_required_gates(saved):
    directory,contract=saved
    assert gate.verify_saved_gate(reference(directory/'receipt.json'),contract)['runtime_accepted'] is True


@pytest.mark.parametrize('defect',['empty_all_tapes','null_all_seals','missing_v2_identity','missing_case','empty_sources','source_crosslink','failed_process','wrong_binary'])
def test_even_rehashed_tampered_native_evidence_fails_closed(saved,defect):
    directory,contract=saved;receipt=gate.read(directory/'receipt.json');plan=gate.read(directory/'plan.json')
    if defect in {'empty_all_tapes','null_all_seals'}:
        for arm in gate.ARMS:
            path=directory/arm/'normal.json.gz';raw=gate.read(path)
            if defect=='empty_all_tapes':raw['outputs']=[]
            else:raw['native_seal']=raw['checkpoint_seal']=None
            reset_raw(path,raw);receipt['raw'][arm]['normal']['sha256']=gate.sha(path)
    elif defect in {'missing_v2_identity','wrong_binary'}:
        path=directory/'native025_timed/planning_snapshot_v2.json.gz';raw=gate.read(path)
        if defect=='wrong_binary':raw['native_binary']['sha256']='f'*64
        else:
            for batch in raw['timing']['batches']:
                batch['command_identities']=[c for c in batch['command_identities'] if c['kind']!='planning_snapshot_v2']
        reset_raw(path,raw);receipt['raw']['native025_timed']['planning_snapshot_v2']['sha256']=gate.sha(path)
    elif defect=='missing_case':receipt['raw']['native025_timed'].pop('exception')
    elif defect in {'empty_sources','source_crosslink'}:
        if defect=='empty_sources':plan['source_sha256']={}
        else:plan['source_sha256']['native025_request_timing.py']='f'*64
        reset_json(directory/'plan.json',plan);receipt['plan_sha256']=gate.sha(directory/'plan.json')
    else:
        path=directory/'native025_timed.process.json';process=gate.read(path);process['exit_code']=1
        reset_json(path,process);receipt['process_sha256']['native025_timed']=gate.sha(path)
    reset_json(directory/'receipt.json',receipt)
    with pytest.raises(ValueError):gate.verify_saved_gate(reference(directory/'receipt.json'),contract)
