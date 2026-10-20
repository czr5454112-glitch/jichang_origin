"""Pure saved-artifact fixtures; no native execution or real run reads."""
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_equivalence as eq


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
    return {"path": str(path), "sha256": eq.sha(path)}


@pytest.mark.parametrize("chunk", [1, 7, 1048576])
def test_chunk_boundaries_unicode_numbers_and_key_order_are_canonical(tmp_path, chunk):
    a = tmp_path/"a.json.gz"
    b = tmp_path/"b.json.gz"
    a.write_bytes(gzip.compress(b'{"unicode":"\\u673a\\u573a","n":1.2e-10,"nested":[true,null,{"x":"a\\\\b\\\"c"}]}'))
    write(b, {"nested": [True, None, {"x": 'a\\b"c'}], "n": 1.2e-10, "unicode": "机场"})
    first = eq.canonical_json_gz(a, chunk_chars=chunk)
    second = eq.canonical_json_gz(b, chunk_chars=chunk)
    assert first["canonical_tree_sha256"] == second["canonical_tree_sha256"]
    assert first["complete_json_and_gzip_tail_consumed"] is True


@pytest.mark.parametrize("raw", [
    b'{"x":1,}', b'[1,]', b'{"x":1,"x":2}', b'{"x":', b'[1] garbage',
    b'[NaN]', b'[Infinity]', b'[1e9999]', b'[00]', b'{"x" 1}', b'',
])
def test_malformed_documents_are_rejected(tmp_path, raw):
    path = tmp_path/"bad.json.gz"
    path.write_bytes(gzip.compress(raw))
    with pytest.raises(ValueError, match="inventory_spi_equivalence"):
        eq.canonical_json_gz(path, chunk_chars=1)


def test_gzip_tail_and_limits_are_not_silently_accepted(tmp_path):
    path = tmp_path/"limits.json.gz"
    write(path, {"long": "x"*200})
    with pytest.raises(ValueError, match="token_character_limit"):
        eq.canonical_json_gz(path, chunk_chars=16, max_token_chars=64)
    write(path, {"a": 1, "b": 2})
    with pytest.raises(ValueError, match="object_key_limit"):
        eq.canonical_json_gz(path, max_object_keys=1)
    path.write_bytes(path.read_bytes()[:-3])
    with pytest.raises(ValueError, match="invalid_gzip"):
        eq.canonical_json_gz(path)


def test_only_fixed_path_timing_number_is_ignored(tmp_path):
    a, b = tmp_path/"a.gz", tmp_path/"b.gz"
    write(a, [{"at": 1., "submit_compute_ms": 10., "request": {"submit_compute_ms": 7.}}])
    write(b, [{"at": 1., "submit_compute_ms": 99., "request": {"submit_compute_ms": 7.}}])
    patterns = eq.FILES["client_calls.json.gz"]
    first, second = [eq.canonical_json_gz(path, ignored_paths=patterns) for path in (a, b)]
    assert first["canonical_tree_sha256"] == second["canonical_tree_sha256"]
    assert first["ignored_timing_counts"] == {"*/submit_compute_ms": 1}
    write(b, [{"at": 1., "submit_compute_ms": 99., "request": {"submit_compute_ms": 8.}}])
    assert first["canonical_tree_sha256"] != eq.canonical_json_gz(b, ignored_paths=patterns)["canonical_tree_sha256"]
    write(b, [{"at": 1., "submit_compute_ms": {"not_a_timing": 1}}])
    with pytest.raises(ValueError, match="ignored_timing_must_be_finite_number"):
        eq.canonical_json_gz(b, ignored_paths=patterns)


def test_history_order_and_late_history_change_are_detected(tmp_path):
    a, b = tmp_path/"a.gz", tmp_path/"b.gz"
    write(a, {"client": {"outbox": {"r": {"payload": {"n": 1}, "terminal": True}}}, "events": [1, 2]})
    write(b, {"client": {"outbox": {"r": {"payload": {"n": 2}, "terminal": True}}}, "events": [1, 2]})
    first = eq.canonical_json_gz(a)
    assert first["canonical_tree_sha256"] != eq.canonical_json_gz(b)["canonical_tree_sha256"]
    write(b, {"client": {"outbox": {"r": {"payload": {"n": 1}, "terminal": True}}}, "events": [2, 1]})
    assert first["canonical_tree_sha256"] != eq.canonical_json_gz(b)["canonical_tree_sha256"]


def test_large_array_retains_only_current_object_child_hashes(tmp_path):
    path = tmp_path/"stream.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write("[")
        for i in range(2000):
            if i:
                stream.write(",")
            json.dump({"row": i, "payload": "x"*1024}, stream)
        stream.write("]")
    result = eq.canonical_json_gz(path, chunk_chars=8192)
    assert result["parsed_counts"]["top_level_array_items"] == 2000
    assert result["maximum_single_object_keys"] == 2
    assert result["decoded_characters"] > 2_000_000


def _runs(tmp_path):
    binary = tmp_path/"dummy.pyd"
    binary.write_bytes(b"DUMMY NEVER EXECUTED")
    input_ref = write(tmp_path/"input.json", {"fixture": True})
    paths = [tmp_path/"left", tmp_path/"right"]
    for index, path in enumerate(paths):
        source = {"files": {"protocol.py": str(index)}}
        source["source_manifest_sha256"] = eq.digest(source["files"])
        source_ref = write(path/"source.json", source)
        plan = {"parent": {"parent_seed": 901}, "method": "C00",
            "input": input_ref, "input_semantic_sha256": eq.digest({"fixture": True}),
            "source_bundle": source_ref, "source_manifest_sha256": source["source_manifest_sha256"],
            "binary": {"path": str(binary), "sha256": eq.sha(binary)}}
        plan_ref = write(path/"plan.json", plan)
        write(path/"receipt.json", {"status": "complete", "worker": {"status": "complete"},
                                   "plan_sha256": plan_ref["sha256"]})
        for filename in eq.FILES:
            value = {} if filename in ("final_result.json.gz", "controller_final_state.json.gz",
                                        "ack_views.json.gz") else []
            write(path/filename, value)
        write(path/"client_calls.json.gz", [{"at": 7200., "submit_compute_ms": index+1.,
                                            "request": {"immutable": "same"}, "reply": {"status": "queued"}}])
        write(path/"controller_final_state.json.gz", {"client": {"outbox": {"r": {"history": [1, 2, 3]}}}})
    return paths


def test_cross_source_execution_equality_does_not_become_same_source_claim(tmp_path):
    left, right = _runs(tmp_path)
    row = eq.compare_closed_runs(left, right)
    assert row["status"] == "complete_canonical_execution_equal"
    assert row["full_source_manifest_equal"] is False
    assert row["strict_same_source_comparison"] is False
    assert row["different_source_paths"] == ["protocol.py"]
    assert len(row["files"]) == 6
    assert row["source_only_ownership_change_proven_by_this_tool"] is False


def test_missing_timing_field_or_changed_history_is_not_equivalence(tmp_path):
    left, right = _runs(tmp_path)
    write(right/"client_calls.json.gz", [{"at": 7200.,
        "request": {"immutable": "same"}, "reply": {"status": "queued"}}])
    row = eq.compare_closed_runs(left, right)
    assert row["status"] == "complete_execution_difference"
    assert row["files"]["client_calls.json.gz"]["canonical_equal"] is True
    assert row["files"]["client_calls.json.gz"]["ignored_timing_field_counts_equal"] is False
    write(right/"controller_final_state.json.gz", {"client": {"outbox": {"r": {"history": [1, 2, 4]}}}})
    row = eq.compare_closed_runs(left, right)
    assert row["files"]["controller_final_state.json.gz"]["canonical_equal"] is False
    assert row["files"]["controller_final_state.json.gz"]["different_top_level_fields"] == ["client"]


def test_both_receipts_are_checked_before_any_plan_or_large_document(tmp_path, monkeypatch):
    left, right = _runs(tmp_path)
    (right/"receipt.json").unlink()
    real_read = eq.read

    def only_receipts(path):
        assert path.name == "receipt.json"
        return real_read(path)

    monkeypatch.setattr(eq, "read", only_receipts)
    with pytest.raises(ValueError, match="both_runs_must_be_closed"):
        eq.compare_closed_runs(left, right)


def test_missing_evidence_and_corrupt_gzip_prevent_success(tmp_path):
    left, right = _runs(tmp_path)
    (right/"ack_views.json.gz").unlink()
    (right/"controller_final_state.json.gz").write_bytes(b"invalid gzip")
    row = eq.compare_closed_runs(left, right)
    assert row["status"] == "unknown_missing_or_invalid_evidence"
    assert row["missing_evidence"] == ["ack_views.json.gz"]
    assert row["errors"][0]["file"] == "controller_final_state.json.gz"
