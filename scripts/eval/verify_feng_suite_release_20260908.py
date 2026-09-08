"""Verify a Feng suite release without executing archived code or changing sources.

Archive extraction is optional and starts only after every archive and member has
passed verification. An extraction failure leaves only the newly created target;
it never overwrites a file or removes files from an existing workspace.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys
import zipfile


SCHEMA = "czr005.feng_suite.release.v1"
CHUNK_BYTES = 1024 * 1024
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)), *(f"COM{i}" for i in "\u00b9\u00b2\u00b3"),
            *(f"LPT{i}" for i in "\u00b9\u00b2\u00b3")}


class VerificationError(ValueError):
    """The release or extraction destination violates the release contract."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def relative_name(value, *, leaf=False):
    require(isinstance(value, str) and bool(value), "Empty or non-string path")
    require("\\" not in value and ":" not in value, f"Unsafe path: {value!r}")
    require(not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).drive,
            f"Absolute or drive path: {value!r}")
    pieces = value.split("/")
    require(not leaf or len(pieces) == 1, f"Expected a filename: {value!r}")
    for piece in pieces:
        require(piece not in ("", ".", ".."), f"Unsafe path component: {value!r}")
        require(not piece.endswith((" ", ".")), f"Windows path alias: {value!r}")
        require(not any(ord(c) < 32 or c in '<>"|?*' for c in piece),
                f"Invalid path character: {value!r}")
        require(piece.split(".")[0].upper() not in RESERVED,
                f"Windows device name: {value!r}")
    return value


def positive_or_zero(value, label):
    require(type(value) is int and value >= 0, f"Invalid {label}: {value!r}")
    return value


def digest_value(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"Invalid SHA-256: {value!r}")
    return value


def digest_stream(stream):
    digest = hashlib.sha256()
    count = 0
    while data := stream.read(CHUNK_BYTES):
        digest.update(data)
        count += len(data)
    return count, digest.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def read_json(text):
    result = json.loads(text, object_pairs_hook=unique_object)
    require(isinstance(result, dict), "Expected a JSON object")
    return result


def regular_file(path):
    require(not path.is_symlink(), f"Symbolic link input: {path}")
    require(path.is_file(), f"Missing regular input file: {path}")
    return path


def target_path(destination, original):
    require(isinstance(original, str) and original, "Missing original_workspace_root")
    require(Path(original).is_absolute() or PureWindowsPath(original).is_absolute(),
            "original_workspace_root must be absolute")
    if destination is None:
        return None
    raw = Path(destination).absolute()
    require(not os.path.lexists(raw), f"Extraction target already exists: {raw}")
    resolved = raw.resolve()
    require(not os.path.lexists(resolved), f"Extraction target already exists: {resolved}")
    require(resolved.parent.is_dir(), "Extraction target parent must already exist")
    if os.name == "nt" or Path(original).is_absolute():
        original_path = Path(original).resolve()
        require(not resolved.is_relative_to(original_path),
                "Extraction target must be outside the original workspace")
    else:
        # A Windows release may be verified on POSIX without reinterpreting C:/
        # as a relative POSIX directory. Such a path cannot contain a POSIX target.
        require(PureWindowsPath(original).is_absolute(), "Invalid original workspace path")
    return resolved


def verify_release(manifest_path, archives_dir, extract_to=None):
    manifest_path = regular_file(Path(manifest_path))
    manifest = read_json(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == SCHEMA, "Unsupported release schema")
    destination = target_path(extract_to, manifest.get("original_workspace_root"))
    files_ref = manifest.get("files_manifest")
    require(isinstance(files_ref, dict), "Missing files_manifest")
    files_name = relative_name(files_ref.get("name"), leaf=True)
    files_sha = digest_value(files_ref.get("sha256"))
    expected_count = positive_or_zero(files_ref.get("count"), "file count")
    index_path = regular_file(manifest_path.parent / files_name)
    index_bytes = index_path.read_bytes()
    require(hashlib.sha256(index_bytes).hexdigest() == files_sha, "files_manifest SHA-256 mismatch")

    parts = manifest.get("parts")
    require(isinstance(parts, list) and bool(parts), "Missing release parts")
    part_index = {}
    part_aliases = set()
    for part in parts:
        require(isinstance(part, dict), "Invalid part record")
        name = relative_name(part.get("name"), leaf=True)
        require(name.casefold() not in part_aliases, f"Duplicate archive part: {name}")
        part_aliases.add(name.casefold())
        digest_value(part.get("sha256"))
        positive_or_zero(part.get("bytes"), "archive size")
        positive_or_zero(part.get("file_count"), "part file count")
        part_index[name] = part

    files = {}
    aliases = set()
    by_part = {name: {} for name in part_index}
    for line_number, line in enumerate(index_bytes.decode("utf-8").splitlines(), 1):
        require(bool(line.strip()), f"Blank files_manifest line: {line_number}")
        record = read_json(line)
        name = relative_name(record.get("path"))
        require(name.casefold() not in aliases, f"Duplicate file path: {name}")
        aliases.add(name.casefold())
        positive_or_zero(record.get("bytes"), "file size")
        digest_value(record.get("sha256"))
        part_name = record.get("part")
        require(isinstance(part_name, str) and part_name in part_index,
                f"Unknown archive part for {name}")
        files[name] = record
        by_part[part_name][name] = record
    require(len(files) == expected_count, "files_manifest count mismatch")
    for name in files:
        for parent in PurePosixPath(name).parents:
            require(str(parent).casefold() not in aliases,
                    f"File/directory path collision: {name}")
    for name, part in part_index.items():
        require(len(by_part[name]) == part["file_count"], f"Part file count mismatch: {name}")

    archives_dir = Path(archives_dir)
    with ExitStack() as stack:
        handles = {}
        # Check every outer archive before trusting or reading any ZIP member.
        for name, part in part_index.items():
            archive_path = regular_file(archives_dir / name)
            stream = stack.enter_context(archive_path.open("rb"))
            require(os.fstat(stream.fileno()).st_size == part["bytes"],
                    f"Archive size mismatch: {name}")
            count, digest = digest_stream(stream)
            require(count == part["bytes"] and digest == part["sha256"],
                    f"Archive SHA-256 mismatch: {name}")
            stream.seek(0)
            handles[name] = stream

        archives = {}
        for name, stream in handles.items():
            archive = stack.enter_context(zipfile.ZipFile(stream, "r"))
            archives[name] = archive
            seen = set()
            for member in archive.infolist():
                require(member.orig_filename == member.filename,
                        f"Truncated ZIP member name: {member.orig_filename!r}")
                member_name = relative_name(member.filename)
                require(not member.is_dir(), f"Unexpected directory entry: {member_name}")
                mode = member.external_attr >> 16
                kind = stat.S_IFMT(mode)
                require(kind in (0, stat.S_IFREG), f"Symbolic link or special member: {member_name}")
                require(not member.flag_bits & 1, f"Encrypted member: {member_name}")
                require(member_name not in seen, f"Duplicate ZIP member: {member_name}")
                seen.add(member_name)
                require(member_name in by_part[name], f"Unexpected ZIP member in {name}: {member_name}")
                record = by_part[name][member_name]
                require(member.file_size == record["bytes"], f"Member size mismatch: {member_name}")
                with archive.open(member) as source:
                    count, digest = digest_stream(source)
                require(count == record["bytes"] and digest == record["sha256"],
                        f"Member SHA-256 mismatch: {member_name}")
            require(seen == set(by_part[name]), f"Missing ZIP members: {name}")

        # Nothing has been extracted or written before this point.
        if destination is not None:
            destination.mkdir(exist_ok=False)
            for part_name, archive in archives.items():
                for name, record in by_part[part_name].items():
                    output = destination.joinpath(*name.split("/"))
                    require(output.resolve().is_relative_to(destination), f"Extraction escaped target: {name}")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    require(output.parent.resolve().is_relative_to(destination), f"Unsafe extraction parent: {name}")
                    digest = hashlib.sha256()
                    count = 0
                    with archive.open(name) as source, output.open("xb") as target:
                        while data := source.read(CHUNK_BYTES):
                            target.write(data)
                            digest.update(data)
                            count += len(data)
                    require(count == record["bytes"] and digest.hexdigest() == record["sha256"],
                            f"Archive changed during extraction: {name}")

    return {"status": "PASS", "schema": SCHEMA, "manifest": str(manifest_path.resolve()),
            "part_count": len(parts), "file_count": len(files),
            "archive_bytes": sum(p["bytes"] for p in parts),
            "file_bytes": sum(r["bytes"] for r in files.values()),
            "files_manifest_sha256": files_sha, "all_archive_hashes_verified": True,
            "all_member_hashes_verified": True, "extracted_to": str(destination) if destination else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--archives-dir", required=True, type=Path)
    parser.add_argument("--extract-to", type=Path,
                        help="New directory outside the original workspace; its parent must exist")
    args = parser.parse_args(argv)
    try:
        result = verify_release(args.manifest, args.archives_dir, args.extract_to)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile,
            NotImplementedError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
