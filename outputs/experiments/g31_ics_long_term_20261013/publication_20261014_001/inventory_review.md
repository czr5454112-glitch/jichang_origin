# Publication inventory review - 2026-10-14

This is a publication dependency review, not new physical experimentation. The root agent owns publication validation, manifest, commit and push. This subagent changed only five delegated test path/fixture lines and copied two immutable workbook fixtures; no production source changed.

## Required source and runtime dependencies

Publish the complete new `cpp/ics_core/{runtime,bindings}/circulation*`, modified `event_driven_junction.hpp`, `CMakeLists.txt`, three new C++ test/fixture files, both `scripts/experiments/g31_ics_circulation/` and `scripts/experiments/ics_circulation_v3/`, all corresponding G31/V3 tests, external review packages, and progress/research documents. Include the V3 bundled `fixtures/nanning_airport_profile.json` (681,974 bytes).

Keep existing tracked mature `src/`, C++ headers, `scripts/eval/`, `data/processed/maps/nanning_airport_profile.json`, `legacy/jichang_origin_readonly/inputdata.txt`, and `artifacts/tasks/g4irsf31_nanning/nanning_{1,2}x_manifest.json` in any complete repository archive. `native_host.py` imports mature `run_g4irsf28_service_potential`; `original_workload.py` imports mature G31 map/workload adapters and G29 densification. A delta ZIP alone is not a runnable repository. Use Python >=3.11, pytest, declared Python dependencies and `PYTHONPATH` including both `src` and root. Current native build requires C++17/CMake3.20+/pybind11. Archived native artifacts are Windows CPython3.11 AMD64, not Linux binaries or universal checkpoints.

## Current 407 regression dependencies and minimal fixes

Four native fixtures eagerly called `next(glob(...))` despite `G31_CIRCULATION_BINARY` being set. Fresh checkouts therefore required irrelevant old build folders. The fallback is now evaluated only when the environment variable is absent; an explicitly invalid configured path still fails. Files are `test_g31_circulation_finite_reference_native.py` (old12), `test_g31_circulation_regional_control.py` (old17), `test_g31_circulation_session.py` (old11), and `test_g31_circulation_joint_window_repair.py` (old22). All four belong to the current407 scope. No assertion/parameter/test was removed or loosened.

The only current407 test directly requiring external workbooks is `tests/test_g31_circulation_original_workload.py::test_source_workbooks_match_profile_without_editing` (old99-103, path101). It now uses existing `source_map.default_source_dir()`. The mature helper already prefers repository `map_nanning` then parent `map_nanning` (`scripts/eval/run_g4irsf31_nanning_map.py:112-116`); source filenames are declared at34-36. `original_workload.py:371,395` and `run_original_control.py:100` already use that helper, so no production change was necessary. The two workbooks are copied byte-for-byte to repository `map_nanning/`, retaining all workbook fields and original hashes.

Full407 additionally requires historical011 for one retained epsilon-order witness and historical011/015 for five identity regressions. `validate_live.py:35,69-75` pins011, while `test_g31_circulation_native_identity.py:11-15` hardcodes011/015 paths and hashes. Keep assertions and distribute an explicitly labeled Windows verification ZIP with exact original extraction paths. Distinguish401 current native/Python tests,1 historical witness,5 identity checks. A fresh current build is not a substitute for a historical artifact. `validate_legacy_parity.py:28-33` additionally requires `build_g31_parity/pinned.exe` and `final_receipt.json`; package these exact files in the verification attachment or state the extra prerequisite.

Artifact identities (independently read):

- native011:1,536,000 bytes, SHA256 `19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec`.
- native015:1,558,016 bytes, SHA256 `5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098`.
- native016:1,558,016 bytes, SHA256 `af34df38784eb2524fceb84311ed26a749f404e8877699c62c354ad0cd64fcb0`.
- legacy `pinned.exe`:870,400 bytes, SHA256 `67820592fc6927755880c43cde1aeb05a6aa515a358fb5292c9b255689745a72`.
- legacy `final_receipt.json`:532 bytes, SHA256 `290780e55939653d829dc8abd496026f26ed66a0b52871b2e96036753cefa2c2`.

## V3 restoration dependencies

`test_ics_circulation_v3_cursor_original_map.py:57-68` requires six full JSON files in `outputs/experiments/ics_circulation_v3/phase4_w3_cursor_original_map_20261009/`: `{cross_cycle,counterflow,near_full}_{original,cursor}.json`, total133,186,733 bytes. They are not used by G31407, but are needed for the V3 suite. Complete lossless gzip copies already exist in `docs/ics_circulation_v3/review_20261011/fixtures/` (4,776,309 bytes), with a hash manifest and `tools/prepare_fixtures.py` restoring exact bytes without overwriting mismatches. Keep that folder/tool even if publishing the raw files too. Do not describe historical V3 reports as a newly executed V3 run.

## Evidence selection and exclusions

At inventory time `outputs/experiments` contained4,006 files/362,068,510 bytes excluding pycache: initial circulation5,909,178; LT-1222,972,599; six V3 fixtures133,186,733. Publish raw event/control/business data, failed and successful receipts, JUnit, archived sources and identity manifests supporting review claims. Material cases include selected24 five-policy015/016,015/016 equality comparison,126-branch P5 runs, strict-order corrections, forecast and native-identity evidence. A result index alone does not contain its cited raw evidence: any absent entries must be marked in the manifest. Preserve negative outcomes and failures locally and in the review scope.

Do not blindly stage whole builds, `.git`, `.codex`, `.agents`, `.aws`, `.env`, virtual environments, cache/pytest temporary roots, compiler intermediates, machine credentials or parent-worktree modifications. Existing ignore rules exclude build directories, pycache, pytest caches, `.env`, local archives and system metadata. Verification ZIP may explicitly include only identified `.pyd` and legacy files, not entire build folders. Repeated delivery ZIPs/patches are redundant when a complete repository archive and exact same sources are published; omission must not delete local history.

## Byte integrity / bounded credential scan

`core.autocrlf=true`. Existing `.gitattributes` protects V3 source/tests/docs and older external review with `-text`; new G31 source/tests/docs/results are not all covered. Apply narrow exact-byte rules or prove staged blobs equal frozen disk bytes. Do not normalize hash-bound archived files. No LFS filter rules were present; git-lfs3.7.1 is installed but not configured for new files.

A high-confidence scan inspected5,318 text files <=8MB in C++, experimental scripts, tests, review docs and results. Rules covered private-key headers, GitHub tokens, long OpenAI-style tokens, AWS access IDs and credential-bearing HTTP URLs. No matches. Six larger V3 JSONs and binary/compressed contents were outside this bounded scan. This is not an absolute proof of no secrets. Environment paths in receipts are provenance; editing old receipts would invalidate their hashes. No secret values were printed.

## Publication edit and copy receipts

The first workbook-copy command failed before copying because `Path('.') .parent` remained relative `.`. Five test changes had already completed; no assertions changed. The retry resolved the absolute root, copied only missing targets and verified any existing target byte-for-byte. It did not reapply the test edits or overwrite different files.

```json
{
  "test_edits": [
    {
      "path": "tests/test_g31_circulation_finite_reference_native.py",
      "before_sha256": "f13b64cc230909f66a41372bd227018b430ea628a9110b483913f3bcdbcdd357",
      "after_sha256": "ca6936b17e05eb8dd840a6cf3ced2ace9dc59626b1974c7cab41e1642faecd85",
      "all_assertion_ast_unchanged": true
    },
    {
      "path": "tests/test_g31_circulation_regional_control.py",
      "before_sha256": "d93c9d5c30b804798fb9eec1285de4e19e1263568bd53d9a985f581b06c57a0d",
      "after_sha256": "072407c98050fb81ffd10fa70d4793527f5bd475427ea1d0219b643f497132d0",
      "all_assertion_ast_unchanged": true
    },
    {
      "path": "tests/test_g31_circulation_session.py",
      "before_sha256": "0817f53965bf1ea88f0c0fcae273fc68a1802f8a0d6441158a6cb7a0948ad1d8",
      "after_sha256": "84221a5f0ccf25ed8c12d5123cadd7532aa6d7af0f151200a3ada4e82863ab18",
      "all_assertion_ast_unchanged": true
    },
    {
      "path": "tests/test_g31_circulation_joint_window_repair.py",
      "before_sha256": "c03178d13c9efe9adcc4661e077b43fe93c4c7a9537168de4f291902ac41ff65",
      "after_sha256": "b2b9d5312e1de625d874f37397a568d42bd1126aa315c4dd23cea599c3eaa1bc",
      "all_assertion_ast_unchanged": true
    },
    {
      "path": "tests/test_g31_circulation_original_workload.py",
      "before_sha256": "93e2b930ea31f1af94377470944bb9c60e0d3f0a93c8530049fa5ed66b6f540a",
      "after_sha256": "55a75ab42255d6de7dc5b82f3a0488281b60fc6ef8b965fbd43888cb88a52c32",
      "all_assertion_ast_unchanged": true
    }
  ],
  "workbook_copies": [
    {
      "source": "C:\\PROGRAMING\\czr005\\map_nanning\\附件：拓扑结构示例1.xlsx",
      "destination": "map_nanning/附件：拓扑结构示例1.xlsx",
      "bytes": 15815,
      "sha256": "802fec3d6640e6a7ed2c087c03cd6a7f4eba1178809789694d621a263b7cd1ce",
      "exact_copy": true
    },
    {
      "source": "C:\\PROGRAMING\\czr005\\map_nanning\\附件：拓扑结构示例2.xlsx",
      "destination": "map_nanning/附件：拓扑结构示例2.xlsx",
      "bytes": 19200,
      "sha256": "3cf4b4ccc8d2a503050d58d6e93684992c81785e7fd9a405d0a32ff33382eb93",
      "exact_copy": true
    }
  ]
}
```

## Minimal diff

```diff
--- tests/test_g31_circulation_finite_reference_native.py (before publication)
+++ tests/test_g31_circulation_finite_reference_native.py (publication)
@@ -9,8 +9,10 @@
 
 @pytest.fixture(scope="module")
 def native():
-    return load_native(os.environ.get("G31_CIRCULATION_BINARY", str(next(
-        (Path(__file__).absolute().parents[1]/"build_lt_session/python").glob("czr005_circulation*.pyd")))))
+    binary = os.environ.get("G31_CIRCULATION_BINARY")
+    if binary is None:
+        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
+    return load_native(binary)
 
 
 @pytest.mark.parametrize("horizon", [20., .1])
--- tests/test_g31_circulation_regional_control.py (before publication)
+++ tests/test_g31_circulation_regional_control.py (publication)
@@ -14,8 +14,10 @@
 
 @pytest.fixture(scope="module")
 def native():
-    return load_native(os.environ.get("G31_CIRCULATION_BINARY", str(next(
-        (Path(__file__).absolute().parents[1]/"build_lt_session/python").glob("czr005_circulation*.pyd")))))
+    binary = os.environ.get("G31_CIRCULATION_BINARY")
+    if binary is None:
+        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
+    return load_native(binary)
 
 
 def scene():
--- tests/test_g31_circulation_session.py (before publication)
+++ tests/test_g31_circulation_session.py (publication)
@@ -8,8 +8,10 @@
 
 @pytest.fixture(scope="module")
 def native():
-    return load_native(os.environ.get("G31_CIRCULATION_BINARY", str(next(
-        (Path(__file__).absolute().parents[1]/"build_lt_session/python").glob("czr005_circulation*.pyd")))))
+    binary = os.environ.get("G31_CIRCULATION_BINARY")
+    if binary is None:
+        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
+    return load_native(binary)
 
 
 def request(now=10):
--- tests/test_g31_circulation_joint_window_repair.py (before publication)
+++ tests/test_g31_circulation_joint_window_repair.py (publication)
@@ -18,8 +18,11 @@
 
 @pytest.fixture(scope="module")
 def native():
-    fallback = Path(__file__).absolute().parents[1] / "build_lt_session_006/python"
-    return load_native(os.environ.get("G31_CIRCULATION_BINARY", str(next(fallback.glob("czr005_circulation*.pyd")))))
+    binary = os.environ.get("G31_CIRCULATION_BINARY")
+    if binary is None:
+        fallback = Path(__file__).absolute().parents[1] / "build_lt_session_006/python"
+        binary = next(fallback.glob("czr005_circulation*.pyd"))
+    return load_native(binary)
 
 
 def test_long_incoming_reservation_starts_at_entry_not_arrival():
--- tests/test_g31_circulation_original_workload.py (before publication)
+++ tests/test_g31_circulation_original_workload.py (publication)
@@ -7,7 +7,7 @@
 
 from scripts.experiments.g31_ics_circulation.original_workload import (
     DEFAULT_MAP, ROOT, ProxyContract, build_input, static_diagnostics,
-    summarize_execution, verify_source_map, return_contract_diagnostics,
+    summarize_execution, verify_source_map, return_contract_diagnostics, source_map,
 )
 
 
@@ -98,7 +98,7 @@
 
 def test_source_workbooks_match_profile_without_editing():
     profile = json.loads(DEFAULT_MAP.read_text(encoding="utf-8"))
-    result = verify_source_map(profile, ROOT.parent/"map_nanning")
+    result = verify_source_map(profile, source_map.default_source_dir())
     assert result["status"] == "exact_source_rows_match"
     assert result["source_files_edited"] is False
 

```

Validation: all five test assertion AST lists are identical before/after; workbook bytes and hashes match. Root will run full publication regression. This subagent did not stage, commit or push.
