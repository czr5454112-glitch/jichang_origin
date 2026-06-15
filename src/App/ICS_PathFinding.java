package App;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Iterator;


public class ICS_PathFinding {
	private ArrayList<Edge> fault_edges = new ArrayList<Edge>();//故障弧
	private ArrayList<Integer>fault_task_id_List=new ArrayList<Integer>();//故障任务编号
	private Map map=new Map();//地图
	String output = "output.txt";
	String outputstarttime = "outputstarttime.txt";
	int count=0;
//	private String input_map_data="Map.txt";//地图数据文件默认路径
	private HashMap<Integer, ArrayList<Node>>saved_routes=new HashMap<Integer, ArrayList<Node>>();//路由列表
	private HashMap<Integer, ArrayList<Node>>fault_routes=new HashMap<Integer, ArrayList<Node>>();//故障任务路由列表
	private ArrayList<task>unfinishTasks=new ArrayList<task>();//未完成任务集合

	public void ICS_path_finding(Tasks tasks, Map map, double epoch, ICS_PathFinding ICS) throws IOException {
		//移除修好的弧
		for (Edge edge :tasks.getRepaired_edges()) {
			remove_edge(edge,ICS.getFault_edges());
		}
		
		//移除故障修复后的任务
        ArrayList<task>repairedTasks = new ArrayList<task>();
        for (int i = 0; i < tasks.getOnpath_tasks_list().size(); i++) {
			task tk = tasks.getOnpath_tasks_list().get(i);
			if (fault_task_id_List.contains(tk.task_ID)) {
				//如果不是直接经过了终点，则添加到repaired_tasks中等待处理
				if (tk.getPassed_vertex_location()!=tk.goal) {
					repairedTasks.add(tk);
				}
				tasks.getOnpath_tasks_list().remove(i);
				tasks.getOnpath_task_ID().remove(tk.task_ID);
				fault_task_id_List.remove(tk.task_ID);
				i--;
			}
		}
        
		//初始化约束集合
		HashMap<Integer, ArrayList<ArrayList<Double>>> constrains=new HashMap<Integer, ArrayList<ArrayList<Double>>>();
		for (int i = 0; i < map.D; i++) {
			ArrayList<ArrayList<Double>> c =new ArrayList<ArrayList<Double>>();
			constrains.put(i,c);
		}
		
		//更新路径及约束——静态方法
//		for (int i = 0; i < tasks.Onpath_tasks_list.size(); i++) {
//			task on_PathTask=tasks.Onpath_tasks_list.get(i);
//			//若行李已到达终点，则移除它，否则根据收到的数据更新路径和约束
//			if (on_PathTask.passed_vertex_location==on_PathTask.goal) {
//				Write_Output_Data(output,on_PathTask,epoch);
//				tasks.Onpath_tasks_list.remove(on_PathTask);
//				ICS.getSaved_routes().remove(on_PathTask.task_ID);
//				i--;
//			}else {
//				update_route_and_constrain(ICS.getSaved_routes().get(on_PathTask.task_ID),on_PathTask,constrains, ICS);
//			}
//		}
//		if (!ICS.getSaved_routes().isEmpty()) {
//			for (int key:ICS.getSaved_routes().keySet()) {
//				if (!tasks.onpath_task_ID.contains(key)) {
//					update_constrain(key, ICS.getSaved_routes().get(key), constrains);
//				}
//			}
//		}
		
		//更新路径及约束
		for (int i = 0; i < tasks.Onpath_tasks_list.size(); i++) {
			task on_PathTask=tasks.Onpath_tasks_list.get(i);
			//若行李已到达终点，则移除它，否则根据收到的数据更新路径和约束
			if (on_PathTask.passed_vertex_location==on_PathTask.goal) {
				Write_Output_Data(output,on_PathTask,epoch);
				tasks.Onpath_tasks_list.remove(on_PathTask);
				ICS.getSaved_routes().remove(on_PathTask.task_ID);
				i--;
			}else {
				//静态方法
				update_route_and_constrain(tasks.Onpath_tasks_list,ICS.getSaved_routes().get(on_PathTask.task_ID),on_PathTask,constrains, ICS);
				//动态方法
				//update_route_and_constrain_dynamic(ICS.getSaved_routes().get(on_PathTask.task_ID),on_PathTask,constrains, ICS);
			}
		}
		if (!ICS.getSaved_routes().isEmpty()) {
			for (int key:ICS.getSaved_routes().keySet()) {
				if (!tasks.onpath_task_ID.contains(key)) {
					update_constrain(key, ICS.getSaved_routes().get(key), constrains);
				}
			}
		}
		
		
		//故障处理
		if (!tasks.fault_edges.isEmpty()) {
			AddAll(ICS.getFault_edges(),tasks.fault_edges);//添加故障弧
			Handling_faults(tasks.fault_edges,ICS.getFault_task_id_List(),tasks.getCur_time(),
					ICS.getSaved_routes(),map,ICS.getFault_edges(),constrains,ICS.getFault_routes());
		}
		
		//处理故障修复后的任务
		if (!repairedTasks.isEmpty()) {
			ArrayList<Edge>new_faultEdges = new ArrayList<Edge>();
			for (task tk : repairedTasks) {
				if (in_fault_edge(ICS.getFault_edges(), tk.passed_vertex_location, tk.pass_vertex_location)) {
					fault_routes.get(tk.getTask_ID()).remove(0);
					fault_task_id_List.add(tk.getTask_ID());
					continue;
				}
				Node star=new Node();Node end =new Node();
				star.setLocation(tk.passed_vertex_location);end.setLocation(tk.getGoal());
			    star.setT1(tk.pass_time);
				ArrayList<Node>new_path=Astar.research(star, end, map, constrains, ICS.getFault_edges());
				if (!new_path.isEmpty()) {
					ICS.getSaved_routes().put(tk.task_ID, new_path);
					fault_routes.remove(tk.getTask_ID());
					update_constrain(tk.getTask_ID(), new_path, constrains);
				}else {
					new_faultEdges.add(findEdge(star.location, tk.pass_vertex_location, map));
					fault_routes.get(tk.getTask_ID()).remove(0);
					fault_task_id_List.add(tk.getTask_ID());
				}
			}
			if (!new_faultEdges.isEmpty()) {
				AddAll(ICS.getFault_edges(),new_faultEdges);//添加故障弧
				Handling_faults(new_faultEdges,ICS.getFault_task_id_List(),tasks.getCur_time(),ICS.getSaved_routes(),
					       map,ICS.getFault_edges(),constrains,ICS.getFault_routes());
			}
		}
		
		//处理未完成任务及新到任务
		ICS.getUnfinishTasks().addAll(tasks.new_tasks_list);
		int numbers=ICS.getUnfinishTasks().size();
		while (numbers!=0) {
			numbers--;
			task curTask=ICS.getUnfinishTasks().remove(0);
			Node star=new Node();Node end =new Node();
			star.setLocation(curTask.star);end.setLocation(curTask.goal);
			star.setT1(tasks.cur_time);
			ArrayList<Node>path=Astar.research(star, end, map, constrains, ICS.getFault_edges());
			if (path.isEmpty()) {
				ICS.getUnfinishTasks().add(curTask);
			}else {
				ICS.getSaved_routes().put(curTask.task_ID, path);
				update_constrain(curTask.task_ID,path,constrains);
				BufferedWriter bw = new BufferedWriter(new FileWriter(outputstarttime,true));
				bw.write(curTask.task_ID+"   "+curTask.star+"  "+curTask.getPass_time()+"  "+epoch);
				bw.newLine();
				bw.close();
			}
		}
	}
	
	private void update_route_and_constrain(ArrayList<task> tasks,ArrayList<Node> Route, task on_PathTask, 
			HashMap<Integer, ArrayList<ArrayList<Double>>> constrains, ICS_PathFinding ICS) {
		for (int i = 0; i < Route.size(); i++) {
			if (Route.get(i).getLocation()!=on_PathTask.passed_vertex_location) {
				Route.remove(i);
				i--;
			}else {
				break;
			}
		}
	    //double bias_time=on_PathTask.pass_time-Route.get(0).getT1();//时间偏差
	    //double bias_time = 3 * Math.random();
		double bias_time = 0;
		//更新预估时间及约束
	    if (bias_time>0.1) {
	    		while (hasconflict(constrains.get(Route.get(0).getLocation()),constrains.get(Route.get(1).getLocation()),
	    				bias_time,Route.get(0),Route.get(1))) {
				bias_time+=2;
				for(task task1 : tasks) {
	    				if(task1.pass_vertex_location == on_PathTask.pass_vertex_location 
	    					&& task1.passed_vertex_location == on_PathTask.passed_vertex_location) {
	    					for(int i = 0; i < ICS.getSaved_routes().get(task1.task_ID).size(); i++) {
	    						Node n = ICS.getSaved_routes().get(task1.task_ID).get(i);
	    						n.t1 += bias_time;
	    						n.t2 += bias_time;
	    					}
	    				}
	    			}
			}
	    		
	    		for (int i = 0; i < Route.size(); i++) {
				Node n = Route.get(i);
				n.t1+=bias_time;
				n.t2+=bias_time;
			}
	    }
	    update_constrain(on_PathTask.task_ID, Route, constrains);
	}

	private void update_route_and_constrain_dynamic(ArrayList<Node> Route, task on_PathTask,
			HashMap<Integer, ArrayList<ArrayList<Double>>> constrains, ICS_PathFinding iCS) {
		for (int i = 0; i < Route.size(); i++) {
			if (Route.get(i).getLocation()!=on_PathTask.passed_vertex_location) {
				Route.remove(i);
				i--;
			}else {
				break;
			}
		}
	    //double bias_time=on_PathTask.pass_time-Route.get(0).getT1();//时间偏差
	    double bias_time = 3 * Math.random();
	    //更新预估时间及约束,
    	//若当前误差没有导致接下来的两个节点上的冲突，则无需更换路径，只需更改相应的通过时间即可；否则需要立刻重新规划路径
	    for (int i = 0; i < Route.size(); i++) {
			Node n = Route.get(i);
			n.t1+=bias_time;
			n.t2+=bias_time;
		}
	}
//    	if(!hasconflict(constrains.get(Route.get(0).getLocation()),constrains.get(Route.get(1).getLocation()),
//    			bias_time,Route.get(0),Route.get(1))) {
//    		for (int i = 0; i < Route.size(); i++) {
//				Node n = Route.get(i);
//				n.t1+=bias_time;
//				n.t2+=bias_time;
//			}
//    		update_constrain(on_PathTask.task_ID, Route, constrains);
//    	}else {
//			//重新规划路径
//    			Node star=new Node();Node end =new Node();
//			star.setLocation(on_PathTask.passed_vertex_location);end.setLocation(on_PathTask.goal);
//			boolean flag=true;double time=on_PathTask.pass_time;
////			while (flag) {
//				star.setT1(time);
//				ArrayList<Node>path=Astar.research(star, end, map, constrains, iCS.getFault_edges());
//				if (path.isEmpty()) {
//					for (int i = 0; i < Route.size(); i++) {
//						Node n = Route.get(i);
//						n.t1+=bias_time;
//						n.t2+=bias_time;
//					}
//		    			update_constrain(on_PathTask.task_ID, Route, constrains);
//					flag=false;
//				}else {
//					flag=false;
//					iCS.getSaved_routes().put(on_PathTask.task_ID, path);
//					update_constrain(on_PathTask.task_ID, path, constrains);
//				}
//			}
////		}
//	}

	private boolean hasconflict(ArrayList<ArrayList<Double>> curNode, ArrayList<ArrayList<Double>> nextNode,
			double bias_time, Node cnode, Node nnode) {
		for (ArrayList<Double>constrain:curNode) {
			if (!(bias_time+cnode.t1>constrain.get(2)||cnode.t2+bias_time<constrain.get(1))) {
				return true;
			}
		}
		for (ArrayList<Double>constrain:nextNode) {
			if (!(bias_time+nnode.t1>constrain.get(2)||nnode.t2+bias_time<constrain.get(1))) {
				return true;
			}
		}
		return false;
	}

	private void AddAll(ArrayList<Edge> fault_edges, ArrayList<Edge> task_fault_edges) {
		for (Edge edge : task_fault_edges) {
			if (!Contain_Edge(edge, fault_edges)) {
				fault_edges.add(edge);
			}
		}
	}

	private boolean Contain_Edge(Edge edge, ArrayList<Edge> fault_edges) {
		for (Edge e : fault_edges) {
			if (e.Star==edge.Star&&e.End==edge.End) {
				return true;
			}
		}
		return false;
	}

	private void remove_edge(Edge edge, ArrayList<Edge> arrayList) {
		Iterator<Edge> iterator=arrayList.iterator();
		while (iterator.hasNext()) {
			Edge e = iterator.next();
			if (e.Star==edge.Star&&e.End==edge.End) {
				iterator.remove();
			}
		}
	}

	private void update_constrain(int task_ID, ArrayList<Node> path,
			HashMap<Integer, ArrayList<ArrayList<Double>>> constrains) {
		for (Node n: path) {
				ArrayList<Double>constrain=new ArrayList<Double>();
				constrain.add((double)task_ID);
				constrain.add(n.t1);
				constrain.add(n.t2);
				ArrayList<Double>c=Contains(constrain,constrains.get(n.getLocation()));
				if (c!=null) {
					constrains.get(n.getLocation()).remove(c);
				}
				constrains.get(n.getLocation()).add(constrain);
			}
		}
		
	private ArrayList<Double> Contains(ArrayList<Double> constrain, ArrayList<ArrayList<Double>> arrayList) {
		for (ArrayList<Double>a:arrayList) {
			if (a.get(0).intValue()==constrain.get(0).intValue()) {
				return a;
			}
		}
		return null;
	}

	private void Handling_faults(ArrayList<Edge> E1, ArrayList<Integer> Fault_task_id_List, double startime, 
			            HashMap<Integer, ArrayList<Node>> saved_routes, Map map, ArrayList<Edge> Fault_edges, 
			            HashMap<Integer, ArrayList<ArrayList<Double>>> constrains, HashMap<Integer, ArrayList<Node>> fault_routes) {
		//在save_routes正在进行的任务集合中,找出经过故障弧段的任务加入到tempfaulTasks，之后再给tempfaulTasks中的任务重新规划路径
		//正处在故障弧段的任务直接加入F2 并保留原路径到fault_routes
		ArrayList<task>tempfaulTasks = new ArrayList<task>();
		ArrayList<Integer>need_removeList = new ArrayList<Integer>();
	loop:	for (int onpath_taskid : saved_routes.keySet()) {
			ArrayList<Node>path_List=saved_routes.get(onpath_taskid);
			if (in_fault_edge(E1,path_List.get(0).getLocation(),path_List.get(1).getLocation())) {
				Fault_task_id_List.add(onpath_taskid);
				fault_routes.put(onpath_taskid, path_List);
				need_removeList.add(onpath_taskid);
				RemoveConstrain(onpath_taskid,constrains);
				continue loop;
			}else {
				if (path_List.size()==2) {
					continue loop;
				}
				for (int i = 1; i < path_List.size()-1; i++) {
					if (in_fault_edge(E1, path_List.get(i).location, path_List.get(i+1).location)) {
						double time=path_List.get(i).t1;
						if (time - startime < map.fault_threshold) {
							for (int j = i; j >= 1; j--) {
								if (find_vertex(path_List.get(j).location, map.getV()).getType()==4) {
									time = path_List.get(j).getT1();
									break;
								}
							}
							task t = new task();
							t.setTask_ID(onpath_taskid);
							t.setPass_time(time);
							tempfaulTasks.add(t);
							continue loop;	
						}
					}
				}
			}
		}
		
		//从save_routes移除任务
		for (int i = 0; i < need_removeList.size(); i++) {
			saved_routes.remove(need_removeList.get(i));
		}
		
		//对tempfaulTasks中剩余的任务重新规划路径
		if (!tempfaulTasks.isEmpty()) {
			Collections.sort(tempfaulTasks,new Comparator<task>() {
				@Override
				public int compare(task o1, task o2) {
					return (int) (o1.pass_time-o2.pass_time);
				}
			});
			ArrayList<Edge>E2=new ArrayList<Edge>();//故障弧段集合
			for (int i = 0; i < tempfaulTasks.size(); i++) {
				int temptask_id = tempfaulTasks.get(i).getTask_ID();
				Node starNode = saved_routes.get(temptask_id).get(1);
				Node endNode =  saved_routes.get(temptask_id).get(saved_routes.get(temptask_id).size()-1);
				ArrayList<Node>path=Astar.research(starNode, endNode, map, constrains,E1);
				if (path.isEmpty()) {
					Edge faultEdge = findEdge(saved_routes.get(temptask_id).get(0).location, starNode.location, map);
					if (!Contain_Edge(faultEdge, E2)) {
						E2.add(faultEdge);
					}
					Fault_task_id_List.add(temptask_id);
					fault_routes.put(temptask_id, saved_routes.get(temptask_id));
					saved_routes.remove(temptask_id);
					RemoveConstrain(temptask_id, constrains);
				}else {
					//更新路由及约束
					saved_routes.put(temptask_id,path);
					update_constrain(temptask_id, path, constrains);
				}
			}
			if (!E2.isEmpty()) {
				AddAll(Fault_edges,E2);
				Handling_faults(E2, Fault_task_id_List, startime, saved_routes, map, Fault_edges, constrains,fault_routes);
			}
		}
	}

	private void RemoveConstrain(int task_ID, HashMap<Integer, ArrayList<ArrayList<Double>>> constrains) {
		for (int i : constrains.keySet()) {
			ArrayList<ArrayList<Double>>c = constrains.get(i);
			for (int j = c.size()-1; j > -1; j--) {
				if (c.get(j).get(0).intValue()==task_ID) {
					c.remove(c.get(j));
				}
			}
		}
	}

	private Vertex find_vertex(int star, ArrayList<Vertex> v2) {
		for (Vertex v:v2) {
			if (v.location==star) {
				return v;
			}
		}
		return null;
	}

	private boolean in_fault_edge(ArrayList<Edge> e1, int star, int end) {
		for (Edge e:e1) {
			if (e.Star==star&&e.End==end) {
				return true;
			}
		}
		return false;
	}

	private Edge findEdge(int star, int end, Map map2) {
		for(Edge edge : map2.E) {
			if(edge.Star==star && edge.End==end) {
				return edge;
			}
		}
		return null;
	}

	public  ArrayList<task> getUnfinishTasks() {
		return unfinishTasks;
	}

	public void setUnfinishTasks(ArrayList<task> unfinishTasks) {
		this.unfinishTasks = unfinishTasks;
	}

	public ArrayList<Edge> getFault_edges() {
		return fault_edges;
	}

	public void setFault_edges(ArrayList<Edge> fault_edges) {
		this.fault_edges = fault_edges;
	}

	public  Map getMap() {
		return map;
	}

	public void setMap(Map map) {
		this.map = map;
	}

	public ArrayList<Integer> getFault_task_id_List() {
		return fault_task_id_List;
	}

	public void setFault_task_id_List(ArrayList<Integer> fault_task_id_List) {
		this.fault_task_id_List = fault_task_id_List;
	}

	public HashMap<Integer, ArrayList<Node>> getFault_routes() {
		return fault_routes;
	}

	public void setFault_routes(HashMap<Integer, ArrayList<Node>> fault_routes) {
		this.fault_routes = fault_routes;
	}

	public HashMap<Integer, ArrayList<Node>> getSaved_routes() {
		return saved_routes;
	}

	public void setSaved_routes(HashMap<Integer, ArrayList<Node>> saved_routes) {
		this.saved_routes = saved_routes;
	}
	private static void Write_Output_Data(String answerPath, task on_PathTask, double epoch) throws IOException {
		BufferedWriter bw;
		bw = new BufferedWriter(new FileWriter(answerPath,true));
		bw.write(on_PathTask.task_ID +"  "+epoch);
		bw.newLine();
		bw.close();
	}
}
