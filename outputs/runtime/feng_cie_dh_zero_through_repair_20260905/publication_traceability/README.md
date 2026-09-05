# Portable evidence and independent traceability audit

This directory closes the publication gap between locally retained native CSV
paths and independently inspectable evidence. The audit does not rerun or
modify the simulator, maps, legacy files or experiment results.

- `map2_shared_archive_manifest.json` binds complete bags, segments and the
  trace header shared byte for byte by original `99bf...`, corrected `3b47...`
  and optimized `809d...` executions. The accompanying gzip files contain all
  28,506 bags and 43,603 segments, so the exact-population regression is
  inspectable without rerunning the original executable.
- `formal_60_workload_identities.json.gz` preserves the exact UTF-8 bytes of
  all 60 input identity JSON files. Its members match the identity hashes in
  both maps' complete formal-OD coverage audit.
- `reused_evidence.json` is a byte-exact copy of the optimized campaign's
  otherwise ignored 150-cell reuse mapping. The accompanying
  `reused_150_normalized_records.json.gz` preserves all 150 normalized JSON
  records verbatim: 90 map2 records (three methods) and 60 Nanning HCA/G31
  records. `reused_150_normalized_archive_manifest.json` verifies original
  and copied bytes match, connects every record to the 60-workload identity
  bundle, and confirms that no invalidated Nanning DH record was reused.
  This makes the old normalized identities, native-evidence hashes,
  denominator/timing contracts and metrics inspectable in Git without
  duplicating large native trajectories.
- `invalidated_30_statuses_and_16_terminal_records.json.gz` preserves exact
  bytes of all 30 old Nanning runner statuses and 16 normalized terminal
  records. It supports the old campaign's scientific-invalidity sidecar at
  `outputs/runtime/cie_external_baseline_robustness/scientific_validity_20260905.json`.
  That sidecar remains at its original path and must be explicitly added to
  Git because the surrounding old campaign directory is otherwise ignored.
- `frozen_input_and_source_identity.json` identifies every tracked map, original
  raw input, shared schedule, Nanning business-role profile and 15 frozen
  legacy Java sources by both Git-blob bytes and measured working-file bytes.
  It records the exact newline conversion needed to recover measured bytes
  without assuming `core.autocrlf`. It also verifies recovery of all three
  production source versions from their immutable Git commits.
- `publication_traceability_audit.json` records independent checksum checks
  of the final/optimized OD archives, the optimization's complete 128-bag
  shared congestion trace, and every population archive exported when the
  audit ran. It lists pending Git additions explicitly. The parent campaign
  may still be producing cells; rerun the audit after the last export before
  publishing, so the recorded population manifest hash reflects that export.

For any ordinary `.csv.gz` or `.jsonl.gz`, decompress it and compare SHA-256
with the manifest's uncompressed digest. Bundled JSON gzip files use
`{"members": [...]}`; each member contains its repository-relative source
path, original SHA-256 and an `utf8` string. Re-encoding that string as UTF-8
reconstructs the original member bytes, including original whitespace and
newlines. Absolute paths inside original JSON remain provenance; resolve
published files using the manifests' repository-relative archive paths.

Example independent checks, using Python's standard library:

```python
import gzip, hashlib, json
from pathlib import Path
root = Path('outputs/runtime/feng_cie_dh_zero_through_repair_20260905/publication_traceability')
bundle = json.loads(gzip.decompress((root / 'formal_60_workload_identities.json.gz').read_bytes()))
assert len(bundle['members']) == 60
for member in bundle['members']:
    assert hashlib.sha256(member['utf8'].encode('utf-8')).hexdigest() == member['sha256']
manifest = json.loads((root / 'map2_shared_archive_manifest.json').read_text())
for member in manifest['files']:
    archive = member['archive']
    data = Path(archive['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == archive['sha256']
    assert hashlib.sha256(gzip.decompress(data)).hexdigest() == archive['uncompressed_sha256']
```

To repeat the complete independent audit on the original experiment workspace,
run `python scripts/eval/audit_feng_publication_traceability.py`. It verifies
existing published archive bytes, checks local source identities, rebuilds
these small portable bundles and reports any pending Git publication paths.
Native invalidated trajectories remain local and are excluded from valid
performance comparisons; no such raw trajectory is needed to inspect the
published corrected population results.
