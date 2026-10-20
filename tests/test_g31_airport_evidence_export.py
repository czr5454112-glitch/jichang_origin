"""Production export byte parity and proposed final-stage ownership tests; pure fixtures."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import random
import io
import time
import weakref

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_evidence_export as export

def write_original(path, value):
    """Exact source of runtime004 evaluator-only writer, for pure comparisons."""
    started = time.perf_counter()
    with Path(path).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1, mtime=0) as stream:
            with io.TextIOWrapper(stream, encoding="utf-8", newline="") as text:
                json.dump(value, text, **export.OPTIONS)
    return {"wall_seconds": time.perf_counter()-started, "gzip_bytes": Path(path).stat().st_size}


def export_before_observing(owned, save_controller, observe_acks):
    """Demonstrate required ownership/order using a sole owning reference box.

    Production translation is three explicit statements:
    write_gzip_json(controller_path, state); state = None; run = None
    followed by the unchanged all-owner observe_protocol calls.
    Any external aliases would still retain history; callers must relinquish them.
    """
    save_controller(owned["state"])
    owned["state"] = None
    owned["run"] = None
    return observe_acks()


def synthetic_state(requests=128, jobs_per_capture=16):
    return {"schema": "g31.protocol_controller_state.v3",
        "config": {"owners": ["A", "B"], "predictive": True},
        "next_tick": 991, "control_boundary_complete": True,
        "client": {"schema": "g31.protocol_client_state.v1", "outbox": {
            f"r{n}": {"kind": "planning_snapshot", "terminal": True,
                "payload": {"request_id": f"r{n}", "owner_id": "A", "target_owner": "B"},
                "client_view": {"last_delivered_ack": {"status": "delivered", "planning_snapshot": {
                    "capture": {"message_id": f"m{n}", "captured_at": n * 60.,
                        "jobs": [{"business_bag_id": f"bag-{j}-机场", "deadline": 57000.+j,
                                  "origin": 0, "destination": 1, "status": "waiting_for_tray"}
                                 for j in range(jobs_per_capture)]}}}}}
            for n in range(requests)}}}



def expected(value):
    return json.dumps(value, **export.OPTIONS).encode("utf8")


def encoded(value, depth=3):
    stats = {}
    pieces = list(export.iter_json_chunks(value, split_depth=depth, stats=stats))
    result = "".join(pieces).encode("utf8")
    assert stats["json_bytes"] == len(result)
    assert stats["chunks"] == len(pieces)
    assert stats["max_chunk_bytes"] == max(map(len, pieces))
    return result, stats


def tree(rng, depth=0):
    leaves = [None, True, False, 0, -17, 2**100, -0.0, 1e-200, 1e200, "机场\n\"\\", "\ud800", ""]
    if depth == 6 or rng.random() < .45:
        return rng.choice(leaves)
    kind = rng.randrange(3)
    count = rng.randrange(5)
    children = [tree(rng, depth+1) for _ in range(count)]
    if kind == 0:
        return children
    if kind == 1:
        return tuple(children)
    keys = ["first", "中文", 123, -2.5, None, False]
    return dict(zip(rng.sample(keys, count), children))


@pytest.mark.parametrize("seed", range(200))
def test_many_generated_nested_fixtures_have_identical_standard_json_bytes(seed):
    value = tree(random.Random(seed))
    before = expected(value)
    for depth in (0, 1, 2, 3, 4):
        actual, _ = encoded(value, depth)
        assert actual == before
    assert expected(value) == before


@pytest.mark.parametrize("value", [
    {"a": 1, "z": 2, "b": 3},
    {1: "int", "1": "str", None: "null", "null": "strnull", 1.25: "float", False: "bool"},
    {"tuple": (1, (2, 3)), "surrogate": "\udfff", "escape": "\t\n\r\"\\\x00"},
    {"empty": {}, "empty_list": [], "empty_tuple": ()},
])
def test_order_key_coercion_tuple_escaping_and_empty_containers(value):
    assert encoded(value)[0] == expected(value)


@pytest.mark.parametrize("where", ["leaf", "deep_leaf", "key", "deep_key"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_and_keys_rejected_by_both_encoders(where, value):
    fixture = {value: 1} if "key" in where else value
    if "deep" in where:
        fixture = {"client": {"outbox": {"r": fixture}}}
    with pytest.raises(ValueError):
        expected(fixture)
    with pytest.raises(ValueError):
        encoded(fixture)


@pytest.mark.parametrize("key", [(1, 2), object()])
def test_unsupported_nonstring_key_types_fail_instead_of_silent_skip(key):
    with pytest.raises(TypeError):
        encoded({key: 1})
    with pytest.raises(TypeError):
        expected({key: 1})


@pytest.mark.parametrize("depth", [0, 1, 2, 3, 4])
def test_cycles_across_split_boundary_rejected_but_aliases_preserved(depth):
    root = {"client": {"outbox": {"r": {}}}}
    root["client"]["outbox"]["r"]["back"] = root
    with pytest.raises(ValueError, match="Circular"):
        encoded(root, depth)
    shared = {"payload": [1, 2, 3]}
    value = {"a": shared, "b": shared}
    assert encoded(value, depth)[0] == expected(value)


@pytest.mark.parametrize("shape", ["controller", "ack"])
def test_realistic_known_paths_limit_chunks_to_one_history_entry(shape):
    state = synthetic_state(32, 4)
    if shape == "controller":
        value = state
        entries = state["client"]["outbox"].values()
    else:
        entries = [r["client_view"]["last_delivered_ack"] for r in state["client"]["outbox"].values()]
        value = {"A": {"delivered_command_acks": entries, "delivered_transfer_acks": []}}
    actual, stats = encoded(value)
    assert actual == expected(value)
    assert stats["max_chunk_bytes"] == max(len(expected(entry)) for entry in entries)
    assert stats["max_chunk_bytes"] < len(actual) / 20


def test_gzip_writer_exact_plaintext_and_same_filename_gzip_bytes(tmp_path):
    value = synthetic_state(8, 2)
    paths = []
    for name, writer in (("old", write_original), ("new", export.write_gzip_json)):
        directory = tmp_path / name
        directory.mkdir()
        path = directory / "controller_final_state.json.gz"
        writer(path, value)
        paths.append(path)
    assert gzip.decompress(paths[0].read_bytes()) == gzip.decompress(paths[1].read_bytes()) == expected(value)
    assert paths[0].read_bytes() == paths[1].read_bytes()
    with pytest.raises(FileExistsError):
        export.write_gzip_json(paths[1], value)


class WeakState(dict):
    pass


def owned_fixture():
    state = WeakState(synthetic_state(2, 2))
    reference = weakref.ref(state)
    box = {"state": state, "run": {"controller_state": state, "result": {"physical_clock": 59400.}}}
    return box, reference, expected(state)


def test_complete_export_precedes_releasing_both_aliases_and_ack_observation(tmp_path):
    box, live, original = owned_fixture()
    events = []
    path = tmp_path / "controller_final_state.json.gz"
    def save(value):
        assert live() is value
        export.write_gzip_json(path, value)
        assert gzip.decompress(path.read_bytes()) == original
        events.append("controller_file_closed_complete")
    def observe():
        assert live() is None
        assert box["state"] is box["run"] is None
        events.append("ack_observed_after_release")
        return {"A": {"delivered_command_acks": []}}
    ack = export_before_observing(box, save, observe)
    assert events == ["controller_file_closed_complete", "ack_observed_after_release"]
    assert ack == {"A": {"delivered_command_acks": []}}


def test_failed_write_keeps_all_history_and_never_observes_ack():
    box, live, original = owned_fixture()
    def fail(value):
        raise OSError("fixture disk full")
    def forbidden():
        pytest.fail("ACK must not be copied after failed state export.")
    with pytest.raises(OSError, match="disk full"):
        export_before_observing(box, fail, forbidden)
    assert live() is box["state"] is box["run"]["controller_state"]
    assert expected(box["state"]) == original


def test_external_alias_would_defeat_reclamation_and_is_detected_by_fixture():
    box, live, _ = owned_fixture()
    forbidden_alias = box["state"]
    export_before_observing(box, lambda value: None, lambda: None)
    assert live() is forbidden_alias
    del forbidden_alias
    assert live() is None
