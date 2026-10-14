"""Prepare the release-only overlay and staging list after code publication."""
from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[4]
P=R/"outputs/experiments/g31_ics_long_term_20261013/publication_20261014_001"
D=R/"docs/g31_ics_circulation"
M=D/"publication_20261014/release_manifest.json"
state=json.loads((D/"RESEARCH_STATE.json").read_text(encoding="utf-8"))
state["publication_result_registration"]=dict(added_entries=11,total_index_entries=289,
    script=Path(__file__).relative_to(R).as_posix())
(D/"RESEARCH_STATE.json").write_text(json.dumps(state,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
a=R/".gitattributes"
a.write_text(a.read_text(encoding="utf-8").replace("\r\n","\n"),encoding="utf-8",newline="\n")
def run(*args):
    return subprocess.run(["git",*args],cwd=R,capture_output=True,check=True).stdout
changed=[x for x in run("diff","--name-only","-z").decode().split("\0") if x]
new=[x for x in run("ls-files","--others","--exclude-standard","-z").decode().split("\0") if x]
files=set(changed)
for name in new:
    p=R/name
    if (name.startswith("docs/g31_ics_circulation/") or name.startswith(P.relative_to(R).as_posix()+"/")) and p.suffix in {".json",".py",".md",".log",".xml",".txt",".zip"}:
        if "clean_checkout" not in name and "pytest_tmp" not in name and p.stat().st_size<10*1024*1024:
            files.add(name)
files.discard(M.relative_to(R).as_posix())
files.discard((P/"release_selection_summary.json").relative_to(R).as_posix())
assert all(n in {".gitignore",".gitattributes"} or n.startswith(("docs/g31_ics_circulation/","outputs/experiments/g31_ics_long_term_20261013/publication_20261014_001/")) for n in files),sorted(files)
assert not any(n.startswith(("cpp/","scripts/","tests/")) for n in changed)
sha=lambda b:hashlib.sha256(b).hexdigest()
manifest=dict(schema="g31.release_overlay.v1",date="2026-10-14",code_commit="89c2935ef2963d769ab6ca75764009b2b3e9365f",
    source_manifest_sha256=sha((D/"publication_20261014/source_manifest.json").read_bytes()),
    scope="Apply these publication docs, metadata and raw validation receipts over source_manifest for the final release tree. This manifest excludes itself; release commit SHA is supplied by Git/ref/archive receipt.",
    production_and_test_changes=[],files={n:dict(bytes=(R/n).stat().st_size,sha256=sha((R/n).read_bytes())) for n in sorted(files)})
M.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
stage=sorted([*files,M.relative_to(R).as_posix()])
(P/"release_staging_paths.nul").write_bytes(b"\0".join((":(literal)"+p).encode("utf-8") for p in stage)+b"\0")
s=dict(status="selected",files=len(stage),bytes=sum(x["bytes"] for x in manifest["files"].values()),manifest_sha256=sha(M.read_bytes()))
(P/"release_selection_summary.json").write_text(json.dumps(s,indent=2)+"\n",encoding="utf-8")
print(json.dumps(s))

