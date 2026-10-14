"""Small experiment-entry contracts; no simulator or algorithm policy changes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def check_output_directory(output: str | Path) -> Path:
    """Read-only preflight. Existing empty real directories remain compatible."""
    output = Path(output)
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Output cannot be overwritten; existing experiment records are immutable. Use a new or empty directory")
    return output


def create_output_directory(output: str | Path) -> Path:
    output = check_output_directory(output)
    output.mkdir(parents=True, exist_ok=True)
    return output


def write_new_json(output: str | Path, value) -> None:
    """File-output equivalent: even an existing zero-byte file is reserved."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Output cannot be overwritten; existing experiment records are immutable")
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def read_json_object(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not value:
        raise ValueError(f"Expected a nonempty JSON object: {path}")
    return value


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_groups(manifest: dict, *, required_splits=None) -> dict[str, list[str]]:
    groups = manifest.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("Manifest requires nonempty groups keyed by split")
    if required_splits is not None and set(groups) != set(required_splits):
        raise ValueError(f"Manifest splits must be exactly {tuple(required_splits)}")
    all_ids = []
    for split, identifiers in groups.items():
        if (not isinstance(split, str) or not split or not isinstance(identifiers, list) or not identifiers
                or any(not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers)):
            raise ValueError("Manifest split IDs must be nonempty lists of nonempty strings")
        all_ids.extend(identifiers)
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Source groups must be unique and cannot overlap splits")
    return {split: list(identifiers) for split, identifiers in groups.items()}


def source_reuse_record(groups, *, mode, history_paths=(), allowed_training_ids=()):
    """Freshness is relative to supplied source registries, never an ID-name claim."""
    manifest_groups({"groups": groups})
    history, seen = {}, set()
    for path in sorted({Path(path).resolve() for path in history_paths}):
        prior = manifest_groups(read_json_object(path))
        ids = {item for values in prior.values() for item in values}
        seen.update(ids)
        history[str(path)] = {"sha256": sha256_file(path), "groups": prior}
    overlaps = {split: sorted(set(identifiers) & seen) for split, identifiers in groups.items()}
    if mode == "fresh-confirmation":
        if any(overlaps[split] for split in groups if split != "train"):
            raise ValueError("Fresh confirmation evaluation sources overlap registered prior development/selection/evaluation sources")
        if set(overlaps.get("train", ())) - set(allowed_training_ids):
            raise ValueError("Training reuse must be explicit through --training-manifest")
    counts = {split: len(ids) for split, ids in groups.items()}
    return {"mode": mode, "history": history, "overlap_with_registered_history": overlaps,
            "disjoint_from_recorded_prior_splits": not any(overlaps.values()),
            "new_independent_source_count": 0 if mode in {"reproduce", "development"} else len(groups["test"]),
            "new_confirmation_test_source_count": len(groups["test"]) if mode == "fresh-confirmation" else 0,
            "executed_source_counts": counts,
            "claim": "development_replay_not_fresh_evidence" if mode == "development" else
                     "same_registered_sources_reproduction_not_additional_samples" if mode == "reproduce" else
                     "test_source_ids_absent_from_declared_history_not_proof_of_real_world_independence",
            "limitations": ["Registry checks cannot detect unregistered prior use, renamed identical sources or topology-family dependence.",
                            "Validation sources are selection data; only untouched test source IDs count as confirmation evaluation.",
                            "Protocol reproduction uses the current recorded implementation; bit-identical algorithm reproduction requires its frozen source checkout."]}
