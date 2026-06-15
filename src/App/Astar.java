package App;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;

public class Astar {
	//判断节点nextNode是否在openList中
	private static Node InOpen(ArrayList<Node> openList, Node nextNode) {
		for (Node n:openList) {
			if (n.getLocation()==nextNode.getLocation()) {
				return n;
			}
		}
		return null;
	}
	//从list中选择F值最小的节点
	private static Node findMinFNodeInOpenList(ArrayList<Node> list) {
		Collections.sort(list, new Comparator<Node>() {
            @Override
            public int compare(Node o1, Node o2) {
                return (int) (o1.getfCost() - o2.getfCost());
            }
        });
        Node highestprionode = list.get(0);
        return highestprionode;
	}
	//根据点找到所表示的弧
	private static Edge findEdge(int Star, int End,Map mapinfo) {
		for(Edge edge : mapinfo.E) {
			if(edge.Star==Star && edge.End==End) {
				return edge;
			}
		}
		return null;
	}
	//根据点编号找到该点通过时间
		@SuppressWarnings("null")
	private static double findTime(int i,Map mapinfo) {
			for(Vertex vertex : mapinfo.V) {
				if(vertex.location==i) {
					return vertex.t;
				}
			}
			return (Double) null;
		}
	//寻找路径
	public static ArrayList<Node> research(Node star, Node goal, Map map, 
				HashMap<Integer, ArrayList<ArrayList<Double>>> constrain_Set, ArrayList<Edge> fault_Edges) {
		//首先创建开始节点为star,目标节点为goal,创建开启列表openList列表,关闭列表closeList列表,创建关闭列表时初始化为空
		ArrayList<Node> openList = new ArrayList<>();
		ArrayList<Node> closeList = new ArrayList<>();
		ArrayList<Node>list=new ArrayList<Node>();
		//将开始节点star加入openList中
		star.t2=star.t1+findTime(star.getLocation(),map);
		openList.add(star);
		//openList为空时结束循环
		while (!openList.isEmpty()) {
			//从openList中选择F值最小的节点currNode
			Node currNode = findMinFNodeInOpenList(openList);
			//把节点currNode从openList中去除，并添加到closeList中
			openList.remove(currNode);
			closeList.add(currNode);
			//判断节点currNode是否是目标节点goal,如果节点currNode是目标节点goal,则退出,并说明找到最优路径
			if (currNode.getLocation()==goal.getLocation()) {
				//根据指向父节点的指针逐次返回，构成最优路径
				 while (currNode.getLocation()!=star.getLocation()) {
					list.add(currNode);
					currNode=currNode.parentNode;
				}
				 list.add(currNode);
				 break;
			}
			//节点currNode不是目标节点goal，生成节点currNode的子节点集
		loop:	for (int i : map.N.get(currNode.getLocation())) {
				if (Inclose(i,closeList)||(in_fault_edges(fault_Edges,currNode.getLocation(),i))) {
					continue;
				}
				Edge edge = findEdge(currNode.getLocation(), i, map);
				double t1=currNode.t2+edge.length/edge.v;
				double t2=t1+findTime(i,map);
				//判断是否满足冲突条件 若会发送冲突继续下一次循环
				if (constrain_Set.containsKey(i)&&i!=goal.location) {
					for (ArrayList<Double>constrain:constrain_Set.get(i)) {
						if (!(t1>constrain.get(2)||t2<constrain.get(1))) {
							continue loop;
						}
					}
				}
				Node node = new Node();
				node.setT1(t1);
				node.setT2(t2);
				node.setLocation(i);
				double gcost=t1;
				double hcost=map.hcost[i][goal.getLocation()];
				if (in_fault_edges(fault_Edges,currNode.getLocation(),i)) {
					gcost+=map.fault_threshold;
				}
				//如果子节点nextNode不在openList中，将其加入openList中，并为其分配一个指向其父节点currNode的指针
				Node n = InOpen(openList,node);
				if (n==null) {
					node.gcost=gcost;
					node.hcost=hcost;
					node.fcost=node.gcost+node.hcost;
					node.parentNode=currNode;
					openList.add(node);
				}else {
					//如果子节点nextNode在openList中，并且gcost新值比旧值小，将新值作为节点nextNode的代价值
					 if (gcost<n.gcost) {
					    n.gcost=gcost;
						n.hcost=hcost;
						n.fcost=n.gcost+n.hcost;
						n.parentNode=currNode;
					}
				}
			}
		}
		
		if (list.isEmpty()) {
			return list;
		}
		Collections.reverse(list);
		return list;
		}
	private static boolean in_fault_edges(ArrayList<Edge> arrayList, int star, int end) {
		if (arrayList==null) {
			return false;
		}
		for (Edge e: arrayList) {
			if (e.Star==star&&e.End==end) {
				return true;
			}
		}
		return false;
	}
	private static boolean Inclose(int i, ArrayList<Node> closeList) {
		for (Node j :closeList) {
			if (j.getLocation()==i) {
				return true;
			}
		}
		return false;
	}
}