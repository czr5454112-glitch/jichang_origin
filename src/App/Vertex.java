package App;

import java.util.ArrayList;

public class Vertex {
	int location;//编号
	int type;//类型，装载点，缓冲点,1表示起点，0表示中间点，2表示终点，4分流点，5合流点
	double t;//通过时间
	int x;//坐标x
	int y;//坐标y;
	boolean cangenerated_task;
	ArrayList<Integer>list=new ArrayList<Integer>();//相邻点
	public int getLocation() {
		return location;
	}
	public void setLocation(int location) {
		this.location = location;
	}
	public int getType() {
		return type;
	}
	public void setType(int type) {
		this.type = type;
	}
	public double getT() {
		return t;
	}
	public void setT(double t) {
		this.t = t;
	}
	public ArrayList<Integer> getList() {
		return list;
	}
	public void setList(ArrayList<Integer> list) {
		this.list = list;
	}
	public int getX() {
		return x;
	}
	public void setX(int x) {
		this.x = x;
	}
	public int getY() {
		return y;
	}
	public void setY(int y) {
		this.y = y;
	}
	public boolean isCangenerated_task() {
		return cangenerated_task;
	}
	public void setCangenerated_task(boolean cangenerated_task) {
		this.cangenerated_task = cangenerated_task;
	}
}
