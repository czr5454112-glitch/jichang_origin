package App;

import java.util.Arrays;

/** Contrast the actual upstream state under blocked and open switch-in tests. */
public final class OutletGateAudit {
    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id, id, 0, 1, 0, 0, 0, 99999, start, goal, false, "");
    }
    private static FengDhSimulator sim(FengDhEdgeLattice g, FengDhBagState... bags) {
        return new FengDhSimulator(g, new FengDhPolicy(g, 0.4, 0.8), Arrays.asList(bags));
    }
    private static void seed(FengDhEdgeLattice g, FengDhBagState b, int edge, int position) {
        b.release(0, false);
        b.enterEdge(0, edge, true, "", false);
        g.enter(edge, b);
        if (position > 0) {
            g.move(edge, b, position);
            b.moveOnEdge(0, position, false);
        }
        b.markDownstreamArrival(0, g.edge(edge).to);
    }
    private static void check(boolean okay, String why) {
        if (!okay) throw new AssertionError(why);
    }
    private static void blocked(double through, boolean gated) {
        FengDhEdgeLattice g = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1, through, 0, 0)
                .addNode(2, 1, 4, 0, 0).addNode(3, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 0.5).addEdge(2, 3, 2).build();
        FengDhBagState a = bag(1, 0, 3), follower = bag(2, 0, 3), blocker = bag(3, 1, 3);
        seed(g, a, 0, 3); seed(g, follower, 0, 1); seed(g, blocker, 1, 0);
        blocker.stopOnEdge(0, "seed_stopped", -1, -1, null, false);
        FengDhSimulator s = sim(g, a, follower, blocker);
        for (int tick = 1; tick <= 15; tick++) {
            s.step(0); g.assertIntegrity();
            if (gated) check(a.getCurrentEdgeId() == 0 && follower.getPositionCell() == 1,
                    "stopped outlet failed to keep upstream footprint and following backpressure");
        }
        if (!gated) check(a.getCurrentEdgeId() == -1, "control did not expose off-edge wait");
        while (s.getTick() < 200 && !(a.isCompleted() && follower.isCompleted() && blocker.isCompleted())) {
            s.step(0); g.assertIntegrity();
        }
        check(a.isCompleted() && follower.isCompleted() && blocker.isCompleted(), "gate did not reopen");
        System.out.println("{\"case\":\"blocked_" + through + "\",\"gated\":" + gated
                + ",\"all_complete\":true,\"completion_tick\":" + a.getCompletionTick() + "}");
    }
    private static void openPorts() {
        FengDhEdgeLattice g = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1, 1, 0, 0).addNode(3, 2)
                .addEdge(0, 2, 2).addEdge(1, 2, 2).addEdge(2, 3, 2).build();
        FengDhBagState a = bag(1, 0, 3), b = bag(2, 1, 3);
        seed(g, a, 0, 3); seed(g, b, 1, 3);
        FengDhSimulator s = sim(g, a, b);
        for (int tick = 1; tick <= 11; tick++) { s.step(0); g.assertIntegrity(); }
        check(a.getCurrentEdgeId() == -1 && b.getCurrentEdgeId() == -1
                && a.getNodeServiceReadyTick() == 16 && b.getNodeServiceReadyTick() == 21,
                "outlet gate incorrectly serialized the free-flow transfer timers");
        System.out.println("{\"case\":\"open_ports_overlap\",\"transfer_ready_ticks\":[16,21],\"pass\":true}");
    }
    private static void finite() {
        FengDhEdgeLattice g = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1, 20, 0, 0).addNode(2, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhSimulator.RunResult r = sim(g, bag(1, 0, 2)).run(new FengDhSimulator.RunConfig(200, 0, 2));
        check(r.status.equals("COMPLETE") && r.endTick == 128, "finite service mistaken for deadlock");
        System.out.println("{\"case\":\"finite_service\",\"completion_tick\":128,\"pass\":true}");
    }
    public static void main(String[] args) {
        boolean gated = args.length > 0 && args[0].equals("gated");
        blocked(0, gated); blocked(1, gated); openPorts(); finite();
    }
}
