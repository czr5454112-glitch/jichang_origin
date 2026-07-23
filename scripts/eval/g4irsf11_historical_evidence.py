"""Validate frozen G4IRSF11 evidence against its producing Git baseline.

G4IRSF11 is historical evidence once G4IRSF12 changes the implementation.  A
historical completion must therefore be checked against the immutable Git tree
that produced it, not against today's source tree.  This module pins the only
trusted baseline, reconstructs its exact source bundle from Git blobs, and
then re-hashes every working-tree evidence artifact named by that baseline.

Nothing here updates a completion hash.  Unknown commits, missing Git objects,
registry edits, source-bundle drift, completion edits, and artifact edits all
fail closed.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence

from scripts.eval.g4irsf11_publication import completion_validation_errors
from scripts.eval.g4irsf11_result_validation import parse_json_object, read_json_object


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "artifacts" / "gates" / "g4irsf11_historical_baseline_registry.json"
REGISTRY_SCHEMA = "czr005.g4irsf11.historical_baseline_registry.v1"
DEFAULT_BASELINE_ID = "g4irsf11_fixed_real_map_84_case_completion"

TRUSTED_REGISTRY_DOCUMENT: dict[str, Any] = {
    "schema": REGISTRY_SCHEMA,
    "baselines": [
        {
            "baseline_id": DEFAULT_BASELINE_ID,
            "commit_sha": "259608cd536f8ca2f6651a01b7d842675f63a9f7",
            "commit_tree_sha": "a9e3db7abf6eee0bc307e721ece8746322e7931e",
            "completion_manifest_path": (
                "artifacts/gates/g4irsf11_event_runtime_completion.json"
            ),
            "completion_manifest_semantic_sha256": (
                "f1270b6bdb7ebbede3df5790dd3bafe7bc7f045b33e74ece8280023aadc39b24"
            ),
            "expected_case_count": 84,
            "implementation_runtime_sha256": (
                "92c7e4588a902770fd14ffd87c4924f7f7af9246a42b00dfc523616591e04ba9"
            ),
            "implementation_source_bundle_sha256": (
                "99758e68f445d97c00b876e2edb788df2fdb51eb2443af42e9384b66ebd801e5"
            ),
            "implementation_source_file_count": 90,
            "implementation_source_path_set_sha256": (
                "cce4eef44f6cda40c7ea68aedb83f6368d5e3fbd20ef78aa5c510e907adc490b"
            ),
            "protocol_manifest_sha256": (
                "54c0bbe092ebf37fc705ef1cf4415a29ee4ba3e8c107730ed70d41601b08b440"
            ),
            "publication_id": "a8d5d66648c44c5aa31ea77b641c3594",
            "scope": "formal",
        }
    ],
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cmake",
    ".cpp",
    ".csv",
    ".h",
    ".hpp",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}


def _semantic_bytes(payload: bytes, path: str) -> bytes:
    if Path(path).suffix.lower() in _TEXT_SUFFIXES:
        return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return payload


def _semantic_sha256(payload: bytes, path: str) -> str:
    return hashlib.sha256(_semantic_bytes(payload, path)).hexdigest()


def _run_git(
    git_root: Path,
    args: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", str(git_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed ({completed.returncode}): {message}")
    return completed


def _git_blob_batch(
    git_root: Path,
    commit_sha: str,
    paths: Sequence[str],
) -> dict[str, bytes]:
    process = subprocess.Popen(
        ["git", "-C", str(git_root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    query = "".join(f"{commit_sha}:{path}\n" for path in paths).encode("utf-8")
    output, error = process.communicate(query)
    if process.returncode != 0:
        raise ValueError(
            "git cat-file --batch failed: "
            + error.decode("utf-8", errors="replace").strip()
        )
    stream = io.BytesIO(output)
    blobs: dict[str, bytes] = {}
    for path in paths:
        header = stream.readline().decode("ascii", errors="replace").strip()
        parts = header.split()
        if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
            raise ValueError(f"historical Git blob is missing or not a blob: {path}: {header}")
        size = int(parts[2])
        payload = stream.read(size)
        delimiter = stream.read(1)
        if len(payload) != size or delimiter != b"\n":
            raise ValueError(f"truncated Git batch payload for {path}")
        blobs[path] = payload
    if stream.read(1):
        raise ValueError("unexpected trailing data in Git batch response")
    return blobs


def _implementation_paths(tree_paths: Sequence[str]) -> list[str]:
    selected: set[str] = set()
    for path in tree_paths:
        lower = path.lower()
        name = path.rsplit("/", 1)[-1]
        if path == "CMakeLists.txt":
            selected.add(path)
        elif path.startswith("cpp/ics_core/") and lower.endswith(
            (".c", ".cc", ".cpp", ".h", ".hpp")
        ):
            selected.add(path)
        elif path.startswith("src/czr005/") and lower.endswith(".py"):
            selected.add(path)
        elif (
            path.startswith("scripts/eval/")
            and "/" not in path[len("scripts/eval/") :]
            and lower.endswith(".py")
            and (name.startswith("g4irsf11") or name.startswith("run_g4irsf11"))
        ):
            selected.add(path)
        elif path in {
            "scripts/eval/validate_g4irsf11_committed_artifacts.py",
            "scripts/eval/g4i_runtime.py",
        }:
            selected.add(path)
    return sorted(selected)


def _path_set_sha256(paths: Sequence[str]) -> str:
    return hashlib.sha256(
        "".join(f"{path}\n" for path in sorted(paths)).encode("utf-8")
    ).hexdigest()


def _source_bundle_sha256(paths: Sequence[str], blobs: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_semantic_sha256(blobs[path], path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_trusted_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = read_json_object(path)
    if registry != TRUSTED_REGISTRY_DOCUMENT:
        raise ValueError(
            "historical baseline registry differs from the reviewed trust anchor"
        )
    return registry


def trusted_baseline(
    baseline_id: str = DEFAULT_BASELINE_ID,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    registry = load_trusted_registry(registry_path)
    matches = [
        row
        for row in registry["baselines"]
        if isinstance(row, Mapping) and row.get("baseline_id") == baseline_id
    ]
    if len(matches) != 1:
        raise ValueError(f"unknown or duplicate historical baseline: {baseline_id}")
    return dict(matches[0])


@lru_cache(maxsize=8)
def _baseline_git_snapshot(
    git_root_text: str,
    commit_sha: str,
) -> dict[str, Any]:
    git_root = Path(git_root_text)
    if not _COMMIT_RE.fullmatch(commit_sha):
        raise ValueError("historical baseline commit SHA is invalid")
    resolved_commit = _run_git(
        git_root, ["rev-parse", "--verify", f"{commit_sha}^{{commit}}"]
    ).stdout.decode("ascii").strip()
    if resolved_commit != commit_sha:
        raise ValueError(
            f"historical baseline resolved to {resolved_commit}, expected {commit_sha}"
        )
    tree_sha = _run_git(git_root, ["rev-parse", f"{commit_sha}^{{tree}}"])
    tree_sha_text = tree_sha.stdout.decode("ascii").strip()
    ancestor = _run_git(
        git_root,
        ["merge-base", "--is-ancestor", commit_sha, "HEAD"],
        check=False,
    )
    if ancestor.returncode != 0:
        raise ValueError(
            "historical baseline commit is not an ancestor of the current checkout"
        )
    tree_paths = _run_git(
        git_root, ["ls-tree", "-r", "--name-only", commit_sha]
    ).stdout.decode("utf-8").splitlines()
    implementation_paths = _implementation_paths(tree_paths)
    completion_path = TRUSTED_REGISTRY_DOCUMENT["baselines"][0][
        "completion_manifest_path"
    ]
    requested_paths = [*implementation_paths, str(completion_path)]
    blobs = _git_blob_batch(git_root, commit_sha, requested_paths)
    return {
        "commit_sha": resolved_commit,
        "commit_tree_sha": tree_sha_text,
        "implementation_paths": implementation_paths,
        "implementation_source_file_count": len(implementation_paths),
        "implementation_source_path_set_sha256": _path_set_sha256(
            implementation_paths
        ),
        "implementation_source_bundle_sha256": _source_bundle_sha256(
            implementation_paths, blobs
        ),
        "completion_path": completion_path,
        "completion_bytes": blobs[str(completion_path)],
        "completion_semantic_sha256": _semantic_sha256(
            blobs[str(completion_path)], str(completion_path)
        ),
    }


def historical_formal_completion_validation_errors(
    artifact_root: Path = ROOT,
    *,
    git_root: Path = ROOT,
    baseline_id: str = DEFAULT_BASELINE_ID,
    registry_path: Path = REGISTRY_PATH,
) -> list[str]:
    """Validate the working historical completion against its producing tree."""

    errors: list[str] = []
    try:
        baseline = trusted_baseline(baseline_id, registry_path=registry_path)
    except (OSError, TypeError, ValueError) as exc:
        return [f"historical baseline trust failure: {type(exc).__name__}: {exc}"]

    for field in (
        "implementation_runtime_sha256",
        "implementation_source_bundle_sha256",
        "implementation_source_path_set_sha256",
        "protocol_manifest_sha256",
        "completion_manifest_semantic_sha256",
    ):
        if not _SHA256_RE.fullmatch(str(baseline.get(field) or "")):
            errors.append(f"trusted baseline {field} is not a SHA-256 digest")
    try:
        snapshot = _baseline_git_snapshot(
            str(git_root.resolve()), str(baseline["commit_sha"])
        )
    except (OSError, TypeError, ValueError) as exc:
        return [*errors, f"historical Git reconstruction failed: {type(exc).__name__}: {exc}"]

    comparisons = {
        "commit tree": (snapshot["commit_tree_sha"], baseline["commit_tree_sha"]),
        "source file count": (
            snapshot["implementation_source_file_count"],
            baseline["implementation_source_file_count"],
        ),
        "source path-set SHA-256": (
            snapshot["implementation_source_path_set_sha256"],
            baseline["implementation_source_path_set_sha256"],
        ),
        "source bundle SHA-256": (
            snapshot["implementation_source_bundle_sha256"],
            baseline["implementation_source_bundle_sha256"],
        ),
        "completion semantic SHA-256": (
            snapshot["completion_semantic_sha256"],
            baseline["completion_manifest_semantic_sha256"],
        ),
    }
    for label, (observed, expected) in comparisons.items():
        if observed != expected:
            errors.append(
                f"historical baseline {label} mismatch: observed={observed} expected={expected}"
            )

    try:
        baseline_completion = parse_json_object(
            snapshot["completion_bytes"].decode("utf-8"),
            label="historical completion Git blob",
        )
    except (UnicodeError, TypeError, ValueError) as exc:
        return [*errors, f"historical completion cannot be decoded: {type(exc).__name__}: {exc}"]
    completion_path = artifact_root / str(baseline["completion_manifest_path"])
    try:
        working_completion = read_json_object(completion_path)
    except (OSError, TypeError, ValueError) as exc:
        errors.append(
            f"working historical completion cannot be decoded: {type(exc).__name__}: {exc}"
        )
        working_completion = {}

    if working_completion and working_completion != baseline_completion:
        errors.append("working historical completion differs from the producing Git baseline")
    if baseline_completion.get("implementation_source_bundle_sha256") != baseline.get(
        "implementation_source_bundle_sha256"
    ):
        errors.append("historical completion source bundle differs from trusted baseline")
    if baseline_completion.get("implementation_sha256") != baseline.get(
        "implementation_runtime_sha256"
    ):
        errors.append("historical completion runtime implementation differs from trusted baseline")
    if baseline_completion.get("protocol_manifest_sha256") != baseline.get(
        "protocol_manifest_sha256"
    ):
        errors.append("historical completion protocol differs from trusted baseline")
    if baseline_completion.get("publication_id") != baseline.get("publication_id"):
        errors.append("historical completion publication ID differs from trusted baseline")
    if baseline_completion.get("expected_case_count") != baseline.get(
        "expected_case_count"
    ):
        errors.append("historical completion case count differs from trusted baseline")

    artifact_paths = baseline_completion.get("artifacts")
    if not isinstance(artifact_paths, Mapping):
        errors.append("historical completion artifacts section is not an object")
        artifact_paths = {}
    try:
        errors.extend(
            completion_validation_errors(
                artifact_root,
                completion_path,
                expected_scope=str(baseline["scope"]),
                expected_source_bundle_sha256=str(
                    baseline["implementation_source_bundle_sha256"]
                ),
                expected_protocol_manifest_sha256=str(
                    baseline["protocol_manifest_sha256"]
                ),
                expected_artifact_paths=list(artifact_paths),
                expected_metadata={
                    "implementation_sha256": baseline[
                        "implementation_runtime_sha256"
                    ],
                    "expected_case_count": baseline["expected_case_count"],
                },
            )
        )
    except (OSError, TypeError, ValueError) as exc:
        errors.append(
            f"historical artifact validation failed: {type(exc).__name__}: {exc}"
        )
    return errors
