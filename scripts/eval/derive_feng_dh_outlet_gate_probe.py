"""Derive one explicit outlet-HOLD-location probe from the preserved control."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'benchmarks/java/feng_cie_dh/App'
DESTINATION = ROOT / 'benchmarks/java/feng_cie_dh_outlet_gate_v3/App'


def main():
    if DESTINATION.exists():
        raise RuntimeError('isolated probe source already exists')
    DESTINATION.mkdir(parents=True)
    for source in SOURCE.glob('*.java'):
        text = source.read_text(encoding='utf-8')
        if source.name == 'FengDhBenchmark.java':
            text = text.replace('"FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION"', '"FENG_DH_OUTLET_GATE_V3"')
        elif source.name == 'FengDhSimulator.java':
            anchor = '                    throughServicesFinishing.add(bag);'
            assert text.count(anchor) == 1
            text = text.replace(anchor, '''                    // Test HOLD before leaving upstream, preserving overlapping transit.
                    if (outletStopped(bag, edge.to, snapshot)) {
                        stopPhysicalHandoff(bag, commitTick,
                                "PRE_TRANSFER_OUTLET_STOPPED", traceSampleModulo);
                        continue;
                    }
''' + anchor)
            anchor = '                approvedNodeServices.put(Long.valueOf(winner.bag.taskId), winner);'
            assert text.count(anchor) == 1
            text = text.replace(anchor, '''                if (mapThroughTicks(winner.node) == 0L
                        && outletStopped(winner.bag, winner.node, snapshot)) {
                    for (NodeServiceProposal proposal : proposals) {
                        stopPhysicalHandoff(proposal.bag, commitTick,
                                "PRE_TRANSFER_OUTLET_STOPPED", traceSampleModulo);
                    }
                    continue;
                }
''' + anchor)
            anchor = '    private void planInternalMovement('
            assert text.count(anchor) == 1
            text = text.replace(anchor, '''    private boolean outletStopped(FengDhBagState bag, int node,
            FengDhEdgeLattice.Snapshot snapshot) {
        FengDhPolicy.Decision decision = policy.choose(node, bag.goalNode, snapshot);
        if (decision == null) return true;
        FengDhEdgeLattice.EntryBlocker blocker = lattice.entryBlocker(decision.selectedEdgeId);
        return blocker != null
                && blocker.bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE;
    }

''' + anchor)
        (DESTINATION / source.name).write_bytes(text.replace('\n', '\r\n').encode('utf-8'))
    print(DESTINATION)


if __name__ == '__main__':
    main()
