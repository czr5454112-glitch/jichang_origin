package ICS_GUI;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Cursor;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.Image;
import java.awt.Stroke;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.util.ArrayList;

import javax.swing.BorderFactory;
import javax.swing.ImageIcon;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JTextField;

import App.Edge;
import App.ICS_PathFinding;
import App.Map;
import App.Node;
import App.Tasks;
import App.Vertex;
import App.task;

public class ICS_GUI extends JPanel{
	private static final long serialVersionUID = 1L;
	private JFrame frame;
	private int jframe_height;//窗口高度
	private int jframe_width;//窗口宽度
	private int rate_x;//横轴缩放系数
	private int rate_y;//纵轴缩放系数
	private int rate;//缩放系数
	int finished_ALLtask=0;
	private double cycle = 200;//刷新频率
	private double delay = 0;//延迟率
	private double time = 0;//时间
	private double fault_probability = 0.000;//当前时间
	private double repaired_probability = 0;//当前时间
	private double epoch = 8260;//当前时间
	//private double epoch = 20000;//当前时间
	private boolean pauseFlag = true;//GUI暂停标志
	private boolean finished = false;//仿真完成标志
	private boolean setTask = true;//任务生成标志
	private boolean setFault = false;//故障生成标志
	private boolean Pathview = false;//路径显示标志
	private boolean reload = false;//重置标志
	private JLabel cycleLabel = new JLabel();
	private JLabel TimeLabel = new JLabel();
//	private JLabel Total_taskLabel = new JLabel();
//	private JLabel finished_taskLabel = new JLabel();
//	private JLabel fault_taskLabel = new JLabel();
	private Map map;
	private Tasks tasks = new Tasks();
	private ICS_PathFinding ICS;
	private int leftspace=15;
	private int upspace=60;

	public JFrame getFrame() {
		return frame;
	}

	public void setFrame(JFrame frame) {
		this.frame = frame;
	}

	public int getJframe_height() {
		return jframe_height;
	}

	public void setJframe_height(int jframe_height) {
		this.jframe_height = jframe_height;
	}

	public int getJframe_width() {
		return jframe_width;
	}

	public void setJframe_width(int jframe_width) {
		this.jframe_width = jframe_width;
	}

	public Map getMap() {
		return map;
	}

	public void setMap(Map map) {
		this.map = map;
	}
	
	public void showmap() {
		frame = new JFrame("ICS_PathFinding Simulation");
		frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
		frame.getContentPane().setLayout(null);
		frame.setSize(1400,800);
		frame.setLocationRelativeTo(null);
		frame.setResizable(false);
		this.setLocation(0, 0);
		this.setSize(frame.getWidth()*82/100,frame.getHeight());
		this.setLayout(null);
		
		//添加控制面板
		JPanel controlPanel = new JPanel();
		controlPanel.setLocation(this.getWidth(), 0);
		controlPanel.setSize(frame.getWidth()-this.getWidth(),800);
		controlPanel.setLayout(null);
		controlPanel.setBackground(Color.WHITE);
		// 左上角显示刷新频率
		cycleLabel.setLocation(10, 0);
		cycleLabel.setSize(controlPanel.getWidth()/2,30);
		cycleLabel.setHorizontalAlignment(JTextField.LEFT);
		controlPanel.add(cycleLabel);
		// 右上角显示当前时间
		TimeLabel.setLocation(controlPanel.getWidth()/2-25,0);
		TimeLabel.setSize(controlPanel.getWidth()/2,30);
		TimeLabel.setHorizontalAlignment(JTextField.RIGHT);
		controlPanel.add(TimeLabel);
		
		//添加图片
		JLabel AD = new JLabel();
		AD.setLocation(40, 30);
		ImageIcon AD_image = new ImageIcon("images/AD.jpg");
		Image img_AD = AD_image.getImage();
		img_AD = img_AD.getScaledInstance(120, 150, Image.SCALE_DEFAULT);
		AD_image.setImage(img_AD);
		AD.setIcon(AD_image);
		AD.setSize(AD_image.getIconWidth(),AD_image.getIconHeight());
		AD.setHorizontalAlignment(JTextField.LEFT);
		controlPanel.add(AD);
		//添加图例图片
		JLabel legend = new JLabel();
		legend.setLocation(0, 565);
		ImageIcon legend_image = new ImageIcon("images/legend.jpg");
		Image img1 = legend_image.getImage();
		img1 = img1.getScaledInstance(150, 200, Image.SCALE_DEFAULT);
		legend_image.setImage(img1);
		legend.setIcon(legend_image);
		legend.setSize(legend_image.getIconWidth(),legend_image.getIconHeight());
		legend.setHorizontalAlignment(JTextField.LEFT);
		controlPanel.add(legend);
		
		//开始暂停按钮
		JButton star_or_pause_Button = new JButton("开       始");
		star_or_pause_Button.setLocation(28, 200);
		star_or_pause_Button.setSize(150, 30);
		star_or_pause_Button.setBorder(BorderFactory.createRaisedBevelBorder());
        setPauseFlag(true);
        star_or_pause_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
					if (time>0){
						setPauseFlag(!pauseFlag);
						if (pauseFlag){
							star_or_pause_Button.setText("开       始");
						}else{
							star_or_pause_Button.setText("暂       停");
						}
					}else{
						JOptionPane.showMessageDialog(null, "Please input the simulation time first !", "Error",JOptionPane.ERROR_MESSAGE);
					}
				}
			}
		});
		controlPanel.add(star_or_pause_Button);
		
		//仿真时长按钮
		JButton simulation_time_Button = new JButton("仿真时长");
		simulation_time_Button.setLocation(28, 240);
		simulation_time_Button.setSize(150, 30);
		simulation_time_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		simulation_time_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
					if (!pauseFlag){
						JOptionPane.showMessageDialog(null, "Please pause first !", "Error", JOptionPane.ERROR_MESSAGE);
					}else{
						String inputValue = JOptionPane.showInputDialog("Please input the time(s) !");
						if (inputValue!=null){
							boolean formalFormat = true;
							for (int i = 0; i < inputValue.length(); i++){
								int c = (int)inputValue.charAt(i);
								// 0到9的ASCII码对应值
								if ((c<48&&c!=46)||c>57){
									formalFormat = false;
									break;
								}
							}
							try{
								time = Double.parseDouble(inputValue);
							}catch(Exception ex){
								formalFormat = false;
							}
							if (formalFormat){
								JOptionPane.showMessageDialog(null, "Set time Succeed!", "Information", JOptionPane.INFORMATION_MESSAGE);
							}else{
								JOptionPane.showMessageDialog(null, "Please input a integer number between 0 and 2147483647!", "Error", JOptionPane.ERROR_MESSAGE);
							}
						}
					}
				}
			}
		});
		controlPanel.add(simulation_time_Button);
		
		//刷新频率按钮
		JButton cycle_Button = new JButton("刷新频率");
		cycle_Button.setLocation(28, 280);
		cycle_Button.setSize(150, 30);
		cycle_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		cycle_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
						String inputValue = JOptionPane.showInputDialog("Please input the cycle(ms) !");
						if (inputValue!=null){
							boolean formalFormat = true;
							for (int i = 0; i < inputValue.length(); i++){
								int c = (int)inputValue.charAt(i);
								// 0到9的ASCII码对应值
								if ((c<48&&c!=46)||c>57){
									formalFormat = false;
									break;
								}
							}
							try{
								cycle = Double.parseDouble(inputValue);
							}catch(Exception ex){
								formalFormat = false;
							}
							if (formalFormat){
								JOptionPane.showMessageDialog(null, "Set cycle Succeed!", "Information", JOptionPane.INFORMATION_MESSAGE);
							}else{
								JOptionPane.showMessageDialog(null, "Please input a integer number between 0 and 2147483647!", "Error", JOptionPane.ERROR_MESSAGE);
							}
						}
				}
			}
		});
		controlPanel.add(cycle_Button);
		
		//延迟概率按钮
		JButton delay_Button = new JButton("延迟概率");
		delay_Button.setLocation(28, 320);
		delay_Button.setSize(150, 30);
		delay_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		delay_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
						String inputValue = JOptionPane.showInputDialog("Please input the delay(0~100%) !");
						if (inputValue!=null){
							boolean formalFormat = true;
							for (int i = 0; i < inputValue.length(); i++){
								int c = (int)inputValue.charAt(i);
								// 0到9的ASCII码对应值
								if ((c<48&&c!=46)||c>57){
									formalFormat = false;
									break;
								}
							}
							try{
								delay = Double.parseDouble(inputValue);
							}catch(Exception ex){
								formalFormat = false;
							}
							if (formalFormat){
								JOptionPane.showMessageDialog(null, "Set delay Succeed!", "Information", JOptionPane.INFORMATION_MESSAGE);
							}else{
								JOptionPane.showMessageDialog(null, "Please input a integer number between 0 and 100!", "Error", JOptionPane.ERROR_MESSAGE);
							}
						}
				}
			}
		});
		controlPanel.add(delay_Button);
		
		//任务生成按钮
		JButton Tasks_Button = new JButton("生成任务");
		Tasks_Button.setLocation(28, 360);
		Tasks_Button.setSize(150, 30);
		Tasks_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		Tasks_Button.addActionListener(new ActionListener() {
			@SuppressWarnings("deprecation")
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
				    if (!pauseFlag) {
				    	JOptionPane.showMessageDialog(null, "Please pause first!", "Error", JOptionPane.ERROR_MESSAGE);
					}else {
						setSetTask(!setTask);
						if (setTask) {
							frame.setCursor(Cursor.HAND_CURSOR);
						}else {
							frame.setCursor(Cursor.DEFAULT_CURSOR);
						}
					}
				}
			}
		});
		controlPanel.add(Tasks_Button);
		
		//故障产生按钮
		JButton fault_Button = new JButton("生成故障");
		fault_Button.setLocation(28, 400);
		fault_Button.setSize(150, 30);
		fault_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		fault_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
				    if (!pauseFlag) {
				    	JOptionPane.showMessageDialog(null, "Please pause first!", "Error", JOptionPane.ERROR_MESSAGE);
					}else {
						setSetFault(!setFault);
						if (setFault) {
							frame.setCursor(Cursor.CROSSHAIR_CURSOR);
						}else {
							frame.setCursor(Cursor.DEFAULT_CURSOR);
						}
					}
				}
			}
		});
		controlPanel.add(fault_Button);
		
		//路径显示按钮
		JButton path_Button = new JButton("显示路径");
		path_Button.setLocation(28, 440);
		path_Button.setSize(150, 30);
		path_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		path_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
				    if (!pauseFlag) {
				    	JOptionPane.showMessageDialog(null, "Please pause first!", "Error", JOptionPane.ERROR_MESSAGE);
					}else {
						setPathview(!Pathview);
						if (Pathview) {
//							String cursor_path = "images/cursor.jpg"; //储存鼠标图片的位置
//							Toolkit tk = Toolkit.getDefaultToolkit();
//							Image image = new ImageIcon(cursor_path).getImage();
//							Cursor curs = tk.createCustomCursor(image, new Point(0, 0), "cursor");
//							frame.setCursor(curs);
							frame.setCursor(Cursor.NW_RESIZE_CURSOR);
						}else {
							repaint();
							frame.setCursor(Cursor.DEFAULT_CURSOR);
						}
					}
				}
			}
		});
		controlPanel.add(path_Button);
		
		//重置按钮
		JButton reload_Button = new JButton("重       置");
		reload_Button.setLocation(28, 480);
		reload_Button.setSize(150, 30);
		reload_Button.setBorder(BorderFactory.createRaisedBevelBorder());
		reload_Button.addActionListener(new ActionListener() {
			public void actionPerformed(ActionEvent e) {
				synchronized(this){
					//重置程序
					reload = true;
//					try {
//						this.finalize();
//					} catch (Throwable e1) {
//						// TODO Auto-generated catch block
//						e1.printStackTrace();
//					}
					frame.dispose(); 
				}
			}
		});
		controlPanel.add(reload_Button);
		
		//鼠标点击地图设置任务和故障以及显示路径
		if (isPauseFlag()) {
			this.addMouseListener(new MouseAdapter() {
			public void mouseClicked(MouseEvent e) {
				int x = e.getX(); int y = e.getY();
				if (e.getButton()==MouseEvent.BUTTON3) {
					if (Pathview) {
						setPathview(!Pathview);
						frame.setCursor(Cursor.DEFAULT_CURSOR);
						repaint();
					}
					if (setTask) {
						setTask = false;
						frame.setCursor(Cursor.DEFAULT_CURSOR);
					}
					if (setFault) {
						setFault = false;
						frame.setCursor(Cursor.DEFAULT_CURSOR);
					}
					return;
				}
				if (e.getButton()==MouseEvent.BUTTON1) {
					//显示路径
					if (Pathview) {
						for (int taskid:ICS.getSaved_routes().keySet()) {
							int point_x; int point_y;//当前点的位置
							Vertex passedVertex = find_vertex(map.getV(), ICS.getSaved_routes().get(taskid).get(0).getLocation());
							Vertex passVertex = find_vertex(map.getV(), ICS.getSaved_routes().get(taskid).get(1).getLocation());
							//到达终点
							if (ICS.getSaved_routes().get(taskid).get(1).getT1()-epoch<1&&ICS.getSaved_routes().get(taskid).size()==2) {
								continue;
							}
							int sx = leftspace+passedVertex.getX()*rate;int sy = upspace+passedVertex.getY()*rate;//弧起点坐标
							int ex = leftspace+passVertex.getX()*rate;int ey = upspace+passVertex.getY()*rate;//弧终点坐标
							Edge edge = find_edge(passedVertex.getLocation(),passVertex.getLocation(),map);
							double time = tasks.getCur_time()-ICS.getSaved_routes().get(taskid).get(0).getT2();
							if (time < 0) {
								point_x=sx;point_y=sy;
							}else if(time > 0){
								double Distacefrompassedvertex = time * edge.getV()/edge.getLength();
								point_x = (int) (Distacefrompassedvertex * ex + (1-Distacefrompassedvertex) * sx);
								point_y = (int) (Distacefrompassedvertex * ey + (1-Distacefrompassedvertex) * sy);
							}else {
								double d = 6/Math.sqrt((ex-sx)*(ex-sx)+(ey-sy)*(ey-sy));
								point_x = (int) (d * ex + (1-d) * sx);
								point_y = (int) (d * ey + (1-d) * sy);
							}
							if (Math.abs(x-point_x)>2||Math.abs(y-point_y)>2) {
								continue;
							}else {
								Graphics2D g =(Graphics2D) getGraphics();
								int end_x;int end_y;
								g.setColor(Color.GREEN);
								ArrayList<Node>path = ICS.getSaved_routes().get(taskid);
								for (int i = 1; i < path.size(); i++) {
									Vertex passVertex1 = find_vertex(map.getV(), path.get(i).getLocation());
									end_x = leftspace+passVertex1.getX()*rate;end_y = upspace+passVertex1.getY()*rate;
									g.drawLine(point_x, point_y, end_x, end_y);
									drawAL(point_x, point_y, end_x, end_y, g);
									point_x=end_x;point_y=end_y;
								}
								return;
							}			
						}
					return;
					}
					//产生新任务
					if (setTask) {
						for (int i =0; i< map.getStar().size(); i++) {
							Vertex v = map.getStar().get(i);
							int x_v=leftspace+v.getX()*rate;
							int y_v=upspace+v.getY()*rate;
							if (x>=x_v-3&&x<=x_v+3&&y>=y_v-3&&y<=y_v+3) {
								int n = JOptionPane.showConfirmDialog(null, "是否产生新任务？", "Title",JOptionPane.YES_NO_OPTION);
							    if (n==0) {
							    	map.getStar().get(i).setCangenerated_task(true);
							    	
								}else {
									map.getStar().get(i).setCangenerated_task(false);
								}
							    return;
							}
						}
					}
					//设置故障
					if (setFault) {
						for (Edge e1 : map.getE()) {
							int star_x;int star_y;int end_x;int end_y;
							Vertex star=find_vertex(map.getV(),e1.getStar());
							Vertex end=find_vertex(map.getV(),e1.getEnd());
							star_x = leftspace+star.getX()*rate;
							end_x = leftspace+end.getX()*rate;
							star_y = upspace+star.getY()*rate;
							end_y = upspace+end.getY()*rate;
							double distance = PointToEdge(x,y,star_x,star_y,end_x,end_y);
							if (distance>0&&distance<5) {
								int n = JOptionPane.showConfirmDialog(null, "是否设置故障？", "Title",JOptionPane.YES_NO_OPTION);
							    if (n==0) {
							    	e1.setFault(true);
								}else {
									e1.setFault(false);
								}
							    return;
							}
						}
					}	
				}
			}
			private double PointToEdge(int x, int y, int x1, int y1, int x2, int y2) {
				double cross = (x2 - x1) * (x - x1) + (y2 - y1) * (y - y1);
				if (cross <= 0) return -1;
				double d2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
				if (cross >= d2) return -1;
				double r = cross / d2;
				double px = x1 + (x2 - x1) * r;
				double py = y1 + (y2 - y1) * r;
				return Math.sqrt((x - px) * (x - px) + (py - y) * (py - y));
			}
			});
		}
		
		frame.add(controlPanel);
		frame.add(this);
		this.setVisible(true);
		frame.setVisible(true);
	}
	
	public  void paint(Graphics g) {
        super.paint(g);
        cycleLabel.setText("刷新频率: "+cycle);
        TimeLabel.setText("当前时间： "+epoch);
        paintmap(g);
        painttask(g);
   }

	private void paintmap(Graphics g2) {
		Graphics2D g=(Graphics2D)g2;
		ArrayList<Vertex>V=map.getV();
		ArrayList<Edge>E=map.getE();
		rate_x=(this.getWidth()-leftspace)/map.getMax_X();
		rate_y=(this.getHeight()-upspace)/map.getMax_Y();
		rate=rate_x>rate_y?rate_y:rate_x;//缩放率
		//画点
		for (Vertex v : V) {
			if (v.getType()==1) {
				g.setColor(Color.GREEN);
			}else if (v.getType()==2) {
				g.setColor(Color.BLACK);
			}else {
				g.setColor(Color.RED);
			}
			int x=leftspace+v.getX()*rate;
			int y=upspace+v.getY()*rate;
			g.fillRect(x-3, y-3, 8, 8);
			g.setColor(Color.BLACK);
			g.drawString(""+ v.getLocation(), x, y+12);
		}
		//画弧
		g.setColor(Color.BLACK);
		paintEdges(g, E);
	}
    private void drawAL(int sx, int sy, int ex, int ey, Graphics2D g2) {
		double H = 8;//箭头高度
		double L = 3;//底边的一半
		double awrad = Math.atan(L/H);
		double a_len = Math.sqrt(L*L+H*H);
		double[] XY1 =  rotateVec(ex  -  sx, ey  -  sy, awrad, a_len);
		double[] XY2 =  rotateVec(ex  -  sx, ey  -  sy, -awrad, a_len);
		int x3 = (int) (ex - XY1[0]);//箭头的第一端点
		int y3 = (int) (ey - XY1[1]);
		int x4 = (int) (ex - XY2[0]);//箭头的第二端点
		int y4 = (int) (ey - XY2[1]);
		int[] x = {ex, x3, x4};
		int[] y = {ey, y3, y4};
		g2.fillPolygon(x, y, 3);
	}

	private double[] rotateVec(int px, int py, double awrad, double a_len) {
		double[] mathstr = new double[2];
		double x = px * Math.cos(awrad) - py * Math.sin(awrad);
		double y = px * Math.sin(awrad) + py * Math.cos(awrad);
		double d = Math.sqrt(x * x + y * y);
		mathstr[0] = x / d * a_len;
		mathstr[1] = y / d * a_len;
		return mathstr;
	}

	private Vertex find_vertex(ArrayList<Vertex> V, int location) {
		for (Vertex vertex : V) {
			if (vertex.getLocation()==location) {
				return vertex;
			}
		}
		return null;
	}

	private void painttask(Graphics g) {
		//画未完成任务
		for (task untask : ICS.getUnfinishTasks()) {
			g.setColor(Color.ORANGE);
            Vertex starVertex = find_vertex(map.getV(), untask.getStar());
            int x = leftspace+starVertex.getX()*rate;
            int y = upspace+starVertex.getY()*rate;
			g.fillOval(x-3, y-3, 6, 6);
			g.setColor(Color.BLACK);
			g.drawString("task "+ untask.getTask_ID(), x-10, y-3);
		}
		
		//画正在执行的任务
		for (int task_id : ICS.getSaved_routes().keySet()) {
			g.setColor(Color.BLUE);
			Vertex passedVertex = find_vertex(map.getV(), ICS.getSaved_routes().get(task_id).get(0).getLocation());
			Vertex passVertex = find_vertex(map.getV(), ICS.getSaved_routes().get(task_id).get(1).getLocation());
			//到达终点
			if (ICS.getSaved_routes().get(task_id).get(1).getT1()-epoch<=1&&ICS.getSaved_routes().get(task_id).size()==2) {
				int sx = leftspace+passVertex.getX()*rate;int sy = upspace+passVertex.getY()*rate;
				g.fillOval(sx-3, sy-3, 6, 6);
				g.setColor(Color.BLACK);
				g.drawString("task "+ task_id, sx-10, sy-3);
				continue;
			}
			int sx = leftspace+passedVertex.getX()*rate;int sy = upspace+passedVertex.getY()*rate;//弧起点坐标
			int ex = leftspace+passVertex.getX()*rate;int ey = upspace+passVertex.getY()*rate;//弧终点坐标
			Edge edge = find_edge(passedVertex.getLocation(),passVertex.getLocation(),map);
			double time = tasks.getCur_time()-ICS.getSaved_routes().get(task_id).get(0).getT2();
			if (time < 0) {
				g.fillOval(sx-3, sy-3, 6, 6);//在起始节点处，需要一定的通过时间
				g.setColor(Color.BLACK);
				g.drawString("task "+ task_id, sx-10, sy-3);
			}else if(time > 0){
				double Distacefrompassedvertex = time * edge.getV()/edge.getLength();
				int x = (int) (Distacefrompassedvertex * ex + (1-Distacefrompassedvertex) * sx);
				int y = (int) (Distacefrompassedvertex * ey + (1-Distacefrompassedvertex) * sy);
				g.fillOval(x-3, y-3, 6, 6);
				g.setColor(Color.BLACK);
//				System.out.println(passedVertex.getLocation());
				g.drawString("task "+ task_id, x-10, y-3);
			}else {
				double d = 6/Math.sqrt((ex-sx)*(ex-sx)+(ey-sy)*(ey-sy));
				int x = (int) (d * ex + (1-d) * sx);
				int y = (int) (d * ey + (1-d) * sy);
				g.fillOval(x-3, y-3, 6, 6);
				g.setColor(Color.BLACK);
				g.drawString("task "+ task_id, x-10, y-3);
			}			
		}
		
		//画故障弧
		Graphics2D g2=(Graphics2D)g;
		g2.setColor(Color.RED);
		paintEdges(g2, tasks.getFault_edges());
		ArrayList<Edge>fault_Edges = find_fault_edges(ICS.getFault_edges(),tasks.getFault_edges());
		if (!fault_Edges.isEmpty()) {
			//g2.setColor(Color.MAGENTA);
			g2.setColor(Color.RED);
			paintEdges(g2, fault_Edges);
		}
		g2.setColor(Color.YELLOW);
		paintEdges(g2, tasks.getRepaired_edges());
	}

	private ArrayList<Edge> find_fault_edges(ArrayList<Edge> fault_edges, ArrayList<Edge> task_fault_edges2) {
		ArrayList<Edge>Edges = new ArrayList<Edge>();
		for (Edge e : fault_edges ) {
			if (!contain_edge(e,task_fault_edges2)) {
				Edges.add(e);
			}
		}
		return Edges;
	}

	private boolean contain_edge(Edge e, ArrayList<Edge> task_fault_edges) {
		for (Edge edge :task_fault_edges) {
			if (edge.getStar()==e.getStar()&&edge.getEnd()==e.getEnd()) {
				return true;
			}
		}
		return false;
	}

	private void paintEdges(Graphics2D g2, ArrayList<Edge> Edges) {
		for (Edge e : Edges) {
			int star_x;int star_y;int end_x;int end_y;
			Vertex star=find_vertex(map.getV(),e.getStar());
			Vertex end=find_vertex(map.getV(),e.getEnd());
			star_x = leftspace+star.getX()*rate;
			end_x = leftspace+end.getX()*rate;
			star_y = upspace+star.getY()*rate;
			end_y = upspace+end.getY()*rate;
			Stroke stroke=new BasicStroke(1.5f);//设置线宽为3.0
			g2.setStroke(stroke);
			g2.drawLine(star_x, star_y, end_x, end_y);
			drawAL(star_x, star_y, end_x, end_y, g2);
		}
	}

	private Edge find_edge(int star, int end, Map map2) {
		for(Edge edge : map2.getE()) {
			if(edge.getStar()==star && edge.getEnd()==end) {
				return edge;
			}
		}
		return null;
	}

	public Tasks getTask() {
		return tasks;
	}

	public void setTask(Tasks tasks) {
		this.tasks = tasks;
	}

	public ICS_PathFinding getICS() {
		return ICS;
	}

	public void setICS(ICS_PathFinding iCS) {
		ICS = iCS;
	}

	public double getCycle() {
		return cycle;
	}

	public void setCycle(double cycle) {
		this.cycle = cycle;
	}

	public double gettime() {
		return time;
	}

	public void settime(double curtime) {
		this.time = curtime;
	}

	public double getEpoch() {
		return epoch;
	}

	public void setEpoch(double epoch) {
		this.epoch = epoch;
	}

	public boolean isPauseFlag() {
		return pauseFlag;
	}

	public void setPauseFlag(boolean pauseFlag) {
		this.pauseFlag = pauseFlag;
	}

	public boolean isFinished() {
		return finished;
	}

	public void setFinished(boolean finished) {
		this.finished = finished;
	}

	public double getFault_probability() {
		return fault_probability;
	}

	public void setFault_probability(double fault_probability) {
		this.fault_probability = fault_probability;
	}

	public double getRepaired_probability() {
		return repaired_probability;
	}

	public void setRepaired_probability(double repaired_probability) {
		this.repaired_probability = repaired_probability;
	}

	public boolean isSetTask() {
		return setTask;
	}

	public void setSetTask(boolean setTask) {
		this.setTask = setTask;
	}

	public boolean isSetFault() {
		return setFault;
	}

	public void setSetFault(boolean setFault) {
		this.setFault = setFault;
	}

	public boolean isReload() {
		return reload;
	}

	public void setReload(boolean reload) {
		this.reload = reload;
	}

	public boolean isPathview() {
		return Pathview;
	}

	public void setPathview(boolean pathview) {
		Pathview = pathview;
	}

	public double getDelay() {
		return delay;
	}

	public void setDelay(double delay) {
		this.delay = delay;
	}
}
