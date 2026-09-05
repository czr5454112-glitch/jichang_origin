package App;

import java.util.HashMap;
import java.util.HashSet;

/** A score view cannot mutate physics or drift when its inputs later change. */
public final class PostMovementSnapshotAudit {
    private static void check(boolean pass, String message) {
        if (!pass) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        FengDhEdgeLattice lattice = FengDhEdgeLattice.builder().addNode(0, 1).addNode(1, 2)
                .addEdge(0, 1, 2).build();
        FengDhBagState bag = new FengDhBagState(2, 1, 0, 1, 0, 0, 0, 9999, 0, 1, false, "");
        bag.release(0, false);
        bag.enterEdge(0, 0, true, "seed", false);
        lattice.enter(0, bag);
        bag.stopOnEdge(0, "seed", -1, -1, null, false);
        FengDhEdgeLattice.Snapshot before = lattice.snapshot();
        HashMap<Long, Integer> positions = new HashMap<Long, Integer>();
        positions.put(Long.valueOf(bag.taskId), Integer.valueOf(1));
        HashSet<Long> departures = new HashSet<Long>();
        FengDhEdgeLattice.Snapshot projected = lattice.scoringSnapshotAfterMovement(positions, departures);
        check(projected.movingCount(0) == 1 && projected.stoppedCount(0) == 0
                && projected.occupants(0).get(0).positionCell == 1, "projection did not reflect planned movement");
        check(bag.getPositionCell() == 0 && bag.getStatus() == FengDhBagState.Status.STOPPED_ON_EDGE,
                "score projection mutated physical bag state");
        positions.clear();
        departures.add(Long.valueOf(bag.taskId));
        lattice.move(0, bag, 2);
        bag.moveOnEdge(1, 2, false);
        check(projected.occupants(0).size() == 1 && projected.occupants(0).get(0).positionCell == 1
                && projected.movingCount(0) == 1 && before.stoppedCount(0) == 1
                && before.occupants(0).get(0).positionCell == 0, "frozen views retained mutable inputs");
        boolean immutable = false;
        try { projected.occupants(0).clear(); }
        catch (UnsupportedOperationException expected) { immutable = true; }
        check(immutable, "score occupants are externally mutable");
        check(lattice.scoringSnapshotAfterMovement(positions, departures).occupants(0).isEmpty(),
                "guaranteed departures must not require a retained movement position");
        departures.clear();
        boolean incompleteRejected = false;
        try { lattice.scoringSnapshotAfterMovement(positions, departures); }
        catch (IllegalStateException expected) { incompleteRejected = true; }
        check(incompleteRejected, "incomplete plan silently falls back to old state");
        lattice.assertIntegrity();
        System.out.println("{\"case_id\":\"PS10_frozen_projection\",\"pass\":true,"
                + "\"physical_state_untouched\":true,\"mutable_inputs_detached\":true,"
                + "\"incomplete_plan_rejected\":true}");
    }
}
