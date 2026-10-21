"""Lossless, bounded-memory observation DAGs in an append-only SQLite store.

Only this new evidence representation changes. Public observations, their
canonical digests and old artifacts remain unchanged. Sealing certifies the
accepted evidence frames, never completion of the native experiment itself.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import zlib

SCHEMA = "g31.joint.observation_dag.v2"
READABLE_SCHEMAS = {SCHEMA, "g31.joint.observation_dag.v1"}
ZERO = "0" * 64
MAX_OBJECT_BYTES = 64 * 1024 * 1024


def _require(condition, reason):
    if not condition:
        raise ValueError("joint_evidence:" + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf8")


def public_digest(observation):
    return hashlib.sha256(canonical(observation)).hexdigest()


def _object_hash(kind, payload):
    value = hashlib.sha256(kind.encode("ascii") + b"\0")
    value.update(payload)
    return value.digest()


def _file_hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _unpack(blob):
    decoder = zlib.decompressobj(wbits=31)
    value = decoder.decompress(blob, MAX_OBJECT_BYTES + 1)
    _require(len(value) <= MAX_OBJECT_BYTES, "object_size_limit")
    _require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
        "incomplete_or_trailing_compressed_object")
    return value


def _atomic_json(path, value):
    path = Path(path)
    _require(not path.exists(), "receipt_already_exists")
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())
    temporary.replace(path)


def _frame_digest(index, root_hash, observation_digest, metadata_digest, previous):
    return hashlib.sha256(canonical([index, root_hash, observation_digest,
        metadata_digest, previous])).hexdigest()


class ObservationStore:
    """Append complete frames transactionally, sharing immutable row/page chunks.

    ``extend([{digest, observation, ...metadata}])`` replaces the old observation
    stream API. A write encodes each leaf once and uses those same canonical
    bytes to verify the original full-observation digest. No per-action work or
    persistent raw-observation cache is performed. The LRU stores hashes only.
    """
    def __init__(self, path, *, page_size=128, index_cache_entries=16384, compresslevel=1):
        self.path = Path(path)
        _require(type(page_size) is int and 2 <= page_size <= 1024, "page_size")
        _require(type(index_cache_entries) is int and index_cache_entries >= 0, "index_cache_entries")
        _require(type(compresslevel) is int and 0 <= compresslevel <= 9, "compression_level")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents replacing an earlier experiment's store.
        with self.path.open("xb"):
            pass
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA cache_size=-8192")
        self.connection.executescript("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE objects (hash BLOB PRIMARY KEY, kind TEXT NOT NULL,
                raw_bytes INTEGER NOT NULL, payload BLOB NOT NULL) WITHOUT ROWID;
            CREATE TABLE frames (sequence INTEGER PRIMARY KEY, root_hash BLOB NOT NULL,
                observation_digest TEXT NOT NULL, metadata_digest TEXT NOT NULL,
                metadata BLOB NOT NULL, previous_digest TEXT NOT NULL, frame_digest TEXT NOT NULL);
        """)
        self.connection.executemany("INSERT INTO metadata VALUES (?, ?)", [
            ("schema", SCHEMA), ("status", "writing"), ("page_size", str(page_size))])
        self.connection.commit()
        self.page_size = page_size
        self.index_cache_entries = index_cache_entries
        self.compresslevel = compresslevel
        self.seen = OrderedDict()
        self.count = 0
        self.tail_digest = ZERO
        self.closed = False
        self.failed = False
        self.receipt = None
        self.stats = dict(object_visits=0, object_insertions=0, index_cache_hits=0,
            sqlite_dedup_hits=0, canonical_observation_bytes=0, max_index_cache_entries=0)

    def _remember(self, identity):
        if not self.index_cache_entries:
            return
        self.seen[identity] = None
        self.seen.move_to_end(identity)
        if len(self.seen) > self.index_cache_entries:
            self.seen.popitem(last=False)
        self.stats["max_index_cache_entries"] = max(self.stats["max_index_cache_entries"], len(self.seen))

    def _put(self, kind, payload):
        _require(len(payload) <= MAX_OBJECT_BYTES, "object_size_limit")
        identity = _object_hash(kind, payload)
        self.stats["object_visits"] += 1
        if identity in self.seen:
            self.stats["index_cache_hits"] += 1
            self.seen.move_to_end(identity)
            return identity
        if self.connection.execute("SELECT 1 FROM objects WHERE hash=?", (identity,)).fetchone():
            self.stats["sqlite_dedup_hits"] += 1
        else:
            self.connection.execute("INSERT INTO objects VALUES (?, ?, ?, ?)",
                (identity, kind, len(payload), gzip.compress(payload,
                    compresslevel=self.compresslevel, mtime=0)))
            self.stats["object_insertions"] += 1
        self._remember(identity)
        return identity

    def _combine_pages(self, pages):
        while len(pages) > 1:
            pages = [self._put("concat", canonical([identity.hex()
                for identity in pages[start:start+self.page_size]]))
                for start in range(0, len(pages), self.page_size)]
        return pages[0]

    def _list_root(self, nodes):
        return self._combine_pages([self._put("list", canonical(nodes[start:start+self.page_size]))
            for start in range(0, len(nodes), self.page_size)])

    def _primitive_column(self, raw_values):
        if not raw_values:
            return self._put("raw", b"[]")
        return self._combine_pages([self._put("raw", b"[" + b",".join(raw_values[start:start+self.page_size]) + b"]")
            for start in range(0, len(raw_values), self.page_size)])

    def _table(self, rows, keys):
        # Changing per-capture demand_observed_at/fifo indexes otherwise creates
        # a new near-identical chunk for every job. Columns share the unchanged
        # job facts and compress those repeated timestamps without losing them.
        columns = [[] for key in keys]
        key_bytes = [canonical(key) for key in keys]
        row_bytes = []
        for row in rows:
            parts = []
            for index, key in enumerate(keys):
                raw = canonical(row[key])
                columns[index].append(raw)
                parts.append(key_bytes[index] + b":" + raw)
            row_bytes.append(b"{" + b",".join(parts) + b"}")
        descriptor = dict(keys=keys, count=len(rows),
            columns=[self._primitive_column(column).hex() for column in columns])
        return ["r", self._put("table", canonical(descriptor)).hex()], b"[" + b",".join(row_bytes) + b"]"

    def _encode(self, value, depth=0):
        _require(depth <= 128, "observation_nesting_limit")
        if isinstance(value, dict):
            _require(all(type(key) is str for key in value), "string_object_keys")
            if not any(isinstance(item, (dict, list, tuple)) for item in value.values()):
                raw = canonical(value)
                return ["r", self._put("raw", raw).hex()], raw
            nodes, parts = [], []
            for key in sorted(value):
                node, raw = self._encode(value[key], depth+1)
                nodes.append([key, node])
                parts.append(canonical(key) + b":" + raw)
            encoded = b"{" + b",".join(parts) + b"}"
            return ["r", self._put("dict", canonical(nodes)).hex()], encoded
        if isinstance(value, (list, tuple)):
            if len(value) >= 2 and all(isinstance(row, dict) for row in value):
                keys = sorted(value[0])
                if all(set(row) == set(keys) and all(type(row[key]) in
                        (str, int, float, bool, type(None)) for key in keys) for row in value):
                    return self._table(value, keys)
            if len(value) <= self.page_size and not any(isinstance(item, (dict, list, tuple)) for item in value):
                raw = canonical(value)
                return ["r", self._put("raw", raw).hex()], raw
            nodes, parts = [], []
            for item in value:
                node, raw = self._encode(item, depth+1)
                nodes.append(node); parts.append(raw)
            identity = self._list_root(nodes)
            return ["r", identity.hex()], b"[" + b",".join(parts) + b"]"
        _require(type(value) in (str, int, float, bool, type(None)), "json_values_only")
        if type(value) is float:
            _require(math.isfinite(value), "finite_json_numbers")
        return ["v", value], canonical(value)

    def write(self, observation, *, expected_digest=None, metadata=None):
        _require(not self.closed and not self.failed, "writer_not_open")
        _require(isinstance(observation, dict), "observation_object")
        metadata = {} if metadata is None else metadata
        _require(isinstance(metadata, dict) and not {"digest", "observation"} & set(metadata), "frame_metadata")
        try:
            with self.connection:
                reference, raw = self._encode(observation)
                observed = hashlib.sha256(raw).hexdigest()
                _require(expected_digest is None or expected_digest == observed, "original_public_digest_mismatch")
                meta_raw = canonical(metadata)
                meta_digest = hashlib.sha256(meta_raw).hexdigest()
                frame_hash = _frame_digest(self.count, reference[1], observed, meta_digest, self.tail_digest)
                self.connection.execute("INSERT INTO frames VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (self.count, bytes.fromhex(reference[1]), observed, meta_digest,
                        gzip.compress(meta_raw, compresslevel=self.compresslevel, mtime=0),
                        self.tail_digest, frame_hash))
            self.stats["canonical_observation_bytes"] += len(raw)
            self.count += 1
            self.tail_digest = frame_hash
            return dict(sequence=self.count-1, digest=observed, root_hash=reference[1], frame_digest=frame_hash)
        except BaseException:
            self.failed = True
            self.seen.clear()  # Rolled-back chunks must never survive in the index.
            raise

    def extend(self, records):
        for record in records:
            _require(isinstance(record, dict) and "observation" in record, "observation_record")
            self.write(record["observation"], expected_digest=record.get("digest"),
                metadata={key: value for key, value in record.items() if key not in ("digest", "observation")})

    def flush(self):
        _require(not self.closed and not self.failed, "writer_not_open")
        self.connection.commit()
        self.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def close(self, *, complete=True):
        if self.closed:
            return self.receipt
        sealed = bool(complete and not self.failed)
        with self.connection:
            self.connection.execute("UPDATE metadata SET value=? WHERE key='status'", ("sealed" if sealed else "aborted",))
            self.connection.executemany("INSERT INTO metadata VALUES (?, ?)",
                [("frame_count", str(self.count)), ("tail_digest", self.tail_digest)])
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        objects, raw_bytes, compressed_bytes = self.connection.execute(
            "SELECT count(*), coalesce(sum(raw_bytes), 0), coalesce(sum(length(payload)), 0) FROM objects").fetchone()
        self.connection.close(); self.closed = True; self.seen.clear()
        self.receipt = dict(schema=SCHEMA, status="sealed" if sealed else "aborted", database=self.path.name,
            database_sha256=_file_hash(self.path), database_bytes=self.path.stat().st_size,
            frame_count=self.count, tail_digest=self.tail_digest, object_count=objects,
            unique_object_raw_bytes=raw_bytes, unique_object_compressed_bytes=compressed_bytes,
            stats=self.stats, page_size=self.page_size, index_cache_entries=self.index_cache_entries,
            closed_at_utc=datetime.now(timezone.utc).isoformat(),
            completeness_scope="only frames accepted by this writer; not native trajectory completion",
            full_observation_digest_verified_on_each_write=True)
        _atomic_json(self.path.with_suffix(self.path.suffix + ".receipt.json"), self.receipt)
        return self.receipt

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        self.close(complete=kind is None)


class ObservationReader:
    """Validate immutable chunks on access; cache bytes, never mutable objects."""
    def __init__(self, path, *, receipt=None, cache_bytes=8*1024*1024):
        self.path = Path(path)
        self.receipt = (json.loads(self.path.with_suffix(self.path.suffix + ".receipt.json").read_text(encoding="utf8"))
            if receipt is None else receipt)
        _require(self.receipt.get("schema") in READABLE_SCHEMAS and self.receipt.get("status") == "sealed", "unsealed_store")
        _require(self.receipt["database_sha256"] == _file_hash(self.path), "database_digest")
        self.connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        self.connection.execute("PRAGMA cache_size=-8192")
        meta = dict(self.connection.execute("SELECT key, value FROM metadata"))
        _require(meta.get("schema") == self.receipt["schema"] and meta.get("status") == "sealed", "database_unsealed")
        _require(int(meta["frame_count"]) == self.receipt["frame_count"]
            and meta["tail_digest"] == self.receipt["tail_digest"], "receipt_frame_binding")
        _require(type(cache_bytes) is int and cache_bytes >= 0, "reader_cache_bytes")
        self.cache_limit = cache_bytes
        self.cache = OrderedDict(); self.cache_size = 0

    def _object(self, identity):
        _require(type(identity) is str and len(identity) == 64, "chunk_reference")
        if identity in self.cache:
            self.cache.move_to_end(identity)
            return self.cache[identity]
        row = self.connection.execute("SELECT kind, raw_bytes, payload FROM objects WHERE hash=?",
            (bytes.fromhex(identity),)).fetchone()
        _require(row is not None, "missing_chunk:" + identity)
        kind, size, blob = row
        payload = _unpack(blob)
        _require(len(payload) == size and _object_hash(kind, payload).hex() == identity, "chunk_digest:" + identity)
        if len(payload) <= self.cache_limit:
            while self.cache and self.cache_size + len(payload) > self.cache_limit:
                _, (_, old) = self.cache.popitem(last=False); self.cache_size -= len(old)
            self.cache[identity] = (kind, payload); self.cache_size += len(payload)
        return kind, payload

    def _node(self, node, depth=0):
        _require(depth <= 128 and isinstance(node, list) and len(node) == 2, "encoded_node")
        if node[0] == "v":
            _require(type(node[1]) in (str, int, float, bool, type(None)), "inline_scalar")
            return node[1]
        _require(node[0] == "r", "encoded_reference")
        kind, payload = self._object(node[1]); decoded = json.loads(payload)
        if kind == "raw":
            return decoded
        if kind == "dict":
            _require(isinstance(decoded, list) and all(isinstance(pair, list) and len(pair) == 2
                and type(pair[0]) is str for pair in decoded), "dictionary_chunk")
            _require(len({pair[0] for pair in decoded}) == len(decoded), "duplicate_dictionary_key")
            return {key: self._node(child, depth+1) for key, child in decoded}
        if kind == "list":
            _require(isinstance(decoded, list), "list_chunk")
            return [self._node(child, depth+1) for child in decoded]
        if kind == "table":
            _require(isinstance(decoded, dict) and type(decoded.get("count")) is int
                and decoded["count"] >= 0 and isinstance(decoded.get("keys"), list)
                and isinstance(decoded.get("columns"), list)
                and len(decoded["keys"]) == len(decoded["columns"])
                and all(type(key) is str for key in decoded["keys"])
                and len(set(decoded["keys"])) == len(decoded["keys"]), "table_chunk")
            columns = [self._node(["r", identity], depth+1) for identity in decoded["columns"]]
            _require(all(isinstance(column, list) and len(column) == decoded["count"] for column in columns),
                "table_column_length")
            return [{key: columns[index][row] for index, key in enumerate(decoded["keys"])}
                for row in range(decoded["count"])]
        _require(kind == "concat" and isinstance(decoded, list), "chunk_kind")
        result = []
        for identity in decoded:
            part = self._node(["r", identity], depth+1)
            _require(isinstance(part, list), "list_page_required")
            result.extend(part)
        return result

    def read(self, sequence):
        row = self.connection.execute("""SELECT root_hash, observation_digest, metadata_digest, metadata,
            previous_digest, frame_digest FROM frames WHERE sequence=?""", (sequence,)).fetchone()
        _require(row is not None, "missing_frame")
        root, expected, metadata_digest, metadata_blob, previous, frame_hash = row
        _require(frame_hash == _frame_digest(sequence, root.hex(), expected, metadata_digest, previous), "frame_digest")
        metadata_raw = _unpack(metadata_blob)
        _require(hashlib.sha256(metadata_raw).hexdigest() == metadata_digest, "frame_metadata_digest")
        metadata = json.loads(metadata_raw)
        _require(isinstance(metadata, dict) and not {"digest", "observation"} & set(metadata), "frame_metadata")
        observation = self._node(["r", root.hex()])
        _require(isinstance(observation, dict) and public_digest(observation) == expected, "reconstructed_public_digest")
        return {**metadata, "digest": expected, "observation": observation}

    def __iter__(self):
        for index in range(self.receipt["frame_count"]):
            yield self.read(index)

    def close(self):
        self.connection.close(); self.cache.clear(); self.cache_size = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def audit_store(path, *, receipt=None):
    """Validate all chunks, ordering and every reconstructed observation."""
    with ObservationReader(path, receipt=receipt) as reader:
        _require(reader.connection.execute("PRAGMA quick_check").fetchone()[0] == "ok", "sqlite_integrity")
        objects = 0
        for (identity,) in reader.connection.execute("SELECT hash FROM objects"):
            reader._object(identity.hex()); objects += 1
        _require(objects == reader.receipt["object_count"], "object_count")
        previous = ZERO; count = 0
        for index, prior, frame_hash in reader.connection.execute(
                "SELECT sequence, previous_digest, frame_digest FROM frames ORDER BY sequence"):
            _require(index == count and prior == previous, "frame_sequence_or_chain")
            reader.read(index)
            count += 1; previous = frame_hash
        _require(count == reader.receipt["frame_count"] and previous == reader.receipt["tail_digest"], "frame_count_or_tail")
        return dict(schema=SCHEMA + ".audit", status="all_chunks_and_observations_verified",
            frame_count=count, object_count=objects, tail_digest=previous,
            database_sha256=reader.receipt["database_sha256"], original_public_digests_conserved=True,
            native_run_completion_certified=False)


def compare_gzip(source, directory):
    """Read-only offline comparison against a preserved old observation stream."""
    import itertools
    import statistics
    import time
    from .foundation_airport_json_stream import iter_json_array_gz
    from .foundation_airport_inventory_spi_campaign import JsonArrayStream
    source, directory = Path(source), Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    source_hash = _file_hash(source)
    module_hash = _file_hash(__file__)
    source_copy = directory / "executed_source.py"
    source_copy.write_bytes(Path(__file__).read_bytes())
    legacy_times, shared_times = [], []
    began = time.monotonic()
    store = ObservationStore(directory / "observations.sqlite")
    legacy = JsonArrayStream(directory / "legacy_reencoded.json.gz")
    try:
        for row in iter_json_array_gz(source):
            tick = time.perf_counter(); legacy.extend([row]); legacy_times.append(time.perf_counter()-tick)
            tick = time.perf_counter(); store.extend([row]); shared_times.append(time.perf_counter()-tick)
        legacy.close(); receipt = store.close()
    except BaseException:
        legacy.close(); store.close(complete=False)
        raise
    write_wall = time.monotonic()-began
    tick = time.monotonic(); audit = audit_store(store.path); audit_seconds = time.monotonic()-tick
    tick = time.monotonic(); compared = 0
    with ObservationReader(store.path) as reader:
        for original, recovered in itertools.zip_longest(iter_json_array_gz(source), reader):
            _require(original == recovered, "offline_original_record_mismatch")
            compared += 1
    comparison_seconds = time.monotonic()-tick
    _require(_file_hash(source) == source_hash and _file_hash(__file__) == module_hash, "comparison_input_or_source_changed")
    def timing(values):
        return dict(sum_seconds=sum(values), p50_ms=1000*statistics.median(values) if values else None,
            p95_ms=1000*sorted(values)[int(.95*(len(values)-1))] if values else None,
            max_ms=1000*max(values) if values else None)
    result = dict(schema=SCHEMA + ".comparison", source=str(source), source_sha256=source_hash,
        source_module_sha256=module_hash, original_bytes=source.stat().st_size,
        legacy_reencoded_bytes=(directory/"legacy_reencoded.json.gz").stat().st_size,
        dag_database_bytes=store.path.stat().st_size,
        dag_receipt_bytes=store.path.with_suffix(".sqlite.receipt.json").stat().st_size,
        frames=compared, original_full_records_compared=compared, all_equal=True,
        source_unchanged=True, native_starts=0, legacy_write=timing(legacy_times), dag_write=timing(shared_times),
        write_wall_seconds_including_input_decode_and_both_writers=write_wall,
        audit_seconds=audit_seconds, source_vs_reconstruction_seconds=comparison_seconds,
        stats=receipt["stats"], audit=audit)
    _atomic_json(directory/"comparison.json", result)
    return result
