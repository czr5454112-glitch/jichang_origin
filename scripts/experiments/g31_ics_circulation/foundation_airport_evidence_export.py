"""Entry-wise C JSON encoding for evaluator artifacts after control finishes.

Preserves the existing compact JSON bytes, gzip options, and close sequence.
This module never mutates evidence, drops history, or interacts with native code.
Temporary encoded text is bounded by one subtree, not by a fixed byte limit.
"""
from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
import time

OPTIONS = {"separators": (",", ":"), "allow_nan": False}


def iter_json_chunks(value, *, split_depth=3, stats=None):
    """Preserve standard compact JSON bytes; bound temporary text by one subtree.

    Depth 3 splits controller/client/outbox/request and ACK/owner/list/entry.
    This is NOT a universal byte cap: one exceptionally large depth-3 subtree
    still needs its own C-encoded string. max_chunk_bytes measures that exposure.
    No source container is mutated or copied. Default ensure_ascii=True makes
    every returned character one UTF-8 byte.
    """
    if type(split_depth) is not int or split_depth < 0:
        raise ValueError("export_prototype:nonnegative_split_depth")
    stats = {} if stats is None else stats
    stats.update(chunks=0, json_bytes=0, max_chunk_bytes=0, c_encoded_subtrees=0)
    ancestors = set()

    def record(chunk):
        size = len(chunk)
        stats["chunks"] += 1
        stats["json_bytes"] += size
        stats["max_chunk_bytes"] = max(stats["max_chunk_bytes"], size)
        return chunk

    def encode(item, depth):
        container = isinstance(item, (dict, list, tuple))
        if container and id(item) in ancestors:
            raise ValueError("Circular reference detected")
        if not container or depth >= split_depth:
            text = json.dumps(item, **OPTIONS)
            stats["c_encoded_subtrees"] += 1
            yield record(text)
            return
        ancestors.add(id(item))
        try:
            if isinstance(item, dict):
                yield record("{")
                first = True
                for key, child in item.items():
                    # Standard encoder performs all legal numeric/bool/null key
                    # conversions and rejects unsupported keys and nonfinite floats.
                    encoded_key = json.dumps({key: None}, **OPTIONS)[1:-6]
                    if not first:
                        yield record(",")
                    yield record(encoded_key)
                    yield record(":")
                    yield from encode(child, depth + 1)
                    first = False
                yield record("}")
            else:
                yield record("[")
                for position, child in enumerate(item):
                    if position:
                        yield record(",")
                    yield from encode(child, depth + 1)
                yield record("]")
        finally:
            ancestors.remove(id(item))
    yield from encode(value, 0)


def write_gzip_json(path, value, *, split_depth=3):
    """Same gzip options and TextIOWrapper closing sequence as runtime004."""
    stats = {}
    started = time.perf_counter()
    with Path(path).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1, mtime=0) as stream:
            with io.TextIOWrapper(stream, encoding="utf-8", newline="") as text:
                for chunk in iter_json_chunks(value, split_depth=split_depth, stats=stats):
                    text.write(chunk)
    stats.update(wall_seconds=time.perf_counter()-started,
                 gzip_bytes=Path(path).stat().st_size, split_depth=split_depth,
                 temporary_text_bound="one subtree at configured split_depth; measured; not a hard byte cap")
    return stats

