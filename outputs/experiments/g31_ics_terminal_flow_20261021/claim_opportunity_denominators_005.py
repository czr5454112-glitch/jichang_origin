"""Classify all excluded-claim opportunities without reconstructing unknown ETA."""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

DATA=Path(__file__).resolve().parent
ROOT=DATA.parents[2]

def bind(p):
    p=Path(p).resolve()
    with p.open('rb') as f:return dict(path=str(p),sha256=hashlib.file_digest(f,'sha256').hexdigest())
def read(ref):
    assert bind(ref['path'])==ref
    return json.loads(Path(ref['path']).read_text(encoding='utf8'))

def classify(decision):
    plan=decision['selection']['flow_plan']
    receivers={r['node']:r['receiver'] for r in plan['station_table']}
    candidates=[r for r in decision['catalog']['candidates'] if r['action_type']=='transfer']
    eligible=[r for r in candidates if receivers[r['destination']]['known'] and receivers[r['destination']]['available_slots']>0]
    if any(r['source_category']=='ordinary_return' for r in eligible):
        eligible=[r for r in eligible if r['source_category']=='ordinary_return']
    od={(r['source'],r['destination']) for r in eligible}
    return dict(transfer_candidates=len(candidates),known_available_receiver_OD=len(od),
        known_available_receiver_sources=len({r['source'] for r in eligible}),
        protected_category_applied=any(r['source_category']=='ordinary_return' for r in eligible))

def main():
    out=DATA/'claim_opportunity_denominators_005_001.json';assert not out.exists()
    summary_ref=bind(DATA/'final_science_005_resumed_001/final_science_report.json');summary=read(summary_ref)
    source=summary['source_bundle'];manifest=read(source)
    relative='scripts/experiments/g31_ics_circulation/foundation_airport_json_stream.py'
    stream_ref=bind(Path(manifest['root'])/relative);assert stream_ref['sha256']==manifest['files'][relative]
    spec=importlib.util.spec_from_file_location('claim_denominator_frozen_stream',stream_ref['path'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    refs=[bind(__file__),summary_ref,source,stream_ref];runs=[];total=collections.Counter()
    import gzip
    for item in summary['runs']:
        if item['method']!='TF-B1-60':continue
        report_ref=item['evidence'];assert bind(report_ref['path'])['sha256']==report_ref['sha256']
        with gzip.open(report_ref['path'],'rt',encoding='utf8') as f:report=json.load(f)
        ref=report['evidence']['decisions.json.gz'];assert bind(ref['path'])['sha256']==ref['sha256']
        refs.extend([dict(path=r['path'],sha256=r['sha256']) for r in (report_ref,ref)])
        valid={(r['owner_id'],r['at']) for r in report['decision_choices']};seen=set();counts=collections.Counter();cases=[]
        for d in module.iter_json_array_gz(ref['path']):
            key=d['owner_id'],d['decision_time']
            if key not in valid:counts['outside_evaluation_window']+=1;continue
            assert key not in seen;seen.add(key);counts['valid_decisions']+=1
            claims=d['selection']['flow_plan']['receiver_claims_deducted']
            if not any(claims.values()):counts['unclaimed_decisions']+=1;continue
            counts['claimed_decisions']+=1;row=classify(d)
            counts['claimed_no_transfer_menu']+=row['transfer_candidates']==0
            counts['claimed_known_available_receiver_OD_'+str(min(row['known_available_receiver_OD'],2))]+=1
            if row['known_available_receiver_OD']>1:
                cases.append(dict(decision_id=d['decision_id'],owner=key[0],at=key[1],
                    public_state_digest=d['public_observation_ref'],claims=claims,classification=row,
                    selected_action=d['requested_action'],plan_id=d['flow_plan_id']))
        assert seen==valid and len(valid)==1740
        total.update(counts);runs.append(dict(parent=item['parent'],counts=dict(counts),competing_claimed_cases=cases,decisions=ref))
    assert len(runs)==4 and total['claimed_decisions']==6530
    for ref in refs:assert bind(ref['path'])==ref
    result=dict(status='complete_descriptive_denominators',inputs=refs,runs=runs,counts=dict(total),native_starts=0,
        raw_observations_opened=False,ACK_opened=False,policy_replayed=False,ranking_reconstructed=False,
        scope='Known receiver capacity uses the recorded plan after logical deductions. No-candidate callbacks cannot exhibit an alternative first-source ranking under that unchanged legal menu. The remaining claimed multi-OD decisions still have no ETA counterfactual reconstruction.')
    with out.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(dict(output=bind(out),counts=dict(total))))

if __name__=='__main__':main()
