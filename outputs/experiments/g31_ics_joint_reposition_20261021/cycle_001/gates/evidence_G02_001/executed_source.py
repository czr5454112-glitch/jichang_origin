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
import io
import json
import math
from pathlib import Path
import sqlite3

SCHEMA = "g31.joint.observation_dag.v1"
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
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as stream:
        value = stream.read(MAX_OBJECT_BYTES + 1)
    _require(len(value) <= MAX_OBJECT_BYTES, "object_size_limit")
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

    def _list_root(self, nodes):
        pages = [self._put("list", canonical(nodes[start:start+self.page_size]))
            for start in range(0, len(nodes), self.page_size)]
        while len(pages) > 1:
            pages = [self._put("concat", canonical([identity.hex()
                for identity in pages[start:start+self.page_size]]))
                for start in range(0, len(pages), self.page_size)]
        return pages[0]

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
        _require(self.receipt.get("schema") == SCHEMA and self.receipt.get("status") == "sealed", "unsealed_store")
        _require(self.receipt["database_sha256"] == _file_hash(self.path), "database_digest")
        self.connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        self.connection.execute("PRAGMA cache_size=-8192")
        meta = dict(self.connection.execute("SELECT key, value FROM metadata"))
        _require(meta.get("schema") == SCHEMA and meta.get("status") == "sealed", "database_unsealed")
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
