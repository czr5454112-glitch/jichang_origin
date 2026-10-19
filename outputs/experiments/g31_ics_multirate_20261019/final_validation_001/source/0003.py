"""Offline diagnosis of retained Python checkpoint objects, without native code.

This reproduces the existing three deepcopy operations on a frozen JSON shard.
It is not a controller performance comparison or a request latency certificate.
"""
from __future__ import annotations

import argparse
import copy
import gc
import gzip
import hashlib
import json
from pathlib import Path
import time


def shape(value):
    pending, seen, containers, elements = [value], set(), 0, 0
    while pending:
        item = pending.pop()
        if not isinstance(item, (dict, list, tuple)) or id(item) in seen:
            continue
        seen.add(id(item))
        containers += 1
        elements += len(item)
        pending.extend(item.values() if isinstance(item, dict) else item)
    return {"unique_containers": containers, "container_entries": elements}


def analyze(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        part = json.load(stream)
    state = part["controller_state"]
    report = {"source_shard": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "physical_time": part["control_continuation"]["physical_time"],
        "new_native_executions": 0, "saved_state": shape(state),
        "previous_diagnostic_records": {key: shape(part[key]) for key in
                                         ("control_records", "native_batches", "client_calls")},
        "state_fields": {key: shape(value) for key, value in state.items()},
        "outbox_requests": len(state["client"]["outbox"]),
        "copy_measurements": [], "gc_during_copy": [],
        "scope": "Offline saved-JSON diagnosis. Concurrent full-day worker; no isolated speed or request-latency claim."}
    active = [None]
    starts = {}

    def callback(phase, info):
        generation = info["generation"]
        if phase == "start":
            starts[generation] = time.perf_counter_ns()
        elif generation in starts:
            report["gc_during_copy"].append({"phase": active[0], "generation": generation,
                "wall_ms": (time.perf_counter_ns() - starts.pop(generation)) / 1e6,
                "collected": info["collected"], "uncollectable": info["uncollectable"]})

    def measure(label, value):
        active[0] = label
        start, cpu = time.perf_counter_ns(), time.process_time_ns()
        result = copy.deepcopy(value)
        report["copy_measurements"].append({"phase": label,
            "wall_ms": (time.perf_counter_ns() - start) / 1e6,
            "cpu_ms": (time.process_time_ns() - cpu) / 1e6})
        active[0] = None
        return result

    gc.callbacks.append(callback)
    try:
        current = measure("controller_entry", state)
        client = measure("client_entry", current["client"])
        current["client"] = measure("controller_return", client)
    finally:
        gc.callbacks.remove(callback)
    report["copied_state_exactly_equal"] = current == state
    report["original_shard_unchanged"] = hashlib.sha256(path.read_bytes()).hexdigest() == report["sha256"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.shard)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({key: result[key] for key in
                     ("physical_time", "outbox_requests", "saved_state", "copy_measurements")}))


if __name__ == "__main__":
    main()
