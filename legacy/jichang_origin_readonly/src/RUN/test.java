package RUN;

import java.io.IOException;

import App.ICS_PathFinding;
import communication.SocketClient;
import communication.decode1;

public class test {

	public static void main(String[] args) throws Exception {
		   //读取地图
		ICS_PathFinding ics_pf = new ICS_PathFinding();
		read_Map(ics_pf);
		decode1.setIcs(ics_pf);
		while (true) {
			//请求连接
			new SocketClient().connect(9999, "192.168.1.201");
		}	
	}

	private static void read_Map(ICS_PathFinding ics_pf) throws IOException {
		String mapdata = "map2.txt";//地图数据
//		ICS_GUI gui = ics_pf.getMap().getGui();
//		gui.setICS(ics_pf);
		ics_pf.getMap().read(ics_pf.getMap(),mapdata);
		//显示地图
//		gui.setMap(ics_pf.getMap());
//		gui.showmap();
	}    
}
