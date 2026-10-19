"""Opt-in lossless API tape candidate; no policy, timing or native changes.

Encode argument snapshots before invoking the API and the result before its
return. Splice those already-encoded JSON values into one complete row and
write it in one text write. The decoded ordered row is the legacy canonical
row, including duplicate JSON object-key last-value/first-position semantics.
Gzip bytes are newly generated evidence, not asserted byte-identical to the old
files. Required encoding, compression, write, hash and manifest work stays in
the API envelope. This module does not install itself or load a native binary.
"""
from __future__ import annotations

import gzip
import json
import re
from . import research_original_low_wip as reference

REFERENCE_SHA256 = '729cbbdd03ecff3a85bd5324653db424bd601632a5fbecdc72c02bb83c3c7bc9'
_SURROGATES = re.compile('[\ud800-\udfff]')
_SURROGATE_ESCAPES = {i: '\\u%04x' % i for i in range(0xd800, 0xe000)}


def encode(value):
    # The legacy first pass uses ensure_ascii=True, then decodes; its final
    # pass uses False. Direct False keeps the same string/numeric/object data.
    # UTF8 failures (e.g. unpaired surrogate) still occur only on final write.
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if _SURROGATES.search(text):
        # Legacy dumps(True)->loads combines valid surrogate pairs, including
        # object keys that may then collide. Normalize the encoded snapshot,
        # never enumerate the possibly stateful caller object a second time.
        text = json.dumps(json.loads(text.translate(_SURROGATE_ESCAPES)),
                          ensure_ascii=False, allow_nan=False)
    return text


def row_text(ordinal, endpoint, args, kwargs, before, result, error, after):
    pieces = ['{"ordinal": ', encode(ordinal), ', "endpoint": ', encode(endpoint),
              ', "args": ', args, ', "kwargs": ', kwargs, ', "before": ', encode(before)]
    if result is not None:
        pieces.extend((', "result": ', result))
    if error is not None:
        pieces.extend((', "error": ', encode(error)))
    pieces.extend((', "after": ', encode(after), '}'))
    return ''.join(pieces)


def write_row(path, text):
    # Keep level1 compression and close-before-hash. A partial failed file is
    # retained, but never receives a valid manifest entry.
    with gzip.open(path, 'wt', encoding='utf-8', compresslevel=1) as stream:
        count = stream.write(text)
        if count != len(text):
            raise OSError('serialize_once_tape:short_row_write')


class SerializedOnceTape(reference.Tape):
    """Separate explicit class. Original Tape and stdlib globals stay intact.

    An artifact-write failure makes this instance unusable. No API may run
    after an unmanifested row, and no accepted prefix is silently overwritten.
    This strengthens diagnostic failure handling, not successful policy work.
    """
    def __init__(self, session, directory):
        if reference.sha(reference.__file__) != REFERENCE_SHA256:
            raise ValueError('serialize_once_tape:reference_source_changed')
        super().__init__(session, directory)
        self.capture_failure = None

    def __getattr__(self, name):
        reference.require(name in reference.ENDPOINTS, 'unclassified_endpoint:' + name)
        def call(*args, **kwargs):
            if self.capture_failure is not None:
                raise RuntimeError('serialize_once_tape:prior_capture_failure')
            ordinal = len(self.rows)
            # Match legacy evaluation order. Native code may mutate the inputs;
            # the saved call must contain the exact pre-call JSON snapshots.
            args_json = encode(args)
            kwargs_json = encode(kwargs)
            before = self.physical_time
            result_json = error_repr = None
            try:
                result = getattr(self.session, name)(*args, **kwargs)
                result_json = encode(result)
                return result
            except BaseException as error:
                error_repr = repr(error)
                raise
            finally:
                try:
                    after = self.physical_time
                    text = row_text(ordinal, name, args_json, kwargs_json, before,
                                    result_json, error_repr, after)
                    path = self.directory / f'{ordinal:06d}.json.gz'
                    write_row(path, text)
                    item = {'path': path.name, 'sha256': reference.sha(path), 'endpoint': name}
                    # Legacy appends metadata to RAM before appending manifest.
                    # The sticky failure prevents another call even if that
                    # final append fails after the metadata was retained.
                    self.rows.append(item)
                    with (self.directory / 'manifest.jsonl').open('a', encoding='utf-8') as stream:
                        line = json.dumps(item) + '\n'
                        if stream.write(line) != len(line):
                            raise OSError('serialize_once_tape:short_manifest_write')
                except BaseException as error:
                    self.capture_failure = {'ordinal': ordinal, 'endpoint': name,
                                            'error': repr(error)}
                    raise
        return call
