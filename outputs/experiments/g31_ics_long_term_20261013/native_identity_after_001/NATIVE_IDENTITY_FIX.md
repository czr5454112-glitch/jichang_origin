# Native artifact identity correction

This is a correctness repair, not a method or research contribution.

The real pre-fix process loaded native015 and then requested native011. The second call silently returned the native015 path, SHA256, and `NativeSession` class. Its actual forecast estimate was 2.0, although a fresh native011 process produces 4.0 for the same input. The pre-fix probe exited 1; its full input, requests, messages, physical receipts, and module identities remain in `../native_identity_before_001/result.json`. The frozen pre-fix source is retained beside it.

`native_host.load_native` now resolves and hashes the requested binary, verifies the actual loaded module's resolved `__file__` and bytes, and pins that artifact identity on the loaded module. A mismatched artifact fails with `ImportError`, includes both paths and hashes, and requires a fresh process. It does not attempt DLL unloading, module-cache deletion, or reloading.

The real post-fix 015-to-011 process rejects the second load (`cross_version.json`). Fresh independent processes confirm that both artifacts still work (`fresh_011.json`, `fresh_015.json`). Both run the same tiny physical service and enter their first edge at 2.0; the old and current forecasts are 4.0 and 2.0 respectively. This deliberately uses a known version-sensitive physical diagnostic, in addition to the actual file identity.

Five regression cases passed with no failures, errors, or skips (`regression.xml`): repeated loading of the same artifact, rejection in both cross-version orders, and each artifact's real fresh-process behavior. Parent pytest imports no native extension; every native case runs in its own subprocess. The tests require the two pinned artifacts to be present and do not claim these builds are portable distributions.

Run from the worktree:

```powershell
C:/PROGRAMING/python3.11.9/python.exe -m pytest -q tests/test_g31_circulation_native_identity.py
```

Post-fix source SHA256: `03c33fbbaff5049b9068471edf7d7208f4921e977cc008e04461c515635bc48b`.

Native011 SHA256: `19b55703676810bacc156e474aac364e4016dda2d2fa7b4fa315a3237a1bdbec`.

Native015 SHA256: `5919ed48a86aed8302f1c9a813574c161feac93600f998e89e5cdfd385bbc098`.

Any previous claim based on switching these extensions inside one process must be rechecked in independent processes. This probe does not identify or invalidate unrelated historical runs that already loaded one binary per process. It also does not assert checkpoint compatibility across versions.
