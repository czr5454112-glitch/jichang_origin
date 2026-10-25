package App;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;

/** Native contract regressions for the explicitly adapted physical HCA. */
public final class HcaUniformProbe {
    private static int checks=0;
    private static void require(boolean ok,String message) { checks++;if(!ok)throw new AssertionError(message); }
    private static Node node(int id,double arrival,double departure) {
        Node n=new Node();n.setLocation(id);n.setT1(arrival);n.setT2(departure);return n;
    }
    private static Map map(double... service) {
        Map m=new Map();m.setD(service.length);m.setHcost(new double[service.length][service.length]);
        for(int i=0;i<service.length;i++) {
            Vertex v=new Vertex();v.setLocation(i);v.setType(4);v.setT(service[i]);m.getV().add(v);
            m.getN().put(i,new ArrayList<Integer>());
        }
        return m;
    }
    private static void edge(Map m,int u,int v,double seconds) {
        Edge e=new Edge();e.setStar(u);e.setEnd(v);e.setLength(seconds);e.setV(1);
        m.getE().add(e);m.getN().get(u).add(v);
    }
    private static ArrayList<Node> route(Map m,int source,int goal,double now,PhysicalReservations ledger) {
        return Astar.research(node(source,now,now),node(goal,0,0),m,new HashMap<Integer,ArrayList<ArrayList<Double>>>(),new ArrayList<Edge>(),ledger);
    }
    private static task task(int id,int source,int goal) {
        task t=new task();t.setTask_ID(id);t.setStar(source);t.setGoal(goal);return t;
    }
    private static Tasks tick(double epoch) { Tasks t=new Tasks();t.setCur_time(epoch);return t; }
    private static void complete(Tasks tick,int id,int source,int goal) {
        task t=task(id,source,goal);t.setPassed_vertex_location(goal);t.setPass_vertex_location(goal);t.setPass_time(tick.getCur_time());
        tick.getOnpath_tasks_list().add(t);tick.getOnpath_task_ID().add(id);
    }
    public static void main(String[] args) throws Exception {
        PhysicalReservations ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(1,10,12)));
        require(ledger.nodeFree(1,12,14),"exact two-second headway is accepted");
        require(ledger.nodeFree(1,8,10),"half-open touching before is accepted");
        require(!ledger.nodeFree(1,11.999999,13.999999),"one microsecond short is rejected");
        require(!ledger.nodeFree(1,11.999,13.999),"1.999-second headway is rejected");
        require(ledger.nodeFree(1,11,11),"zero service is empty even inside a busy interval");
        require(PhysicalReservations.ticks(PhysicalReservations.add(1.1,0.2))==1300000,"integer duration sum");

        ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(0,0,0),node(1,.1,.1)));
        require(!ledger.edgeFree(0,1,1.999999),"edge entry one microsecond short rejected");
        require(ledger.edgeFree(0,1,2),"edge entry exact two accepted");
        require(ledger.edgeFree(1,0,0),"directed reverse edge is independent");
        require(ledger.nodeFree(0,0,100),"zero source creates no node interval");
        ledger.prune(1);require(!ledger.edgeFree(0,1,1),"short edge entrance window survives arrival and cleanup");
        ledger.prune(2);require(ledger.edgeFree(0,1,2),"entry interval expires at its end");
        ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(0,0,0),node(1,100,100)));
        require(ledger.edgeFree(0,1,2),"long edge permits pipelining; entire edge is not exclusive");

        ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(9,20,22)));
        boolean rejected=false;try { ledger.commit(Arrays.asList(node(8,0,2),node(9,20,22))); } catch(IllegalStateException e) { rejected=true; }
        require(rejected,"invalid multi-resource commit rejected");require(ledger.nodeFree(8,0,2),"failed commit has no partial reservation");
        Map m=map(2,2);edge(m,0,1,1);
        ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(0,0,2)));
        require(route(m,0,1,0,ledger).isEmpty(),"positive initial source conflict checked");
        require(route(m,0,1,2,ledger).size()==2,"positive initial source touching boundary accepted");
        ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(1,3,5)));
        require(route(m,0,1,0,ledger).isEmpty(),"positive task goal conflict checked");
        require(route(m,0,1,2,ledger).size()==2,"goal touching boundary accepted");
        m=map(0,0);edge(m,0,1,.1);ledger=new PhysicalReservations();ledger.commit(Arrays.asList(node(0,0,0),node(1,.1,.1)));
        require(route(m,0,1,1,ledger).isEmpty(),"zero endpoints still enforce edge entry gap");
        require(route(m,0,1,2,ledger).size()==2,"zero endpoints and exact edge gap accepted");

        // Same business ID must not exempt its outbound from inbound's surviving goal reservation.
        m=map(2,2,2);edge(m,0,1,.8);edge(m,1,2,1);
        ICS_PathFinding ics=new ICS_PathFinding();ics.setMap(m);Tasks t=tick(0);t.getNew_tasks_list().add(task(10,0,1));
        ics.ICS_path_finding(t,m,0,ics);require(ics.getSaved_routes().containsKey(10),"first inbound planned");
        t=tick(3);complete(t,10,0,1);t.getNew_tasks_list().add(task(10,1,2));ics.ICS_path_finding(t,m,3,ics);
        require(!ics.getSaved_routes().containsKey(10),"goal business completion removes route but outbound cannot overlap its resource");
        require(ics.getUnfinishTasks().size()==1,"outbound waits only outside network");
        require(!ics.getPhysicalReservations().nodeFree(1,4.799999,6.799999),"goal future resource survives observed finish");
        require(ics.getPhysicalReservations().nodeFree(1,4.8,6.8),"goal releases exactly at planned departure");
        t=tick(4);ics.ICS_path_finding(t,m,4,ics);require(!ics.getSaved_routes().containsKey(10),"same-ID retry remains blocked");
        t=tick(5);ics.ICS_path_finding(t,m,5,ics);require(ics.getSaved_routes().get(10).get(0).getT1()==5,"outbound admits when source interval is free");

        m=map(0,0);edge(m,0,1,.1);ics=new ICS_PathFinding();ics.setMap(m);t=tick(0);t.getNew_tasks_list().add(task(20,0,1));ics.ICS_path_finding(t,m,0,ics);
        t=tick(1);complete(t,20,0,1);t.getNew_tasks_list().add(task(21,0,1));ics.ICS_path_finding(t,m,1,ics);
        require(!ics.getSaved_routes().containsKey(21),"completed short-edge task still protects its edge entry window");
        t=tick(2);ics.ICS_path_finding(t,m,2,ics);require(ics.getSaved_routes().containsKey(21),"short-edge next bag enters at exact two seconds");
        System.out.println("{\"pass\":true,\"assertions\":"+checks+",\"time_grid_seconds\":0.000001,\"source_goal_strict\":true,\"same_business_id_no_exemption\":true,\"short_edge_persistent\":true}");
    }
}
