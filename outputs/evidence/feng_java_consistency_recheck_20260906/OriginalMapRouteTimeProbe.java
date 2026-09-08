package App;
import java.util.ArrayList;
import java.util.HashMap;
public final class OriginalMapRouteTimeProbe {
 public static void main(String[] args)throws Exception {
  Map map=new Map();map.read(map,args[0]);Node s=new Node();s.location=Integer.parseInt(args[1]);s.t1=Double.parseDouble(args[3]);Node g=new Node();g.location=Integer.parseInt(args[2]);
  HashMap<Integer,ArrayList<ArrayList<Double>>> c=new HashMap<>();for(int i=0;i<map.D;i++)c.put(i,new ArrayList<ArrayList<Double>>());
  ArrayList<Node> r=Astar.research(s,g,map,c,new ArrayList<Edge>());int mismatches=0;
  System.out.print("{\"scope\":\"original_map_empty_reservations_probe_not_replay_of_congested_formal_cell\",\"nodes\":[");
  for(int i=0;i<r.size();i++){Node n=r.get(i);double expected=n.t1;if(i>0){Node p=r.get(i-1);for(Edge e:map.E)if(e.Star==p.location&&e.End==n.location)expected=p.t2+e.length/e.v;}if(Math.abs(expected-n.t1)>1e-7)mismatches++;if(i>0)System.out.print(',');System.out.print("{\"node\":"+n.location+",\"t1\":"+n.t1+",\"t2\":"+n.t2+",\"expected_t1_from_actual_parent_t2\":"+expected+"}");}
  System.out.println("],\"parent_time_mismatch_count\":"+mismatches+"}");
 }
}
