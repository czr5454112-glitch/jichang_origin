"""Select the authorized code/evidence publication; no git mutation."""
from pathlib import Path
import os, hashlib, json, re, subprocess

ROOT=Path(__file__).resolve().parents[4]
PUB=ROOT/"docs/g31_ics_circulation/publication_20261014"
OUT=ROOT/"outputs/experiments/g31_ics_long_term_20261013/publication_20261014_001"
MANIFEST=PUB/"source_manifest.json"
# The human handoff receives the immutable code SHA in a separate release commit.
LATER={"docs/g31_ics_circulation/GPTPRO_REVIEW_AND_NEXT_STAGE_20261014.md",
       "docs/g31_ics_circulation/PUBLICATION_AND_REPRODUCIBILITY_20261014.md",
       MANIFEST.relative_to(ROOT).as_posix()}
SUFFIXES={".py",".hpp",".cpp",".md",".json",".jsonl",".gz",".xml",".log",".txt",".csv",".tsv",".zip",".patch",".cmd",".prof",".pstats",".xlsx"}
paths={ROOT/".gitattributes",ROOT/"CMakeLists.txt"}
for pattern in ["cpp/**/*.hpp","cpp/**/*.cpp","tests/test_g31_circulation_*.py",
    "tests/test_g31_fixed_blocking_certificate.py","tests/test_g31_original_mechanism.py",
    "tests/test_ics_circulation_v3_*.py","tests/test_ics_v3_*.py","map_nanning/*.xlsx"]:
    paths.update(p for p in ROOT.glob(pattern) if p.is_file())
excluded=[]
for folder in ["scripts/experiments","docs/g31_ics_circulation","docs/ics_circulation_v3","docs/external_review","outputs/experiments"]:
    for base,dirs,files in os.walk(ROOT/folder):
        dirs[:]=[d for d in dirs if d not in {"__pycache__",".pytest_cache","pytest_tmp","clean_checkout_001","publication_downloads"}]
        for name in files:
            p=Path(base)/name;rel=p.relative_to(ROOT).as_posix()
            if rel in LATER or (p.parent==OUT and name in {"staging_paths.nul","selection_summary.json"}):
                continue
            if p.suffix in SUFFIXES:paths.add(p)
            else:excluded.append(dict(path=rel,reason="not an approved source/evidence suffix",bytes=p.stat().st_size))
paths={p for p in paths if p.relative_to(ROOT).as_posix() not in LATER}
# One declared attributes file is already configured as LF in Git.
a=ROOT/".gitattributes"
a.write_text(a.read_text(encoding="utf-8").replace("\r\n","\n"),encoding="utf-8",newline="\n")
sha=lambda b:hashlib.sha256(b).hexdigest()
secret_patterns=[re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),re.compile(rb"github_pat_[A-Za-z0-9_]{60,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),re.compile(rb"https?://[^\s/:]+:[^\s/@]+@")]
files={};hits=[];eol_only=[];scanned=0
for p in sorted(paths):
    rel=p.relative_to(ROOT).as_posix();data=p.read_bytes()
    assert len(data)<100*1024*1024,("individual_file_exceeds_100MiB",rel)
    if p.suffix not in {".gz",".zip",".xlsx",".prof",".pstats"}:
        scanned+=1
        if any(pattern.search(data) for pattern in secret_patterns):hits.append(rel)
    files[rel]=dict(bytes=len(data),sha256=sha(data))
    if rel.startswith("cpp/") or rel=="CMakeLists.txt":
        old=subprocess.run(["git","cat-file","blob","HEAD:"+rel],cwd=ROOT,capture_output=True)
        if old.returncode==0 and old.stdout!=data and old.stdout.replace(b"\r\n",b"\n")==data.replace(b"\r\n",b"\n"):
            eol_only.append(rel)
assert not hits,("potential_credential_pattern_paths_only",hits)
manifest=dict(schema="g31.source_publication_manifest.v1",date="2026-10-14",
    base_commit="46cc46ab6bc121628fd6357e9f3c7636745fd732",
    code_commit_location="GPTPRO_REVIEW_AND_NEXT_STAGE_20261014.md added after immutable code commit",
    scope="Explicit current code/imported reference/tests/docs/raw local evidence additions; existing mature repository files remain inherited. Manifest excludes itself and later release handoff to avoid self-reference.",
    files=files,file_count=len(files),total_bytes=sum(x["bytes"] for x in files.values()),
    eol_only_mature_cpp_dependencies=eol_only,
    scan=dict(text_files=scanned,high_confidence_hits=[],scope="High-confidence local credential patterns only; not a guarantee for arbitrary secrets or compressed/binary content."),
    excluded=excluded,other_exclusions="Ignored build trees, objects, pytest temp/cache, venv and unrelated parent worktrees. Exactly five author Windows artifacts are separately packed and hash-listed.",
    historical_receipts="Old absolute paths and pushed=false remain original execution metadata; use manifest/reproduction notes to resolve published relative files.",
    user_original_file_preservation="Parent bounded_local_pibt.hpp must retain SHA b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951.")
MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
to_stage=sorted([*files,MANIFEST.relative_to(ROOT).as_posix()])
(OUT/"staging_paths.nul").write_bytes(b"\0".join((":(literal)"+p).encode("utf-8") for p in to_stage)+b"\0")
summary=dict(status="selected",files=len(files),bytes=manifest["total_bytes"],eol_only=len(eol_only),credential_scan_text_files=scanned,excluded=len(excluded),manifest_sha256=sha(MANIFEST.read_bytes()))
(OUT/"selection_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary))

