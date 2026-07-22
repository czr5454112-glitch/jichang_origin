from __future__ import annotations

from pathlib import Path

import pytest

from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_HASH_SEMANTICS,
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_RELATIVE_PATH,
    CANONICAL_MAP_SHA256,
    FixedRealMapError,
    assert_canonical_map,
    canonical_graph_records,
    canonical_map_identity,
    normalised_text_sha256,
)


def test_canonical_map2_identity_and_dimensions_are_frozen() -> None:
    assert assert_canonical_map() == CANONICAL_MAP_PATH
    identity = canonical_map_identity()
    assert identity["fixed_real_map_only"] is True
    assert identity["repo_relative_path"] == CANONICAL_MAP_RELATIVE_PATH.as_posix()
    assert identity["sha256"] == CANONICAL_MAP_SHA256
    assert identity["sha256_semantics"] == CANONICAL_MAP_HASH_SEMANTICS
    assert identity["topology_mutation_allowed"] is False

    nodes, edges, heuristic = canonical_graph_records()
    assert len(nodes) == 54
    assert len(edges) == 69
    assert len(heuristic) == 54
    assert all(len(row) == 54 for row in heuristic)


def test_non_map_repository_input_is_rejected_without_constructing_a_graph() -> None:
    non_map = CANONICAL_MAP_PATH.parents[1] / "tasks" / "inputdata.jsonl"
    with pytest.raises(FixedRealMapError, match="accepts only"):
        assert_canonical_map(non_map)


def test_canonical_hash_is_cross_platform_newline_stable(tmp_path: Path) -> None:
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    text = "{\n  \"value\": 1\n}\n"
    lf.write_bytes(text.encode("utf-8"))
    crlf.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert normalised_text_sha256(lf) == normalised_text_sha256(crlf)
