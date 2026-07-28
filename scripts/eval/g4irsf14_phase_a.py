"""Freeze the G4IRSF14 starting identity without rerunning old experiments.

Stage 14A is an evidence admission gate, not a simulator.  It validates the
protected map/task inputs, the authoritative G4IRSF13 controls and decision,
the final F2 runtime identity, and the no-scale lock.  Only after every check
passes may ``--write`` publish the five small ``g4irsf14_`` artifacts.

Hash conventions intentionally match the sealed predecessor:

* file hashes are SHA-256 over exact bytes;
* semantic text hashes decode UTF-8, normalize CRLF/CR to LF, re-encode UTF-8,
  and do no JSON canonicalization;
* structured/self hashes use compact, sorted, UTF-8 JSON with NaN forbidden.

The phase-start commit is an exact snapshot identity.  After Stage 14A is
committed, validation permits descendant commits while continuing to require
the phase-start commit to be an ancestor and every protected inherited path
to remain unchanged since that commit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PHASE_DATE = "2026-07-28"
SCHEMA_PREFIX = "czr005.g4irsf14"

START_BRANCH = "codex/czr005-rewrite"
START_HEAD = "750a14ca52755df99fa5f6f0952f04e014ff2274"
START_UPSTREAM = "origin/codex/czr005-rewrite"
START_UPSTREAM_HEAD = START_HEAD

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
TASK_SEMANTIC_SHA256 = TASK_RAW_SHA256
MAP_NODE_COUNT = 54
MAP_EDGE_COUNT = 69
TASK_SEGMENT_COUNT = 43603
TASK_RAW_BAG_COUNT = 28506

F2_MEAN_MINUTES = 41.514218717973414
V2_SAFE_MEAN_MINUTES = 41.49530698780892
HISTORICAL_HCA_MEAN_MINUTES = 43.13593828041816
F2_DECISION_SENSITIVE_MEAN_MINUTES = 4.143217183651398
F2_SOURCE_WAIT_MEAN_MINUTES = 0.3627182289108726
F2_NETWORK_TIME_MEAN_MINUTES = 3.7804989547405254
F2_PATH_EDGES_MEAN = 11.95572861853645
F2_DELTA_V2_SECONDS = 1.1347038098698192
F2_DELTA_HCA_SECONDS = -97.30317374668473

F2_CONFIG_SHA256 = "60c91e937f3c8f14ff4a80f685ec3294da6e22196cdf254eea998acb677becf1"
FINAL_BINARY_SHA256 = "814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7"
FINAL_SOURCE_BUNDLE_SHA256 = (
    "95026955f7ff96f9894220b2c4fea17b1ed2270b39ca59bd9feded8e4b7423e3"
)
FINAL_SOURCE_PATH_MANIFEST_SHA256 = (
    "2bc2abca4612464f2e59a774158c3b44ac76c3c29702cd1e7ad08a61b20e8b40"
)
FROZEN_MODEL_SHA256 = "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
FROZEN_BINARY_PATH = Path(
    "build_g4irsf12/python/czr005_cpp.cp311-win_amd64.pyd"
)
FROZEN_MODEL_PATH = Path("artifacts/models/g4e_risk_calibrated_policy.json")

SEALED_F2_BINARY_SHA256 = (
    "82f15f08a8cff0e887447f017f0aa03fffabe9bfb3a79a563b16d779219d8222"
)
SEALED_F2_SOURCE_BUNDLE_SHA256 = (
    "eca01993a9094c8e86558d15246628acd3162d5d769916ded6365ec6437f0df7"
)
SEALED_F2_SOURCE_MANIFEST_SHA256 = (
    "720843eb169dc451d8949c4d6b4d8dec8f3d43a6288492c5d23ef8321a712c3b"
)

BASELINE_REGISTRY_PATH = Path("artifacts/gates/g4irsf14_baseline_registry.json")
F2_FROZEN_CONTROL_PATH = Path(
    "artifacts/policies/g4irsf14_f2_frozen_control.json"
)
FAULT_FROZEN_CONTROL_PATH = Path(
    "artifacts/policies/g4irsf14_fault_frozen_control.json"
)
START_STATE_REPORT_PATH = Path("outputs/reports/g4irsf14_start_state.md")
GIT_IDENTITY_TABLE_PATH = Path("outputs/tables/g4irsf14_git_identity.csv")
OUTPUT_PATHS = (
    BASELINE_REGISTRY_PATH,
    F2_FROZEN_CONTROL_PATH,
    FAULT_FROZEN_CONTROL_PATH,
    START_STATE_REPORT_PATH,
    GIT_IDENTITY_TABLE_PATH,
)

G13_BASELINE_MANIFEST_PATH = Path(
    "artifacts/gates/g4irsf13_baseline_freeze_manifest.json"
)
G13_F2_POLICY_PATH = Path("artifacts/policies/g4irsf13_f2_frozen_baseline.json")
G13_FINAL_BUNDLE_PATH = Path(
    "artifacts/policies/g4irsf13_final_candidate_bundle.json"
)
G13_FAULT_BUNDLE_PATH = Path(
    "artifacts/policies/g4irsf13_fault_control_bundle.json"
)
G13_NO_SCALE_GATE_PATH = Path(
    "artifacts/gates/g4irsf13_kl_unlock_decision.json"
)
G12_DENOMINATOR_PATH = Path(
    "artifacts/policies/g4irsf12_denominator_reconciliation.json"
)
G13_FINAL_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_original_scale_joint_decision.md"
)
G13_FINAL_TABLE_PATH = Path(
    "outputs/tables/g4irsf13_original_scale_joint_ab.csv"
)
G13_FAULT_REPORT_PATH = Path(
    "outputs/reports/g4irsf13_fault_recovery_results.md"
)
G13_FAULT_TABLE_PATH = Path("outputs/tables/g4irsf13_fault_causal_ab.csv")

INHERITED_FILE_SHA256: dict[Path, str] = {
    G13_BASELINE_MANIFEST_PATH: (
        "8f6729789c4fc30815d73b8dc136a3ccbc7749b393af4b90a06a900ce09abbe4"
    ),
    G13_F2_POLICY_PATH: (
        "9fdbb15c5446ac1dd693d0fdb1fdc87aba550e104706515f137859f2f3950054"
    ),
    G13_FINAL_BUNDLE_PATH: (
        "202b6fbf4608ceaeba9bb215a02ece5473471330705358bb191ff9d2f8f95fc8"
    ),
    G13_FAULT_BUNDLE_PATH: (
        "2725cde581268aacc2bd37ad15e6b1c19fe4204c04f233eaa947d55986ac2272"
    ),
    G13_NO_SCALE_GATE_PATH: (
        "3c8f45d47dd81194c8c62d046c8fa5f3ac97b7f51df45127d3bb8ed693c25cd9"
    ),
    G12_DENOMINATOR_PATH: (
        "618c040a5b5bd13ce81c502832575a7ea52bd8b82998ce481ffe79da9b8de4e6"
    ),
    G13_FINAL_REPORT_PATH: (
        "3952d4a61e300bcaeb66dcfa751512efd10d8fd3f0e095d6289643623beabf14"
    ),
    G13_FINAL_TABLE_PATH: (
        "4763ece0c7467826723f8184e50e01a25435560479cbaa8b0c9911ebc018f3d7"
    ),
    G13_FAULT_REPORT_PATH: (
        "0e560943c0b27ca738b70f0f041fe906fb70911fc346972db3ae10f7c1b9f781"
    ),
    G13_FAULT_TABLE_PATH: (
        "acd60372deaf2b4a9f5f91ae12df7b252a46691521602d66ae3b3c96c7383250"
    ),
    FROZEN_MODEL_PATH: FROZEN_MODEL_SHA256,
}

FINAL_SOURCE_FILES: tuple[tuple[Path, str], ...] = (
    (
        Path("scripts/eval/g4irsf13_final_joint_evaluation.py"),
        "45bef8d4d8c682765c0ad21cc6dc7e7b5ef2d855f409f5cd5094fb533e94f431",
    ),
    (
        Path("scripts/eval/g4irsf13_cde_experiments.py"),
        "98f944a665a5c58a472c79eb342dda8d1c38902d7225a83c8d800f14fedb7ed2",
    ),
    (
        Path("scripts/eval/g4irsf12_reproducible_harness.py"),
        "d138faba4f46a9933e7530c0d7cb2ff1339fd6f671ec2400882c0ec23bdef37c",
    ),
    (
        Path("src/czr005/cpp_backend.py"),
        "27ea588191767ca3cdc71eca86ef7be5a612036c66bdd4890f3ced5e497e531c",
    ),
    (
        Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
        "bbd6b09f9c1ac32bb94c58b0edfff1b9765cd44f99d2e49032c03ad3cd9709d0",
    ),
    (
        Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
        "9d985f46a4e46148060dc2a8eee9cff1bde5c3ee28e6903f24e6644ab7c2b600",
    ),
    (
        Path("cpp/ics_core/runtime/expiring_first_edge_credit.hpp"),
        "d4f56d9146bd425f8229d84038c7b0bf4c6ea1d93692f5eefd6048e8c9418116",
    ),
    (
        Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
        "668c0bae91695fa76e5c0708ed4c223affa50787f09060c9c8bc61b3ade1ee72",
    ),
    (FROZEN_MODEL_PATH, FROZEN_MODEL_SHA256),
)

PROTECTED_GIT_PATHS: tuple[Path, ...] = (
    Path("legacy"),
    MAP_PATH,
    TASK_PATH,
    *INHERITED_FILE_SHA256.keys(),
)
IMMUTABILITY_SNAPSHOT_PATHS: tuple[Path, ...] = tuple(
    dict.fromkeys(
        (
            MAP_PATH,
            TASK_PATH,
            *INHERITED_FILE_SHA256.keys(),
            *(path for path, _ in FINAL_SOURCE_FILES),
            FROZEN_BINARY_PATH,
        )
    )
)


class FreezeError(ValueError):
    """Raised when Stage 14A cannot admit an inherited input."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise FreezeError(f"missing required file: {path}")
    return sha256_bytes(path.read_bytes())


def normalised_text_sha256(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FreezeError("semantic hash input is not valid UTF-8") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return sha256_bytes(normalized.encode("utf-8"))


def semantic_file_sha256(path: Path) -> str:
    if not path.is_file():
        raise FreezeError(f"missing semantic hash input: {path}")
    return normalised_text_sha256(path.read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def self_hash(value: Mapping[str, Any], field: str) -> str:
    projection = dict(value)
    projection.pop(field, None)
    return canonical_sha256(projection)


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FreezeError(f"expected JSON object: {path}")
    return value


def _git(
    root: Path,
    *args: str,
    allow_failure: bool = False,
) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode and not allow_failure:
        raise FreezeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def collect_git_identity(root: Path = ROOT) -> dict[str, Any]:
    _, head, _ = _git(root, "rev-parse", "HEAD")
    _, branch, _ = _git(root, "branch", "--show-current")
    _, upstream, _ = _git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
    )
    _, upstream_head, _ = _git(root, "rev-parse", "@{u}")
    start_ancestor_code, _, _ = _git(
        root,
        "merge-base",
        "--is-ancestor",
        START_HEAD,
        "HEAD",
        allow_failure=True,
    )
    start_upstream_ancestor_code, _, _ = _git(
        root,
        "merge-base",
        "--is-ancestor",
        START_HEAD,
        "@{u}",
        allow_failure=True,
    )
    _, tracked_status, _ = _git(
        root,
        "status",
        "--short",
        "--untracked-files=no",
    )
    protected_args = [path.as_posix() for path in PROTECTED_GIT_PATHS]
    _, protected_status, _ = _git(
        root,
        "status",
        "--short",
        "--",
        *protected_args,
    )
    _, protected_commit_diff, _ = _git(
        root,
        "diff",
        "--name-only",
        f"{START_HEAD}..HEAD",
        "--",
        *protected_args,
    )
    return {
        "head": head,
        "branch": branch,
        "upstream": upstream,
        "upstream_head": upstream_head,
        "start_is_ancestor_of_head": start_ancestor_code == 0,
        "start_is_ancestor_of_upstream": start_upstream_ancestor_code == 0,
        "tracked_status": tracked_status.splitlines() if tracked_status else [],
        "protected_status": (
            protected_status.splitlines() if protected_status else []
        ),
        "protected_commit_diff": (
            protected_commit_diff.splitlines()
            if protected_commit_diff
            else []
        ),
    }


def validate_git_identity(
    identity: Mapping[str, Any],
    *,
    require_exact_start: bool,
) -> list[str]:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(identity.get("branch") == START_BRANCH, "unexpected Git branch")
    require(identity.get("upstream") == START_UPSTREAM, "unexpected Git upstream")
    require(
        identity.get("start_is_ancestor_of_head") is True,
        "phase-start commit is not an ancestor of HEAD",
    )
    require(
        identity.get("start_is_ancestor_of_upstream") is True,
        "phase-start commit is not an ancestor of upstream",
    )
    require(
        not identity.get("tracked_status"),
        "tracked worktree is not clean",
    )
    require(
        not identity.get("protected_status"),
        "protected inherited paths have worktree changes",
    )
    require(
        not identity.get("protected_commit_diff"),
        "protected inherited paths changed since phase start",
    )
    if require_exact_start:
        require(identity.get("head") == START_HEAD, "HEAD is not exact phase start")
        require(
            identity.get("upstream_head") == START_UPSTREAM_HEAD,
            "upstream HEAD is not exact phase start",
        )
    return sorted(set(failures))


def _map_identity(root: Path) -> dict[str, Any]:
    path = root / MAP_PATH
    payload = path.read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"canonical map is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise FreezeError("canonical map must be a JSON object")
    heuristic = value.get("heuristic_time", [])
    if not isinstance(heuristic, list):
        heuristic = []
    return {
        "path": MAP_PATH.as_posix(),
        "raw_sha256": sha256_bytes(payload),
        "semantic_sha256": normalised_text_sha256(payload),
        "node_count": len(value.get("nodes", [])),
        "edge_count": len(value.get("edges", [])),
        "heuristic_row_count": len(heuristic),
        "heuristic_column_counts": [
            len(row) if isinstance(row, list) else -1 for row in heuristic
        ],
    }


def _task_identity(root: Path) -> dict[str, Any]:
    path = root / TASK_PATH
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FreezeError("canonical task source is not valid UTF-8") from exc
    row_count = 0
    task_ids: set[int] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FreezeError(
                f"task row {line_number} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise FreezeError(f"task row {line_number} is not an object")
        try:
            task_ids.add(int(value["task_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise FreezeError(
                f"task row {line_number} has no integer task_id"
            ) from exc
        row_count += 1
    return {
        "path": TASK_PATH.as_posix(),
        "raw_sha256": sha256_bytes(payload),
        "semantic_sha256": normalised_text_sha256(payload),
        "segment_count": row_count,
        "raw_bag_count": len(task_ids),
    }


def _descriptors(
    root: Path,
    expected: Mapping[Path, str],
) -> dict[str, dict[str, str]]:
    return {
        path.as_posix(): {
            "path": path.as_posix(),
            "file_sha256": file_sha256(root / path),
            "expected_file_sha256": digest,
        }
        for path, digest in expected.items()
    }


def _phase_start_blob(
    root: Path,
    path: Path,
    expected_sha256: str,
) -> tuple[bytes, str] | None:
    """Return the frozen checkout bytes, or ``None`` for a non-Git temp copy.

    The frozen source bundle records the exact phase-start working-tree bytes.
    Most source files were LF while one tracked model was checked out as CRLF,
    so neither raw Git blobs nor checkout-filtered blobs alone reproduce every
    recorded digest.  Admit the unique Git representation that matches the
    frozen per-file digest and fail closed if neither does.
    """

    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode:
        return None
    variants = (
        (
            "git_blob_raw",
            ["git", "cat-file", "blob", f"{START_HEAD}:{path.as_posix()}"],
        ),
        (
            "git_blob_filtered",
            [
                "git",
                "cat-file",
                "--filters",
                f"--path={path.as_posix()}",
                f"{START_HEAD}:{path.as_posix()}",
            ],
        ),
    )
    observed: list[str] = []
    for label, command in variants:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
        )
        if result.returncode:
            raise FreezeError(
                f"cannot read frozen phase-start Git blob: {path.as_posix()}"
            )
        digest = sha256_bytes(result.stdout)
        observed.append(f"{label}={digest}")
        if digest == expected_sha256:
            return result.stdout, f"{label}:{START_HEAD}"
    raise FreezeError(
        "frozen phase-start Git representations do not match "
        f"{path.as_posix()} expected={expected_sha256} "
        f"observed={','.join(observed)}"
    )


def _source_descriptors(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path, expected in FINAL_SOURCE_FILES:
        blob = _phase_start_blob(root, path, expected)
        payload = blob[0] if blob is not None else (root / path).read_bytes()
        rows.append(
            {
                "path": path.as_posix(),
                "sha256": sha256_bytes(payload),
                "expected_sha256": expected,
                "identity_source": (
                    blob[1] if blob is not None else "temp_copy"
                ),
            }
        )
    return rows


def collect_inherited_evidence(
    root: Path = ROOT,
    *,
    require_binary: bool = False,
) -> dict[str, Any]:
    """Read all Stage-14A inherited inputs without writing repository files."""

    inherited = _descriptors(root, INHERITED_FILE_SHA256)
    source_files = _source_descriptors(root)
    source_rows = [
        {"path": row["path"], "sha256": row["sha256"]}
        for row in source_files
    ]
    f2_policy = read_object(root / G13_F2_POLICY_PATH)
    final_bundle = read_object(root / G13_FINAL_BUNDLE_PATH)
    fault_bundle = read_object(root / G13_FAULT_BUNDLE_PATH)
    no_scale_gate = read_object(root / G13_NO_SCALE_GATE_PATH)
    baseline_manifest = read_object(root / G13_BASELINE_MANIFEST_PATH)
    denominator = read_object(root / G12_DENOMINATOR_PATH)
    binary_path = root / FROZEN_BINARY_PATH
    binary_present = binary_path.is_file()
    if require_binary and not binary_present:
        raise FreezeError(f"missing required file: {binary_path}")
    return {
        "map": _map_identity(root),
        "task": _task_identity(root),
        "inherited_files": inherited,
        "source_files": source_files,
        "source_bundle_sha256": canonical_sha256(source_rows),
        "source_path_manifest_sha256": canonical_sha256(
            [row["path"] for row in source_rows]
        ),
        "binary": {
            "path": FROZEN_BINARY_PATH.as_posix(),
            "file_sha256": (
                file_sha256(binary_path) if binary_present else None
            ),
            "expected_file_sha256": FINAL_BINARY_SHA256,
            "physical_present": binary_present,
            "tracked_artifact": False,
        },
        "f2_policy": f2_policy,
        "final_bundle": final_bundle,
        "fault_bundle": fault_bundle,
        "no_scale_gate": no_scale_gate,
        "baseline_manifest": baseline_manifest,
        "denominator": denominator,
    }


def _close(left: Any, right: float, tolerance: float = 1.0e-9) -> bool:
    try:
        return abs(float(left) - right) <= tolerance
    except (TypeError, ValueError):
        return False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_inherited_evidence(evidence: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    map_identity = _mapping(evidence.get("map"))
    task_identity = _mapping(evidence.get("task"))
    require(
        map_identity.get("raw_sha256") == MAP_RAW_SHA256,
        "canonical map raw SHA-256 drift",
    )
    require(
        map_identity.get("semantic_sha256") == MAP_SEMANTIC_SHA256,
        "canonical map semantic SHA-256 drift",
    )
    require(map_identity.get("node_count") == MAP_NODE_COUNT, "map node-count drift")
    require(map_identity.get("edge_count") == MAP_EDGE_COUNT, "map edge-count drift")
    require(
        map_identity.get("heuristic_row_count") == MAP_NODE_COUNT,
        "map heuristic row-count drift",
    )
    require(
        map_identity.get("heuristic_column_counts") == [MAP_NODE_COUNT] * MAP_NODE_COUNT,
        "map heuristic shape drift",
    )
    require(
        task_identity.get("raw_sha256") == TASK_RAW_SHA256,
        "canonical task raw SHA-256 drift",
    )
    require(
        task_identity.get("semantic_sha256") == TASK_SEMANTIC_SHA256,
        "canonical task semantic SHA-256 drift",
    )
    require(
        task_identity.get("segment_count") == TASK_SEGMENT_COUNT,
        "canonical task segment-count drift",
    )
    require(
        task_identity.get("raw_bag_count") == TASK_RAW_BAG_COUNT,
        "canonical task raw-bag-count drift",
    )

    descriptors = _mapping(evidence.get("inherited_files"))
    for path, expected in INHERITED_FILE_SHA256.items():
        descriptor = _mapping(descriptors.get(path.as_posix()))
        require(
            descriptor.get("file_sha256") == expected,
            f"inherited artifact physical SHA-256 drift: {path.as_posix()}",
        )

    source_files = _list(evidence.get("source_files"))
    expected_source_rows = [
        {"path": path.as_posix(), "sha256": digest}
        for path, digest in FINAL_SOURCE_FILES
    ]
    observed_source_rows = [
        {"path": row.get("path"), "sha256": row.get("sha256")}
        for row in source_files
        if isinstance(row, Mapping)
    ]
    require(
        observed_source_rows == expected_source_rows,
        "final F2 source-file bindings drift",
    )
    require(
        evidence.get("source_bundle_sha256") == FINAL_SOURCE_BUNDLE_SHA256,
        "final F2 source-bundle SHA-256 drift",
    )
    require(
        evidence.get("source_path_manifest_sha256")
        == FINAL_SOURCE_PATH_MANIFEST_SHA256,
        "final F2 source path-manifest SHA-256 drift",
    )
    binary = _mapping(evidence.get("binary"))
    require(
        binary.get("path") == FROZEN_BINARY_PATH.as_posix(),
        "final F2 binary path drift",
    )
    require(
        binary.get("expected_file_sha256") == FINAL_BINARY_SHA256,
        "final F2 expected binary SHA-256 drift",
    )
    physical_present = binary.get("physical_present")
    require(
        isinstance(physical_present, bool),
        "final F2 binary presence evidence is missing",
    )
    if physical_present is True:
        require(
            binary.get("file_sha256") == FINAL_BINARY_SHA256,
            "final F2 binary physical SHA-256 drift",
        )
    elif physical_present is False:
        require(
            binary.get("file_sha256") is None,
            "absent final F2 binary has a physical SHA-256",
        )

    baseline = _mapping(evidence.get("baseline_manifest"))
    require(
        baseline.get("schema") == "czr005.g4irsf13.baseline_freeze_manifest.v1",
        "G4IRSF13 baseline manifest schema drift",
    )
    require(baseline.get("status") == "PASS", "G4IRSF13 baseline status drift")
    require(
        baseline.get("manifest_sha256") == self_hash(baseline, "manifest_sha256"),
        "G4IRSF13 baseline manifest self-hash drift",
    )
    require(
        _mapping(baseline.get("phase_start")).get("branch") == START_BRANCH,
        "G4IRSF13 baseline branch drift",
    )
    require(baseline.get("g4j_status") == "CLOSED", "G4IRSF13 G4J status drift")
    require(
        baseline.get("phase_l_status") == "NOT_RUN",
        "G4IRSF13 phase-L status drift",
    )

    f2 = _mapping(evidence.get("f2_policy"))
    require(
        f2.get("schema") == "czr005.g4irsf13.f2_frozen_baseline.v1",
        "G4IRSF13 F2 schema drift",
    )
    require(
        f2.get("candidate_id") == "G4IRSF13_F2_FROZEN",
        "G4IRSF13 F2 candidate ID drift",
    )
    require(
        f2.get("policy_sha256") == self_hash(f2, "policy_sha256"),
        "G4IRSF13 F2 policy self-hash drift",
    )
    config = _mapping(f2.get("configuration"))
    for name, expected in {
        "resource": "R3_java_node_window_compatible",
        "scorer": "S1_frozen_g4e_legal_local_adapter",
        "pibt": "P2",
        "control": "C0",
        "framework": "event_loop_one_step",
        "pressure_mode": "off",
        "admission_mode": "off",
        "reservation_depth": 1,
    }.items():
        require(config.get(name) == expected, f"F2 configuration drift: {name}")
    metrics = _mapping(f2.get("metrics"))
    for name, expected in {
        "original_entry_mean_minutes": F2_MEAN_MINUTES,
        "decision_sensitive_mean_minutes": F2_DECISION_SENSITIVE_MEAN_MINUTES,
        "source_wait_mean_minutes": F2_SOURCE_WAIT_MEAN_MINUTES,
        "network_time_mean_minutes": F2_NETWORK_TIME_MEAN_MINUTES,
        "delta_vs_v2_safe_seconds": F2_DELTA_V2_SECONDS,
    }.items():
        require(_close(metrics.get(name), expected), f"F2 metric drift: {name}")
    hard_gates = _mapping(f2.get("hard_gates"))
    for name, expected in {
        "complete_raw_bags": TASK_RAW_BAG_COUNT,
        "completed_segments": TASK_SEGMENT_COUNT,
        "failed_segments": 0,
        "conflicts": 0,
        "unsafe_entries": 0,
        "runtime_full_astar_calls": 0,
        "global_reservation_scans": 0,
        "future_routes_stored": 0,
        "unresolved_deadlocks": 0,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "max_edges_selected_per_bag_per_decision": 1,
    }.items():
        require(hard_gates.get(name) == expected, f"F2 hard-gate drift: {name}")
    sealed_provenance = _mapping(f2.get("provenance"))
    for name, expected in {
        "case_config_sha256": F2_CONFIG_SHA256,
        "binary_sha256": SEALED_F2_BINARY_SHA256,
        "source_bundle_sha256": SEALED_F2_SOURCE_BUNDLE_SHA256,
        "source_path_manifest_sha256": SEALED_F2_SOURCE_MANIFEST_SHA256,
    }.items():
        require(
            sealed_provenance.get(name) == expected,
            f"sealed F2 provenance drift: {name}",
        )

    final = _mapping(evidence.get("final_bundle"))
    require(
        final.get("schema") == "czr005.g4irsf13.final_candidate_bundle.v1",
        "G4IRSF13 final bundle schema drift",
    )
    require(
        final.get("bundle_sha256") == self_hash(final, "bundle_sha256"),
        "G4IRSF13 final bundle self-hash drift",
    )
    require(final.get("status") == "COMPLETE", "G4IRSF13 final status drift")
    require(
        final.get("decision_status") == "HISTORICAL_ONLY_PASS",
        "G4IRSF13 final decision drift",
    )
    require(
        final.get("deployment_recommendation")
        == "KEEP_F2_FROZEN_CONTROL_NO_NEW_CANDIDATE_PROMOTION",
        "G4IRSF13 deployment recommendation drift",
    )
    require(
        final.get("all_1x_hard_gates_pass") is True,
        "G4IRSF13 final 1x hard gate drift",
    )
    corrected = _mapping(final.get("corrected_controls"))
    for name, expected in {
        "f2_reconciled_raw_entry_minutes": F2_MEAN_MINUTES,
        "frozen_v2_safe_raw_entry_minutes": V2_SAFE_MEAN_MINUTES,
        "historical_hca_raw_entry_minutes": HISTORICAL_HCA_MEAN_MINUTES,
    }.items():
        require(
            _close(corrected.get(name), expected),
            f"G4IRSF13 corrected control drift: {name}",
        )
    decision = _mapping(final.get("decision"))
    for name, expected in {
        "decision_status": "HISTORICAL_ONLY_PASS",
        "strict_win_vs_v2_safe": False,
        "strict_win_vs_historical_hca": True,
        "v3_contribution_proven": False,
        "delta_vs_v2_safe_seconds_per_bag": F2_DELTA_V2_SECONDS,
        "delta_vs_historical_hca_seconds_per_bag": F2_DELTA_HCA_SECONDS,
    }.items():
        observed = decision.get(name)
        condition = (
            _close(observed, expected)
            if isinstance(expected, float)
            else observed == expected
        )
        require(condition, f"G4IRSF13 final decision field drift: {name}")
    source_bundle = _mapping(final.get("source_bundle"))
    require(
        source_bundle.get("files") == expected_source_rows,
        "G4IRSF13 final source-file manifest drift",
    )
    require(
        source_bundle.get("bundle_sha256") == FINAL_SOURCE_BUNDLE_SHA256,
        "G4IRSF13 final declared source-bundle drift",
    )
    require(
        source_bundle.get("path_manifest_sha256")
        == FINAL_SOURCE_PATH_MANIFEST_SHA256,
        "G4IRSF13 final declared path-manifest drift",
    )
    f2_repeats = [
        row
        for row in _list(final.get("repeat_bindings"))
        if isinstance(row, Mapping) and row.get("candidate_id") == "H0_F2_FROZEN"
    ]
    require(len(f2_repeats) == 1, "expected one final H0 F2 repeat binding")
    if len(f2_repeats) == 1:
        repeat = f2_repeats[0]
        for name, expected in {
            "binary_sha256": FINAL_BINARY_SHA256,
            "source_bundle_sha256": FINAL_SOURCE_BUNDLE_SHA256,
            "map_raw_sha256": MAP_RAW_SHA256,
            "task_raw_sha256": TASK_RAW_SHA256,
            "repeat_count": 5,
        }.items():
            require(
                repeat.get(name) == expected,
                f"final H0 F2 runtime identity drift: {name}",
            )
        require(
            repeat.get("hard_gate_statuses") == ["PASS"] * 5,
            "final H0 F2 repeat hard-gate drift",
        )
        final_metrics = _mapping(repeat.get("metrics"))
        require(
            _close(final_metrics.get("original_entry_mean_minutes"), F2_MEAN_MINUTES),
            "final H0 F2 mean drift",
        )
        require(
            _close(final_metrics.get("path_edge_count_mean"), F2_PATH_EDGES_MEAN),
            "final H0 F2 path-edge mean drift",
        )

    fault = _mapping(evidence.get("fault_bundle"))
    require(
        fault.get("schema") == "czr005.g4irsf13.fault_control.v1",
        "G4IRSF13 fault schema drift",
    )
    require(
        fault.get("self_sha256") == self_hash(fault, "self_sha256"),
        "G4IRSF13 fault self-hash drift",
    )
    for name, expected in {
        "status": "FAULT_DISCRIMINATING_PASS",
        "executed_case_gate_pass": True,
        "frozen_binary_match_pass": True,
        "frozen_binary_sha256": FINAL_BINARY_SHA256,
        "f2_case_config_sha256": F2_CONFIG_SHA256,
        "unsafe_entry_count": 0,
        "v3_fault_aware_status": (
            "NOT_RUN_FRESH_HOLDOUT_OFFLINE_FAIL_RUNTIME_ACTIVATION_FORBIDDEN"
        ),
    }.items():
        require(fault.get(name) == expected, f"G4IRSF13 fault field drift: {name}")

    no_scale = _mapping(evidence.get("no_scale_gate"))
    require(
        no_scale.get("schema") == "czr005.g4irsf13.kl_unlock_decision.v1",
        "G4IRSF13 no-scale schema drift",
    )
    require(
        no_scale.get("self_sha256") == self_hash(no_scale, "self_sha256"),
        "G4IRSF13 no-scale self-hash drift",
    )
    for name, expected in {
        "decision": "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "g4j_status": "CLOSED",
        "phase_k_status": "UNKNOWN/CLOSED",
        "phase_l_status": "NOT_RUN",
        "scale_execution_count": 0,
        "scale_execution_status": "NOT_RUN",
        "all_five_gates_pass": False,
    }.items():
        require(no_scale.get(name) == expected, f"no-scale gate drift: {name}")
    gate_results = {
        row.get("gate_id"): row.get("passed")
        for row in _list(no_scale.get("gates"))
        if isinstance(row, Mapping)
    }
    require(
        gate_results
        == {
            "strict_v2_win": False,
            "v3_contribution": False,
            "fault_discriminating": True,
            "numeric_demand_calibration": False,
            "original_task_generation_audit": True,
        },
        "no-scale conjunctive gate ledger drift",
    )

    denominator = _mapping(evidence.get("denominator"))
    require(
        denominator.get("reconciliation_sha256")
        == self_hash(denominator, "reconciliation_sha256"),
        "G4IRSF12 denominator self-hash drift",
    )
    targets = _mapping(denominator.get("corrected_targets"))
    require(
        _close(targets.get("v2_safe_raw_entry_target_minutes"), V2_SAFE_MEAN_MINUTES),
        "denominator v2-safe target drift",
    )
    require(
        _close(
            targets.get("historical_hca_raw_entry_target_minutes"),
            HISTORICAL_HCA_MEAN_MINUTES,
        ),
        "denominator historical HCA target drift",
    )
    return sorted(set(failures))


def _descriptor(
    evidence: Mapping[str, Any],
    path: Path,
    *,
    self_hash_field: str | None = None,
) -> dict[str, Any]:
    physical = _mapping(
        _mapping(evidence.get("inherited_files")).get(path.as_posix())
    )
    descriptor: dict[str, Any] = {
        "path": path.as_posix(),
        "file_sha256": physical.get("file_sha256"),
    }
    if self_hash_field:
        payload_by_path = {
            G13_BASELINE_MANIFEST_PATH: evidence.get("baseline_manifest"),
            G13_F2_POLICY_PATH: evidence.get("f2_policy"),
            G13_FINAL_BUNDLE_PATH: evidence.get("final_bundle"),
            G13_FAULT_BUNDLE_PATH: evidence.get("fault_bundle"),
            G13_NO_SCALE_GATE_PATH: evidence.get("no_scale_gate"),
            G12_DENOMINATOR_PATH: evidence.get("denominator"),
        }
        payload = _mapping(payload_by_path.get(path))
        descriptor["self_hash_field"] = self_hash_field
        descriptor["declared_self_sha256"] = payload.get(self_hash_field)
        descriptor["self_hash_valid"] = (
            payload.get(self_hash_field) == self_hash(payload, self_hash_field)
        )
    return descriptor


def build_f2_frozen_control(evidence: Mapping[str, Any]) -> dict[str, Any]:
    f2 = _mapping(evidence["f2_policy"])
    final = _mapping(evidence["final_bundle"])
    final_repeat = next(
        row
        for row in _list(final.get("repeat_bindings"))
        if isinstance(row, Mapping) and row.get("candidate_id") == "H0_F2_FROZEN"
    )
    payload: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.f2_frozen_control.v1",
        "phase": "G4IRSF14-A",
        "status": "PASS_FROZEN_CONTROL",
        "candidate_id": "G4IRSF14_F2_FROZEN_CONTROL",
        "inherited_candidate_id": f2["candidate_id"],
        "configuration": dict(_mapping(f2["configuration"])),
        "protected_inputs": {
            "map": dict(_mapping(evidence["map"])),
            "task": dict(_mapping(evidence["task"])),
            "hash_semantics": (
                "raw=sha256_exact_bytes; semantic=sha256_utf8_after_crlf_cr_to_lf"
            ),
        },
        "comparators": {
            "f2_original_entry_mean_minutes": F2_MEAN_MINUTES,
            "frozen_v2_safe_original_entry_mean_minutes": V2_SAFE_MEAN_MINUTES,
            "historical_hca_original_entry_mean_minutes": (
                HISTORICAL_HCA_MEAN_MINUTES
            ),
            "delta_vs_v2_safe_seconds_per_bag": F2_DELTA_V2_SECONDS,
            "delta_vs_historical_hca_seconds_per_bag": F2_DELTA_HCA_SECONDS,
            "primary_denominator": "original_entry_time_tth",
        },
        "metrics": {
            "original_entry_mean_minutes": F2_MEAN_MINUTES,
            "decision_sensitive_mean_minutes": (
                F2_DECISION_SENSITIVE_MEAN_MINUTES
            ),
            "source_wait_mean_minutes": F2_SOURCE_WAIT_MEAN_MINUTES,
            "network_time_mean_minutes": F2_NETWORK_TIME_MEAN_MINUTES,
            "path_edge_count_mean": F2_PATH_EDGES_MEAN,
        },
        "hard_gates": dict(_mapping(f2["hard_gates"])),
        "final_runtime_identity": {
            "binary": {
                "path": FROZEN_BINARY_PATH.as_posix(),
                "file_sha256": FINAL_BINARY_SHA256,
                "expected_file_sha256": FINAL_BINARY_SHA256,
                "tracked_artifact": False,
            },
            "case_config_sha256": F2_CONFIG_SHA256,
            "source_bundle_sha256": FINAL_SOURCE_BUNDLE_SHA256,
            "source_path_manifest_sha256": (
                FINAL_SOURCE_PATH_MANIFEST_SHA256
            ),
            "source_files": [
                {"path": row["path"], "sha256": row["sha256"]}
                for row in _list(evidence["source_files"])
                if isinstance(row, Mapping)
            ],
            "model": {
                "path": FROZEN_MODEL_PATH.as_posix(),
                "file_sha256": FROZEN_MODEL_SHA256,
                "model_type": "g4e_risk_calibrated_policy",
            },
            "repeat_count": final_repeat["repeat_count"],
            "repeat_result_file_sha256": (
                final_repeat["repeat_result_file_sha256"]
            ),
            "runtime_deterministic_sha256": (
                final_repeat["runtime_deterministic_sha256"]
            ),
            "bags_sha256": final_repeat["bags_sha256"],
            "junction_state_sha256": final_repeat["junction_state_sha256"],
            "algorithm_summary_sha256": (
                final_repeat["algorithm_summary_sha256"]
            ),
            "trace_context_sha256": final_repeat["trace_context_sha256"],
        },
        "sealed_predecessor_runtime_identity": {
            "binary_sha256": SEALED_F2_BINARY_SHA256,
            "case_config_sha256": F2_CONFIG_SHA256,
            "source_bundle_sha256": SEALED_F2_SOURCE_BUNDLE_SHA256,
            "source_path_manifest_sha256": (
                SEALED_F2_SOURCE_MANIFEST_SHA256
            ),
            "claim_boundary": (
                "Earlier sealed F2 evidence generation; retained separately "
                "and not conflated with the final five-repeat binary."
            ),
        },
        "source_bindings": {
            "f2_policy": _descriptor(
                evidence,
                G13_F2_POLICY_PATH,
                self_hash_field="policy_sha256",
            ),
            "final_candidate_bundle": _descriptor(
                evidence,
                G13_FINAL_BUNDLE_PATH,
                self_hash_field="bundle_sha256",
            ),
            "denominator_reconciliation": _descriptor(
                evidence,
                G12_DENOMINATOR_PATH,
                self_hash_field="reconciliation_sha256",
            ),
        },
        "claim_boundary": (
            "Frozen control only: complete and safe at original 1x, better than "
            "corrected historical HCA, but 1.1347038098698192 s/bag slower "
            "than frozen v2-safe. No new candidate is promoted."
        ),
    }
    payload["control_sha256"] = canonical_sha256(payload)
    return payload


def build_fault_frozen_control(evidence: Mapping[str, Any]) -> dict[str, Any]:
    fault = _mapping(evidence["fault_bundle"])
    payload: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.fault_frozen_control.v1",
        "phase": "G4IRSF14-A",
        "status": "FAULT_DISCRIMINATING_PASS_FROZEN",
        "policy_id": fault["policy_id"],
        "runtime_scope": fault["runtime_scope"],
        "bti_scope": fault["bti_scope"],
        "ddi_scope": fault["ddi_scope"],
        "physical_interlock": fault["physical_interlock"],
        "containment": list(_list(fault["containment"])),
        "repair": list(_list(fault["repair"])),
        "forbidden": list(_list(fault["forbidden"])),
        "runtime_identity": {
            "binary_sha256": fault["frozen_binary_sha256"],
            "case_config_sha256": fault["f2_case_config_sha256"],
            "map_raw_sha256": fault["map_raw_sha256"],
            "task_raw_sha256": fault["task_raw_sha256"],
            "frozen_binary_match_pass": fault["frozen_binary_match_pass"],
        },
        "executed_evidence": {
            "executed_case_count": 13,
            "informative_fault_case_count": 12,
            "hard_failure_count": 0,
            "unsafe_entry_count": fault["unsafe_entry_count"],
            "executed_case_gate_pass": fault["executed_case_gate_pass"],
            "physical_generation_audit_pass": (
                fault["physical_generation_audit_pass"]
            ),
            "causally_promoted_case_ids": list(
                _list(fault["causally_promoted_case_ids"])
            ),
        },
        "unproven_boundary": {
            "v3_fault_aware_status": fault["v3_fault_aware_status"],
            "multi_fault_active_policy_benefit": "NOT_PROVEN",
            "cut_isolation_active_policy_benefit": "NOT_PROVEN",
        },
        "source_bindings": {
            "fault_bundle": _descriptor(
                evidence,
                G13_FAULT_BUNDLE_PATH,
                self_hash_field="self_sha256",
            ),
            "fault_report": _descriptor(evidence, G13_FAULT_REPORT_PATH),
            "fault_table": _descriptor(evidence, G13_FAULT_TABLE_PATH),
        },
        "claim_boundary": fault["claim_boundary"],
    }
    payload["control_sha256"] = canonical_sha256(payload)
    return payload


def _json_payload(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def build_baseline_registry(
    evidence: Mapping[str, Any],
    f2_control: Mapping[str, Any],
    fault_control: Mapping[str, Any],
    *,
    f2_file_sha256: str,
    fault_file_sha256: str,
) -> dict[str, Any]:
    final = _mapping(evidence["final_bundle"])
    no_scale = _mapping(evidence["no_scale_gate"])
    payload: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.baseline_registry.v1",
        "phase": "G4IRSF14-A",
        "status": "PASS_BASELINE_FROZEN",
        "phase_start": {
            "date": PHASE_DATE,
            "branch": START_BRANCH,
            "head": START_HEAD,
            "upstream": START_UPSTREAM,
            "upstream_head": START_UPSTREAM_HEAD,
            "head_equals_upstream_head": True,
        },
        "protected_inputs": {
            "map": dict(_mapping(evidence["map"])),
            "task": dict(_mapping(evidence["task"])),
        },
        "f2_frozen_control": {
            "path": F2_FROZEN_CONTROL_PATH.as_posix(),
            "file_sha256": f2_file_sha256,
            "control_sha256": f2_control["control_sha256"],
            "status": f2_control["status"],
        },
        "fault_frozen_control": {
            "path": FAULT_FROZEN_CONTROL_PATH.as_posix(),
            "file_sha256": fault_file_sha256,
            "control_sha256": fault_control["control_sha256"],
            "status": fault_control["status"],
        },
        "g4irsf13_final_decision": {
            "decision_status": final["decision_status"],
            "deployment_recommendation": final["deployment_recommendation"],
            "selected_candidate_id": final["selected_candidate_id"],
            "all_1x_hard_gates_pass": final["all_1x_hard_gates_pass"],
            "strict_win_vs_v2_safe": final["strict_win_vs_v2_safe"],
            "strict_win_vs_f2": final["strict_win_vs_f2"],
            "v3_contribution_proven": final["v3_contribution_proven"],
            "source": _descriptor(
                evidence,
                G13_FINAL_BUNDLE_PATH,
                self_hash_field="bundle_sha256",
            ),
            "report": _descriptor(evidence, G13_FINAL_REPORT_PATH),
            "table": _descriptor(evidence, G13_FINAL_TABLE_PATH),
        },
        "comparators": {
            "denominator": "original_entry_time_tth",
            "f2_raw_entry_mean_minutes": F2_MEAN_MINUTES,
            "v2_safe_raw_entry_mean_minutes": V2_SAFE_MEAN_MINUTES,
            "historical_hca_raw_entry_mean_minutes": (
                HISTORICAL_HCA_MEAN_MINUTES
            ),
            "f2_delta_vs_v2_safe_seconds_per_bag": F2_DELTA_V2_SECONDS,
            "f2_delta_vs_historical_hca_seconds_per_bag": (
                F2_DELTA_HCA_SECONDS
            ),
        },
        "no_scale_gate": {
            "decision": no_scale["decision"],
            "g4j_status": no_scale["g4j_status"],
            "phase_k_status": no_scale["phase_k_status"],
            "phase_l_status": no_scale["phase_l_status"],
            "scale_execution_count": no_scale["scale_execution_count"],
            "scale_execution_status": no_scale["scale_execution_status"],
            "all_five_gates_pass": no_scale["all_five_gates_pass"],
            "source": _descriptor(
                evidence,
                G13_NO_SCALE_GATE_PATH,
                self_hash_field="self_sha256",
            ),
        },
        "inherited_artifacts": {
            path: {
                "path": descriptor["path"],
                "file_sha256": descriptor["file_sha256"],
                "access": "READ_ONLY",
            }
            for path, descriptor in sorted(
                _mapping(evidence["inherited_files"]).items()
            )
        },
        "governance": {
            "namespace": "g4irsf14_",
            "old_reports_recomputed": False,
            "sealed_g4irsf12_or_g4irsf13_artifacts_rewritten": False,
            "scale_workload_materialized_or_executed": False,
            "drift_policy": "FAIL_CLOSED",
            "publication_outputs": [path.as_posix() for path in OUTPUT_PATHS],
        },
    }
    payload["registry_sha256"] = canonical_sha256(payload)
    return payload


def render_git_identity_csv() -> bytes:
    rows = [
        {
            "scope": "git",
            "check": "phase_start_branch",
            "status": "PASS",
            "observed": START_BRANCH,
            "expected": START_BRANCH,
            "evidence": "git branch --show-current",
            "notes": "exact Stage-14A generation snapshot",
        },
        {
            "scope": "git",
            "check": "phase_start_head",
            "status": "PASS",
            "observed": START_HEAD,
            "expected": START_HEAD,
            "evidence": "git rev-parse HEAD",
            "notes": "exact Stage-14A generation snapshot",
        },
        {
            "scope": "git",
            "check": "phase_start_upstream",
            "status": "PASS",
            "observed": START_UPSTREAM,
            "expected": START_UPSTREAM,
            "evidence": "git rev-parse --abbrev-ref --symbolic-full-name @{u}",
            "notes": "",
        },
        {
            "scope": "git",
            "check": "phase_start_upstream_head",
            "status": "PASS",
            "observed": START_UPSTREAM_HEAD,
            "expected": START_UPSTREAM_HEAD,
            "evidence": "git rev-parse @{u}",
            "notes": "local HEAD equaled upstream HEAD before Stage-14A writes",
        },
        {
            "scope": "git",
            "check": "tracked_worktree_clean",
            "status": "PASS",
            "observed": "true",
            "expected": "true",
            "evidence": "git status --short --untracked-files=no",
            "notes": "unrelated pre-existing untracked scratch directories excluded",
        },
        {
            "scope": "protection",
            "check": "legacy_clean",
            "status": "PASS",
            "observed": "true",
            "expected": "true",
            "evidence": "git status --short -- legacy",
            "notes": "",
        },
        {
            "scope": "protection",
            "check": "canonical_map_clean",
            "status": "PASS",
            "observed": "true",
            "expected": "true",
            "evidence": f"git status --short -- {MAP_PATH.as_posix()}",
            "notes": "",
        },
        {
            "scope": "protection",
            "check": "canonical_task_clean",
            "status": "PASS",
            "observed": "true",
            "expected": "true",
            "evidence": f"git status --short -- {TASK_PATH.as_posix()}",
            "notes": "",
        },
        {
            "scope": "identity",
            "check": "map_raw_sha256",
            "status": "PASS",
            "observed": MAP_RAW_SHA256,
            "expected": MAP_RAW_SHA256,
            "evidence": MAP_PATH.as_posix(),
            "notes": "SHA-256 over exact bytes",
        },
        {
            "scope": "identity",
            "check": "map_semantic_sha256",
            "status": "PASS",
            "observed": MAP_SEMANTIC_SHA256,
            "expected": MAP_SEMANTIC_SHA256,
            "evidence": MAP_PATH.as_posix(),
            "notes": "UTF-8 with CRLF/CR normalized to LF",
        },
        {
            "scope": "identity",
            "check": "task_raw_sha256",
            "status": "PASS",
            "observed": TASK_RAW_SHA256,
            "expected": TASK_RAW_SHA256,
            "evidence": TASK_PATH.as_posix(),
            "notes": "SHA-256 over exact bytes",
        },
        {
            "scope": "identity",
            "check": "task_semantic_sha256",
            "status": "PASS",
            "observed": TASK_SEMANTIC_SHA256,
            "expected": TASK_SEMANTIC_SHA256,
            "evidence": TASK_PATH.as_posix(),
            "notes": "UTF-8 with CRLF/CR normalized to LF",
        },
        {
            "scope": "identity",
            "check": "task_counts",
            "status": "PASS",
            "observed": "43603 segments / 28506 raw bags",
            "expected": "43603 segments / 28506 raw bags",
            "evidence": TASK_PATH.as_posix(),
            "notes": "raw bags are unique task_id values",
        },
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "scope",
            "check",
            "status",
            "observed",
            "expected",
            "evidence",
            "notes",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def render_start_state(registry: Mapping[str, Any]) -> bytes:
    text = f"""# G4IRSF14-A Start State

Date: {PHASE_DATE}

Status: `PASS_BASELINE_FROZEN`.

Stage 14A records the starting identities and references G4IRSF13 evidence
without rerunning it. Any identity, self-hash, provenance, or protected-file
drift is `FAIL_CLOSED`.

## Exact Git snapshot

| Item | Frozen value |
| --- | --- |
| Branch | `{START_BRANCH}` |
| HEAD | `{START_HEAD}` |
| Upstream | `{START_UPSTREAM}` |
| Upstream HEAD | `{START_UPSTREAM_HEAD}` |
| HEAD equals upstream HEAD | `true` |
| Tracked worktree before Stage-14A writes | clean |

Descendant commits are valid only while `{START_HEAD}` remains an ancestor and
the protected inherited paths have no worktree or committed drift.

## Protected real-map workload

| Item | Frozen value |
| --- | --- |
| Map | `{MAP_PATH.as_posix()}` |
| Map raw SHA-256 | `{MAP_RAW_SHA256}` |
| Map semantic SHA-256 | `{MAP_SEMANTIC_SHA256}` |
| Map shape | {MAP_NODE_COUNT} nodes / {MAP_EDGE_COUNT} directed edges / 54x54 heuristic |
| Task source | `{TASK_PATH.as_posix()}` |
| Task raw SHA-256 | `{TASK_RAW_SHA256}` |
| Task semantic SHA-256 | `{TASK_SEMANTIC_SHA256}` |
| Task counts | {TASK_SEGMENT_COUNT:,} segments / {TASK_RAW_BAG_COUNT:,} raw bags |

Raw hashes cover exact bytes. Semantic hashes decode UTF-8 and normalize only
CRLF/CR newlines to LF; JSON is not rewritten or semantically reordered.

## Frozen controls

| Control | Frozen result |
| --- | --- |
| F2 configuration | `R3 / S1 / P2 / C0 / Q0`, reservation depth 1 |
| F2 raw-entry mean | `{F2_MEAN_MINUTES:.12f}` min |
| Frozen v2-safe raw-entry mean | `{V2_SAFE_MEAN_MINUTES:.12f}` min |
| Corrected historical HCA raw-entry mean | `{HISTORICAL_HCA_MEAN_MINUTES:.12f}` min |
| F2 delta vs v2-safe | `+{F2_DELTA_V2_SECONDS:.12f}` s/bag |
| F2 delta vs historical HCA | `{F2_DELTA_HCA_SECONDS:.12f}` s/bag |
| Final F2 binary SHA-256 | `{FINAL_BINARY_SHA256}` |
| Final F2 source-bundle SHA-256 | `{FINAL_SOURCE_BUNDLE_SHA256}` |
| Frozen model SHA-256 | `{FROZEN_MODEL_SHA256}` |
| F2 case-config SHA-256 | `{F2_CONFIG_SHA256}` |

The earlier sealed F2 artifact names a different execution generation
(`{SEALED_F2_BINARY_SHA256}` binary and
`{SEALED_F2_SOURCE_BUNDLE_SHA256}` source bundle). It remains frozen and is
recorded separately; it is not presented as the final five-repeat binary.

## G4IRSF13 decision and scale lock

- Final decision: `HISTORICAL_ONLY_PASS`.
- Deployment: `KEEP_F2_FROZEN_CONTROL_NO_NEW_CANDIDATE_PROMOTION`.
- Strict win versus frozen v2-safe: `false`.
- Independent V3 contribution proven: `false`.
- Fault control: `FAULT_DISCRIMINATING_PASS` (13 executed, 12 informative,
  zero hard failures, aggregate unsafe entry 0).
- G4J: `CLOSED`; phase K: `UNKNOWN/CLOSED`; phase L: `NOT_RUN`.
- Scale execution count: `0`.

No scale workload is materialized or executed by Stage 14A.

## Machine-readable authority

- Baseline registry: `{BASELINE_REGISTRY_PATH.as_posix()}`
- F2 control: `{F2_FROZEN_CONTROL_PATH.as_posix()}`
- Fault control: `{FAULT_FROZEN_CONTROL_PATH.as_posix()}`
- Git/identity ledger: `{GIT_IDENTITY_TABLE_PATH.as_posix()}`
- Registry self-hash: `{registry["registry_sha256"]}`

All new Stage-14A artifacts use the `g4irsf14_` namespace.
No G4IRSF12 or G4IRSF13 artifact is rewritten.
"""
    return text.encode("utf-8")


def build_payloads(evidence: Mapping[str, Any]) -> dict[Path, bytes]:
    failures = validate_inherited_evidence(evidence)
    if failures:
        raise FreezeError("FAIL_CLOSED: " + "; ".join(failures))
    f2_control = build_f2_frozen_control(evidence)
    fault_control = build_fault_frozen_control(evidence)
    f2_bytes = _json_payload(f2_control)
    fault_bytes = _json_payload(fault_control)
    registry = build_baseline_registry(
        evidence,
        f2_control,
        fault_control,
        f2_file_sha256=sha256_bytes(f2_bytes),
        fault_file_sha256=sha256_bytes(fault_bytes),
    )
    return {
        BASELINE_REGISTRY_PATH: _json_payload(registry),
        F2_FROZEN_CONTROL_PATH: f2_bytes,
        FAULT_FROZEN_CONTROL_PATH: fault_bytes,
        START_STATE_REPORT_PATH: render_start_state(registry),
        GIT_IDENTITY_TABLE_PATH: render_git_identity_csv(),
    }


def snapshot_files(
    root: Path,
    paths: Iterable[Path] = IMMUTABILITY_SNAPSHOT_PATHS,
) -> dict[str, str]:
    return {
        path.as_posix(): file_sha256(root / path)
        for path in paths
    }


def publish_payloads(
    payloads: Mapping[Path, bytes],
    root: Path = ROOT,
) -> tuple[Path, ...]:
    """Publish only the five namespaced outputs and prove inputs were untouched."""

    if set(payloads) != set(OUTPUT_PATHS):
        raise FreezeError("refusing publication outside the five Stage-14A outputs")
    before = snapshot_files(root)
    written: list[Path] = []
    for relative in OUTPUT_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
        temporary.write_bytes(payloads[relative])
        temporary.replace(target)
        written.append(target)
    after = snapshot_files(root)
    if after != before:
        changed = sorted(path for path in before if before[path] != after.get(path))
        raise FreezeError(
            "protected input changed during publication: " + ", ".join(changed)
        )
    return tuple(written)


def _read_csv_bytes(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def validate_output_payloads(
    payloads: Mapping[Path, bytes],
    evidence: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    try:
        expected = build_payloads(evidence)
    except Exception as exc:  # noqa: BLE001 - admission must fail closed
        return [f"cannot rebuild expected outputs: {exc}"]
    if set(payloads) != set(OUTPUT_PATHS):
        failures.append("output set is not exactly the five Stage-14A artifacts")
    for relative, expected_bytes in expected.items():
        observed = payloads.get(relative)
        if observed is None:
            failures.append(f"missing output payload: {relative.as_posix()}")
        elif observed != expected_bytes:
            failures.append(
                f"output differs from deterministic render: {relative.as_posix()}"
            )
    if failures:
        return sorted(set(failures))

    try:
        registry = json.loads(payloads[BASELINE_REGISTRY_PATH].decode("utf-8"))
        f2 = json.loads(payloads[F2_FROZEN_CONTROL_PATH].decode("utf-8"))
        fault = json.loads(payloads[FAULT_FROZEN_CONTROL_PATH].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return [f"generated JSON parse failure: {exc}"]
    if registry.get("registry_sha256") != self_hash(registry, "registry_sha256"):
        failures.append("baseline registry self-hash mismatch")
    if f2.get("control_sha256") != self_hash(f2, "control_sha256"):
        failures.append("F2 frozen control self-hash mismatch")
    if fault.get("control_sha256") != self_hash(fault, "control_sha256"):
        failures.append("fault frozen control self-hash mismatch")
    if (
        registry.get("f2_frozen_control", {}).get("file_sha256")
        != sha256_bytes(payloads[F2_FROZEN_CONTROL_PATH])
    ):
        failures.append("registry-to-F2 physical hash binding mismatch")
    if (
        registry.get("fault_frozen_control", {}).get("file_sha256")
        != sha256_bytes(payloads[FAULT_FROZEN_CONTROL_PATH])
    ):
        failures.append("registry-to-fault physical hash binding mismatch")
    rows = _read_csv_bytes(payloads[GIT_IDENTITY_TABLE_PATH])
    if len(rows) != 13:
        failures.append("Git identity table must contain exactly 13 checks")
    if any(row.get("status") != "PASS" for row in rows):
        failures.append("Git identity table contains a non-PASS row")
    report = payloads[START_STATE_REPORT_PATH].decode("utf-8")
    for required in (
        "Status: `PASS_BASELINE_FROZEN`",
        START_HEAD,
        MAP_RAW_SHA256,
        MAP_SEMANTIC_SHA256,
        TASK_RAW_SHA256,
        "HISTORICAL_ONLY_PASS",
        "Scale execution count: `0`",
        "No G4IRSF12 or G4IRSF13 artifact is rewritten",
    ):
        if required not in report:
            failures.append(f"start-state report missing required text: {required}")
    return sorted(set(failures))


def validate_committed_outputs(
    root: Path = ROOT,
    evidence: Mapping[str, Any] | None = None,
) -> list[str]:
    if evidence is None:
        try:
            evidence = collect_inherited_evidence(root)
        except Exception as exc:  # noqa: BLE001 - fail closed on any read error
            return [f"inherited evidence collection failed: {exc}"]
    payloads: dict[Path, bytes] = {}
    for relative in OUTPUT_PATHS:
        path = root / relative
        if not path.is_file():
            return [f"missing committed Stage-14A output: {relative.as_posix()}"]
        payloads[relative] = path.read_bytes()
    return validate_output_payloads(payloads, evidence)


def run_audit(
    root: Path = ROOT,
    *,
    require_exact_start: bool,
    require_outputs: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    evidence: dict[str, Any] | None = None
    try:
        git_identity = collect_git_identity(root)
        failures.extend(
            validate_git_identity(
                git_identity,
                require_exact_start=require_exact_start,
            )
        )
    except Exception as exc:  # noqa: BLE001 - Git collection fails closed
        failures.append(f"Git identity collection failed: {exc}")
    try:
        evidence = collect_inherited_evidence(
            root,
            require_binary=require_exact_start,
        )
        failures.extend(validate_inherited_evidence(evidence))
    except Exception as exc:  # noqa: BLE001 - input collection fails closed
        failures.append(f"inherited evidence collection failed: {exc}")
    if require_outputs and evidence is not None:
        failures.extend(validate_committed_outputs(root, evidence))
    return evidence, sorted(set(failures))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="publish the five Stage-14A outputs after exact-start validation",
    )
    parser.add_argument(
        "--validate-committed",
        action="store_true",
        help="validate the five committed outputs deterministically",
    )
    parser.add_argument(
        "--require-exact-start",
        action="store_true",
        help="require HEAD and upstream HEAD to equal the frozen start SHA",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo.resolve()
    require_exact = args.write or args.require_exact_start
    evidence, failures = run_audit(
        root,
        require_exact_start=require_exact,
        require_outputs=args.validate_committed and not args.write,
    )
    written: list[str] = []
    if args.write and not failures and evidence is not None:
        try:
            payloads = build_payloads(evidence)
            written_paths = publish_payloads(payloads, root)
            written = [path.resolve().as_posix() for path in written_paths]
            failures.extend(validate_committed_outputs(root, evidence))
        except Exception as exc:  # noqa: BLE001 - publication fails closed
            failures.append(f"publication failed: {exc}")
    failures = sorted(set(failures))
    result = {
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "phase": "G4IRSF14-A",
        "phase_start_head": START_HEAD,
        "failures": failures,
        "written": written,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
