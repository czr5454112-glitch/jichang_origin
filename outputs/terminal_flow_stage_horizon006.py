"""Prepare a reviewable 1800-second projection arm without editing active code.

This writes candidate source copies only. Applying/freezing/running requires a
separate registered admission after source005 follow-ups close.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
OUT=DATA/'horizon_repair_preparation_006'
REL=Path('scripts/experiments/g31_ics_circulation')

def replace_once(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new)

def candidate_sources():
    p=ROOT/REL/'foundation_airport_joint_campaign.py';raw=p.read_bytes();text=raw.decode('utf8').replace('\r\n','\n')
    text=replace_once(text,"TRANSPORT_METHODS=('TF-current','TF-B1-60','TF-B1-300'",
        "TRANSPORT_METHODS=('TF-current','TF-B1-60','TF-B1-60-H1800','TF-B1-300'")
    text=replace_once(text,"plan.update(transport_config={**DEFAULT_CONFIG, **(transport_config or {})},",
        "plan.update(projection_horizon_seconds=1800. if method=='TF-B1-60-H1800' else 600.,\n            transport_config={**DEFAULT_CONFIG, **(transport_config or {})},")
    text=replace_once(text,"if (plan['forecast_horizon_seconds']!=1800. or plan['projection_horizon_seconds']!=600.",
        "expected_projection=1800. if plan['method']=='TF-B1-60-H1800' else 600.\n        if (plan['forecast_horizon_seconds']!=1800. or plan['projection_horizon_seconds']!=expected_projection")
    yield p,raw,text.encode('utf8')
    p=ROOT/REL/'foundation_airport_transport_campaign.py';raw=p.read_bytes();text=raw.decode('utf8').replace('\r\n','\n')
    text=replace_once(text,'REFERENCES = {"TF-B1-300": "TF-B1-60",',
        'REFERENCES = {"TF-B1-60-H1800": "TF-B1-60", "TF-B1-300": "TF-B1-60",')
    text=replace_once(text,'ALLOWED_COMPARISON_DIFFERENCES = {',
        'ALLOWED_COMPARISON_DIFFERENCES = {\n    "TF-B1-60-H1800": ("projection_horizon",),')
    text=replace_once(text,'"projection_horizon_seconds": 600., "supply_mode": "committed_only"}',
        '"projection_horizon_seconds": 1800. if method == "TF-B1-60-H1800" else 600.,\n        "supply_mode": "committed_only"}')
    yield p,raw,text.encode('utf8')

def main():
    assert not OUT.exists();OUT.mkdir()
    rows=[]
    for path,before,after in candidate_sources():
        compile(after,str(path),'exec')
        target=OUT/path.name;target.write_bytes(after)
        rows.append(dict(relative=path.relative_to(ROOT).as_posix(),before_sha256=hashlib.sha256(before).hexdigest(),
            candidate=str(target),candidate_sha256=hashlib.sha256(after).hexdigest()))
    manifest=dict(status='candidate_copies_only_not_applied',method='TF-B1-60-H1800',reference='TF-B1-60',
        axis='projection_horizon_seconds',fixed_forecast_horizon_seconds=1800,fixed_forecast_bin_seconds=60,
        fixed_supply_mode='committed_only',files=rows,production_modified=False,native_starts=0,
        source006_frozen=False,parameters_fitted=False,
        motivation='Source005 source149 cost is zero over600 despite forecast demand3.36 over1800; delayed source service and journeys beyond600 warrant an independent horizon diagnosis. This does not establish causality or service gain.')
    (OUT/'PREPARATION.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    print(json.dumps(manifest))

if __name__=='__main__':main()
