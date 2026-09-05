# Outlet gate frozen-snapshot fixtures

This small audit preserves the original V3 source and full-run outputs. The distinct snapshot probe corrects the use of live STOPPED status during a frozen-tick plan. It does not claim original Feng implementation fidelity or run a new population experiment.

Compile the tracked five probe sources and the two audit classes from the repository root:

```powershell
$probeSources = Get-ChildItem benchmarks/java/feng_cie_dh_outlet_gate_v3_snapshot/App -Filter '*.java' | Select-Object -ExpandProperty FullName
& 'C:/PROGRAMING/jdk-18/bin/javac.exe' -encoding UTF-8 -d build/feng_cie_dh_outlet_gate_v3_snapshot $probeSources
& 'C:/PROGRAMING/jdk-18/bin/javac.exe' -encoding UTF-8 -cp build/feng_cie_dh_outlet_gate_v3_snapshot -d build/feng_cie_dh_outlet_gate_v3_snapshot_audit tests/java/App/OutletGateAudit.java tests/java/App/OutletGateSnapshotAudit.java
& 'C:/PROGRAMING/jdk-18/bin/java.exe' -cp 'build/feng_cie_dh_outlet_gate_v3_snapshot;build/feng_cie_dh_outlet_gate_v3_snapshot_audit' App.OutletGateSnapshotAudit frozen
& 'C:/PROGRAMING/jdk-18/bin/java.exe' -cp 'build/feng_cie_dh_outlet_gate_v3_snapshot;build/feng_cie_dh_outlet_gate_v3_snapshot_audit' App.OutletGateAudit gated
```

To reproduce the diagnostic control contrast, compile the preserved original `benchmarks/java/feng_cie_dh_outlet_gate_v3/App` sources to `build/feng_dh_outlet_gate_v3`, then run:

```powershell
& 'C:/PROGRAMING/jdk-18/bin/java.exe' -cp 'build/feng_dh_outlet_gate_v3;build/feng_cie_dh_outlet_gate_v3_snapshot_audit' App.OutletGateSnapshotAudit live
```

Original V3 permits the upstream handoff only for one of the two node-ID orders. The corrected version permits it for both: the frozen outlet occupant was moving at tick start even when another zero-through gate marks it stopped later in planning. Both versions still stop the middle bag at its originally stopped outlet. The transferred bag's ready tick remains 11.

`verification.json` records the exact commands, eight successful fixture observations, both source/class identities, and the explicit absence of full-population and Nanning runs. Production class hashes exclude the audit classes, which are compiled to a separate directory. Source bytes are CRLF to preserve the recorded aggregate identity in a Windows checkout. The derivation source is `scripts/eval/derive_feng_dh_outlet_gate_snapshot_probe.py`.
