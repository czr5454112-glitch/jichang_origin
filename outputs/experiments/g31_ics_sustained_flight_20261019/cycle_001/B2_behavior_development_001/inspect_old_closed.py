"""Small stdlib historical exclusion check, not a complete dataset export."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'C00_cyclic_od_001'/'C00'
def read(name):
    with gzip.open(OLD/name,'rt',encoding='utf8')as stream:return json.load(stream)
def ref(path):
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
raw=read('raw.json.gz');result=raw['final_result'];calls=read('client_calls.json.gz')
chosen=[row for row in calls if row['kind']=='transfer' and row['retry'] is False and 43200.<=row['at']<=57300.]
identities={row['request']['request_id']for row in chosen}
assert len(identities)==len(chosen)
transfers={row['request_id']:row for row in result['transfers']}
statuses=collections.Counter(transfers[key]['status']if key in transfers else 'missing'for key in identities)
received=[row for row in result['receipts']if row['event']=='EMPTY_RECEIVED'and row['reason']in identities]
report={'status':'completed_historical_exclusion_check','native_sessions':0,'fit_calls':0,'labels_created':0,
    'source':ref(Path(__file__).resolve()),'raw':ref(OLD/'raw.json.gz'),'client_calls':ref(OLD/'client_calls.json.gz'),
    'first_submission_interval':[43200.,57300.],'unique_first_submissions':len(chosen),
    'final_transfer_status_counts':dict(statuses),'matching_empty_received_count':len(received),
    'latest_any_empty_received_at':max(row['time']for row in result['receipts']if row['event']=='EMPTY_RECEIVED'),
    'scope':'Historical status/effect exclusion evidence; not the complete callback/ACK data readiness exporter.',
    'conclusion':'No successful execution training label is justified by these pending submission replies.'}
with (HERE/'old_cyclic_exclusion_check.json').open('x',encoding='utf8')as stream:json.dump(report,stream,indent=2)
print(json.dumps({'submissions':len(chosen),'statuses':dict(statuses),'received':len(received)}))
