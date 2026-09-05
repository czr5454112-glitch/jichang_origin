"""Preserve V3 and derive its frozen-outlet-status correction as a distinct probe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmarks/java/feng_cie_dh_outlet_gate_v3/App"
DESTINATION = ROOT / "benchmarks/java/feng_cie_dh_outlet_gate_v3_snapshot/App"


def main():
    if DESTINATION.exists():
        raise RuntimeError("isolated snapshot probe source already exists")
    sources = sorted(SOURCE.glob("*.java"))
    assert len(sources) == 5
    DESTINATION.mkdir(parents=True)
    for source in sources:
        content = source.read_text(encoding="utf-8")
        if source.name == "FengDhBenchmark.java":
            anchor = '"FENG_DH_OUTLET_GATE_V3"'
            assert content.count(anchor) == 1
            content = content.replace(anchor, '"FENG_DH_OUTLET_GATE_V3_SNAPSHOT"')
        elif source.name == "FengDhSimulator.java":
            anchor = """        FengDhEdgeLattice.EntryBlocker blocker = lattice.entryBlocker(decision.selectedEdgeId);
        return blocker != null
                && blocker.bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE;"""
            assert content.count(anchor) == 1
            content = content.replace(anchor, """        // Earlier zero-through HOLD proposals must not leak their status
        // mutations into another node's decision in this same planning tick.
        for (FengDhEdgeLattice.OccupantSnapshot occupant
                : snapshot.occupants(decision.selectedEdgeId)) {
            if (occupant.positionCell < lattice.getFootprintCells()
                    && occupant.status == FengDhBagState.Status.STOPPED_ON_EDGE) {
                return true;
            }
        }
        return false;""")
        (DESTINATION / source.name).write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
    print(DESTINATION)


if __name__ == "__main__":
    main()
