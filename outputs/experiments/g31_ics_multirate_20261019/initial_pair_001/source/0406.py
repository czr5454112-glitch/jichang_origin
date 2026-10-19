"""Read producer-manifest-bound raw shards without repeated state materialization.

This is a restricted projection of the exact ``streaming.gz`` serializer, not a
general JSON parser. Intermediate controller-state bytes remain opaque and are
bound by the SHA256 of the complete gzip file to the producer's already fully
parsed manifest. Every other field is parsed by Python's standard JSON decoder.
The final shard must be decoded in full. No native module is loaded here.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path


STATE = b', "controller_state": '
RECORDS = b', "control_records": '
KEYS = ("status", "result", "controller_state", "control_records", "client_calls",
        "native_batches", "control_continuation", "wall_seconds",
        "complete_100ms_requirement_certified", "scope")
OPTIONAL_KEYS = ("native_state_sha256", "diagnostic_seal_wall_ms")
STRING = re.compile(rb'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
NON_BRACKETS = bytes(n for n in range(256) if n not in b"{}[]")


def single_object_boundary(raw):
    """Prove one exact object container, respecting strings and escapes.

    C regex removes complete JSON string tokens, then C translate extracts only
    structural brackets. The small bracket stream is checked in Python. This
    proves the subtree boundary; it deliberately does not validate scalar or
    member grammar inside that opaque subtree.
    """
    stripped = STRING.sub(b"", raw)
    if b'"' in stripped:
        raise ValueError("raw_shard:invalid_or_unterminated_state_string")
    structure = stripped.translate(None, NON_BRACKETS)
    if not structure or structure[0] != ord("{"):
        raise ValueError("raw_shard:state_not_object")
    stack = []
    for index, token in enumerate(structure):
        if token in (ord("{"), ord("[")):
            stack.append(token)
        else:
            expected = ord("{") if token == ord("}") else ord("[")
            if not stack or stack.pop() != expected:
                raise ValueError("raw_shard:unbalanced_state_container")
            if not stack and index != len(structure) - 1:
                raise ValueError("raw_shard:extra_value_in_skipped_state_region")
    if stack:
        raise ValueError("raw_shard:unterminated_state_container")


def sha256_file(path, block_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("raw_shard:duplicate_json_key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("raw_shard:nonfinite_json_constant:" + value)


def decode_shard(raw, *, final=False):
    """Return all fields; only an intermediate controller_state becomes None.

    The caller must bind the complete raw gzip SHA to a producer manifest before
    using this projection. It deliberately does not certify skipped JSON syntax.
    Exact marker uniqueness, order and the resulting top-level field order are
    required. Unsupported serialization formats fail closed, never guessed.
    """
    if not isinstance(raw, bytes):
        raise TypeError("raw_shard:bytes_required")
    if not final:
        if raw.count(STATE) != 1 or raw.count(RECORDS) != 1:
            raise ValueError("raw_shard:unsupported_or_ambiguous_state_markers")
        start = raw.index(STATE) + len(STATE)
        stop = raw.index(RECORDS)
        if start >= stop or raw[start:start+1] != b"{" or raw[stop-1:stop] != b"}":
            raise ValueError("raw_shard:unsupported_state_shape")
        single_object_boundary(raw[start:stop])
        raw = raw[:start] + b"null" + raw[stop:]
    part = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    keys = tuple(part) if isinstance(part, dict) else ()
    if keys[:len(KEYS)] != KEYS or any(k not in OPTIONAL_KEYS for k in keys[len(KEYS):]):
        raise ValueError("raw_shard:unsupported_top_level_schema_or_order")
    if (final and not isinstance(part["controller_state"], dict)) or (not final and part["controller_state"] is not None):
        raise ValueError("raw_shard:state_projection_mismatch")
    for key in ("control_records", "client_calls", "native_batches"):
        if not isinstance(part[key], list) or any(not isinstance(row, dict) for row in part[key]):
            raise ValueError("raw_shard:invalid_record_array")
    return part


def read_bound_shard(path, expected_sha256, *, final=False):
    """Hash compressed bytes and decompress from the same immutable byte image.

    Memory is bounded by one shard, not the whole run. Reading compressed bytes
    once avoids a time-of-check/read gap and a separate second disk pass.
    gzip.decompress validates gzip trailers/CRC and all concatenated members.
    """
    compressed = Path(path).read_bytes()
    if hashlib.sha256(compressed).hexdigest() != expected_sha256:
        raise ValueError("raw_shard:compressed_hash_mismatch")
    return decode_shard(gzip.decompress(compressed), final=final)
