"""Offline, bounded-memory comparison of complete controller/native evidence.

This is a comparison of saved executions, not an execution or a proof that a
source refactor is generally semantics preserving. No history is truncated.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from .foundation_airport_inventory_spi_audit import read, sha, _ref, _bound, digest, ACTOR_SOURCE_FILES

SCHEMA = "g31.inventory_spi_streaming_equivalence.v1"
FILES = {
    "final_result.json.gz": (("advance", "wall_seconds"),),
    "controller_final_state.json.gz": (),
    "client_calls.json.gz": (("*", "submit_compute_ms"),),
    "control_records.json.gz": (
        ("*", "preparation_compute_ms"),
        ("*", "offline_tick_start_observer_ms"),
        ("*", "owner_decisions", "*", "compute_ms"),
        ("*", "owner_decisions", "*", "offline_evaluator_ms"),
        ("*", "owner_decisions", "*", "inventory_return", "offline_evaluator_ms"),
    ),
    "ack_views.json.gz": (),
    "inventory_snapshot_reads.json.gz": (("*", "endpoint_read_ms"), ("*", "byte_measurement_ms")),
}
_WS = re.compile(r"[ \t\r\n]*")


def require(ok, reason):
    if not ok:
        raise ValueError("inventory_spi_equivalence:" + reason)


def _finite(value):
    number = float(value)
    require(math.isfinite(number), "nonfinite_number")
    return number


def _constant(_):
    raise ValueError("inventory_spi_equivalence:nonfinite_constant")


def _hash(tag, value=b""):
    return hashlib.sha256(tag + value).digest()


class _TreeReader:
    """One JSON token plus one object's child hashes, never a decoded history."""

    def __init__(self, stream, patterns, chunk_chars, max_token_chars, max_object_keys):
        self.stream = stream
        self.patterns = patterns
        self.chunk = chunk_chars
        self.max_token = max_token_chars
        self.max_keys = max_object_keys
        self.buffer, self.pos, self.eof = "", 0, False
        self.decoder = json.JSONDecoder(parse_float=_finite, parse_constant=_constant)
        self.counts = Counter()
        self.ignored = Counter()
        self.peak_keys = 0
        self.read_chars = 0
        self.top_level_children = {}

    def fill(self):
        self.buffer = self.buffer[self.pos:]
        self.pos = 0
        piece = self.stream.read(self.chunk)
        self.read_chars += len(piece)
        self.buffer += piece
        self.eof = not piece

    def peek(self):
        while True:
            self.pos = _WS.match(self.buffer, self.pos).end()
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if self.eof:
                return ""
            self.fill()

    def token(self):
        """Decode one primitive, checking its complete lexical delimiter."""
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError as exc:
                require(len(self.buffer)-self.pos <= self.max_token, "token_character_limit")
                if self.eof:
                    raise ValueError("inventory_spi_equivalence:malformed_or_truncated_token") from exc
                self.fill()
                continue
            require(end-self.pos <= self.max_token, "token_character_limit")
            if end == len(self.buffer) and not self.eof:
                self.fill()
                continue
            if end < len(self.buffer) and self.buffer[end] not in " \t\r\n,:]}":
                require(len(self.buffer)-self.pos <= self.max_token, "token_character_limit")
                if not self.eof:
                    self.fill()
                    continue
                require(False, "invalid_token_delimiter")
            self.pos = end
            return value

    def ignored_pattern(self, path):
        for pattern in self.patterns:
            if len(path) == len(pattern) and all(
                    expected == actual or expected == "*" and type(actual) is int
                    for expected, actual in zip(pattern, path)):
                return "/".join(pattern)
        return None

    def value(self, path=(), depth=0):
        require(depth <= 256, "json_depth_limit")
        first = self.peek()
        require(bool(first), "truncated_value")
        if first == "{":
            self.pos += 1
            fields = {}
            if self.peek() != "}":
                while True:
                    require(self.peek() == '"', "object_key_required")
                    key = self.token()
                    require(type(key) is str and key not in fields, "unique_object_key_required")
                    require(len(fields) < self.max_keys, "object_key_limit")
                    require(self.peek() == ":", "object_colon_required")
                    self.pos += 1
                    child_hash, child_type, numeric = self.value(path+(key,), depth+1)
                    ignored = self.ignored_pattern(path+(key,))
                    if ignored:
                        require(child_type == "number" and numeric, "ignored_timing_must_be_finite_number")
                        self.ignored[ignored] += 1
                        fields[key] = None  # retain duplicate detection, omit from canonical value
                    else:
                        fields[key] = child_hash
                    punctuation = self.peek()
                    if punctuation == "}":
                        break
                    require(punctuation == ",", "object_separator_required")
                    self.pos += 1
                    require(self.peek() != "}", "object_trailing_comma")
            self.pos += 1
            self.peak_keys = max(self.peak_keys, len(fields))
            hashed = hashlib.sha256(b"object\0")
            for key in sorted(fields):
                if fields[key] is None:
                    continue
                encoded = key.encode("utf-8")
                hashed.update(len(encoded).to_bytes(8, "big"))
                hashed.update(encoded)
                hashed.update(fields[key])
            if not path:
                self.top_level_children = {key: value.hex() for key, value in fields.items() if value is not None}
            self.counts["objects"] += 1
            return hashed.digest(), "object", False
        if first == "[":
            self.pos += 1
            hashed = hashlib.sha256(b"array\0")
            count = 0
            if self.peek() != "]":
                while True:
                    child_hash, _, _ = self.value(path+(count,), depth+1)
                    hashed.update(child_hash)
                    count += 1
                    punctuation = self.peek()
                    if punctuation == "]":
                        break
                    require(punctuation == ",", "array_separator_required")
                    self.pos += 1
                    require(self.peek() != "]", "array_trailing_comma")
            self.pos += 1
            hashed.update(count.to_bytes(8, "big"))
            if not path:
                self.counts["top_level_array_items"] = count
            self.counts["arrays"] += 1
            return hashed.digest(), "array", False
        value = self.token()
        require(not isinstance(value, (list, dict)), "primitive_expected")
        kind = ("number" if type(value) in (int, float) else
                "boolean" if type(value) is bool else "null" if value is None else "string")
        self.counts[kind] += 1
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()
        return _hash(b"primitive\0", encoded), kind, kind == "number"


def canonical_json_gz(path, *, ignored_paths=(), chunk_chars=1024*1024,
                      max_token_chars=16*1024*1024, max_object_keys=1000000):
    """Return a domain-separated tree hash; this is not SHA of JSON text.

    Object insertion order/whitespace are immaterial; array order, numeric
    representation after standard JSON decoding, and all non-timing data count.
    Memory is bounded by token/chunk limits and child hashes of open objects.
    """
    require(all(type(n) is int and n > 0 for n in (chunk_chars, max_token_chars, max_object_keys)),
            "positive_parser_limits")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            parser = _TreeReader(stream, tuple(ignored_paths), chunk_chars, max_token_chars, max_object_keys)
            hashed, kind, _ = parser.value()
            require(parser.peek() == "" and parser.eof, "trailing_data_after_document")
    except (OSError, EOFError, UnicodeError) as exc:
        raise ValueError("inventory_spi_equivalence:invalid_gzip_or_utf8") from exc
    return {"canonical_tree_sha256": hashed.hex(), "root_type": kind,
        "parsed_counts": dict(parser.counts), "ignored_timing_counts": dict(parser.ignored),
        "top_level_child_hashes": parser.top_level_children,
        "decoded_characters": parser.read_chars, "maximum_single_object_keys": parser.peak_keys,
        "complete_json_and_gzip_tail_consumed": True,
        "algorithm": "sha256 domain-separated recursive JSON tree v1"}


def _file_comparison(left, right, patterns):
    output = {"left": _ref(left), "right": _ref(right),
              "ignored_paths": [list(p) for p in patterns]}
    a = canonical_json_gz(left, ignored_paths=patterns)
    b = canonical_json_gz(right, ignored_paths=patterns)
    expected_root = "object" if left.name in (
        "final_result.json.gz", "controller_final_state.json.gz", "ack_views.json.gz") else "array"
    require(a["root_type"] == b["root_type"] == expected_root, "artifact_root_type")
    require(sha(left) == output["left"]["sha256"] and sha(right) == output["right"]["sha256"],
            "evidence_changed_during_comparison")
    output.update(left_canonical=a, right_canonical=b,
                  canonical_equal=a["canonical_tree_sha256"] == b["canonical_tree_sha256"],
                  identical_raw_gzip_bytes=output["left"]["sha256"] == output["right"]["sha256"],
                  ignored_timing_field_counts_equal=a["ignored_timing_counts"] == b["ignored_timing_counts"],
                  different_top_level_fields=sorted(key for key in
                    a["top_level_child_hashes"].keys() | b["top_level_child_hashes"].keys()
                    if a["top_level_child_hashes"].get(key) != b["top_level_child_hashes"].get(key)))
    return output


def compare_closed_runs(left_directory, right_directory):
    """Require both final receipts before reading plans or any large evidence."""
    directories = [Path(left_directory), Path(right_directory)]
    receipts = []
    for directory in directories:
        require((directory/"receipt.json").is_file(), "both_runs_must_be_closed")
        receipt = read(directory/"receipt.json")
        require(receipt.get("status") == "complete", "both_runs_must_be_complete")
        require(receipt.get("worker", {}).get("status") == "complete", "worker_completion_required")
        receipts.append(receipt)
    plans = []
    for directory, receipt in zip(directories, receipts):
        require(sha(directory/"plan.json") == receipt["plan_sha256"], "receipt_plan_binding")
        plans.append(read(directory/"plan.json"))
    keys = ("parent", "method", "input_semantic_sha256", "controller", "controller_identity",
            "activate_at", "horizon", "cost_window", "event_budget", "global_event_budget",
            "pair", "model", "behavior_model", "rule", "forecast_binding")
    mismatch = [key for key in keys if plans[0].get(key) != plans[1].get(key)]
    require(plans[0]["binary"]["sha256"] == plans[1]["binary"]["sha256"], "common_native_binary")
    require(not mismatch, "execution_contract_mismatch:" + ",".join(mismatch))
    source = [_bound(plan["source_bundle"]) for plan in plans]
    source_files = [item["files"] for item in source]
    for plan, manifest in zip(plans, source):
        require(plan["source_manifest_sha256"] == manifest["source_manifest_sha256"]
                == digest(manifest["files"]), "source_manifest_content_binding")
        require(sha(plan["binary"]["path"]) == plan["binary"]["sha256"], "actual_binary_bytes")
        require(digest(_bound(plan["input"])) == plan["input_semantic_sha256"], "actual_input_bytes")
    actor_maps = [{key: files[key] for key in ACTOR_SOURCE_FILES if key in files} for files in source_files]
    output = {"schema": SCHEMA, "status": "pending", "run_names": [p.name for p in directories],
        "receipts": [_ref(p/"receipt.json") for p in directories],
        "plans": [_ref(p/"plan.json") for p in directories],
        "same_binary_sha256": plans[0]["binary"]["sha256"],
        "full_source_manifest_equal": plans[0]["source_manifest_sha256"] == plans[1]["source_manifest_sha256"],
        "different_source_paths": sorted(key for key in source_files[0].keys() | source_files[1].keys()
                                        if source_files[0].get(key) != source_files[1].get(key)),
        "actor_source_hashes_from_bound_manifests": actor_maps,
        "fixed_actor_source_subset_equal": actor_maps[0] == actor_maps[1] if all(
            len(item) == len(ACTOR_SOURCE_FILES) for item in actor_maps) else None,
        "actor_source_scope": "registered core file subset from bound manifests; not full source closure",
        "source_only_ownership_change_proven_by_this_tool": False,
        "strict_same_source_comparison": False, "files": {}, "errors": [], "missing_evidence": [],
        "all_history_preserved_in_comparison": True, "native_starts": 0, "fits": 0,
        "physical_correctness_or_cost_certified_by_this_tool": False,
        "requires_independent_cost_and_invariant_audit": True,
        "implementation": _ref(Path(__file__)),
        "scope": "complete saved execution equivalence on one registered scenario; no general refactor or policy benefit proof"}
    for filename, patterns in FILES.items():
        paths = [directory/filename for directory in directories]
        if not all(path.is_file() for path in paths):
            output["missing_evidence"].append(filename)
            continue
        try:
            output["files"][filename] = _file_comparison(*paths, patterns)
        except (ValueError, KeyError, TypeError) as exc:
            output["errors"].append({"file": filename, "error": str(exc)})
    verified = (not output["errors"] and not output["missing_evidence"]
                and len(output["files"]) == len(FILES))
    matched = verified and all(row["canonical_equal"] and row["ignored_timing_field_counts_equal"]
                               for row in output["files"].values())
    output["status"] = ("complete_canonical_execution_equal" if matched else
                        "complete_execution_difference" if verified else "unknown_missing_or_invalid_evidence")
    output["strict_same_source_comparison"] = matched and output["full_source_manifest_equal"]
    return output
