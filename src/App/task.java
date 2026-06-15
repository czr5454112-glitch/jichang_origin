package App;

public class task{
	int task_ID;//任务编号
	int pallet_ID;//托盘编号
	int star;//任务起点
	int goal;//任务终点
	int passed_vertex_location;//最近通过的点编号
	int pass_vertex_location;//将要通过的点编号
	double pass_time;//到达该节点的时间
	private double STD;
	public int getTask_ID() {
		return task_ID;
	}
	public void setTask_ID(int task_ID) {
		this.task_ID = task_ID;
	}
	public int getPallet_ID() {
		return pallet_ID;
	}
	public void setPallet_ID(int pallet_ID) {
		this.pallet_ID = pallet_ID;
	}
	public int getStar() {
		return star;
	}
	public void setStar(int star) {
		this.star = star;
	}
	public int getGoal() {
		return goal;
	}
	public void setGoal(int goal) {
		this.goal = goal;
	}
	public int getPassed_vertex_location() {
		return passed_vertex_location;
	}
	public void setPassed_vertex_location(int passed_vertex_location) {
		this.passed_vertex_location = passed_vertex_location;
	}
	public int getPass_vertex_location() {
		return pass_vertex_location;
	}
	public void setPass_vertex_location(int pass_vertex_location) {
		this.pass_vertex_location = pass_vertex_location;
	}
	public double getPass_time() {
		return pass_time;
	}
	public void setPass_time(double pass_time) {
		this.pass_time = pass_time;
	}
	public double getSTD() {
		return STD;
	}
	public void setSTD(double sTD) {
		STD = sTD;
	}
}
