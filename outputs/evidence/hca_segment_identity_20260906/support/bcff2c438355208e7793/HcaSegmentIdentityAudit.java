import App.task;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;

/** Inspects the actual objects handed to unchanged HCA code, not only CSV labels. */
public final class HcaSegmentIdentityAudit {
    public static void main(String[] args) throws Exception {
        HashMap<Integer, ArrayList<task>> pending = new HashMap<>();
        pending.put(0, new ArrayList<task>());
        pending.put(2, new ArrayList<task>());
        ArrayList<Object> mapping = new ArrayList<>();
        Method read = HcaSegmentIdentityBenchmark.class.getDeclaredMethod("readTaskList", String.class,
            HashMap.class, Double.TYPE, Integer.TYPE, Integer.TYPE, Double.TYPE, ArrayList.class);
        read.setAccessible(true);
        read.invoke(null, args[0], pending, 5.0, 1, 2, 5.0, mapping);
        HashSet<Integer> ids = new HashSet<>();
        int count = 0;
        for (ArrayList<task> tasks : pending.values()) {
            for (task value : tasks) {
                if (!ids.add(value.getTask_ID())) throw new AssertionError("duplicate live execution ID");
                if (value.getTask_ID() != value.getPallet_ID()) throw new AssertionError("Task/Pallet identity mismatch");
                count++;
            }
        }
        if (count != mapping.size()) throw new AssertionError("mapping omitted a live task");
        ArrayList<Integer> sorted = new ArrayList<>(ids);
        Collections.sort(sorted);
        System.out.println("{\"status\":\"PASS\",\"task_object_count\":" + count
            + ",\"execution_ids\":" + sorted + ",\"task_and_pallet_identity_equal\":true}");
    }
}
