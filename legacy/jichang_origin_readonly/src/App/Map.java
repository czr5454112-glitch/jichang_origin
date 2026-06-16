package App;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;

import ICS_GUI.ICS_GUI;

public class Map {
	int D;//点的个数
	ArrayList<Vertex>V=new ArrayList<Vertex>();
	ArrayList<Vertex>star=new ArrayList<Vertex>();//起点集合
	ArrayList<Vertex>end=new ArrayList<Vertex>();//终点集合
	ArrayList<Edge>E=new ArrayList<Edge>();
	double AGV_length;
	double safe_length;
	double fault_threshold;
	double[][] hcost;
	ICS_GUI gui=new ICS_GUI();
	HashMap<Integer, ArrayList<Integer>> N=new HashMap<Integer, ArrayList<Integer>>();//邻接点信息
	int max_X=0;
	int max_Y=0;
	public void read(Map mapinfo, String map_path) throws IOException {
		BufferedReader reader = new BufferedReader(new FileReader(map_path));
		String tempString = reader.readLine();
		String [] line1 = tempString.split(" ");
		mapinfo.D=Integer.valueOf(line1[0]);
		mapinfo.AGV_length=Double.valueOf(line1[1]);
		mapinfo.safe_length=Double.valueOf(line1[2]);
		mapinfo.fault_threshold=Double.valueOf(line1[3]);
//		mapinfo.setFault_threshold(999);
		for(int j=0;j<D;j++) {
			tempString = reader.readLine();
			String[] line = tempString.split(" ");
			//读取地图点信息
			Vertex vertex = new Vertex();
			vertex.setLocation(Integer.valueOf(line[0]));
			vertex.setType(Integer.valueOf(line[1]));
			vertex.setT(Double.valueOf(line[2]));
			vertex.setY(Integer.valueOf(line[3]));
			vertex.setX(Integer.valueOf(line[4]));
			if (vertex.getX()>max_X) {
				max_X=vertex.getX();
			}
			if (vertex.getY()>max_Y) {
				max_Y=vertex.getY();
			}
			mapinfo.V.add(vertex);
			if (vertex.getType()==1) {
				vertex.setCangenerated_task(true);//默认产生任务，不用通过GUI得任务生成按钮进行设置
				star.add(vertex);
			}else if (vertex.getType() == 2) {
				end.add(vertex);
			}
			//添加邻接表
			ArrayList<Integer> list=new ArrayList<Integer>();
			for (int i=5;i<line.length;i++) {
	            list.add(Integer.valueOf(line[i]));
	        }
	        mapinfo.N.put(vertex.getLocation(), list);
		}
		hcost=new double[mapinfo.D][mapinfo.D];
		for (int i = 0; i < mapinfo.D; i++) {
			tempString = reader.readLine();
			String[] line = tempString.split(" ");
			for (int j = 0; j < line.length; j++) {
				hcost[i][j]=Double.valueOf(line[j])/2.5;
			}
		}
		while ((tempString = reader.readLine()) != null) {
			String[] line = tempString.split(" ");
			//读取地图弧信息
			Edge edge = new Edge();
			edge.setStar(Integer.valueOf(line[0]));
			edge.setEnd(Integer.valueOf(line[1]));
			edge.setLength(Double.valueOf(line[2]));
			edge.setV(2.5);
			mapinfo.E.add(edge);
		}
		reader.close();
	}
	public ICS_GUI getGui() {
		return gui;
	}
	public void setGui(ICS_GUI gui) {
		this.gui = gui;
	}
	public int getD() {
		return D;
	}
	public void setD(int d) {
		D = d;
	}
	public ArrayList<Vertex> getV() {
		return V;
	}
	public void setV(ArrayList<Vertex> v) {
		V = v;
	}
	public ArrayList<Edge> getE() {
		return E;
	}
	public void setE(ArrayList<Edge> e) {
		E = e;
	}
	public double getAGV_length() {
		return AGV_length;
	}
	public void setAGV_length(double aGV_length) {
		AGV_length = aGV_length;
	}
	public double getSafe_length() {
		return safe_length;
	}
	public void setSafe_length(double safe_length) {
		this.safe_length = safe_length;
	}
	public double getFault_threshold() {
		return fault_threshold;
	}
	public void setFault_threshold(double fault_threshold) {
		this.fault_threshold = fault_threshold;
	}
	public double[][] getHcost() {
		return hcost;
	}
	public void setHcost(double[][] hcost) {
		this.hcost = hcost;
	}
	public HashMap<Integer, ArrayList<Integer>> getN() {
		return N;
	}
	public void setN(HashMap<Integer, ArrayList<Integer>> n) {
		N = n;
	}
	public int getMax_X() {
		return max_X;
	}
	public void setMax_X(int max_X) {
		this.max_X = max_X;
	}
	public int getMax_Y() {
		return max_Y;
	}
	public void setMax_Y(int max_Y) {
		this.max_Y = max_Y;
	}
	public ArrayList<Vertex> getStar() {
		return star;
	}
	public void setStar(ArrayList<Vertex> star) {
		this.star = star;
	}
}
