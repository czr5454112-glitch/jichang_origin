package App;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Random;

public class Tasks {
	int flag=0;//地图全局是否发生更改,默认值0表示未发生更改
	double cur_time;//当前时间
	ArrayList<Integer> onpath_task_ID=new ArrayList<Integer>();//任务编号集合
	ArrayList<task>Onpath_tasks_list=new ArrayList<task>();//正在进行的任务集合
	ArrayList<task>new_tasks_list=new ArrayList<task>();//新任务集合
	ArrayList<Edge>fault_edges= new ArrayList<Edge>();
	ArrayList<Edge>repaired_edges= new ArrayList<Edge>();
	public void read(Tasks taskinfo, String task_path, Map map) throws IOException {
		BufferedReader reader = new BufferedReader(new FileReader(task_path));
		String tempString = reader.readLine();
		String [] line1 = tempString.split(" ");
		taskinfo.flag=Integer.valueOf(line1[0]);
		taskinfo.cur_time=Double.valueOf(line1[1]);
		while ((tempString = reader.readLine()) != null) {
			String[] line2 = tempString.split(" ");
			//故障弧或者修好的弧，第一个数据为0表示是故障弧
			if (line2.length==3) {
				int a=Integer.valueOf(line2[0]);
				int b=Integer.valueOf(line2[1]);
				int c=Integer.valueOf(line2[2]);
				for (Edge e:map.E) {
					if (e.getStar()==b&&e.getEnd()==c) {
						if (a==0) {
							fault_edges.add(e);
						}else {
							repaired_edges.add(e);
						}
						break;
					}
				}
			}
			//若长度小于6，则为新任务数据
			else if (line2.length==4) {
				task new_Task=new task();
				new_Task.task_ID=Integer.valueOf(line2[0]);
				new_Task.pallet_ID=Integer.valueOf(line2[1]);
				new_Task.star=Integer.valueOf(line2[2]);
				new_Task.goal=Integer.valueOf(line2[3]);
				new_tasks_list.add(new_Task);
			}else {
				task ON_task=new task();
				ON_task.task_ID=Integer.valueOf(line2[0]);
				ON_task.pallet_ID=Integer.valueOf(line2[1]);
				ON_task.star=Integer.valueOf(line2[2]);
				ON_task.goal=Integer.valueOf(line2[3]);
				ON_task.passed_vertex_location=Integer.valueOf(line2[4]);
				ON_task.pass_vertex_location=Integer.valueOf(line2[5]);
				ON_task.pass_time=Double.valueOf(line2[6]);
				Onpath_tasks_list.add(ON_task);
				onpath_task_ID.add(ON_task.task_ID);
			}
		}
		reader.close();
	}
	public int getFlag() {
		return flag;
	}
	public void setFlag(int flag) {
		this.flag = flag;
	}
	public double getCur_time() {
		return cur_time;
	}
	public void setCur_time(double cur_time) {
		this.cur_time = cur_time;
	}
	public ArrayList<Integer> getOnpath_task_ID() {
		return onpath_task_ID;
	}
	public void setOnpath_task_ID(ArrayList<Integer> onpath_task_ID) {
		this.onpath_task_ID = onpath_task_ID;
	}
	public ArrayList<task> getOnpath_tasks_list() {
		return Onpath_tasks_list;
	}
	public void setOnpath_tasks_list(ArrayList<task> onpath_tasks_list) {
		Onpath_tasks_list = onpath_tasks_list;
	}
	public ArrayList<task> getNew_tasks_list() {
		return new_tasks_list;
	}
	public void setNew_tasks_list(ArrayList<task> new_tasks_list) {
		this.new_tasks_list = new_tasks_list;
	}
	public ArrayList<Edge> getFault_edges() {
		return fault_edges;
	}
	public void setFault_edges(ArrayList<Edge> fault_edges) {
		this.fault_edges = fault_edges;
	}
	public ArrayList<Edge> getRepaired_edges() {
		return repaired_edges;
	}
	public void setRepaired_edges(ArrayList<Edge> repaired_edges) {
		this.repaired_edges = repaired_edges;
	}
	public void generate_tasks(HashMap<Integer,ArrayList<task>> task_List, Tasks new_Tasks, double epoch, 
			ICS_PathFinding ics_pf, double fault, double repaire, double delay) throws IOException {
		String path = "task/"+epoch+".txt";//任务数据路径
		BufferedWriter bw= new BufferedWriter(new FileWriter(path));
		bw.write(0+" "+epoch);
		bw.newLine();
		if (epoch == 0) {
//			for (int i = 0; i < ics_pf.getMap().star.size(); i++) {
//				if (!ics_pf.getMap().star.get(i).cangenerated_task) {
//					continue;
//				}
//				Random random = new Random();
//				int end_index = random.nextInt(ics_pf.getMap().end.size());
//				bw.write(ics_pf.count+" "+ics_pf.count+" "+ics_pf.getMap().star.get(i).location+" "
//				+ics_pf.getMap().end.get(end_index).location);
//			    bw.newLine();
//			    ics_pf.count++;
//			}
		}else {
			//产生故障弧,故障率服从标准正太分布，若概率p<fault则认为有故障
			for (Edge edge : ics_pf.getMap().E) {
				if (!contain_edge(edge, ics_pf.getFault_edges())) {
					double p = Math.random();
					if (edge.isFault()||p<fault) {
						bw.write(0+ " "+edge.Star+" "+edge.End);
						bw.newLine();
					}
				}
			}
			//修好的弧
			ArrayList<Edge>repEdges = new ArrayList<Edge>();
			for (Edge edge : ics_pf.getFault_edges()) {
				double p = Math.random();
				if (!edge.isFault()||p<repaire) {
					bw.write(1+ " "+edge.Star+" "+edge.End);
					bw.newLine();
					repEdges.add(edge);
				}
			}
			
			//产生新任务
			for (int i = 0; i < ics_pf.getMap().star.size(); i++) {
				if (!contains(ics_pf.getUnfinishTasks(),ics_pf.getMap().star.get(i).getLocation())
						&&ics_pf.getMap().star.get(i).cangenerated_task) {
					if(task_List.get(ics_pf.getMap().star.get(i).getLocation()).isEmpty()) {
						continue;
					}
					task temptask = task_List.get(ics_pf.getMap().star.get(i).getLocation()).get(0);
					if(temptask.getPass_time() - epoch >= 1) {
						continue;
					}
					task_List.get(ics_pf.getMap().star.get(i).getLocation()).remove(0);
//					Random random = new Random();
//					int end_index = random.nextInt(ics_pf.getMap().end.size());
					ics_pf.count = temptask.getTask_ID();
					bw.write(ics_pf.count+" "+ics_pf.count+" "+ics_pf.getMap().star.get(i).getLocation()+" "
					+temptask.getGoal());
				    bw.newLine();
//				    ics_pf.count++;
				}
			}
			//产生正在进行的任务数据
			for (int taskid :ics_pf.getSaved_routes().keySet()) {
				//行李在当前时刻即将到达路径上的下一个节点时才有可能产生任务数据
				if (epoch>=ics_pf.getSaved_routes().get(taskid).get(1).getT1()) {
					//即将到终点
					if (ics_pf.getSaved_routes().get(taskid).size()==2) {
						bw.write(taskid+" "+taskid+" "+0+" "+ics_pf.getSaved_routes().get(taskid).get(1).getLocation()
								+" "+ics_pf.getSaved_routes().get(taskid).get(1).location+" "
								+ics_pf.getSaved_routes().get(taskid).get(1).location+" "+epoch);
						bw.newLine();
						continue;
					}
					
					//若延迟出现，则当前时刻不会收到任务数据
//					if (delay>0) {
//						double p = Math.random();
//						if (p*100<delay) {
//							continue;
//						}
//					}
					//产生任务数据，编号，类型，起点，终点，当前节点，下一节点，通过当前节点的时间
					bw.write(taskid+" "+taskid+" "+0+" "+ics_pf.getSaved_routes().get(taskid).get(ics_pf.getSaved_routes().get(taskid).size()-1).getLocation()
							+" "+ics_pf.getSaved_routes().get(taskid).get(1).location+" "+ics_pf.getSaved_routes().get(taskid).get(2).location
							+" "+ics_pf.getSaved_routes().get(taskid).get(1).getT1());
					bw.newLine();
				}
			}
		}
		bw.close();
		new_Tasks.read(new_Tasks, path, ics_pf.getMap());
	}
	private boolean contain_edge(Edge edge, ArrayList<Edge> fault_edges) {
		if (fault_edges.isEmpty()||fault_edges==null) {
			return false;
		}
		for (Edge edge2 : fault_edges) {
			if (edge2.Star==edge.Star&&edge2.End==edge.End) {
				return true;
			}
		}
		return false;
	}
	
	private boolean contains(ArrayList<task> unfinishTasks, int location) {
		for (task t : unfinishTasks ) {
			if (t.getStar() == location) {
				return true;
			}
		}
		return false;
	}
}
