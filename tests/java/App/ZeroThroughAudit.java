package App;

import java.io.File;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;

/** Independent state-machine regressions, deliberately outside the five production sources. */
public final class ZeroThroughAudit {
    private static File output;

    public static void main(String[] args) throws Exception {
        output = new File(args[1]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }
        boolean gate = "--gate".equals(args[0]);
        single(0.0d, gate);
        single(1.0d, gate);
        if (!gate) {
            return;
        }
        following(1.0d);
        following(0.5d);
        competition();
        downstreamBlocked();
        finiteServiceAndDeadlock();
        duplicateService();
        zeroGoal();
        realNanning(args[2]);
        simultaneousSourceEntry();
    }

    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id, id, 0, 1, 0, 0, 0, 999, start, goal, false, "");
    }

    private static FengDhEdgeLattice line(double through, double footprint) {
        return FengDhEdgeLattice.builder().physicalDimensions(footprint, 0)
                .addNode(0, 1, 1, 0, 0).addNode(1, 1, through, 0, 0)
                .addNode(2, 2, 0, 0, 0).addEdge(0, 1, 2).addEdge(1, 2, 2).build();
    }

    private static FengDhSimulator sim(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        return new FengDhSimulator(lattice, new FengDhPolicy(lattice, 0.4, 0.8),
                Arrays.asList(bags));
    }

    private static void single(double through, boolean gate) throws Exception {
        FengDhEdgeLattice lattice = line(through, 1.0d);
        FengDhBagState bag = bag(1, 0, 2);
        FengDhSimulator simulator = sim(lattice, bag);
        FengDhSimulator.RunResult result = simulator.run(new FengDhSimulator.RunConfig(100, 1, 10));
        long starts = count(bag, "NODE_SERVICE_START", 1, "ZERO_MAP_THROUGH_TIME");
        String id = through == 0.0d ? "Z1_zero_intermediate" : "Z2_positive_control";
        trace(id, bag);
        boolean pass = "COMPLETE".equals(result.status) && result.completedRawBags == 1
                && result.endTick == (through == 0.0d ? 28 : 33)
                && lattice.activeOnEdges() == 0 && (through != 0.0d || starts == 1);
        System.out.println("{\"case_id\":\"" + id + "\",\"status\":\"" + result.status
                + "\",\"completed\":" + result.completedRawBags + ",\"end_tick\":" + result.endTick
                + ",\"zero_service_starts\":" + starts + ",\"state\":\"" + bag.getStatus()
                + "\",\"pass\":" + pass + "}");
        if (gate) {
            check(pass, id);
        }
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

    private static void following(double footprint) throws Exception {
        FengDhEdgeLattice lattice = line(0, footprint);
        FengDhBagState leader = bag(1, 0, 2);
        FengDhBagState follower = bag(2, 0, 2);
        seed(lattice, leader, 0, 3);
        int prior = 3 - lattice.getFootprintCells();
        seed(lattice, follower, 0, prior);
        FengDhSimulator simulator = sim(lattice, follower, leader);
        simulator.step(1);
        check(leader.getCurrentEdgeId() == -1 && leader.getStatus()
                == FengDhBagState.Status.AT_LOADING_OR_JUNCTION, "zero service releases footprint");
        check(leader.getNodeServiceStartTick() == 1 && leader.getNodeServiceReadyTick() == 11,
                "zero service starts the fixed transfer exactly once");
        check(follower.getPositionCell() == prior + 1, "same-commit follower uses vacated footprint");
        checkedFinish(simulator, lattice, 100, leader, follower);
        check(leader.getCompletionTick() < follower.getCompletionTick(), "FIFO following");
        check(count(leader, "NODE_SERVICE_START", 1, "ZERO_MAP_THROUGH_TIME") == 1
                && count(follower, "NODE_SERVICE_START", 1, "ZERO_MAP_THROUGH_TIME") == 1,
                "one zero service per arrival");
        String id = footprint == 1.0d ? "Z3_following" : "Z4_one_cell_footprint";
        trace(id, leader, follower);
        passed(id);
    }

    private static void competition() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 2).addNode(3, 1)
                .addEdge(0, 1, 2).addEdge(3, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState lowerId = bag(1, 0, 2);
        FengDhBagState higherId = bag(2, 3, 2);
        seed(lattice, lowerId, 0, 3);
        seed(lattice, higherId, 1, 3);
        FengDhSimulator simulator = sim(lattice, higherId, lowerId);
        simulator.step(1);
        check(lowerId.getCurrentEdgeId() == -1, "tie resolves by deterministic local FIFO");
        check(higherId.getCurrentEdgeId() == 1 && higherId.getStatus()
                == FengDhBagState.Status.STOPPED_ON_EDGE, "competing bag stops on its own edge");
        simulator.step(1);
        check(higherId.getNodeServiceStartTick() == 2 && higherId.getNodeServiceReadyTick() == 12,
                "loser admitted next tick without stale service occupant");
        checkedFinish(simulator, lattice, 100, lowerId, higherId);
        check(lowerId.getCompletionTick() < higherId.getCompletionTick(), "merge preserves FIFO");
        trace("Z5_simultaneous_competition", lowerId, higherId);
        passed("Z5_simultaneous_competition");
    }

    private static void downstreamBlocked() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1, 4.0d, 0, 0)
                .addNode(3, 2).addEdge(0, 1, 2).addEdge(1, 2, 0.5d)
                .addEdge(2, 3, 2).build();
        FengDhBagState waiting = bag(1, 0, 3);
        FengDhBagState blocker = bag(2, 1, 3);
        seed(lattice, waiting, 0, 3);
        seed(lattice, blocker, 1, 0);
        FengDhSimulator simulator = sim(lattice, waiting, blocker);
        for (int i = 0; i < 12; i++) {
            simulator.step(1);
            integrity(lattice, waiting, blocker);
        }
        check(waiting.getStatus() == FengDhBagState.Status.AT_LOADING_OR_JUNCTION
                && waiting.getCurrentEdgeId() == -1 && waiting.getNodeServiceReadyTick() == 11,
                "blocked downstream retains completed transfer timer off the upstream edge");
        check(count(waiting, "NODE_SERVICE_START", 1, "ZERO_MAP_THROUGH_TIME") == 1
                && waiting.getLastHoldReason().equals("ENTRY_STOPPED_OCCUPANT"),
                "no restart while held for stopped downstream occupant");
        checkedFinish(simulator, lattice, 200, waiting, blocker);
        check(blocker.getCompletionTick() < waiting.getCompletionTick(), "blocking bag not crossed");
        trace("Z6_downstream_blocked_then_release", waiting, blocker);
        passed("Z6_downstream_blocked_then_release");
    }

    private static void finiteServiceAndDeadlock() throws Exception {
        FengDhEdgeLattice lattice = line(20, 1);
        FengDhBagState bag = bag(1, 0, 2);
        FengDhSimulator.RunResult result = sim(lattice, bag).run(
                new FengDhSimulator.RunConfig(200, 1, 2));
        check("COMPLETE".equals(result.status) && result.endTick == 128,
                "finite source/through/transfer countdowns are progress with short idle threshold");
        trace("Z7_finite_service_not_deadlock", bag);
        passed("Z7_finite_service_not_deadlock");

        lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 2).build();
        bag = bag(2, 0, 1);
        result = sim(lattice, bag).run(new FengDhSimulator.RunConfig(200, 1, 2));
        check("DEADLOCK".equals(result.status) && result.endTick == 11,
                "expired service and repeated unreachable decisions do not count as progress");
        trace("Z8_no_path_deadlock", bag);
        passed("Z8_no_path_deadlock");
    }

    private static void duplicateService() {
        FengDhEdgeLattice lattice = line(0, 1);
        FengDhBagState bag = bag(1, 0, 2);
        seed(lattice, bag, 0, 3);
        bag.beginBoundaryService(1, 1, 1, "zero", false);
        boolean rejected = false;
        try {
            bag.beginBoundaryService(2, 1, 2, "zero", false);
        } catch (IllegalStateException expected) {
            rejected = expected.getMessage().contains("duplicate boundary service");
        }
        check(rejected, "duplicate zero boundary service has explicit diagnostic");
        passed("Z9_duplicate_service_rejected");
    }

    private static void zeroGoal() throws Exception {
        FengDhEdgeLattice lattice = line(0, 1);
        FengDhBagState bag = bag(1, 0, 1);
        FengDhSimulator.RunResult result = sim(lattice, bag).run(
                new FengDhSimulator.RunConfig(100, 1, 10));
        check("COMPLETE".equals(result.status) && result.endTick == 14
                && count(bag, "NODE_SERVICE_START", 1, "") == 0,
                "zero goal completes directly without intermediate transfer");
        trace("Z10_zero_goal", bag);
        passed("Z10_zero_goal");
    }

    private static void realNanning(String mapPath) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.readLegacyMap(new File(mapPath));
        FengDhBagState bag = bag(1, 130, 58);
        check(lattice.edge(130, 57) != null && lattice.edge(57, 58) != null
                && lattice.nodes().get(Integer.valueOf(57)).throughTimeSeconds == 0,
                "real Nanning zero intermediate fixture");
        FengDhSimulator.RunResult result = sim(lattice, bag).run(
                new FengDhSimulator.RunConfig(5000, 1, 10));
        check("COMPLETE".equals(result.status) && result.completedRawBags == 1
                && count(bag, "NODE_SERVICE_START", 57, "ZERO_MAP_THROUGH_TIME") == 1,
                "real Nanning 130 to 57 to 58 completes");
        trace("Z11_real_nanning_130_57_58", bag);
        System.out.println("{\"case_id\":\"Z11_real_nanning_130_57_58\",\"end_tick\":"
                + result.endTick + ",\"completed\":1,\"pass\":true}");
    }

    private static void simultaneousSourceEntry() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 2)
                .addEdge(0, 1, 0.5d).addEdge(1, 2, 2).build();
        FengDhBagState leader = bag(1, 0, 2);
        FengDhBagState source = bag(2, 0, 2);
        seed(lattice, leader, 0, 0);
        source.release(0, true);
        source.beginNodeService(0, 0, 0, "seed_source_transfer_complete", true);
        FengDhSimulator simulator = sim(lattice, source, leader);
        simulator.step(1);
        check(leader.getCurrentEdgeId() == -1 && source.getCurrentEdgeId() == 0
                && source.getFirstAdmissionTick() == 1,
                "ready source enters the upstream edge in the zero departure commit");
        checkedFinish(simulator, lattice, 100, leader, source);
        check(leader.getCompletionTick() < source.getCompletionTick(), "source FIFO survives merge");
        trace("Z12_same_commit_source_entry", leader, source);
        passed("Z12_same_commit_source_entry");
    }

    private static void checkedFinish(FengDhSimulator simulator, FengDhEdgeLattice lattice,
            int horizon, FengDhBagState... bags) {
        while (simulator.getTick() < horizon) {
            boolean done = true;
            for (FengDhBagState bag : bags) {
                done &= bag.isCompleted();
            }
            if (done) {
                check(lattice.activeOnEdges() == 0, "complete population releases lattice");
                return;
            }
            simulator.step(1);
            integrity(lattice, bags);
        }
        throw new AssertionError("population did not complete");
    }

    private static void integrity(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        lattice.assertIntegrity();
        HashSet<Long> seen = new HashSet<Long>();
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                check(seen.add(Long.valueOf(bag.taskId)), "unique edge identity");
            }
        }
        for (FengDhBagState bag : bags) {
            check((bag.getCurrentEdgeId() >= 0) == seen.contains(Long.valueOf(bag.taskId)),
                    "every edge-state bag owns exactly one footprint");
        }
    }

    private static long count(FengDhBagState bag, String event, int node, String detail) {
        long count = 0;
        for (FengDhBagState.TraceEvent value : bag.getTrace()) {
            if (value.event.equals(event) && value.node == node && value.detail.contains(detail)) {
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
                    writer.println(bag.taskId + "\t" + event.tick + "\t" + event.event + "\t"
                            + event.node + "\t" + event.edgeId + "\t" + event.positionCell
                            + "\t" + event.detail);
                }
            }
        } finally {
            writer.close();
        }
    }

    private static void passed(String id) {
        System.out.println("{\"case_id\":\"" + id + "\",\"pass\":true}");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
