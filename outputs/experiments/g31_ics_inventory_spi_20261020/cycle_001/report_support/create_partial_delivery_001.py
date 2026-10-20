"""Package an already built, immutable partial CAS with its frozen audit tools."""
import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def bound(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(ref):
    path = Path(ref["path"])
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == ref["sha256"], str(path)
    return data


def build(package, manifest_sha256, output):
    package, output = Path(package).resolve(), Path(output).resolve()
    assert package.is_relative_to(HERE) and package.is_dir()
    assert output.is_relative_to(HERE) and not output.exists()
    manifest_ref = {"path": str(package / "PACKAGE_MANIFEST.json"), "sha256": manifest_sha256}
    manifest = json.loads(checked(manifest_ref))
    assert manifest["schema"] == "g31.inventory_spi.partial_compact_publication.v1.package"
    declared = {"PACKAGE_MANIFEST.json"} | {r["package_path"] for r in manifest["files"]}
    actual = {str(p.relative_to(package)).replace("\\", "/") for p in package.rglob("*") if p.is_file()}
    assert actual == declared, "exact CAS inventory"
    for row in manifest["files"]:
        p = package / row["package_path"]
        assert p.resolve().is_relative_to(package)
        assert p.stat().st_size == row["bytes"]
        checked({"path": str(p), "sha256": row["sha256"]})

    inventory_path = HERE / "partial_portable_validator_inventory_001.json"
    inventory = json.loads(checked({
        "path": str(inventory_path),
        "sha256": "c931e05992cb60acaa3b18d1677927baa52dd39b9401c45dd6342d2f0e01f776",
    }))
    assert inventory["validator_file_count"] == 6 and len(inventory["files"]) == 6
    extras = {}
    for row in inventory["files"]:
        extras[row["portable_path"]] = checked(row["source"])
    mapped = {str(Path(r["original_path"]).resolve()).casefold(): r["sha256"]
              for r in manifest["original_path_map"]}

    def included_report(path):
        reference = bound(path)
        assert mapped[str(Path(path).resolve()).casefold()] == reference["sha256"]
        return checked(reference)

    report = HERE / "INVENTORY_SPI_STAGE_REPORT_001.md"
    extras["report/" + report.name] = included_report(report)
    for suffix in ("png", "svg"):
        relative = f"paired_cost_harm_figure_002/paired_cost_and_known_harm_002.{suffix}"
        extras["report/" + relative] = included_report(HERE / relative)
    extras["validator_inventory.json"] = json.dumps({
        "schema": "g31.inventory_spi.partial_delivery.validator_inventory.v1",
        "scope": "Exact six frozen validator files; no audit result implied by packaging.",
        "files": inventory["files"],
    }, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    hashes = "\n".join(f"- {r['portable_path']}: {r['source']['sha256']}" for r in inventory["files"])
    readme = f"""G31 airport inventory SPI: partial evidence delivery

Manifest SHA256: {manifest_sha256}
The ZIP SHA and actual audit result are supplied in a separate delivery receipt.
Obtain trusted expected hashes from that separately supplied receipt. The ZIP
does not contain its own hash or claim a future audit result.

Scope
The original fixed40 formal slots remain: 36 completed and4 unstarted.
All40 primary_J values are null. Completed-cell descriptive costs are permitted;
formal averages, ranking, promotion, protected takeover and test-set model
selection are not. Missing and failed outputs are retained, never filled with0.
Read report/INVENTORY_SPI_STAGE_REPORT_001.md for scientific findings and limits.

Layout
evidence/ contains ONLY PACKAGE_MANIFEST.json and objects/<sha256>.
validators/ contains the six exact frozen standard-library Python validators.
report/, README.txt and validator_inventory.json remain outside evidence/.
Do not add an audit report or any other file inside evidence/.

Audit on Windows Python3.11, in a fresh deep directory outside the repository:
  $auditRoot = Join-Path $env:TEMP ('g31_audit_' + [guid]::NewGuid().ToString('N'))
  $delivery = Join-Path $auditRoot 'level1\\level2\\level3\\delivery'
  New-Item -ItemType Directory -Path $delivery | Out-Null
  Expand-Archive -LiteralPath 'C:\\PATH\\TO\\DELIVERY.zip' -DestinationPath $delivery
  $validators = Join-Path $delivery 'validators'
  python -I -B (Join-Path $validators 'compact_partial_publication_001.py') audit `
    (Join-Path $delivery 'evidence') --manifest-sha256 '{manifest_sha256}' `
    --helper-directory $validators --output (Join-Path $auditRoot 'audit.json')

Inspect audit.json status, not just process exit0. Expected successful status:
partial_included_evidence_verified_with_missing_and_failures_retained

No repository, pip packages, network, native binary loading or training is needed
for this audit command. Original paths are CAS mapping/provenance keys, not file
fallbacks. The deep extraction path is required by two frozen helpers' imports.
Windows path semantics are required; Linux/macOS auditing has not been verified.
Do not use producer preflight/build/select as a portable audit substitute.

The audit rehashes all included objects and checks model hashes, identities,
frozen training metadata and permitted raw costs/pair labels. It does not
recompute model fitting or development selection, rerun trajectories, replay
excluded large histories, certify clock chronology or independently repeat all
physical replay. Individual CAS members are limited to32MiB and decoded JSON to
256MiB. None of these checks establishes an RL benefit or complete formal test.

Frozen validator SHA256 values:
{hashes}
"""
    extras["README.txt"] = readme.encode("utf-8")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in sorted(declared):
            archive.write(package / relative, "evidence/" + relative)
        for relative, data in sorted(extras.items()):
            archive.writestr(relative, data)
    receipt = {
        "schema": "g31.inventory_spi.partial_delivery_build.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "delivery_built_pending_isolated_audit",
        "implementation": bound(__file__),
        "manifest": manifest_ref,
        "zip": bound(output),
        "zip_bytes": output.stat().st_size,
        "evidence_members": len(declared),
        "validator_count": 6,
        "scientific_report": bound(report),
        "extras": [{"path": n, "bytes": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                   for n, d in sorted(extras.items())],
        "native_operations": 0, "fit_operations": 0,
        "isolated_audit_performed": False,
        "python": sys.version,
    }
    receipt_path = output.with_suffix(".build.json")
    with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return {"receipt": bound(receipt_path), "zip": receipt["zip"], "zip_bytes": receipt["zip_bytes"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.package, args.manifest_sha256, args.output), ensure_ascii=False))
