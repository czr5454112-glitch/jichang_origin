package App;

/** Value-level cache regression; also executable against the unoptimized classes. */
public final class FengDhOptimizationRegression {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void decision(
            FengDhPolicy.Decision actual, int edge, int moving, int stopped,
            double eta, int ties, String message) {
        require(actual != null, message + ": null");
        require(actual.selectedEdgeId == edge && actual.movingBags == moving
                        && actual.stoppedBags == stopped
                        && Double.doubleToLongBits(actual.etaSeconds)
                                == Double.doubleToLongBits(eta)
                        && actual.equalScoreCandidateCount == ties,
                message + ": " + actual.traceDetail());
    }

    public static void main(String[] args) {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder()
                .addNode(0, 1).addNode(1, 1).addNode(2, 1).addNode(3, 1).addNode(4, 1)
                .addEdge(0, 1, 5.0d).addEdge(1, 3, 5.0d)
                .addEdge(0, 2, 5.0d).addEdge(2, 3, 5.0d).build();
        FengDhPolicy policy = new FengDhPolicy(lattice, 0.4d, 0.8d);
        FengDhEdgeLattice.Snapshot empty = lattice.snapshot();
        decision(policy.choose(0, 3, empty), 0, 0, 0, 4.0d, 2, "first tied request");
        decision(policy.choose(0, 3, empty), 0, 0, 0, 4.0d, 2, "cached tied request");

        FengDhBagState bag = new FengDhBagState(
                1L, 1L, 0, 1, 0.0d, 0.0d, 0L, 999.0d, 0, 3, false, "");
        bag.release(0L, false);
        bag.enterEdge(0L, 0, true, "", false);
        lattice.enter(0, bag);
        bag.stopOnEdge(0L, "fixture", 0, -1, null, false);
        FengDhEdgeLattice.Snapshot stopped = lattice.snapshot();
        require(stopped.movingCount(0) == 0 && stopped.stoppedCount(0) == 1,
                "stopped snapshot counts");
        require(empty.movingCount(0) == 0 && empty.stoppedCount(0) == 0,
                "old snapshot remains empty after live admission");
        decision(policy.choose(0, 3, stopped), 2, 0, 0, 4.0d, 1, "changed occupancy");
        decision(policy.choose(0, 3, stopped), 2, 0, 0, 4.0d, 1, "cached untied request");

        lattice.move(0, bag, 1);
        bag.moveOnEdge(1L, 1, false);
        require(stopped.movingCount(0) == 0 && stopped.stoppedCount(0) == 1,
                "snapshot counts must not read mutable live bag state");
        decision(policy.choose(0, 3, stopped), 2, 0, 0, 4.0d, 1, "same frozen snapshot");
        FengDhEdgeLattice.Snapshot moving = lattice.snapshot();
        require(moving.movingCount(0) == 1 && moving.stoppedCount(0) == 0,
                "new snapshot sees stopped-to-moving change");
        decision(policy.choose(0, 1, moving), 0, 1, 0, 2.4d, 1, "different goal key");
        decision(policy.choose(0, 1, moving), 0, 1, 0, 2.4d, 1, "cached moving count");

        require(policy.choose(0, 4, moving) == null, "unreachable request");
        require(policy.choose(0, 4, moving) == null, "cached unreachable request");
        require(policy.choose(4, 4, moving) == null, "goal request");
        require(policy.getUnreachableDecisions() == 2L,
                "goal request is not unreachable; both missing-route requests count");

        lattice.remove(0, bag);
        FengDhEdgeLattice.Snapshot cleared = lattice.snapshot();
        decision(policy.choose(0, 3, cleared), 0, 0, 0, 4.0d, 2, "removal invalidates score");
        decision(policy.choose(0, 3, stopped), 2, 0, 0, 4.0d, 1, "revisiting old snapshot");
        require(moving.movingCount(0) == 1 && cleared.movingCount(0) == 0,
                "old and new counts remain independent after removal");
        require(cleared.movingCount(-1) == 0 && cleared.stoppedCount(999) == 0,
                "unknown edges preserve empty count behavior");
        require(policy.getDecisions() == 12L && policy.getTiedDecisions() == 3L
                        && policy.getUnreachableDecisions() == 2L,
                "logical request/tie/unreachable counters must include cache hits");
        System.out.println("{\"status\":\"PASS\",\"decisions\":12,"
                + "\"tied_decisions\":3,\"unreachable_decisions\":2,"
                + "\"snapshot_invalidation\":true,\"frozen_counts\":true,"
                + "\"revisited_snapshot\":true,\"per_goal_key\":true}");
    }
}
