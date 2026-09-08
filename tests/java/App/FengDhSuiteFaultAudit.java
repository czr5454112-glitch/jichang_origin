package App;

import java.util.Arrays;

/** Known-topology fault conservation and real alternative-route execution. */
public final class FengDhSuiteFaultAudit {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        for (boolean unreachable : new boolean[]{false, true}) {
            FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                    .addNode(0, 0).addNode(1, 1).addNode(2, 1).addNode(3, 2)
                    .addEdge(0, 1, 2).addEdge(1, 3, 2).addEdge(0, 2, 5).addEdge(2, 3, 5).build();
            lattice.setInitialBlockedEdges(unreachable ? "1:3;2:3" : "1:3");
            FengDhBagState bag = new FengDhBagState(0, 0, 0, 1, 0, 0, 0, 1000, 0, 3, false, "");
            FengDhSimulator simulator = new FengDhSimulator(lattice,
                    new FengDhPolicy(lattice, .4, .8), Arrays.asList(bag));
            FengDhSimulator.RunResult result = simulator.run(new FengDhSimulator.RunConfig(1000, 1, Long.MAX_VALUE));
            require(result.segmentPopulation == 1 && result.rawBagPopulation == 1, "population removed");
            if (unreachable) {
                require(result.endTick == 1000 && !bag.isCompleted() && result.completedRawBags == 0,
                        "unreachable bag fabricated complete or stopped before fixed horizon");
            } else {
                require(bag.isCompleted() && bag.getCurrentNode() == 3, "reroute failed");
                boolean usedAlternative = false;
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    if (event.event.equals("ENTER_EDGE")) {
                        require(event.edgeId != 1, "entered failed edge");
                        if (event.edgeId == 2) usedAlternative = true;
                    }
                }
                require(usedAlternative, "no alternative route executed");
            }
            lattice.assertIntegrity();
            System.out.println("{\"test\":\"known_fault\",\"unreachable\":"+unreachable+",\"pass\":true}");
        }
    }
}
