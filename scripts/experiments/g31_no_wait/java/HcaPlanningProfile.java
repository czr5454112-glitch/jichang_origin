package App;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;

/** Observation only. Single-thread benchmark scopes overlap and MUST NOT be summed. */
public final class HcaPlanningProfile {
    private static final boolean ENABLED=Boolean.getBoolean("g31.hca.profile");
    private static final ThreadMXBean THREAD=ManagementFactory.getThreadMXBean();
    private static final boolean CPU_AVAILABLE=enableCpu();
    public static final int WINDOW=0,SEARCH=1,CONTROLLER=2,GENERATOR_IO=3,PRUNE=4,COMMIT=5;
    private static final String[] NAMES={"window","astar_search","controller_including_search_calendar_and_io","generator_including_epoch_file_write_read","calendar_prune","calendar_commit"};
    private static final long[][] COUNTS=new long[NAMES.length][3];
    private static long searchSuccess=0,searchFailure=0,searchExceptions=0;
    private static boolean enableCpu() {
        if(!ENABLED || !THREAD.isCurrentThreadCpuTimeSupported())return false;
        try { if(!THREAD.isThreadCpuTimeEnabled())THREAD.setThreadCpuTimeEnabled(true);return THREAD.isThreadCpuTimeEnabled(); }
        catch(SecurityException|UnsupportedOperationException ex) { return false; }
    }
    public static long[] begin() {
        if(!ENABLED)return null;
        return new long[]{System.nanoTime(),CPU_AVAILABLE?THREAD.getCurrentThreadCpuTime():-1};
    }
    public static void end(int stage,long[] start) {
        if(start==null)return;
        long cpu=CPU_AVAILABLE?THREAD.getCurrentThreadCpuTime():-1,wall=System.nanoTime();
        COUNTS[stage][0]++;COUNTS[stage][1]+=wall-start[0];
        if(cpu>=0 && start[1]>=0)COUNTS[stage][2]+=cpu-start[1];
    }
    public static void reset() {
        for(long[] row:COUNTS)java.util.Arrays.fill(row,0);
        searchSuccess=searchFailure=searchExceptions=0;
    }
    public static ArrayList<Node> search(Node source,Node goal,Map map,
            HashMap<Integer,ArrayList<ArrayList<Double>>> constraints,ArrayList<Edge> faults,PhysicalReservations ledger) {
        if(!ENABLED)return Astar.research(source,goal,map,constraints,faults,ledger);
        long[] start=begin();
        try {
            ArrayList<Node> result=Astar.research(source,goal,map,constraints,faults,ledger);
            if(result.isEmpty())searchFailure++;else searchSuccess++;
            return result;
        } catch(RuntimeException|Error ex) { searchExceptions++;throw ex; }
        finally { end(SEARCH,start); }
    }
    public static void prune(PhysicalReservations ledger,double epoch) {
        long[] start=begin();try { ledger.prune(epoch); } finally { end(PRUNE,start); }
    }
    public static void commit(PhysicalReservations ledger,ArrayList<Node> path) {
        long[] start=begin();try { ledger.commit(path); } finally { end(COMMIT,start); }
    }
    public static void controller(Tasks tasks,Map map,double epoch,ICS_PathFinding ics) throws IOException {
        long[] start=begin();try { ics.ICS_path_finding(tasks,map,epoch,ics); } finally { end(CONTROLLER,start); }
    }
    public static void write(String filename) throws IOException {
        if(!ENABLED)return;
        StringBuilder json=new StringBuilder("{\"schema\":\"g31.hca.planning_profile.v1\",\"enabled\":true,\"thread_cpu_available\":").append(CPU_AVAILABLE)
            .append(",\"thread_id\":").append(Thread.currentThread().getId())
            .append(",\"search_success\":").append(searchSuccess).append(",\"search_failure\":").append(searchFailure)
            .append(",\"search_exceptions\":").append(searchExceptions)
            .append(",\"scopes_overlap_do_not_sum\":true,\"cpu_scope\":\"Current planner thread total CPU; excludes other JVM/JIT/GC threads. Wall includes blocking and instrumentation overhead.\",\"scopes\":{");
        for(int i=0;i<NAMES.length;i++) {
            if(i>0)json.append(',');json.append('"').append(NAMES[i]).append("\":{\"calls\":").append(COUNTS[i][0])
                .append(",\"elapsed_ns\":").append(COUNTS[i][1]).append(",\"thread_cpu_ns\":").append(CPU_AVAILABLE?Long.toString(COUNTS[i][2]):"null").append('}');
        }
        json.append("}}\n");Files.writeString(Path.of(filename),json.toString(),StandardCharsets.UTF_8);
    }
}
