package App;

import java.io.File;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;

/** Runs against both parent and V6, including actual counterfactual exit changes. */
public final class PostMovementScoringAudit {
    private static boolean post;
    private static File output;

    public static void main(String[] args) throws Exception {
        post = args[0].equals("post");
        output = new File(args[1]);
        if (!output.isDirectory() && !output.mkdirs()) throw new IllegalStateException("output");
        branch("PS1_newly_stopped", 5.5d, 1.0d, 1, 0, 2);
        branch("PS2_newly_moving", 3.5d, 1.0d, 2, 2, 0);
        branch("PS3_goal_departure", 2.5d, 1.0d, 3, 2, 0);
        branch("PS4_zero_departure", 2.5d, 0.0d, 4, 2, 0);
        branch("PS5_positive_departure", 2.5d, 1.0d, 5, 2, 0);
        simultaneousEntrants();
        originalStoppedEntryGate();
        single(0.0d, 28);
        single(1.0d, 33);
    }

    private static FengDhBagState bag(long id, int start, int goal) {
        return new FengDhBagState(id * 2, id, 0, 1, 0, 0, 0, 9999, start, goal, false, "");
    }

    private static void ready(FengDhBagState bag, int tick) {
        bag.release(0, true);
        bag.beginNodeService(0, bag.startNode, tick, "fixture_ready_source", true);
    }

    private static FengDhSimulator sim(FengDhEdgeLattice lattice, FengDhBagState... bags) {
        return new FengDhSimulator(lattice, new FengDhPolicy(lattice, .4d, .8d), Arrays.asList(bags));
    }

    private static void seed(FengDhEdgeLattice lattice, FengDhBagState bag, int edge, int pos, boolean stopped) {
        bag.release(0, true);
        bag.enterEdge(0, edge, true, "seed", true);
        lattice.enter(edge, bag);
        if (pos > 0) {
            lattice.move(edge, bag, pos);
            bag.moveOnEdge(0, pos, true);
        }
        if (pos == lattice.edge(edge).cellCount - 1) bag.markDownstreamArrival(0, lattice.edge(edge).to);
        if (stopped) bag.stopOnEdge(0, "seed_stopped", -1, -1, null, true);
    }

    private static void check(boolean pass, String message) {
        if (!pass) throw new AssertionError(message);
    }

    private static void close(double a, double b, String message) {
        check(Math.abs(a - b) < 1.0e-9d, message + ": " + a + " vs " + b);
    }

    private static void step(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        simulator.step(1);
        lattice.assertIntegrity();
        HashSet<Long> occupants = new HashSet<Long>();
        for (FengDhEdgeLattice.EdgeData edge : lattice.edges()) {
            for (FengDhBagState bag : lattice.occupantsDownstreamFirst(edge.id)) {
                check(occupants.add(Long.valueOf(bag.taskId)), "duplicate physical identity");
            }
        }
        for (FengDhBagState bag : bags) {
            check(occupants.contains(Long.valueOf(bag.taskId)) == (bag.getCurrentEdgeId() >= 0), "ownership mismatch");
        }
    }

    private static void finish(FengDhSimulator simulator, FengDhEdgeLattice lattice, FengDhBagState... bags) {
        while (simulator.getTick() < 400) {
            boolean complete = true;
            for (FengDhBagState bag : bags) complete &= bag.isCompleted();
            if (complete) {
                check(lattice.activeOnEdges() == 0, "completed occupancy");
                return;
            }
            step(simulator, lattice, bags);
        }
        throw new AssertionError("finite fixture failed completion");
    }

    private static FengDhBagState.TraceEvent firstSelect(FengDhBagState bag) {
        for (FengDhBagState.TraceEvent event : bag.getTrace()) {
            if (event.event.equals("SELECT")) return event;
        }
        throw new AssertionError("missing actual route choice");
    }

    private static double eta(FengDhBagState.TraceEvent event) {
        for (String field : event.detail.split(";")) {
            if (field.startsWith("eta_seconds=")) return Double.parseDouble(field.substring(12));
        }
        throw new AssertionError("missing actual selected score");
    }

    private static double scoreA(FengDhEdgeLattice.Snapshot snapshot, long excluded) {
        double score = 1.6d;
        for (int edge = 0; edge <= 1; edge++) {
            for (FengDhEdgeLattice.OccupantSnapshot bag : snapshot.occupants(edge)) {
                if (bag.taskId != excluded) {
                    score += bag.status == FengDhBagState.Status.MOVING_ON_EDGE ? .4d : .8d;
                }
            }
        }
        return score;
    }

    private static void branch(String id, double altLength, double through, int mechanism,
            int parentExit, int postExit) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1)
                .addNode(2, 1).addNode(3, 1, through, 0, 0).addNode(4, 2)
                .addEdge(0, 1, 2).addEdge(1, 3, 2)
                .addEdge(0, 2, altLength).addEdge(2, 3, 2).addEdge(3, 4, 2).build();
        FengDhBagState query = bag(1, 0, 3);
        ready(query, mechanism == 5 ? 6 : 1);
        FengDhBagState occupant = bag(2, 1, mechanism == 3 ? 3 : 4);
        seed(lattice, occupant, 1, mechanism == 2 ? 1 : 3, mechanism == 1 || mechanism == 2);
        FengDhBagState[] bags;
        if (mechanism == 1) {
            FengDhBagState follower = bag(3, 1, 4);
            seed(lattice, follower, 1, 1, false);
            bags = new FengDhBagState[] {query, occupant, follower};
        } else bags = new FengDhBagState[] {query, occupant};
        FengDhSimulator simulator = sim(lattice, bags);
        while (simulator.getTick() < (mechanism == 5 ? 5 : 0)) step(simulator, lattice, bags);
        long decisionTick = simulator.getTick();
        FengDhEdgeLattice.Snapshot old = lattice.snapshot();
        FengDhPolicy.Decision parent = new FengDhPolicy(lattice, .4d, .8d).choose(0, 3, old);
        check(parent.selectedEdgeId == parentExit, "counterfactual fixture does not discriminate");
        double parentA = scoreA(old, query.taskId), alternate = (altLength + 2.0d) / 2.5d;
        step(simulator, lattice, bags);
        FengDhBagState.TraceEvent actual = firstSelect(query);
        check(actual.tick == decisionTick, "first divergence tick misidentified");
        int expected = post ? postExit : parentExit;
        check(actual.edgeId == expected, "actual route choice used incorrect observation phase");
        // Independently reconstruct phase-(a) counts from the committed physical
        // bags, removing this tick's newly entering query rather than the blocker.
        double projectedA = scoreA(lattice.snapshot(), query.taskId);
        check((projectedA < alternate ? 0 : 2) == postExit, "projected fixture scores do not discriminate");
        double expectedScore = post ? (postExit == 0 ? projectedA : alternate) : parent.etaSeconds;
        close(eta(actual), expectedScore, "actual selected score differs from declared view");
        check(parentExit != postExit, "missing changed exit");
        finish(simulator, lattice, bags);
        write(id, "\"first_decision_tick\":" + decisionTick + ",\"first_commit_tick\":" + (decisionTick + 1)
                + ",\"parent_selected_edge\":" + parentExit + ",\"post_selected_edge\":" + postExit
                + ",\"actual_selected_edge\":" + actual.edgeId + ",\"tick_start_candidate_A_eta\":" + parentA
                + ",\"post_movement_candidate_A_eta\":" + projectedA + ",\"candidate_B_eta\":" + alternate, bags);
    }

    private static void simultaneousEntrants() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1)
                .addNode(2, 1).addNode(3, 2).addEdge(0, 1, 2).addEdge(1, 3, 2)
                .addEdge(0, 2, 2.5d).addEdge(2, 3, 2).build();
        FengDhBagState a = bag(1, 0, 3), b = bag(2, 0, 3);
        ready(a, 1); ready(b, 1);
        FengDhSimulator simulator = sim(lattice, b, a);
        step(simulator, lattice, a, b);
        check(firstSelect(a).edgeId == 0 && firstSelect(b).edgeId == 0,
                "current entrants leaked into a later request's score");
        close(eta(firstSelect(a)), 1.6d, "first request score");
        close(eta(firstSelect(b)), 1.6d, "later request must use same frozen view");
        check(a.getCurrentEdgeId() == 0 && b.getCurrentEdgeId() == -1
                && b.getLastHoldReason().equals("LOCAL_FIFO_ENTRY_CONFLICT"), "entry arbitration changed");
        finish(simulator, lattice, a, b);
        write("PS6_new_entries_excluded", "\"first_selected_edges\":[0,0],\"selected_eta\":1.6", a, b);
    }

    private static void originalStoppedEntryGate() throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().physicalDimensions(.5d, 0)
                .addNode(0, 1).addNode(1, 2).addEdge(0, 1, 2).build();
        FengDhBagState query = bag(1, 0, 1), occupant = bag(2, 0, 1);
        ready(query, 1);
        seed(lattice, occupant, 0, 0, true);
        FengDhSimulator simulator = sim(lattice, query, occupant);
        step(simulator, lattice, query, occupant);
        check(occupant.getPositionCell() == 1 && occupant.getStatus() == FengDhBagState.Status.MOVING_ON_EDGE,
                "stopped entry occupant did not resume in plan");
        check(query.getFirstAdmissionTick() == -1 && query.getLastHoldReason().equals("ENTRY_STOPPED_OCCUPANT"),
                "scoring state leaked into original stopped entrance arbitration");
        close(eta(firstSelect(query)), post ? 1.2d : 1.6d, "score phase did not change stopped/moving count");
        step(simulator, lattice, query, occupant);
        check(query.getFirstAdmissionTick() == 2, "entry admission timing changed");
        finish(simulator, lattice, query, occupant);
        write("PS7_original_entry_gate", "\"query_admission_tick\":2,\"first_selected_eta\":"
                + eta(firstSelect(query)), query, occupant);
    }

    private static void single(double through, long completion) throws Exception {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 1, through, 0, 0)
                .addNode(2, 2).addEdge(0, 1, 2).addEdge(1, 2, 2).build();
        FengDhBagState bag = bag(1, 0, 2);
        finish(sim(lattice, bag), lattice, bag);
        check(bag.getCompletionTick() == completion && bag.getFirstAdmissionTick() == 10, "single free-flow time changed");
        write(through == 0 ? "PS8_zero_single" : "PS9_positive_single", "\"completion_tick\":" + completion, bag);
    }

    private static void write(String id, String detail, FengDhBagState... bags) throws Exception {
        PrintWriter writer = new PrintWriter(new File(output, id + ".tsv"), "UTF-8");
        try {
            writer.println("task_id\ttick\tevent\tnode\tedge\tposition\tdetail");
            for (FengDhBagState bag : bags) {
                for (FengDhBagState.TraceEvent event : bag.getTrace()) {
                    writer.println(bag.taskId + "\t" + event.tick + "\t" + event.event + "\t" + event.node
                            + "\t" + event.edgeId + "\t" + event.positionCell + "\t" + event.detail);
                }
            }
        } finally { writer.close(); }
        System.out.println("{\"case_id\":\"" + id + "\",\"pass\":true,\"post_movement_scoring\":"
                + post + ",\"all_complete\":true," + detail + "}");
    }
}
