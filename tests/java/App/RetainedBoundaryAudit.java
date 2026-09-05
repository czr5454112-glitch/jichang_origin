package App;

import java.io.File;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;

/** Mechanism gates for the separate upstream-retained transfer hypothesis. */
public final class RetainedBoundaryAudit {
    private static File output;

    public static void main(String[] args) throws Exception {
        output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create audit output");
        }
        single(0.0d, 28L);
        single(1.0d, 33L);
        blockedOutlet();
        overlappingIncomingPorts();
        zeroOneShotAndFiniteProgress();
        closedBlockedCycle();
        unchangedSourceAndGoal();
        nanning(args[1]);
        incomingHeadway();
    }

    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id, id, 0, 1, 0, 0, 0, 99999, start, goal, false, "");
    }

    private static FengDhSimulator sim(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        return new FengDhSimulator(lattice, new FengDhPolicy(lattice, 0.4d, 0.8d), Arrays.asList(bags));
    }

    private static void seed(FengDhEdgeLattice lattice, FengDhBagState bag, int edge, int pos) {
        bag.release(0, true);
        bag.enterEdge(0, edge, true, "seed", true);
        lattice.enter(edge, bag);
        if (pos > 0) {
            lattice.move(edge, bag, pos);
            bag.moveOnEdge(0, pos, true);
        }
        if (pos == lattice.edge(edge).cellCount - 1) {
            bag.markDownstreamArrival(0, lattice.edge(edge).to);
        }
    }

    private static void check(boolean pass, String message) {
        if (!pass) {
            throw new AssertionError(message);
        }
    }

    private static void integrity(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        lattice.assertIntegrity();
        HashSet<Long> edges = new HashSet<Long>();
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                check(edges.add(Long.valueOf(bag.taskId)), "duplicate lattice identity");
            }
        }
        for (FengDhBagState bag : bags) {
            check(edges.contains(Long.valueOf(bag.taskId)) == (bag.getCurrentEdgeId() >= 0),
                    "bag/edge ownership mismatch");
            check(bag.getFirstAdmissionTick() < 0 || bag.isCompleted() || bag.getCurrentEdgeId() >= 0,
                    "admitted unfinished bag escaped into occupancy-free intermediate storage");
            if (bag.isRetainedBoundaryTransfer()) {
                check(bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE,
                        "retained transfer must be a physical stopped footprint");
            }
        }
    }

    private static void step(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        simulator.step(1);
        integrity(lattice, bags);
    }

    private static void finish(FengDhSimulator simulator, FengDhEdgeLattice lattice,
            int horizon, FengDhBagState... bags) {
        while (simulator.getTick() < horizon) {
            boolean complete = true;
            for (FengDhBagState bag : bags) {
                complete &= bag.isCompleted();
            }
            if (complete) {
                check(lattice.activeOnEdges() == 0, "completed population still occupies edges");
                return;
            }
            step(simulator, lattice, bags);
        }
        throw new AssertionError("fixture did not finish by " + horizon);
    }

    private static void single(double through, long expected) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1, through, 0, 0).addNode(2, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        FengDhSimulator simulator = sim(lattice, bag);
        finish(simulator, lattice, 100, bag);
        check(bag.getCompletionTick() == expected, "single-bag dwell doubled or source/goal changed");
        String id = through == 0 ? "RB1_zero_single_28_ticks" : "RB2_positive_single_33_ticks";
        trace(id, bag);
        passed(id, "\"completion_tick\":" + bag.getCompletionTick());
    }

    private static void blockedOutlet() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1, 4.0d, 0, 0).addNode(3, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 0.5d).addEdge(2, 3, 2).build();
        FengDhBagState waiting = bag(1, 0, 3), follower = bag(2, 0, 3), blocker = bag(3, 1, 3);
        seed(lattice, waiting, 0, 3);
        seed(lattice, follower, 0, 1);
        seed(lattice, blocker, 1, 0);
        FengDhSimulator simulator = sim(lattice, follower, blocker, waiting);
        for (int tick = 1; tick <= 30; tick++) {
            step(simulator, lattice, waiting, follower, blocker);
            check(waiting.getCurrentEdgeId() == 0 && waiting.getPositionCell() == 3,
                    "blocked outlet must retain the original incoming footprint");
            check(follower.getPositionCell() == 1, "queue did not propagate behind retained transfer");
            if (tick >= 11) {
                check(waiting.getNodeServiceReadyTick() == 11, "expired zero-transfer timer restarted");
            }
        }
        step(simulator, lattice, waiting, follower, blocker);
        check(simulator.getTick() == 31 && waiting.getCurrentEdgeId() == 1
                && blocker.getCurrentEdgeId() == 2 && follower.getPositionCell() == 2,
                "conditional same-commit outlet vacancy and follower advance were lost");
        finish(simulator, lattice, 200, waiting, follower, blocker);
        check(blocker.getCompletionTick() < waiting.getCompletionTick()
                && waiting.getCompletionTick() < follower.getCompletionTick(), "FIFO/overtaking violation");
        trace("RB3_blocked_outlet_retains_upstream", waiting, follower, blocker);
        passed("RB3_blocked_outlet_retains_upstream", "\"upstream_release_tick\":31,\"expired_timer_ready_tick\":11");
    }

    private static void overlappingIncomingPorts() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1, 1.0d, 0, 0).addNode(3, 2)
                .addEdge(0, 2, 2).addEdge(1, 2, 2).addEdge(2, 3, 2).build();
        FengDhBagState a = bag(1, 0, 3), b = bag(2, 1, 3);
        seed(lattice, a, 0, 3);
        seed(lattice, b, 1, 3);
        FengDhSimulator simulator = sim(lattice, b, a);
        for (int tick = 1; tick <= 11; tick++) {
            step(simulator, lattice, a, b);
        }
        check(a.isRetainedBoundaryTransfer() && b.isRetainedBoundaryTransfer()
                && a.getCurrentEdgeId() == 0 && b.getCurrentEdgeId() == 1,
                "two incoming ports cannot retain separate physical transfers");
        check(a.getNodeServiceReadyTick() == 16 && b.getNodeServiceReadyTick() == 21,
                "two-second per-bag transfer became a three-second node-wide exclusive service");
        check(firstService(a, "MAP_JUNCTION_THROUGH_EXCLUSIVE") == 1
                && firstService(b, "MAP_JUNCTION_THROUGH_EXCLUSIVE") == 6,
                "map-through service identity was not released at tick 6");
        finish(simulator, lattice, 100, a, b);
        trace("RB4_two_ports_no_three_second_exclusivity", a, b);
        passed("RB4_two_ports_no_three_second_exclusivity", "\"through_start_ticks\":[1,6],\"transfer_ready_ticks\":[16,21]");
    }

    private static void zeroOneShotAndFiniteProgress() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1, 20.0d, 0, 0).addNode(2, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        FengDhSimulator.RunResult result = sim(lattice, bag).run(new FengDhSimulator.RunConfig(200, 1, 2));
        check(result.status.equals("COMPLETE") && result.endTick == 128, "finite retained transfer misclassified as deadlock");
        integrity(lattice, bag);
        trace("RB5_finite_countdowns", bag);
        passed("RB5_finite_countdowns", "\"completion_tick\":128");

        lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1).addNode(2, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        bag = bag(2, 0, 2);
        seed(lattice, bag, 0, 3);
        FengDhSimulator simulator = sim(lattice, bag);
        step(simulator, lattice, bag);
        boolean rejected = false;
        try {
            bag.beginRetainedBoundaryTransfer(2, 12, "duplicate", false);
        } catch (IllegalStateException expected) {
            rejected = true;
        }
        check(rejected && bag.getNodeServiceStartTick() == 1 && bag.getNodeServiceReadyTick() == 11,
                "retained transfer can be silently restarted");
        finish(simulator, lattice, 100, bag);
        check(serviceCount(bag, "ZERO_MAP_THROUGH_TIME") == 1
                && serviceCount(bag, "INTERMEDIATE_FIXED_TRANSFER_DELAY") == 1, "zero arrival started repeated services");
        trace("RB6_zero_one_shot", bag);
        passed("RB6_zero_one_shot", "\"zero_service_starts\":1,\"transfer_starts\":1");
    }

    private static void closedBlockedCycle() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 2).addNode(3, 2)
                .addEdge(0, 1, 0.5d).addEdge(1, 0, 0.5d)
                .addEdge(0, 2, 1).addEdge(1, 3, 1).build();
        FengDhBagState a = bag(1, 0, 2), b = bag(2, 1, 3);
        seed(lattice, a, 0, 0);
        seed(lattice, b, 1, 0);
        FengDhSimulator simulator = sim(lattice, a, b);
        FengDhSimulator.RunResult result = simulator.run(new FengDhSimulator.RunConfig(100, 1, 2));
        check(result.status.equals("DEADLOCK") && result.endTick == 12,
                "blocked ready timers fabricate progress or rotate a full stopped cycle");
        integrity(lattice, a, b);
        check(a.getCurrentEdgeId() == 0 && b.getCurrentEdgeId() == 1, "blocked cycle escaped into free node queues");
        trace("RB7_blocked_cycle_deadlock", a, b);
        passed("RB7_blocked_cycle_deadlock", "\"deadlock_tick\":12");
    }

    private static void unchangedSourceAndGoal() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1, 10, 0, 0).addNode(1, 2, 10, 0, 0).addEdge(0, 1, 2).build();
        FengDhBagState bag = bag(1, 0, 1);
        FengDhSimulator simulator = sim(lattice, bag);
        finish(simulator, lattice, 100, bag);
        check(bag.getFirstAdmissionTick() == 10 && bag.getCompletionTick() == 14,
                "source induction or direct goal semantics changed");
        trace("RB8_source_goal_unchanged", bag);
        passed("RB8_source_goal_unchanged", "\"admission_tick\":10,\"completion_tick\":14");
    }

    private static void nanning(String mapPath) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(new File(mapPath));
        FengDhBagState bag = bag(1, 130, 58);
        FengDhSimulator simulator = sim(lattice, bag);
        finish(simulator, lattice, 5000, bag);
        check(bag.getCompletionTick() == 251 && serviceCount(bag, "ZERO_MAP_THROUGH_TIME") == 1,
                "real Nanning zero intermediate changed uncongested dwell or repeated service");
        trace("RB9_real_nanning_zero_intermediate", bag);
        passed("RB9_real_nanning_zero_intermediate", "\"completion_tick\":251");
    }

    private static void incomingHeadway() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1, 1.0d, 0, 0).addNode(2, 2)
                .addEdge(0, 1, 2).addEdge(1, 2, 20).build();
        FengDhBagState a = bag(1, 0, 2), b = bag(2, 0, 2);
        seed(lattice, a, 0, 3);
        seed(lattice, b, 0, 1);
        FengDhSimulator simulator = sim(lattice, a, b);
        finish(simulator, lattice, 200, a, b);
        long first = firstService(a, "MAP_JUNCTION_THROUGH_EXCLUSIVE");
        long second = firstService(b, "MAP_JUNCTION_THROUGH_EXCLUSIVE");
        check(first == 1 && second == 18, "retained same-port headway changed unexpectedly");
        trace("RB10_same_incoming_port_headway", a, b);
        passed("RB10_same_incoming_port_headway", "\"through_start_ticks\":[1,18],\"headway_seconds\":3.4");
    }

    private static long firstService(FengDhBagState bag, String detail) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals("NODE_SERVICE_START") && event.detail.contains(detail)) {
                return event.tick;
            }
        }
        return -1;
    }

    private static int serviceCount(FengDhBagState bag, String detail) {
        int count = 0;
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals("NODE_SERVICE_START") && event.detail.contains(detail)) {
                count++;
            }
        }
        return count;
    }

    private static void trace(String id, FengDhBagState... bags) throws Exception {
        PrintWriter writer = new PrintWriter(new File(output, id + ".tsv"), "UTF-8");
        try {
            writer.println("task_id\ttick\tevent\tnode\tedge\tposition\tdetail");
            for (FengDhBagState bag : bags) {
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    writer.println(bag.taskId + "\t" + event.tick + "\t" + event.event + "\t" + event.node
                            + "\t" + event.edgeId + "\t" + event.positionCell + "\t" + event.detail);
                }
            }
        } finally {
            writer.close();
        }
    }

    private static void passed(String id, String detail) {
        System.out.println("{\"case_id\":\"" + id + "\",\"pass\":true," + detail + "}");
    }
}
