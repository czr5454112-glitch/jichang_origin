"""Read-only execution-data diagnosis for Nanning 1x / seed 155921.

Reads existing logs or their SHA-bound archives; never executes Java, modifies
a simulation input, or changes a frozen result. Archive reads use a contained
temporary workspace; only the separate diagnostic JSON is retained. The common
completed cohort is diagnostic, never a formal THT estimate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external

NEW = ROOT / "outputs/runtime/hca_segment_identity_20260906/nanning_1p00x/seed_155921/hca_segment_identity"
OLD = ROOT / "outputs/runtime/cie_external_baseline_robustness/nanning_1p00x/seed_155921/hca_native/run_01"
OLD_TABLE = ROOT / "outputs/tables/feng_dh_v5_cells_20260905.csv"
OUTPUT = ROOT / "outputs/runtime/hca_segment_identity_20260906/diagnostics/nanning_1p00x_seed_155921_release_delay.json"
COMPONENTS = ("scheduled_D_THT", "native_release_minus_D", "planning_minus_native_release", "completion_minus_planning")
EVIDENCE = ROOT / "outputs/evidence/hca_segment_identity_20260906"
PRIOR_EVIDENCE = ROOT / "outputs/evidence/feng_dh_boundary_clearance_v5_20260905"
ADDENDUM = OUTPUT.parent / "old_native_events_addendum"
PRIOR_MANIFEST_SHA = "133808d1c2fb94149f2ec5e717d14f7384faea957ab3386deedabfef5c8f8f40"
SLOW_NATIVE_MANIFEST_SHA = "3fe65c17d6f62ef85ea0e9b90f65f547d65ccfbe0df7733b2be05d514773af09"
ADDENDUM_MANIFEST_SHA = "b326c077de8b42c902e6a1c5fc2450d0d0f74cc3e86622b54afc175939db90f1"
OLD_TABLE_SHA = "702d20c22a639c7b5e1f8143dda7bf44158e9b3cae1627d3d6c1c8a49b7eda09"
RECORDED_ROOT = "C:/PROGRAMING/czr005/.feng_cie_dh_worktree/"
NEW_FILES = ("normalized_result.json", "runner_status.json", "build_identity.json", "segment_execution_identity.csv",
             "release.csv", "routes.csv", "outputstarttime.txt", "output.txt", "segment_lifecycle.csv", "raw_bag_timings.csv", "summary.csv")
OLD_FILES = ("metrics.json", "release.csv", "routes.csv", "outputstarttime.txt", "output.txt", "segment_lifecycle.csv", "raw_bag_timings.csv", "summary.csv")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def indexed(values, field):
    result = {str(r[field]): r for r in values}
    require(len(result) == len(values), "duplicate " + field)
    return result


def numeric(value):
    return None if value in (None, "") else float(value)


def close(a, b, message):
    require(a is not None and b is not None and math.isfinite(float(a)) and math.isfinite(float(b))
            and abs(float(a)-float(b)) < 1e-7, message)


def describe(values):
    return {"count": len(values), "mean": statistics.fmean(values), "min": min(values),
            "p95": external._quantile(values, .95), "p99": external._quantile(values, .99), "max": max(values)}


def source_key(value):
    """Interpret saved provenance without following its original absolute path."""
    value = str(value).replace("\\", "/")
    if value.startswith(RECORDED_ROOT):
        value = value[len(RECORDED_ROOT):]
    require(not Path(value).is_absolute() and ":" not in value and ".." not in value.split("/"), "unsafe source provenance")
    return value


def archive_path(value, archive_root):
    """Resolve a descriptor by its evidence-directory suffix in this checkout."""
    archive_root = Path(archive_root).resolve(strict=True)
    parts = str(value).replace("\\", "/").split("/")
    require(".." not in parts and parts.count(archive_root.name) == 1, "unsafe or ambiguous archive path")
    suffix = parts[parts.index(archive_root.name)+1:]
    require(suffix and all(p and ":" not in p for p in suffix), "invalid archive suffix")
    target = archive_root.joinpath(*suffix).resolve(strict=True)
    require(target.is_relative_to(archive_root) and target.is_file(), "archive path escapes evidence root")
    return target


def checked_archive_bytes(descriptor, archive_root):
    target = archive_path(descriptor["archive_path"], archive_root)
    container = target.read_bytes()
    require(len(container) == descriptor["archive_size_bytes"] and
            hashlib.sha256(container).hexdigest() == descriptor["archive_sha256"], "archive container SHA/size differs")
    data = gzip.decompress(container) if descriptor["gzip"] else container
    require(len(data) == descriptor["source_size_bytes"] and
            hashlib.sha256(data).hexdigest() == descriptor["source_sha256"], "restored source SHA/size differs")
    return data


def scientific_payload(value):
    """All non-location scientific fields, including every cohort digest."""
    return {k: v for k, v in value.items() if k not in ("evidence", "archive_read_provenance")}


def diagnose_from_archive(evidence_root=EVIDENCE, prior_evidence=PRIOR_EVIDENCE, addendum=ADDENDUM):
    """Restore only this diagnostic's files in a new, contained workspace temp.

    Original JSON bytes are not rewritten: path overrides are in-memory inputs
    to the same diagnose() function. No native simulation directory is read.
    """
    evidence_root, prior_evidence, addendum = map(Path, (evidence_root, prior_evidence, addendum))
    current_path, prior_path, addendum_path = (evidence_root / "campaign_manifest.json",
                                             prior_evidence / "campaign_manifest.json", addendum / "manifest.json")
    require(sha(prior_path) == PRIOR_MANIFEST_SHA, "previous V5 manifest differs")
    require(sha(addendum_path) == ADDENDUM_MANIFEST_SHA, "old native addendum manifest differs")
    require(sha(OLD_TABLE) == OLD_TABLE_SHA, "previous frozen cell table differs")
    current, prior, supplemental = map(read, (current_path, prior_path, addendum_path))
    current_sha = sha(current_path)
    require(current["source_prior_manifest_sha256"] == PRIOR_MANIFEST_SHA, "current support points at another prior campaign")
    require(supplemental["prior_v5_campaign_manifest_sha256"] == PRIOR_MANIFEST_SHA, "old event addendum prior binding differs")
    support = indexed([{**f, "source_path": source_key(f["source_path"])} for f in current["support_files"]], "source_path")
    old_cells = [c for c in prior["cells"] if (c["map"], float(c["load_factor"]), int(c["seed"]), c["method"]) ==
                 ("nanning", 1.0, 155921, "FENG_NATIVE_HCA")]
    require(len(old_cells) == 1, "archived old cell missing or duplicated")
    old_files = old_cells[0]["files"] + prior["scientific_interpretation"]["files"]
    old_index = indexed([{**f, "source_path": source_key(f["source_path"])} for f in old_files], "source_path")
    supplemental_index = indexed(supplemental["files"], "source_path")
    new_prefix = NEW.relative_to(ROOT).as_posix()
    native_manifest_key = new_prefix + "/native_archive/manifest.json"
    require(native_manifest_key in support, "slow preflight native archive is absent from current support")
    manifest_bytes = checked_archive_bytes(support[native_manifest_key], evidence_root)
    require(hashlib.sha256(manifest_bytes).hexdigest() == SLOW_NATIVE_MANIFEST_SHA, "slow preflight native manifest differs")
    native_manifest = json.loads(manifest_bytes)
    require(native_manifest["method"] == "HCA_SEGMENT_IDENTITY_V1", "wrong native archive method")
    native_index = indexed(native_manifest["files"], "source_name")
    restored_provenance, read_records = {}, []
    temporary_parent = (ROOT / "build/hca_release_delay_archive_restore").resolve()
    require(temporary_parent.is_relative_to(ROOT.resolve()), "temporary parent escapes workspace")
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="single_cell_", dir=temporary_parent) as directory:
        temporary_root = Path(directory).resolve(strict=True)
        require(temporary_root.is_relative_to(temporary_parent), "temporary restore escapes parent")

        def restore(data, destination, logical_source, descriptors):
            destination = destination.resolve()
            require(destination.is_relative_to(temporary_root) and not destination.exists(), "unsafe or duplicate restore target")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(data)
            restored_provenance[destination.relative_to(ROOT).as_posix()] = logical_source
            read_records.append({"source_path": logical_source, "source_sha256": hashlib.sha256(data).hexdigest(),
                                 "source_size_bytes": len(data), "archive_descriptors": descriptors})
            return destination

        new, old, inputs = temporary_root / "new", temporary_root / "old", {}
        for name in NEW_FILES:
            inner = native_index[name]
            require(inner["path"] == "native_archive/"+name+".gz", "unexpected native member path")
            outer = support[new_prefix+"/"+inner["path"]]
            container = checked_archive_bytes(outer, evidence_root)
            require(hashlib.sha256(container).hexdigest() == inner["sha256"], "nested native container SHA differs")
            data = gzip.decompress(container)
            require(hashlib.sha256(data).hexdigest() == inner["uncompressed_sha256"] and
                    len(data) == inner["uncompressed_size_bytes"], "nested native source SHA/size differs")
            restore(data, new / name, new_prefix+"/"+name, [outer, inner])
        old_prefix = OLD.relative_to(ROOT).as_posix()
        for name in OLD_FILES:
            logical = old_prefix+"/"+name
            if logical in supplemental_index:
                descriptor, archive_root = supplemental_index[logical], addendum
            else:
                require(logical in old_index, "old native/derived evidence not archived: "+name)
                descriptor, archive_root = old_index[logical], prior_evidence
            restore(checked_archive_bytes(descriptor, archive_root), old / name, logical, [descriptor])
        normalized = read(new / "normalized_result.json")
        identity_key = source_key(normalized["workload_identity_path"])
        identity_descriptor = old_index[identity_key]
        identity_path = restore(checked_archive_bytes(identity_descriptor, prior_evidence), temporary_root / "input/identity.json",
                                identity_key, [identity_descriptor])
        identity = read(identity_path)
        for name in ("raw", "canonical", "map"):
            logical = source_key(identity[name+"_path"])
            descriptor = old_index[logical]
            inputs[name] = restore(checked_archive_bytes(descriptor, prior_evidence), temporary_root / "input" / name,
                                   logical, [descriptor])
        value = diagnose(new, old, identity_path=identity_path, input_paths=inputs)
        for record in value["evidence"]:
            record["path"] = restored_provenance.get(record["path"], record["path"])
        value["archive_read_provenance"] = {"mode": "FROM_ARCHIVE_ONLY_NATIVE_PATHS_NOT_FOLLOWED",
            "current_campaign_manifest_sha256": current_sha, "current_campaign_manifest_status_at_read": current["status"],
            "current_campaign_scope": "ONLY_BOUND_SINGLE_CELL_SUPPORT_READ_NOT_A_FULL_CAMPAIGN_VERIFICATION",
            "prior_v5_campaign_manifest_sha256": PRIOR_MANIFEST_SHA, "slow_native_manifest_sha256": SLOW_NATIVE_MANIFEST_SHA,
            "old_native_addendum_manifest_sha256": ADDENDUM_MANIFEST_SHA,
            "old_native_addendum_is_new_preservation_not_part_of_prior_v5_manifest": True,
            "temporary_restore_containment_verified": True, "original_json_bytes_not_rewritten": True,
            "files": read_records}
        require(sha(current_path) == current_sha, "current manifest changed while reading; retry after export")
        require(temporary_root.resolve().is_relative_to(temporary_parent), "temporary cleanup escapes parent")
        return value


def native_new_lifecycle(new, canonical):
    """Rebuild each new segment from exact execution-ID native events."""
    mapping = indexed(rows(new / "segment_execution_identity.csv"), "execution_id")
    release = indexed(rows(new / "release.csv"), "task_id")
    route = indexed(rows(new / "routes.csv"), "task_id")
    plans, completions = {}, {}
    for line in (new / "outputstarttime.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            eid, start, legacy_pass, epoch = line.split()
            require(eid not in plans, "duplicate native planning event")
            plans[eid] = {"start": int(start), "epoch": float(epoch), "legacy_pass": float(legacy_pass)}
    for line in (new / "output.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            eid, epoch = line.split()
            require(eid not in completions, "duplicate native completion event")
            completions[eid] = float(epoch)
    require(set(mapping) == set(release) == set(plans) == set(route) == set(completions),
            "this diagnosis requires every new segment to be released/planned/completed exactly once")
    by_raw_leg = {(int(r["task_id"]), r["leg"]): r for r in canonical}
    require(len(by_raw_leg) == len(canonical) == len(mapping), "canonical mapping population differs")
    rebuilt = {}
    for eid, m in mapping.items():
        raw_leg = int(m["raw_task_id"]), m["leg"]
        require(raw_leg in by_raw_leg, "native mapping refers to foreign raw/leg")
        can = by_raw_leg[raw_leg]
        for field in ("start", "goal"):
            require(int(m[field]) == int(can[field]) == int(release[eid][field]) == int(route[eid][field]), "native OD mismatch")
        close(m["scheduled_release_seconds"], can["pass_time"], "native D mapping mismatch")
        close(m["deadline_seconds"], can["std"], "native STD mapping mismatch")
        require(plans[eid]["start"] == int(can["start"]), "planning source mismatch")
        close(plans[eid]["epoch"], route[eid]["epoch"], "route/planning time mismatch")
        r, p, e = float(release[eid]["release_epoch"]), plans[eid]["epoch"], completions[eid]
        require(8260 <= r <= p <= e <= 98259, "native clock order differs")
        rebuilt[can["segment_id"]] = {"execution_id": int(eid), "segment_id": can["segment_id"],
            "task_id": int(can["task_id"]), "leg": can["leg"], "start": int(can["start"]), "goal": int(can["goal"]),
            "original_entry_time": float(can["original_entry_time"]), "scheduled_pass_time": float(can["pass_time"]),
            "release_epoch": r, "processed_attempt_epoch": p, "finish_epoch": e}
    require(len(rebuilt) == len(canonical), "native reconstruction omits a canonical segment")
    stored = indexed(rows(new / "segment_lifecycle.csv"), "segment_id")
    require(set(stored) == set(rebuilt), "derived lifecycle population differs")
    for sid, r in rebuilt.items():
        for field, value in r.items():
            if field in ("segment_id", "leg"):
                require(stored[sid][field] == value, "derived lifecycle identity mismatch")
            else:
                close(stored[sid][field], value, "derived lifecycle/native events differ")
    return rebuilt


def bag_components(lifecycle):
    grouped = defaultdict(list)
    for r in lifecycle.values():
        grouped[int(r["task_id"])].append(r)
    complete = {}
    for raw, segments in grouped.items():
        if all(numeric(r["finish_epoch"]) is not None for r in segments):
            values = {}
            for name, end, start in ((COMPONENTS[0], "finish_epoch", "scheduled_pass_time"),
                                     (COMPONENTS[1], "release_epoch", "scheduled_pass_time"),
                                     (COMPONENTS[2], "processed_attempt_epoch", "release_epoch"),
                                     (COMPONENTS[3], "finish_epoch", "processed_attempt_epoch")):
                values[name] = math.fsum(float(s[end])-float(s[start]) for s in segments)
            close(values[COMPONENTS[0]], math.fsum(values[k] for k in COMPONENTS[1:]), "bag timing decomposition differs")
            complete[raw] = values
    return complete


def verify_old_native(old, canonical, lifecycle):
    """Old full-bag sums can be verified without assigning raw-ID E to a leg."""
    by_od, by_start, by_raw = defaultdict(list), defaultdict(list), defaultdict(list)
    for can in canonical:
        raw = int(can["task_id"])
        by_od[raw, int(can["start"]), int(can["goal"])].append(can)
        by_start[raw, int(can["start"])].append(can)
        by_raw[raw].append(can)
    released, planned, raw_completion = {}, {}, defaultdict(list)
    for event in rows(old / "release.csv"):
        candidates = by_od[int(event["task_id"]), int(event["start"]), int(event["goal"])]
        require(len(candidates) == 1, "old native release OD does not uniquely identify a canonical segment")
        sid = candidates[0]["segment_id"]
        require(sid not in released, "duplicate old release segment")
        released[sid] = float(event["release_epoch"])
        close(released[sid], lifecycle[sid]["release_epoch"], "old native release/lifecycle mismatch")
    for line in (old / "outputstarttime.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw, start, _legacy_pass_time, epoch = line.split()
        candidates = by_start[int(raw), int(start)]
        require(len(candidates) == 1, "old native planning source does not uniquely identify a segment")
        sid = candidates[0]["segment_id"]
        require(sid not in planned, "duplicate old successful planning segment")
        planned[sid] = float(epoch)
        close(planned[sid], lifecycle[sid]["processed_attempt_epoch"], "old native planning/lifecycle mismatch")
    require(set(released) == set(planned) == set(lifecycle), "old native release/planning coverage differs")
    for line in (old / "output.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw, epoch = line.split()
            raw_completion[int(raw)].append(float(epoch))
    require(set(raw_completion) <= set(by_raw), "foreign old raw completion identity")
    complete_native_tht = {}
    lifecycle_by_raw = defaultdict(list)
    for item in lifecycle.values():
        lifecycle_by_raw[int(item["task_id"])].append(item)
    for raw, can_segments in by_raw.items():
        events = raw_completion[raw]
        stored = [numeric(s["finish_epoch"]) for s in lifecycle_by_raw[raw] if numeric(s["finish_epoch"]) is not None]
        require(sorted(events) == sorted(stored) and len(events) <= len(can_segments), "old native/raw completion accounting differs")
        if len(events) == len(can_segments):
            complete_native_tht[raw] = math.fsum(events)-math.fsum(float(c["pass_time"]) for c in can_segments)
    derived = bag_components(lifecycle)
    require(set(complete_native_tht) == set(derived), "old complete-cohort membership differs")
    for raw, value in complete_native_tht.items():
        close(value, derived[raw][COMPONENTS[0]], "old native raw-sum THT/lifecycle mismatch")
    return {"status": "PASS", "released_segments": len(released), "successful_planning_segments": len(planned),
            "completed_events": sum(map(len, raw_completion.values())), "complete_raw_bags": len(complete_native_tht),
            "old_complete_bag_THT_verified_without_completion_to_leg_FIFO_join": True,
            "formula": "sum(native raw-ID completion epochs) - sum(canonical segment D), only when all raw-bag segments have an event",
            "limitation": "Does not identify which physical leg produced an ambiguous old raw-ID event or restore missing events."}


def source_release_replay(lifecycle):
    """Replay release eligibility conditional on observed order and plan times.

    This is not a route-planning replay. Legacy generate_tasks precedes the
    planner at each epoch, so a prior pending task planned at P frees its
    source for the next task only at P+1.
    """
    grouped = defaultdict(list)
    for r in lifecycle.values():
        grouped[r["start"]].append(r)
    sources, differences = [], []
    for source, segments in sorted(grouped.items()):
        segments.sort(key=lambda r: r["release_epoch"])
        previous = None
        for r in segments:
            predicted = max(8260, math.floor(r["scheduled_pass_time"]),
                            previous["processed_attempt_epoch"]+1 if previous is not None else 8260)
            if predicted != r["release_epoch"]:
                differences.append({"segment_id": r["segment_id"], "actual": r["release_epoch"], "predicted": predicted})
            previous = r
        offsets = [s["release_epoch"]-s["scheduled_pass_time"] for s in segments]
        sources.append({"source_node": source, "segments": len(segments), "positive_release_delay_count": sum(v > 0 for v in offsets),
            "native_release_minus_D": describe(offsets),
            "sum_planning_minus_release_seconds": math.fsum(s["processed_attempt_epoch"]-s["release_epoch"] for s in segments),
            "last_release_epoch": segments[-1]["release_epoch"]})
    return {"condition": "OBSERVED_NATIVE_SOURCE_ORDER_AND_SUCCESSFUL_PLANNING_TIMES",
            "formula": "R_i = max(8260, floor(D_i), P_previous_same_source + 1)",
            "first_task_formula": "R_first = max(8260, floor(D_first))",
            "checked_segments": len(lifecycle), "mismatch_count": len(differences), "differences": differences,
            "sources": sources,
            "limitation": "No A-star replay or causal isolation of why each earlier planning attempt returned no path; no Python replacement of the legacy non-total integer-difference comparator."}


def diagnose(new=NEW, old=OLD, old_table=OLD_TABLE, *, identity_path=None, input_paths=None):
    normalized = read(new / "normalized_result.json")
    require((normalized["map"], normalized["load_factor"], normalized["seed"], normalized["method"]) ==
            ("nanning", 1.0, 155921, "HCA_SEGMENT_IDENTITY_V1"), "diagnostic scope is only Nanning 1x seed 155921")
    identity_path = Path(normalized["workload_identity_path"]) if identity_path is None else Path(identity_path)
    identity = read(identity_path)
    input_paths = {k: Path(identity[k+"_path"]) for k in ("raw", "canonical", "map")} if input_paths is None else input_paths
    old_rows = [r for r in rows(old_table) if (r["map"], float(r["load_factor"]), int(r["seed"]), r["method"]) ==
                ("nanning", 1.0, 155921, "FENG_NATIVE_HCA")]
    require(len(old_rows) == 1, "old frozen HCA cell missing")
    old_row = old_rows[0]
    actual_inputs = {k: sha(input_paths[k]) for k in ("raw", "canonical", "map")}
    for field, old_field in (("raw", "input_sha256"), ("canonical", "canonical_sha256"), ("map", "map_sha256")):
        require(actual_inputs[field] == identity[field+"_sha256"] == normalized["workload_"+field+"_sha256"] == old_row[old_field],
                "old/new actual input identity mismatch")
    require(sha(identity_path) == normalized["workload_identity_sha256"] == old_row["workload_identity_sha256"], "workload identity bytes differ")
    require(float(old_row["fixed_horizon_seconds"]) == normalized["fixed_horizon_seconds"] == 98259, "shared horizon differs")
    canonical = [json.loads(line) for line in input_paths["canonical"].read_text(encoding="utf-8").splitlines() if line.strip()]
    new_life = native_new_lifecycle(new, canonical)
    old_life = indexed(rows(old / "segment_lifecycle.csv"), "segment_id")
    require(set(new_life) == set(old_life), "old/new canonical segment population differs")
    old_native_audit = verify_old_native(old, canonical, old_life)
    comparisons = {}
    for field in ("task_id", "leg", "start", "goal", "original_entry_time", "scheduled_pass_time", "release_epoch", "processed_attempt_epoch", "finish_epoch"):
        changes = []
        for sid, r in new_life.items():
            a, b = old_life[sid][field], r[field]
            equal = str(a) == str(b) if field == "leg" else numeric(a) == numeric(b)
            if not equal:
                changes.append({"segment_id": sid, "old": numeric(a) if field != "leg" else a, "new": b})
        comparisons[field] = {"difference_count": len(changes), "differences": changes}
    require(all(comparisons[f]["difference_count"] == 0 for f in comparisons if f != "finish_epoch"),
            "this archived single-cell release/plan identity diagnosis no longer reproduces")
    bags = {"new": bag_components(new_life), "old_completed_diagnostic_only": bag_components(old_life)}
    new_bags, old_bags = bags.values()
    stored = indexed(rows(new / "raw_bag_timings.csv"), "task_id")
    require(len(new_bags) == len(stored) == normalized["raw_bag_denominator"], "new full-bag population differs")
    for raw, v in new_bags.items():
        close(v[COMPONENTS[0]], stored[str(raw)]["tht_scheduled_release_seconds"], "stored raw THT differs from native reconstruction")
        close(v[COMPONENTS[3]], stored[str(raw)]["tht_processed_attempt_seconds"], "stored post-planning THT differs")
    stats = {label: {k: describe([v[k] for v in values.values()]) for k in COMPONENTS} for label, values in bags.items()}
    for stat in ("min", "mean", "p95", "p99", "max"):
        close(stats["new"][COMPONENTS[0]][stat], normalized["metrics"][f"tht_scheduled_release_{stat}_seconds"], "new normalized common-D distribution differs")
        close(stats["new"][COMPONENTS[3]][stat], normalized["metrics"][f"tht_admission_{stat}_seconds"], "new normalized post-planning distribution differs")
    common_ids = sorted(set(new_bags) & set(old_bags))
    common_differences = [{"task_id": r, "delta": new_bags[r][COMPONENTS[0]]-old_bags[r][COMPONENTS[0]]}
                          for r in common_ids if new_bags[r][COMPONENTS[0]] != old_bags[r][COMPONENTS[0]]]
    common_digest = lambda bag_map: hashlib.sha256(json.dumps([[r, bag_map[r][COMPONENTS[0]]] for r in common_ids], separators=(",", ":")).encode()).hexdigest()
    extra = sorted(set(new_bags)-set(old_bags))
    summary = {"new": rows(new / "summary.csv")[0], "old": rows(old / "summary.csv")[0]}
    shared_contract = ("speed_mps", "start_epoch", "max_epochs", "max_new_tasks", "epochs_run", "fault_event_count",
                       "repair_event_count", "active_fault_count", "generated_fault_edge_count", "generated_repair_edge_count", "last_epoch")
    require(all(numeric(summary["new"][f]) == numeric(summary["old"][f]) for f in shared_contract), "native run controls differ")
    sources = source_release_replay(new_life)
    require(sources["mismatch_count"] == 0, "source release replay differs; inspect before interpreting")
    evidence_paths = [Path(__file__), old_table, identity_path, *[input_paths[k] for k in ("raw", "canonical", "map")],
                      *[new/name for name in ("normalized_result.json", "runner_status.json", "build_identity.json", "segment_execution_identity.csv",
                        "release.csv", "routes.csv", "outputstarttime.txt", "output.txt", "segment_lifecycle.csv", "raw_bag_timings.csv", "summary.csv")],
                      *[old/name for name in ("metrics.json", "release.csv", "routes.csv", "outputstarttime.txt", "output.txt", "segment_lifecycle.csv", "raw_bag_timings.csv", "summary.csv")],
                      ROOT / "benchmarks/java/HcaSegmentIdentityBenchmark.java", ROOT / "legacy/jichang_origin_readonly/src/App/Tasks.java",
                      ROOT / "legacy/jichang_origin_readonly/src/App/ICS_PathFinding.java"]
    evidence = [{"path": p.resolve().relative_to(ROOT).as_posix(), "sha256": sha(p), "size_bytes": p.stat().st_size} for p in evidence_paths]
    highest = sorted(new_bags, key=lambda raw: new_bags[raw][COMPONENTS[0]], reverse=True)[:5]
    return {"schema": "czr005.hca_segment_identity_release_delay_diagnostic.v1", "status": "PASS",
        "scope": {"map": "nanning", "load_factor": 1.0, "seed": 155921, "single_cell_only": True,
                  "run_role": "REPAIRED_NATIVE_CONTROL_PREFLIGHT_BEFORE_FAST_CLEANUP_CAMPAIGN",
                  "not_a_sixty_cell_or_ten_seed_conclusion": True},
        "evidence": evidence, "identity": {"workload_identity_sha256": sha(identity_path), **actual_inputs,
            "raw_bags": identity["raw_bag_count"], "segments": identity["segment_count"], "fixed_horizon_seconds": 98259,
            "source_sha256": normalized["normalization_contract"]["reconstruction_java_source_sha256"],
            "class_sha256": normalized["normalization_contract"]["compiled_java_class_sha256"]},
        "native_summaries": summary, "native_control_fields_equal": list(shared_contract),
        "native_new_segment_to_raw_reconstruction": "ALL_NATIVE_EVENTS_EXACT_EXECUTION_ID_MATCH_AND_ALL_RAW_THT_RECOMPUTED",
        "old_native_event_reconstruction": old_native_audit,
        "segment_comparison": comparisons, "timing_decomposition_seconds": stats,
        "new_mean_release_minus_D_fraction": stats["new"][COMPONENTS[1]]["mean"]/stats["new"][COMPONENTS[0]]["mean"],
        "old_formal_timing_status": old_row["formal_timing_status"],
        "old_scheduled_mean_formally_exported": numeric(old_row["tht_scheduled_release_mean_seconds"]),
        "common_completed_cohort_diagnostic": {"bags": len(common_ids), "difference_count": len(common_differences),
            "differences": common_differences, "old_ordered_timing_sha256": common_digest(old_bags), "new_ordered_timing_sha256": common_digest(new_bags),
            "formal_timing_eligible": False, "reason": "OLD_ALL_POPULATION_INCOMPLETE_AND_ACCOUNTING_ANOMALOUS; NO_SURVIVOR_ESTIMATE_FOR_PERFORMANCE_COMPARISON"},
        "newly_resolved_raw_bags": [{"task_id": raw, "components": new_bags[raw],
            "old_segments": [r for r in old_life.values() if int(r["task_id"]) == raw],
            "new_segments": [r for r in new_life.values() if int(r["task_id"]) == raw]} for raw in extra],
        "highest_THT_bags": [{"task_id": raw, "components": new_bags[raw],
            "segments": [r for r in new_life.values() if int(r["task_id"]) == raw]} for raw in highest],
        "source_release_rule_replay": sources,
        "observations": ["All scheduled D, native release and successful planning times match the old cell exactly.",
            "The common completed-bag THT values are unchanged; the new full-population mean includes a formerly incomplete raw bag.",
            "The large common-D time already exists in the old native release logs; post-planning timing is a different clock."],
        "inferences_and_limits": ["Observed source delays are consistent with legacy source-order, one release per source per epoch and pending-plan source blocking.",
            "Conditioned release replay does not independently replay A-star or explain each no-path planning attempt.",
            "Old runtime source/class identity was not recorded; unchanged readable App sources do not reconstruct that old build.",
            "Independent scheduled EBS segments may overlap or finish outbound before inbound; no new physical precedence claim follows.",
            "No extrapolation to other 59 repaired HCA cells or ten-seed aggregate results is supported by this diagnosis."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--from-archive", action="store_true", help="read bound gzip archives without following original native paths")
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    parser.add_argument("--prior-evidence-root", type=Path, default=PRIOR_EVIDENCE)
    args = parser.parse_args()
    value = diagnose_from_archive(args.evidence_root, args.prior_evidence_root) if args.from_archive else diagnose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": value["status"], "scope": value["scope"], "output": str(args.output),
                      "common_bag_differences": value["common_completed_cohort_diagnostic"]["difference_count"]}))


if __name__ == "__main__":
    main()
