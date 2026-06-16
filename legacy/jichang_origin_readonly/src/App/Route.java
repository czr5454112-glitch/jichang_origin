package App;

import java.util.ArrayList;
import java.util.HashMap;

public class Route {
	HashMap<Integer, ArrayList<Node>> solution=new HashMap<Integer, ArrayList<Node>>();
	double cost;
	HashMap<Integer, ArrayList<ArrayList<Double>>> constrains=new HashMap<Integer, ArrayList<ArrayList<Double>>>();
	public void setcost(HashMap<Integer, ArrayList<Node>> solution) {
		double f=0;
		for (int k :solution.keySet()) {
			double t=solution.get(k).get(solution.get(k).size()-1).t2;
			if (t>f) {
				f=t;
			}
		}
		this.cost=f;
	}
	public double getCost() {
		return cost;
	}
	public void addAllsolution(HashMap<Integer, ArrayList<Node>> newsolution, HashMap<Integer, ArrayList<Node>> solution) {
		for (int key :solution.keySet()) {
			ArrayList<Node>list=new ArrayList<Node>();
			list.addAll(solution.get(key));
			newsolution.put(key,list);
		}	
	}
	public void addAllconstrain(HashMap<Integer, ArrayList<ArrayList<Double>>> newconstrains,
			HashMap<Integer, ArrayList<ArrayList<Double>>> constrains) {
		for (int k :constrains.keySet()) {
			ArrayList<ArrayList<Double>>newlList=new ArrayList<ArrayList<Double>>();
			for (ArrayList<Double>list:constrains.get(k)) {
				ArrayList<Double>list1=new ArrayList<Double>();
				list1.addAll(list);
				newlList.add(list1);
			}
			newconstrains.put(k,newlList);
		}
	}
}
