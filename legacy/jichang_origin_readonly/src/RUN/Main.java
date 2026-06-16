package RUN;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;

import javax.swing.JOptionPane;

import App.ICS_PathFinding;
import App.Tasks;
import App.Vertex;
import App.task;
import ICS_GUI.ICS_GUI;

public class Main {
	static HashMap<Integer, ArrayList<task>>Task_List = new HashMap<Integer, ArrayList<task>>(); 
	public static  void run() throws IOException {
		String mapdata = "map2.txt";//地图数据
		//String output = "output.txt";//输出路径
		boolean Flag = false;//程序结束标志
		ICS_PathFinding ics_pf = new ICS_PathFinding();
		ICS_GUI gui = ics_pf.getMap().getGui();
		gui.setICS(ics_pf);
		ics_pf.getMap().read(ics_pf.getMap(),mapdata);//读取地图
		
		
			
		//初始化任务集合
		for (Vertex i : ics_pf.getMap().getStar()) {
			ArrayList<task> tasks = new ArrayList<task>();
			Task_List.put(i.getLocation(), tasks);
		}
		
		String path = "inputdata.txt";//任务数据路径
		//读取任务数据
		double time = 4800;//早到时间
		ReadTaskList(path, Task_List, time);
				
		//将任务按开始时间从小到大进行排序
		for (int i : Task_List.keySet()) {
			Sort(Task_List.get(i));
		}
		//输出任务预计的开始时间
		//Write_Output_Starttime(Task_List);
		
		
		//显示地图
		gui.setMap(ics_pf.getMap());
		gui.showmap();
		double epoch = 8260;//仿真时长
		while (true) {
			synchronized(gui){
			if (gui.isReload()) {
				gui.setReload(false);
				run();
			}
			if (gui.gettime()!=0&&!gui.isPauseFlag()&&epoch <= gui.gettime()&&!gui.isFinished()) {
				//生成任务
				Tasks new_Tasks = new Tasks();
				new_Tasks.generate_tasks(Task_List, new_Tasks, epoch, ics_pf,gui.getFault_probability(),
						gui.getRepaired_probability(),gui.getDelay());
				//显示任务数据
				gui.setTask(new_Tasks);
				gui.setEpoch(epoch);
				//规划路径
				ics_pf.ICS_path_finding(new_Tasks,ics_pf.getMap(),epoch,ics_pf);
				gui.repaint();
				try {
					Thread.sleep((int) gui.getCycle());
				} catch (InterruptedException e) {
					e.printStackTrace();
				}
				//Write_Output_Data(output,ics_pf,epoch);
				epoch++;
			}else {
				if (gui.gettime()>0&&gui.gettime()-epoch<0.0001&&!Flag) {
					Flag=true;
		        	JOptionPane.showMessageDialog(null, "Finished!", "Information", JOptionPane.INFORMATION_MESSAGE);
				}
			}
		}
		}
   }

	private static void Sort(ArrayList<task> arrayList) {
		Collections.sort(arrayList,new Comparator<task>() {
			@Override
			public int compare(task o1, task o2) {
				return (int) (o1.getPass_time()-o2.getPass_time());
			}
		});
	}
	
	private static void ReadTaskList(String path, HashMap<Integer, ArrayList<task>> task_List, double time) throws IOException {
		BufferedReader reader = new BufferedReader(new FileReader(path));
		reader.readLine();
		String line = null;
		while((line = reader.readLine())!=null) {				
			task newtask= new task();
			String Order[] = line.split(" ");
			newtask.setTask_ID(Integer.valueOf(Order[0]));
			newtask.setPallet_ID(Integer.valueOf(Order[0]));
			newtask.setPass_time(Double.valueOf(Order[1]));
			newtask.setSTD(Double.valueOf(Order[2]));
			newtask.setStar(Integer.valueOf(Order[3]));
			
			if (newtask.getSTD()-newtask.getPass_time() < time) {
				newtask.setGoal(Integer.valueOf(Order[4]));
				task_List.get(newtask.getStar()).add(newtask);
			}else {
				//先到早到行李存储区
				newtask.setGoal(47);
				task_List.get(newtask.getStar()).add(newtask);
				//再从早到行李存储区装运去目的地
				task newtask1= new task();
				newtask1.setTask_ID(Integer.valueOf(Order[0]));
				newtask1.setPallet_ID(Integer.valueOf(Order[0]));
				newtask1.setSTD(Double.valueOf(Order[2]));
				double passtime = newtask1.getSTD()-2700;
				newtask1.setPass_time(passtime);
				newtask1.setStar(52);
				newtask1.setGoal(Integer.valueOf(Order[4]));
				task_List.get(newtask1.getStar()).add(newtask1);
			}
		}
		reader.close();
	
	}
	
	public static void main(String[] args) throws IOException {
		run();
	}
//	private static void Write_Output_Starttime(HashMap<Integer, ArrayList<task>> Task_List) throws IOException {
//		String outputstarttime = "outputstarttime.txt";
//		BufferedWriter bw = new BufferedWriter(new FileWriter(outputstarttime));
//		bw.write("task_ID   "+"loader   "+"unloader   "+"starTime   "+"endTime   ");
//		bw.newLine();
//		for(int i : Task_List.keySet()) {
//			ArrayList<task> Task = Task_List.get(i);
//			for(task task : Task) {
//				bw.write(task.getTask_ID()+"   "+ task.getStar()+"   "+task.getGoal()+"   "+task.getPass_time()+"   "+task.getSTD());
//				bw.newLine();
//			}
//		}
//		bw.close();
//	}
//	private static void Write_Output_Data(String answerPath, ICS_PathFinding ics_pf, double epoch) throws IOException {
//		BufferedWriter bw;
//		if (epoch-0<0.0001) {
//			bw = new BufferedWriter(new FileWriter(answerPath));
//		}else {
//			bw = new BufferedWriter(new FileWriter(answerPath,true));
//		}
//		bw.write("第 "+epoch+" 秒的输出为：");
//		bw.newLine();
//		bw.write("故障弧段有：");
//		bw.newLine();
//		if (ics_pf.getFault_edges().isEmpty()||ics_pf.getFault_edges()==null) {
//			bw.write("NULL");
//		}else {
//			for (Edge e: ics_pf.getFault_edges()) {
//				bw.write("( "+e.getStar()+" , "+e.getEnd()+" )  ");
//			}
//		}
//		bw.newLine();
//		bw.write("故障任务有：");
//		bw.newLine();
//		if (ics_pf.getFault_task_id_List().isEmpty()||ics_pf.getFault_task_id_List()==null) {
//			bw.write("NULL");
//		}else {
//			for (int t :ics_pf.getFault_task_id_List()) {
//				bw.write("任务编号： "+t+"  ,"+"故障任务下一节点为："+ics_pf.getFault_routes().get(t).get(0).getLocation()+".  ");
//			}
//		}
//		bw.newLine();
//		bw.write("路由列表：");
//		bw.newLine();
//		for (int i : ics_pf.getSaved_routes().keySet()) {
//			ArrayList<Node>path=ics_pf.getSaved_routes().get(i);
//			bw.write("任务编号为"+i+"的路由列表为： ");
//			for (int j = 0; j < path.size()-1; j++) {
//				bw.write(path.get(j).getLocation()+"->");
//			}
//			bw.write(path.get(path.size()-1).getLocation()+"");
//			bw.newLine();
//		}
//		bw.newLine();
//		bw.close();
//		
//	}
	
	
	
	
	
	
//	String arc = "arc.txt";//地图数据
//	BufferedReader arccc = new BufferedReader(new FileReader(arc));
//	int[][] arcc = new int[69][4];
//	for(int i=0;i<69;i++) {
//		String tempString = arccc.readLine();
//		String[] line = tempString.split(" ");
//		arcc[i][0]=Integer.valueOf(line[0]);//编号
//		arcc[i][1]=Integer.valueOf(line[1]);//弧起点
//		arcc[i][2]=Integer.valueOf(line[2]);//弧终点
//		arcc[i][3]=Integer.valueOf(line[3]);//弧长
//	}
//	arccc.close();
//	Map mappp = new Map();
//	mappp.read(mappp, mapdata);//读取地图
//	String outputstarttime = "output1111111.txt";
//	String outputarc = "output222222.txt";
//	for(int i=0;i<54;i++) {
//		for(int j=0;j<54;j++) {
//			if(i==j) {
//				continue;
//			}
//
//			Node star=new Node();Node end =new Node();
//			star.setLocation(i);end.setLocation(j);
//			star.setT1(0);
//			ArrayList<Node>path=Astar.research(star, end, mappp, null, null);
//			if (!path.isEmpty()) {
//				BufferedWriter bw1 = new BufferedWriter(new FileWriter(outputarc,true));
//				bw1.write(star.getLocation()+" "+end.getLocation()+"       ");
//				System.out.print(star.getLocation()+" "+end.getLocation()+"       ");
//				BufferedWriter bw = new BufferedWriter(new FileWriter(outputstarttime,true));
//				bw.write(star.getLocation()+" "+end.getLocation()+"       ");
//				//System.out.print(star.getLocation()+" "+end.getLocation()+"       ");
//				for(int num=0;num<path.size();num++) {
//					bw.write(path.get(num).getLocation()+" ");
//					//System.out.print(path.get(num).getLocation()+" ");
//				}
//				bw.write("=="+ mappp.getHcost()[star.getLocation()][end.getLocation()]);
//				//System.out.print("=="+mappp.getHcost()[star.getLocation()][end.getLocation()]);
//				//System.out.println();
//				bw.newLine();
//				bw.close();
//				
//				for(int num=0;num<path.size();num++) {
//					if(num==path.size()-1) {
//						continue;
//					}
//					for(int p=0;p<69;p++) {
//						if(arcc[p][1]==path.get(num).getLocation()&&arcc[p][2]==path.get(num+1).getLocation()) {
//							bw1.write(arcc[p][0]+" ");
//							System.out.print(arcc[p][0]+" ");
//							break;
//						}
//					}
//					bw1.newLine();
//				}
//				System.out.println();
//				bw1.close();
//			}
//		}
//	}
}
