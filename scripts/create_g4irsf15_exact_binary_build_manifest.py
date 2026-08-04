"""Build and attest the exact native binary used by G4IRSF15.

The manifest is intentionally emitted by the process that performs a clean
Release build.  It binds the resulting extension module to its local source
inputs, CMake cache, toolchain, Git HEAD, and the exact dirty source state.
Downstream campaign tools must recompute these bindings instead of treating a
module path or a source checkout hash as proof of how a binary was built.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "czr005.g4irsf15.exact_binary_build_manifest.v2"
DIRTY_STATE_ALGORITHM = "GIT_BINARY_DIFF_FULL_INDEX_SCOPED_V2"
INVENTORY_METHOD = "CMAKE_DEPENDENCY_SCAN_PLUS_EXPLICIT_HEADERS"
REPOSITORY_BINDING_METHOD = "GIT_REVISION_BLOB_SHA256_V1"
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_row(path: Path, *, display_path: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": display_path,
        "sha256": _sha256_file(path),
        "byte_count": stat.st_size,
    }


def _run_bytes(
    argv: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        [str(item) for item in argv],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if check and result.returncode != 0:
        rendered = subprocess.list2cmdline([str(item) for item in argv])
        stderr = result.stderr.decode("utf-8", errors="replace")
        stdout = result.stdout.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {rendered}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return result


def _repository_blob_binding(
    *,
    repo_root: Path,
    revision: str,
    display_path: str,
) -> dict[str, Any]:
    object_id = _run_bytes(
        ["git", "rev-parse", "--verify", f"{revision}:{display_path}"],
        cwd=repo_root,
    ).stdout.decode("ascii").strip()
    blob = _run_bytes(
        ["git", "cat-file", "blob", object_id],
        cwd=repo_root,
    ).stdout
    return {
        "method": REPOSITORY_BINDING_METHOD,
        "object_id": object_id,
        "sha256": _sha256_bytes(blob),
        "byte_count": len(blob),
    }


def _repository_file_row(
    path: Path,
    *,
    display_path: str,
    repo_root: Path,
    revision: str = "HEAD",
) -> dict[str, Any]:
    return {
        **_file_row(path, display_path=display_path),
        "repository_blob": _repository_blob_binding(
            repo_root=repo_root,
            revision=revision,
            display_path=display_path,
        ),
    }


def _repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _repo_relative_or_external_absolute(
    path: Path, repo_root: Path
) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _explicit_local_inputs(repo_root: Path) -> list[Path]:
    inputs: set[Path] = set()
    core = repo_root / "cpp" / "ics_core"
    if not core.is_dir():
        raise FileNotFoundError(f"missing native source root: {core}")
    for path in core.rglob("*"):
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
            inputs.add(path.resolve())
    for relative in ("CMakeLists.txt",):
        path = (repo_root / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"missing build input: {path}")
        inputs.add(path)
    return sorted(inputs, key=lambda item: _repo_relative(item, repo_root))


def _input_snapshot(paths: Iterable[Path], repo_root: Path) -> dict[str, str]:
    return {
        _repo_relative(path, repo_root): _sha256_file(path)
        for path in sorted(paths, key=lambda item: _repo_relative(item, repo_root))
    }


def _decode_tlog(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if b"\x00" in raw[:256]:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8", errors="replace")


def _cmake_dependency_paths(build_dir: Path, repo_root: Path) -> list[Path]:
    """Return repository-local dependencies recorded by the active generator."""

    found: set[Path] = set()
    for tlog in build_dir.rglob("CL.read.*.tlog"):
        if "czr005_cpp.tlog" not in tlog.as_posix().lower():
            continue
        for raw_line in _decode_tlog(tlog).splitlines():
            line = raw_line.lstrip("^").strip()
            if not line:
                continue
            candidate = Path(line)
            if candidate.is_file() and _is_within(candidate, repo_root):
                found.add(candidate.resolve())

    # CMake depfiles use "target: dependency ..." syntax.  They are uncommon
    # for the Visual Studio generator but make the attestor portable.
    for depfile in build_dir.rglob("*.d"):
        if "czr005_cpp" not in depfile.as_posix().lower():
            continue
        text = depfile.read_text(encoding="utf-8", errors="replace")
        text = text.replace("\\\n", " ")
        _, separator, dependencies = text.partition(":")
        if not separator:
            continue
        for token in re.split(r"\s+", dependencies.strip()):
            if not token:
                continue
            candidate = Path(token.replace("\\ ", " "))
            if not candidate.is_absolute():
                candidate = (depfile.parent / candidate).resolve()
            if candidate.is_file() and _is_within(candidate, repo_root):
                found.add(candidate.resolve())
    return sorted(found, key=lambda item: _repo_relative(item, repo_root))


def collect_transitive_source_inventory(
    *,
    repo_root: Path,
    build_dir: Path,
    revision: str = "HEAD",
) -> dict[str, Any]:
    dependency_inputs = set(_cmake_dependency_paths(build_dir, repo_root))
    explicit_inputs = set(_explicit_local_inputs(repo_root))
    paths = sorted(
        dependency_inputs | explicit_inputs,
        key=lambda item: _repo_relative(item, repo_root),
    )
    rows = [
        _repository_file_row(
            path,
            display_path=_repo_relative(path, repo_root),
            repo_root=repo_root,
            revision=revision,
        )
        for path in paths
    ]
    return {
        "method": INVENTORY_METHOD,
        "repository_binding_method": REPOSITORY_BINDING_METHOD,
        "dependency_scan_local_file_count": len(dependency_inputs),
        "explicit_local_file_count": len(explicit_inputs),
        "files": rows,
        "bundle_sha256": _sha256_bytes(_canonical_bytes(rows)),
    }


def _git_stdout(repo_root: Path, argv: Sequence[str]) -> bytes:
    return _run_bytes(["git", *argv], cwd=repo_root).stdout


def collect_dirty_source_state(
    *,
    repo_root: Path,
    source_paths: Sequence[str],
) -> dict[str, Any]:
    ordered_paths = sorted(set(source_paths))
    head = _git_stdout(repo_root, ["rev-parse", "HEAD"]).decode().strip()
    tracked = _git_stdout(
        repo_root,
        [
            "diff",
            "--binary",
            "--no-ext-diff",
            "--full-index",
            "HEAD",
            "--",
            *ordered_paths,
        ],
    )
    staged = _git_stdout(
        repo_root,
        [
            "diff",
            "--cached",
            "--binary",
            "--no-ext-diff",
            "--full-index",
            "HEAD",
            "--",
            *ordered_paths,
        ],
    )
    untracked_raw = _git_stdout(
        repo_root,
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *ordered_paths,
        ],
    )
    untracked_paths = sorted(
        value.decode("utf-8", errors="surrogateescape")
        for value in untracked_raw.split(b"\0")
        if value
    )
    untracked_rows = [
        _file_row(
            repo_root / relative,
            display_path=Path(relative).as_posix(),
        )
        for relative in untracked_paths
    ]
    state: dict[str, Any] = {
        "algorithm": DIRTY_STATE_ALGORITHM,
        "head": head,
        "source_path_count": len(ordered_paths),
        "source_paths_sha256": _sha256_bytes(
            _canonical_bytes(ordered_paths)
        ),
        "tracked_worktree_diff_sha256": _sha256_bytes(tracked),
        "staged_diff_sha256": _sha256_bytes(staged),
        "untracked_source_files": untracked_rows,
    }
    state["state_sha256"] = _sha256_bytes(_canonical_bytes(state))
    return state


def _require_clean_publication_source_state(
    state: Mapping[str, Any],
) -> None:
    empty_sha256 = _sha256_bytes(b"")
    if (
        state.get("tracked_worktree_diff_sha256") != empty_sha256
        or state.get("staged_diff_sha256") != empty_sha256
        or state.get("untracked_source_files") != []
    ):
        raise RuntimeError(
            "publication exact build requires clean tracked, staged, and "
            "untracked source paths"
        )


def _parse_cmake_cache(cache_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key_and_type, value = line.split("=", 1)
        key = key_and_type.split(":", 1)[0]
        values[key] = value
    return values


def _parse_cmake_compiler_file(build_dir: Path) -> dict[str, str]:
    candidates = sorted(
        build_dir.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("CMakeCXXCompiler.cmake was not generated")
    text = candidates[0].read_text(encoding="utf-8", errors="replace")
    values: dict[str, str] = {}
    for key in (
        "CMAKE_CXX_COMPILER",
        "CMAKE_CXX_COMPILER_ID",
        "CMAKE_CXX_COMPILER_VERSION",
        "CMAKE_CXX_COMPILER_ARCHITECTURE_ID",
    ):
        match = re.search(
            rf'^set\({re.escape(key)}\s+"?([^"\r\n)]*)"?\)',
            text,
            flags=re.MULTILINE,
        )
        values[key] = match.group(1) if match else ""
    return values


def _version_line(argv: Sequence[str], cwd: Path) -> str:
    result = _run_bytes(argv, cwd=cwd)
    text = (result.stdout + b"\n" + result.stderr).decode(
        "utf-8",
        errors="replace",
    )
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _command_evidence(
    argv: Sequence[str],
    result: subprocess.CompletedProcess[bytes],
) -> dict[str, Any]:
    return {
        "argv": [str(item) for item in argv],
        "return_code": result.returncode,
        "stdout_sha256": _sha256_bytes(result.stdout),
        "stderr_sha256": _sha256_bytes(result.stderr),
    }


def _find_binary(build_dir: Path, configuration: str) -> Path:
    roots = [build_dir / "python" / configuration, build_dir / "python"]
    suffixes = ("*.pyd", "*.so", "*.dylib")
    candidates: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for suffix in suffixes:
            candidates.update(
                path.resolve()
                for path in root.glob(f"czr005_cpp*{suffix[1:]}")
                if path.is_file()
            )
    if len(candidates) != 1:
        rendered = ", ".join(str(path) for path in sorted(candidates))
        raise RuntimeError(
            "expected exactly one built czr005_cpp extension module; "
            f"found {len(candidates)}: {rendered}"
        )
    return next(iter(candidates))


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        # Windows does not generally allow opening directories this way.
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _target_python_metadata(
    python_executable: Path,
    *,
    cwd: Path,
) -> dict[str, str]:
    program = (
        "import importlib.metadata,json,sys;"
        "import pybind11;"
        "print(json.dumps({"
        "'executable':sys.executable,"
        "'version':sys.version,"
        "'implementation':sys.implementation.name,"
        "'pybind11_version':importlib.metadata.version('pybind11'),"
        "'pybind11_cmake_dir':pybind11.get_cmake_dir()"
        "},sort_keys=True))"
    )
    result = _run_bytes(
        [str(python_executable.resolve()), "-c", program],
        cwd=cwd,
    )
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "target Python did not emit valid environment metadata"
        ) from exc
    required = {
        "executable",
        "version",
        "implementation",
        "pybind11_version",
        "pybind11_cmake_dir",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RuntimeError("target Python environment metadata is incomplete")
    return {key: str(item) for key, item in value.items()}


def build_exact_binary_manifest(
    *,
    repo_root: Path,
    build_dir: Path,
    output_path: Path,
    cmake_executable: str,
    configuration: str,
    generator: str | None,
    python_executable: Path,
    pybind11_dir: Path,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    build_dir = build_dir.resolve()
    output_path = output_path.resolve()
    python_executable = python_executable.resolve()
    pybind11_dir = pybind11_dir.resolve()
    resolved_cmake_text = shutil.which(cmake_executable) or cmake_executable
    cmake_path = Path(resolved_cmake_text).resolve(strict=True)
    python_metadata = _target_python_metadata(
        python_executable,
        cwd=repo_root,
    )
    reported_python = Path(python_metadata["executable"]).resolve()
    try:
        same_python = os.path.samefile(python_executable, reported_python)
    except OSError:
        same_python = os.path.normcase(str(python_executable)) == os.path.normcase(
            str(reported_python)
        )
    if not same_python:
        raise RuntimeError(
            "requested Python executable is a wrapper or launcher for a "
            f"different interpreter: requested={python_executable}, "
            f"reported={reported_python}"
        )
    reported_pybind11_dir = Path(
        python_metadata["pybind11_cmake_dir"]
    ).resolve()
    if reported_pybind11_dir != pybind11_dir:
        raise RuntimeError(
            "requested pybind11 CMake directory does not belong to the target "
            f"Python environment: requested={pybind11_dir}, "
            f"reported={reported_pybind11_dir}"
        )
    explicit_inputs = _explicit_local_inputs(repo_root)
    producer = Path(__file__).resolve()
    build_head = _git_stdout(repo_root, ["rev-parse", "HEAD"]).decode().strip()
    branch = _git_stdout(
        repo_root, ["branch", "--show-current"]
    ).decode().strip()
    before_paths = sorted(
        {*explicit_inputs, producer},
        key=lambda item: _repo_relative(item, repo_root),
    )
    before = _input_snapshot(before_paths, repo_root)

    configure_argv = [
        str(cmake_path),
        "-S",
        str(repo_root),
        "-B",
        str(build_dir),
    ]
    if generator:
        configure_argv.extend(["-G", generator])
    configure_argv.extend(
        [
            f"-DCMAKE_BUILD_TYPE={configuration}",
            f"-DPython3_EXECUTABLE={python_executable}",
            f"-Dpybind11_DIR={pybind11_dir}",
        ]
    )
    configure_result = _run_bytes(configure_argv, cwd=repo_root)
    build_argv = [
        str(cmake_path),
        "--build",
        str(build_dir),
        "--config",
        configuration,
        "--target",
        "czr005_cpp",
        "--clean-first",
    ]
    build_result = _run_bytes(build_argv, cwd=repo_root)

    after_paths = sorted(
        {*_explicit_local_inputs(repo_root), producer},
        key=lambda item: _repo_relative(item, repo_root),
    )
    after = _input_snapshot(after_paths, repo_root)
    after_head = _git_stdout(repo_root, ["rev-parse", "HEAD"]).decode().strip()
    after_branch = _git_stdout(
        repo_root, ["branch", "--show-current"]
    ).decode().strip()
    if (
        before != after
        or build_head != after_head
        or branch != after_branch
    ):
        raise RuntimeError(
            "source or Git identity changed while the exact binary was built"
        )

    binary_path = _find_binary(build_dir, configuration)
    inventory = collect_transitive_source_inventory(
        repo_root=repo_root,
        build_dir=build_dir,
        revision=build_head,
    )
    source_paths = [
        *[str(row["path"]) for row in inventory["files"]],
        _repo_relative(producer, repo_root),
    ]
    dirty_state = collect_dirty_source_state(
        repo_root=repo_root,
        source_paths=source_paths,
    )
    if dirty_state["head"] != build_head:
        raise RuntimeError("Git HEAD changed before dirty source capture")
    _require_clean_publication_source_state(dirty_state)

    cache_path = build_dir / "CMakeCache.txt"
    if not cache_path.is_file():
        raise FileNotFoundError(f"missing CMake cache: {cache_path}")
    cache = _parse_cmake_cache(cache_path)
    compiler = _parse_cmake_compiler_file(build_dir)
    compiler_path = Path(compiler["CMAKE_CXX_COMPILER"])
    if not compiler_path.is_file():
        raise FileNotFoundError(
            f"recorded C++ compiler does not exist: {compiler_path}"
        )
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "COMPLETE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "binary": _file_row(
            binary_path,
            display_path=_repo_relative_or_external_absolute(
                binary_path, repo_root
            ),
        ),
        "git": {
            "head": build_head,
            "branch": branch,
        },
        "dirty_source_state": dirty_state,
        "transitive_source_inventory": inventory,
        "toolchain": {
            "configuration": configuration,
            "generator": cache.get("CMAKE_GENERATOR", ""),
            "generator_platform": cache.get("CMAKE_GENERATOR_PLATFORM", ""),
            "generator_toolset": cache.get("CMAKE_GENERATOR_TOOLSET", ""),
            "cmake": {
                **_file_row(cmake_path, display_path=str(cmake_path)),
                "version": _version_line(
                    [str(cmake_path), "--version"],
                    repo_root,
                ),
            },
            "compiler": {
                "id": compiler["CMAKE_CXX_COMPILER_ID"],
                "version": compiler["CMAKE_CXX_COMPILER_VERSION"],
                "architecture": compiler[
                    "CMAKE_CXX_COMPILER_ARCHITECTURE_ID"
                ],
                **_file_row(compiler_path, display_path=str(compiler_path)),
            },
            "python": {
                "path": str(python_executable),
                "reported_executable": python_metadata["executable"],
                "version": python_metadata["version"],
                "implementation": python_metadata["implementation"],
                "sha256": _sha256_file(python_executable),
            },
            "pybind11": {
                "version": python_metadata["pybind11_version"],
                "cmake_dir": str(pybind11_dir),
            },
            "configure_argv": configure_argv,
            "build_argv": build_argv,
            "cmake_cache": _file_row(
                cache_path,
                display_path=os.path.relpath(cache_path, repo_root).replace(
                    "\\",
                    "/",
                ),
            ),
        },
        "build_execution": {
            "clean_first": True,
            "configure": _command_evidence(
                configure_argv,
                configure_result,
            ),
            "build": _command_evidence(build_argv, build_result),
            "source_inventory_unchanged_during_build": True,
            "source_and_git_identity_unchanged_during_build": True,
        },
        "producer": _repository_file_row(
            producer,
            display_path=_repo_relative(producer, repo_root),
            repo_root=repo_root,
            revision=build_head,
        ),
        "claim_boundary": (
            "This manifest proves which local source state and toolchain were "
            "used by this clean native build. It does not by itself prove any "
            "causal label, policy benefit, or distributed deployment claim."
        ),
    }
    manifest["self_sha256"] = _sha256_bytes(_canonical_bytes(manifest))
    _atomic_write_json(output_path, manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=Path("build_g4irsf15"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "outputs/manifests/g4irsf15_exact_binary_build_manifest.json"
        ),
    )
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--configuration", default="Release")
    parser.add_argument("--generator")
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=Path(sys.executable),
    )
    parser.add_argument("--pybind11-dir", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    build_dir = (
        args.build_dir
        if args.build_dir.is_absolute()
        else repo_root / args.build_dir
    )
    output = args.output if args.output.is_absolute() else repo_root / args.output
    python_metadata = _target_python_metadata(
        args.python_executable.resolve(),
        cwd=repo_root,
    )
    pybind11_dir = args.pybind11_dir or Path(
        python_metadata["pybind11_cmake_dir"]
    )
    manifest = build_exact_binary_manifest(
        repo_root=repo_root,
        build_dir=build_dir,
        output_path=output,
        cmake_executable=args.cmake,
        configuration=args.configuration,
        generator=args.generator,
        python_executable=args.python_executable,
        pybind11_dir=pybind11_dir,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "binary_sha256": manifest["binary"]["sha256"],
                "source_bundle_sha256": manifest[
                    "transitive_source_inventory"
                ]["bundle_sha256"],
                "dirty_source_state_sha256": manifest[
                    "dirty_source_state"
                ]["state_sha256"],
                "manifest_self_sha256": manifest["self_sha256"],
                "output": str(output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
