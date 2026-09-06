import App.ICS_PathFinding;
import App.Node;
import App.task;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;

/** Bounded storage/lookup isolation test; it does not test collision feasibility. */
public final class HcaSegmentReservationAudit {
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static Node node(int location, double start, double finish) {
        Node result = new Node();
        result.setLocation(location);
        result.setT1(start);
        result.setT2(finish);
        return result;
    }

    private static ArrayList<Node> path(double first, double second) {
        return new ArrayList<Node>(Arrays.asList(node(17, first, first + 2), node(18, second, second + 2)));
    }

    private static ArrayList<Double> query(int id) {
        return new ArrayList<Double>(Arrays.asList((double) id, 0.0, 0.0));
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        HashMap<Integer, ArrayList<task>> pending = new HashMap<>();
        pending.put(0, new ArrayList<task>());
        pending.put(2, new ArrayList<task>());
        ArrayList<Object> mapping = new ArrayList<>();
        Method read = HcaSegmentIdentityBenchmark.class.getDeclaredMethod("readTaskList", String.class,
            HashMap.class, Double.TYPE, Integer.TYPE, Integer.TYPE, Double.TYPE, ArrayList.class);
        read.setAccessible(true);
        read.invoke(null, args[0], pending, 5.0, 1, 2, 5.0, mapping);
        ArrayList<Integer> ids = new ArrayList<>();
        for (ArrayList<task> list : pending.values()) {
            for (task value : list) ids.add(value.getTask_ID());
        }
        Collections.sort(ids);
        require(ids.size() == 2 && !ids.get(0).equals(ids.get(1)), "fixture must map one early bag to two unique live IDs");
        int firstId = ids.get(0), secondId = ids.get(1);

        ICS_PathFinding scheduler = new ICS_PathFinding();
        Method update = ICS_PathFinding.class.getDeclaredMethod("update_constrain", Integer.TYPE, ArrayList.class, HashMap.class);
        Method contains = ICS_PathFinding.class.getDeclaredMethod("Contains", ArrayList.class, ArrayList.class);
        update.setAccessible(true);
        contains.setAccessible(true);
        HashMap<Integer, ArrayList<ArrayList<Double>>> constraints = new HashMap<>();
        constraints.put(17, new ArrayList<ArrayList<Double>>());
        constraints.put(18, new ArrayList<ArrayList<Double>>());

        // Deliberately overlapping sample intervals exercise identity storage,
        // not path feasibility or physical collision admission.
        update.invoke(scheduler, firstId, path(10, 30), constraints);
        update.invoke(scheduler, secondId, path(10.5, 30.5), constraints);
        ArrayList<Double> second17 = (ArrayList<Double>) contains.invoke(scheduler, query(secondId), constraints.get(17));
        ArrayList<Double> second18 = (ArrayList<Double>) contains.invoke(scheduler, query(secondId), constraints.get(18));
        require(second17 != null && second18 != null, "second execution reservation missing");
        for (int location : new int[] {17, 18}) {
            require(constraints.get(location).size() == 2, "two execution reservations did not coexist");
            require(contains.invoke(scheduler, query(firstId), constraints.get(location)) != null, "first reservation missing");
            require(contains.invoke(scheduler, query(999999), constraints.get(location)) == null, "foreign execution lookup matched");
        }
        update.invoke(scheduler, firstId, path(20, 40), constraints);
        require(constraints.get(17).size() == 2 && constraints.get(18).size() == 2, "updating first execution removed another reservation");
        require(contains.invoke(scheduler, query(secondId), constraints.get(17)) == second17
            && contains.invoke(scheduler, query(secondId), constraints.get(18)) == second18,
            "second execution reservation object was replaced");
        require(second17.equals(Arrays.asList((double) secondId, 10.5, 12.5))
            && second18.equals(Arrays.asList((double) secondId, 30.5, 32.5)), "second execution interval changed");
        require(contains.invoke(scheduler, query(firstId), constraints.get(17)).equals(Arrays.asList((double) firstId, 20.0, 22.0)),
            "first execution interval was not updated");

        HashMap<Integer, ArrayList<ArrayList<Double>>> colliding = new HashMap<>();
        colliding.put(17, new ArrayList<ArrayList<Double>>());
        colliding.put(18, new ArrayList<ArrayList<Double>>());
        update.invoke(scheduler, firstId, path(10, 30), colliding);
        update.invoke(scheduler, firstId, path(10.5, 30.5), colliding);
        require(colliding.get(17).size() == 1 && colliding.get(18).size() == 1,
            "same-ID negative control did not demonstrate replacement semantics");
        System.out.println("{\"status\":\"PASS\",\"live_execution_ids\":" + ids
            + ",\"shared_nodes\":[17,18],\"two_reservations_coexist\":true,\"update_isolated_by_execution_id\":true,"
            + "\"unmodified_other_execution_object_and_interval\":true,\"foreign_id_lookup_null\":true,"
            + "\"same_id_negative_control_replaces_prior_reservation\":true,\"collision_feasibility_tested\":false}");
    }
}
