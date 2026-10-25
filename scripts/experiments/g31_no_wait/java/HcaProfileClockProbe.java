package App;

import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

/** Small clock-resolution/empty-scope calibration; no transport simulation. */
public final class HcaProfileClockProbe {
    public static void main(String[] args) throws Exception {
        ThreadMXBean bean=ManagementFactory.getThreadMXBean();
        HcaPlanningProfile.begin();
        boolean available=bean.isCurrentThreadCpuTimeSupported() && bean.isThreadCpuTimeEnabled();
        for(int i=0;i<10000;i++) { long[] start=HcaPlanningProfile.begin();HcaPlanningProfile.end(HcaPlanningProfile.COMMIT,start); }
        HcaPlanningProfile.reset();
        long outerCpu=available?bean.getCurrentThreadCpuTime():-1,outerWall=System.nanoTime();
        for(int i=0;i<20000;i++) { long[] start=HcaPlanningProfile.begin();HcaPlanningProfile.end(HcaPlanningProfile.COMMIT,start); }
        long elapsed=System.nanoTime()-outerWall,cpu=available?bean.getCurrentThreadCpuTime()-outerCpu:-1;
        HcaPlanningProfile.write("empty_scope_profile.json");
        long minDelta=Long.MAX_VALUE,changes=0;
        if(available) {
            long prior=bean.getCurrentThreadCpuTime();
            for(int i=0;i<50000;i++) {
                long now=bean.getCurrentThreadCpuTime();
                if(now>prior) { minDelta=Math.min(minDelta,now-prior);changes++; }
                prior=now;
            }
        }
        System.out.println("{\"calls\":20000,\"warmup_calls\":10000,\"outer_elapsed_ns\":"+elapsed
            +",\"outer_thread_cpu_ns\":"+(available?Long.toString(cpu):"null")
            +",\"minimum_positive_observed_cpu_delta_ns\":"+(changes>0?Long.toString(minDelta):"null")
            +",\"positive_cpu_clock_changes\":"+changes+",\"cpu_available\":"+available+"}");
    }
}
