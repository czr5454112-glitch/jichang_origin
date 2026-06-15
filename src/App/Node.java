package App;
public class Node {
	int location;//编号
	double t1;//到达时间
	double t2;//离开时间
	double gcost;
	double hcost;
	double fcost;
	double cost;//成本
	Node parentNode= null;
	public int getLocation() {
		return location;
	}
	public void setLocation(int location) {
		this.location = location;
	}
	public double getT1() {
		return t1;
	}
	public void setT1(double t1) {
		this.t1 = t1;
	}
	public double getT2() {
		return t2;
	}
	public void setT2(double t2) {
		this.t2 = t2;
	}
	public double getCost() {
		return cost;
	}
	public void setCost(double cost) {
		this.cost = cost;
	}
	public Node getParentNode() {
		return parentNode;
	}
	public void setParentNode(Node parentNode) {
		this.parentNode = parentNode;
	}
	public double getfCost() {return fcost;}
	public void setfcost(double fcost) {
		this.fcost=fcost;
	}


}
