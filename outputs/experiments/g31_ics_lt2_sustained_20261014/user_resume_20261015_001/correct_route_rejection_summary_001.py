"""Correct only prose aggregation, preserving the accurate per-request evidence."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=OUT/'native_preexisting_business_003_failure_diagnosis.json'
r=json.loads(source.read_bytes());rejected=Counter();mismatches=Counter()
for row in r['rows'].values():
    for operation in row['route_operations']:
        if operation['ack']['status']=='rejected':
            rejected[operation['request']['business_bag_id']]+=1
        if operation['selected_vs_actual_mismatch']:
            mismatches[operation['ack']['status']]+=1
assert rejected=={'loaded':45,'reuse1':5} and mismatches=={'updated':9,'rejected':5}
changes={
 'RESEARCH_STATE.json':('but50 initialR1receiving_full and14 selectedreuse3/actual8 mismatches.',
  'but45 initialR1 and5 laterR1 requests rejected receiving_full.14 selectedreuse3/actual8 mismatches comprise9 updated-then-fallback and5 rejected requests.'),
 'NEXT_ACTION.md':('50初始R1被receiving_full拒绝，另有14个后续选择3却实际走8。',
  '45条初始R1、5条后续R1被receiving_full拒绝；14个后续选择3却实际走8，其中9个已更新后回退、5个更新时已被拒。'),
 'RESUMPTION_20261015.md':('但50条初始改路真实被拒绝，14条另有后续所选路径与实际入边不同。',
  '但45条初始改路和5条后续改路真实被拒绝；14条后续路径不一致中，9条是已更新后回退、5条更新时已被拒。'),
 'NOVELTY_LEDGER.md':('025另60业务分支中50初始R1被接收满拒绝，14条另有后来所选3而实际入8；',
  '025另60业务分支中45初始R1及5后续R1被接收满拒绝；14条后来所选3而实际入8，其中9条已更新后回退、5条在更新时已被拒；'),
}
dest=HERE/'route_rejection_summary_correction_001';dest.mkdir(exist_ok=False)
evidence={}
for name,(old,new) in changes.items():
    p=ROOT/'docs/g31_ics_circulation'/name
    before=p.read_bytes();text=before.decode('utf-8')
    assert text.count(old)==1,(name,text.count(old))
    (dest/name).write_bytes(before)
    p.write_text(text.replace(old,new),encoding='utf-8')
    evidence[name]={'before_sha256':sha(dest/name),'after_sha256':sha(p)}
(dest/'receipt.json').write_text(json.dumps({'schema':'g31.route_rejection_summary_correction.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'source':str(source),'source_sha256':sha(source),
 'rejected_requests_by_job':dict(rejected),'mismatch_ack_status':dict(mismatches),'documents':evidence,
 'reason':'Earlier summary incorrectly attributed all50 rejections to initial route and all14 mismatches to updated ACKs; original per-request diagnosis/raw remain correct and unchanged.',
 'old_experiment_verdicts_unchanged':True,'new_native_executions':0},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'receipt_sha256':sha(dest/'receipt.json'),'rejected':dict(rejected),'mismatches':dict(mismatches)}))
