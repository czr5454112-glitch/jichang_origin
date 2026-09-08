package App;
import java.util.ArrayList;
import java.util.HashMap;
public final class OriginalAstarTimestampProbe {
  private static void add(Map map,int a,int b,double travel) {
    Edge e=new Edge(); e.Star=a;e.End=b;e.length=travel;e.v=1.0; map.E.add(e); map.N.get(a).add(b);
  }
  public static void main(String[] args) {
    Map map=new Map(); map.D=5; map.hcost=new double[5][5];
    HashMap<Integer,ArrayList<ArrayList<Double>>> constraints=new HashMap<>();
    for(int i=0;i<5;i++){Vertex v=new Vertex();v.location=i;v.t=0.0;map.V.add(v);map.N.put(i,new ArrayList<Integer>());constraints.put(i,new ArrayList<ArrayList<Double>>());}
    add(map,0,1,1); add(map,0,2,2); add(map,1,3,10); add(map,2,3,1); add(map,3,4,1);
    Node start=new Node();start.location=0;start.t1=0;Node goal=new Node();goal.location=4;
    ArrayList<Node> route=Astar.research(start,goal,map,constraints,new ArrayList<Edge>());
    boolean mismatch=false;StringBuilder nodes=new StringBuilder(),times=new StringBuilder();
    for(int i=0;i<route.size();i++){Node n=route.get(i);if(i>0){nodes.append(',');times.append(',');Node p=route.get(i-1);for(Edge e:map.E)if(e.Star==p.location&&e.End==n.location){if(Math.abs(n.t1-(p.t2+e.length/e.v))>1e-9)mismatch=true;}}nodes.append(n.location);times.append(n.t1);}
    System.out.println("{\"status\":\""+(mismatch?"COUNTEREXAMPLE_CONFIRMED":"NOT_REPRODUCED")+"\",\"route\":["+nodes+"],\"arrival_times\":["+times+"],\"expected_no_wait_arrival_times\":[0.0,2.0,3.0,4.0],\"scope\":\"synthetic_five_node_original_class_only_not_campaign_incidence\"}");
    if(!mismatch)throw new IllegalStateException("expected original relaxation timestamp inconsistency");
  }
}
