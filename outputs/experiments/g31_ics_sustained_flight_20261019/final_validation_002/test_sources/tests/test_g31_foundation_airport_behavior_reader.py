"""Closed-file evidence decoder counterexamples, independent of producer code."""
import gzip
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_reader as reader


def files(tmp_path):
    value=[{'job':'x','count':None,'truth':False,'zero':0,'time':0.0}]
    identity=reader.value_sha(value)
    blob={'sha256':identity,'value':value}
    row={'schema':'g31.foundation.airport_policy_observation.v2','sequence':0,
        'observation':{'kind':'object','fields':{'jobs':{'kind':'list','length':1,'chunks':[identity]},
            'owner_id':{'kind':'inline','value':'A'}}},
        'policy_options':{'kind':'object','fields':{}},
        'decision':{'kind':'object','fields':{'intents':{'kind':'list','length':0,'chunks':[]}}}}
    path=tmp_path/'refs.gz';blobs=tmp_path/'blobs.gz'
    return path,blobs,row,blob


def save(path,rows):
    path.write_bytes(b''.join(gzip.compress(json.dumps(row,separators=(',',':')).encode(),mtime=0)for row in rows))


def test_decode_preserves_unknown_types_order_and_does_not_import_native(tmp_path):
    path,blobs,row,blob=files(tmp_path);save(path,[row]);save(blobs,[blob])
    decoded=list(reader.read_records(path,blobs))
    assert decoded[0]['observation']['jobs']==blob['value']
    assert type(decoded[0]['observation']['jobs'][0]['zero']) is int
    assert type(decoded[0]['observation']['jobs'][0]['time']) is float
    assert decoded[0]['observation']['jobs'][0]['count'] is None
    assert decoded[0]['decision']['intents']==[]
    assert 'foundation_airport_observations_v2' not in Path(reader.__file__).read_text()


@pytest.mark.parametrize('mutation',['hash','duplicate_blob','missing_blob','truncated_blob','truncated_ref','sequence','length','descriptor'])
def test_closed_evidence_rejects_incomplete_or_forged_storage(tmp_path,mutation):
    path,blobs,row,blob=files(tmp_path)
    if mutation=='hash':blob['value'][0]['count']=0
    elif mutation=='sequence':row['sequence']=1
    elif mutation=='length':row['observation']['fields']['jobs']['length']=2
    elif mutation=='descriptor':row['observation']['fields']['jobs']['kind']='guess'
    save(path,[row]);save(blobs,[blob,blob] if mutation=='duplicate_blob'else[]if mutation=='missing_blob'else[blob])
    if mutation=='truncated_blob':blobs.write_bytes(blobs.read_bytes()[:-3])
    if mutation=='truncated_ref':path.write_bytes(path.read_bytes()[:-3])
    with pytest.raises((ValueError,EOFError)):
        list(reader.read_records(path,blobs))


def test_independent_nonoverlap_gate_counts_windows_not_bags():
    from scripts.experiments.g31_ics_circulation.foundation_airport_behavior_readiness import disjoint_count
    assert disjoint_count([43200.,43200.,43260.,43499.,43500.,43800.,44100.])==4
