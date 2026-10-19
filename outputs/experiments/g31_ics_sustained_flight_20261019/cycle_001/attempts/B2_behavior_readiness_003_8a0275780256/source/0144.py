"""Independent strict stdlib decoder for closed airport v2 evidence files.

No import of the live recorder/controller/native source closure. Blob bytes,
member CRCs, descriptors and row sequence are checked; partial recovery is
deliberately unsupported for a supervised-label dataset.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import zlib


def require(ok,reason):
    if not ok:raise ValueError('airport_behavior_reader:'+reason)


def value_sha(value):
    return hashlib.sha256(json.dumps(value,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def closed_members(path):
    """A byte range is yielded only after zlib verifies that member's trailer."""
    offset=0;start=0;pending=b'';decoder=zlib.decompressobj(31);parts=[];active=False
    with Path(path).open('rb') as stream:
        while True:
            if not pending:
                pending=stream.read(32768)
                if not pending:
                    require(not active,'truncated_gzip_member')
                    return
            active=True;parts.append(decoder.decompress(pending))
            consumed=len(pending)-len(decoder.unused_data)
            offset+=consumed
            if decoder.eof:
                yield b''.join(parts),start,offset-start
                pending=decoder.unused_data;start=offset;parts=[];active=False;decoder=zlib.decompressobj(31)
            else:
                pending=b''


def read_records(path,blobs_path):
    blobs_path=Path(blobs_path);index={}
    for payload,offset,length in closed_members(blobs_path):
        row=json.loads(payload)
        require(set(row)=={'sha256','value'} and row['sha256']==value_sha(row['value']),'blob_content_identity')
        require(row['sha256'] not in index,'duplicate_blob_identity')
        index[row['sha256']]=(offset,length)

    @lru_cache(maxsize=128)
    def blob(identity):
        require(identity in index,'missing_blob_reference')
        offset,length=index[identity]
        with blobs_path.open('rb') as stream:
            stream.seek(offset);row=json.loads(gzip.decompress(stream.read(length)))
        require(row['sha256']==identity==value_sha(row['value']),'indexed_blob_bytes_changed')
        return row['value']

    def decode(descriptor):
        kind=descriptor['kind']
        if kind=='inline':
            require(set(descriptor)=={'kind','value'} and (descriptor['value'] is None or type(descriptor['value']) in (bool,int,float,str)), 'inline_scalar_shape')
            return descriptor['value']
        if kind=='value':
            require(set(descriptor)=={'kind','sha256'},'value_descriptor_shape')
            return copy.deepcopy(blob(descriptor['sha256']))
        if kind=='list':
            require(set(descriptor)=={'kind','length','chunks'} and type(descriptor['length']) is int
                and descriptor['length']>=0 and type(descriptor['chunks']) is list,'list_descriptor_shape')
            chunks=[blob(identity)for identity in descriptor['chunks']]
            require(all(type(chunk) is list and 1<=len(chunk)<=64 for chunk in chunks)
                and all(len(chunk)==64 for chunk in chunks[:-1]),'exact_ordered_chunk_lengths')
            value=[copy.deepcopy(item)for chunk in chunks for item in chunk]
            require(len(value)==descriptor['length'],'reconstructed_list_length')
            return value
        if kind=='object':
            require(set(descriptor)=={'kind','fields'} and type(descriptor['fields']) is dict,'object_descriptor_shape')
            return {key:decode(value)for key,value in descriptor['fields'].items()}
        raise ValueError('airport_behavior_reader:unsupported_descriptor_kind')

    for sequence,(payload,_,_) in enumerate(closed_members(path)):
        row=json.loads(payload)
        require(row['schema']=='g31.foundation.airport_policy_observation.v2'
            and type(row['sequence']) is int and row['sequence']==sequence,'record_schema_and_sequence')
        for field in ('observation','policy_options','decision'):
            row[field]=decode(row[field])
        yield row
