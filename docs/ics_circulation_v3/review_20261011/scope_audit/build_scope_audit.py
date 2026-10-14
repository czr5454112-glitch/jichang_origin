"""Read-only repository audit and deterministic, lossless fixture packaging.

Writes only the review bundle; never stages, commits, pushes or edits source.
The SHA fields distinguish working bytes, LF normalization and predicted Git
blob content. A later publish manifest must confirm the actual committed blob.
"""
from __future__ import annotations

import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[4]
REVIEW = ROOT / "docs/ics_circulation_v3/review_20261011"
DEST = REVIEW / "scope_audit"
CPP = "cpp/ics_core/runtime/bounded_local_pibt.hpp"
FREEZE = "outputs/experiments/ics_circulation_v3/phase4_round11_independent_review_20261011/closure_001/results.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, data=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, input=data,
                                   stderr=subprocess.DEVNULL)


def blob_oid(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    cpu, wall = process_time(), perf_counter()
    freeze = json.loads((ROOT / FREEZE).read_text())
    frozen = freeze["source_sha256"]
    files, missing_imports, third_party, special_strings = [], [], set(), []
    local_imports = []
    for relative, expected in sorted(frozen.items()):
        path = ROOT / relative
        content = path.read_bytes()
        lf = content.replace(b"\r\n", b"\n")
        predicted = git("hash-object", "--path", relative, "--stdin", data=content).decode().strip()
        if predicted == blob_oid(content):
            rule, blob_sha256 = "raw", sha(content)
        elif predicted == blob_oid(lf):
            rule, blob_sha256 = "crlf_to_lf_only", sha(lf)
        else:
            rule, blob_sha256 = "other_filter_unknown", None
        row = dict(path=relative, bytes=len(content), frozen_raw_sha256=expected,
                   working_raw_sha256=sha(content), lf_normalized_sha256=sha(lf),
                   frozen_equal=sha(content) == expected,
                   predicted_git_blob_oid=predicted, predicted_git_blob_sha256=blob_sha256,
                   predicted_git_content_rule=rule,
                   publish=relative != CPP)
        files.append(row)
        if path.suffix != ".py":
            continue
        tree = ast.parse(content.decode("utf-8-sig"), filename=relative)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.module:
                        candidate = path.parent.joinpath(*node.module.split(".")).with_suffix(".py")
                        local_imports.append([relative, candidate.relative_to(ROOT).as_posix()])
                        if not candidate.is_file():
                            missing_imports.append(local_imports[-1])
                    continue
                names = [node.module] if node.module else []
            for name in names:
                top = name.split(".")[0]
                if top == "scripts":
                    candidate = ROOT.joinpath(*name.split("."))
                    if not candidate.is_dir() and not candidate.with_suffix(".py").is_file():
                        missing_imports.append([relative, name])
                    local_imports.append([relative, name.replace(".", "/")])
                elif top.startswith("test_ics"):
                    candidate = ROOT / "tests" / (top + ".py")
                    if not candidate.is_file():
                        missing_imports.append([relative, top])
                elif top not in sys.stdlib_module_names and top != "__future__":
                    third_party.add(top)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(x in node.value for x in ("outputs/", "C:\\", "C:/", ".worktree", "Downloads", "AppData")):
                    special_strings.append(dict(path=relative, line=node.lineno, value=node.value))
    assert len(files) == 212 and sum(x["publish"] for x in files) == 211
    assert all(x["frozen_equal"] for x in files), "Live source differs from final freeze"
    assert not missing_imports, missing_imports

    fixture_dir = REVIEW / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_rows = []
    output = Path("outputs/experiments/ics_circulation_v3/phase4_w3_cursor_original_map_20261009")
    for scene in ("cross_cycle", "counterflow", "near_full"):
        for kind in ("original", "cursor"):
            relative = output / f"{scene}_{kind}.json"
            source = ROOT / relative
            target = fixture_dir / (source.name + ".gz")
            with source.open("rb") as stream, target.open("wb") as packed:
                with gzip.GzipFile(filename="", fileobj=packed, mode="wb", compresslevel=9, mtime=0) as compressed:
                    shutil.copyfileobj(stream, compressed)
            original, archived = source.read_bytes(), target.read_bytes()
            assert gzip.decompress(archived) == original
            fixture_rows.append(dict(original_path=relative.as_posix(), original_sha256=sha(original),
                                     original_bytes=len(original), gzip_path=target.relative_to(ROOT).as_posix(),
                                     gzip_sha256=sha(archived), gzip_bytes=len(archived)))
    fixture_manifest = dict(schema="ics-v3-complete-cursor-fixtures-v1",
                            encoding="Full original JSON bytes; gzip mtime=0, empty filename, level=9",
                            no_sampling=True, fixtures=fixture_rows)
    (fixture_dir / "manifest.json").write_text(json.dumps(fixture_manifest, indent=2) + "\n", encoding="utf-8")

    release = sorted(x["path"] for x in files if x["publish"])
    additions = sorted(p.relative_to(ROOT).as_posix()
                       for p in (ROOT / "scripts/experiments/ics_circulation_v3").rglob("*")
                       if p.is_file() and p.suffix in (".md", ".json"))
    # Current bundle files are owned by multiple authors. Root adds these whole
    # declared directories after all authors finish; this list enumerates only
    # the deterministic source/test/dependency payload audited here.
    required = sorted(set(release + additions + ["pyproject.toml", ".gitattributes",
        "docs/ics_circulation_v3/ICS_plan_revision_and_learning_20261006.md",
        "docs/ics_circulation_v3/review_input_provenance.json",
        "docs/ics_circulation_v3/review_20261011/tools/prepare_fixtures.py",
        "docs/ics_circulation_v3/review_20261011/fixtures/manifest.json"] +
        [x["gzip_path"] for x in fixture_rows]))
    (DEST / "source_release_paths.txt").write_text("\n".join(release) + "\n", encoding="utf-8")
    (DEST / "recommended_repository_paths.txt").write_text("\n".join(required) + "\n", encoding="utf-8")
    (DEST / "pytest_paths.txt").write_text("\n".join(x for x in release if x.startswith("tests/")) + "\n", encoding="utf-8")
    cpp_head = git("show", "HEAD:" + CPP)
    result = dict(status="passed", head=git("rev-parse", "HEAD").decode().strip(),
        branch=git("branch", "--show-current").decode().strip(), freeze_manifest=FREEZE,
        freeze_manifest_sha256=sha((ROOT / FREEZE).read_bytes()),
        source_count=212, publish_source_count=211,
        counts=dict(Counter("test" if x["path"].startswith("tests/") else
                            "protected_cpp" if x["path"] == CPP else "production_python" for x in files)),
        source_drift=[], missing_static_imports=missing_imports,
        third_party_imports=sorted(third_party), core_autocrlf=git("config", "--get", "core.autocrlf").decode().strip(),
        cpp_excluded=dict(path=CPP, working_raw_sha256=sha((ROOT / CPP).read_bytes()),
                          head_blob_sha256=sha(cpp_head), head_blob_oid=git("rev-parse", "HEAD:" + CPP).decode().strip(),
                          reason="Pre-existing G4IRSF14 blocker/grant changes; protected workspace object, not ICS release code"),
        static_special_path_strings=special_strings, source_manifest=files,
        fixture_count=6, original_fixture_bytes=sum(x["original_bytes"] for x in fixture_rows),
        packed_fixture_bytes=sum(x["gzip_bytes"] for x in fixture_rows),
        physical_runs=0, tests_run=0,
        cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        resource_scope="This process: hashing, AST and gzip verification. Git subprocess CPU is not measured. No regression rerun.")
    (DEST / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "source_count", "publish_source_count", "counts", "third_party_imports", "fixture_count", "original_fixture_bytes", "packed_fixture_bytes", "cpu_seconds", "wall_seconds")}, indent=2))


if __name__ == "__main__":
    main()
