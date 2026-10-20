"""Bounded incremental reader for persisted gzip JSON arrays, using stdlib only."""
from __future__ import annotations

import gzip
import json
import math


def _bad(reason):
    raise ValueError("airport_json_stream:" + reason)


def _finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        _bad("nonfinite_json_number")
    return value


def iter_json_array_gz(path, *, chunk_chars=1024*1024, max_item_chars=64*1024*1024):
    """Yield one array item at a time; exhaust to verify complete JSON/gzip tail.

    Limits are decoded Unicode characters, not compressed or network bytes.
    Memory is bounded by one decoded item plus at most its character limit and
    one input chunk. Earlier yielded items are not retained by this function.
    Parsing all items does not authorize consuming them as actor observations.
    """
    if type(chunk_chars) is not int or chunk_chars <= 0:
        _bad("positive_chunk_chars_required")
    if type(max_item_chars) is not int or max_item_chars <= 0:
        _bad("positive_max_item_chars_required")
    decoder = json.JSONDecoder(parse_float=_finite_float,
        parse_constant=lambda _: _bad("nonfinite_json_constant"))
    buffer, eof = "", False
    try:
        with gzip.open(path, "rt", encoding="utf8") as stream:
            def fill():
                nonlocal buffer, eof
                text = stream.read(min(chunk_chars, max_item_chars+1))
                if text:
                    buffer += text
                else:
                    eof = True

            def whitespace():
                nonlocal buffer
                while True:
                    buffer = buffer.lstrip(" \t\r\n")
                    if buffer or eof:
                        return
                    fill()

            whitespace()
            if not buffer.startswith("["):
                _bad("top_level_array_required")
            buffer = buffer[1:]
            after_comma = False
            while True:
                whitespace()
                if not buffer:
                    _bad("truncated_array")
                if buffer[0] == "]":
                    if after_comma:
                        _bad("trailing_comma")
                    buffer = buffer[1:]
                    whitespace()
                    if buffer:
                        _bad("trailing_data_after_array")
                    return
                while True:
                    try:
                        value, end = decoder.raw_decode(buffer)
                    except json.JSONDecodeError as exc:
                        if len(buffer) > max_item_chars:
                            _bad("item_character_limit_exceeded")
                        if eof:
                            raise ValueError("airport_json_stream:malformed_or_truncated_item") from exc
                        fill()
                        continue
                    if end > max_item_chars:
                        _bad("item_character_limit_exceeded")
                    # A number can legally continue in the next chunk. Do not
                    # accept a decoded prefix until its array delimiter exists.
                    remainder = buffer[end:].lstrip(" \t\r\n")
                    if not remainder or remainder[0] not in ",]":
                        if eof:
                            _bad("malformed_or_truncated_item_delimiter")
                        if len(buffer) > max_item_chars:
                            _bad("item_character_limit_exceeded")
                        fill()
                        continue
                    delimiter = remainder[0]
                    buffer = remainder[1:]
                    if delimiter == "]":
                        whitespace()
                        if buffer:
                            _bad("trailing_data_after_array")
                        yield value
                        return
                    after_comma = True
                    yield value
                    # Drop our previous decoded reference before reading again.
                    del value
                    break
    except (OSError, EOFError, UnicodeError) as exc:
        raise ValueError("airport_json_stream:invalid_gzip_or_utf8") from exc
