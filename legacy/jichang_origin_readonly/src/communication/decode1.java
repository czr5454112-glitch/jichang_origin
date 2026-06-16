package communication;
import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.ByteToMessageDecoder;
import net.sf.json.JSONArray;
import net.sf.json.JSONObject;

import java.util.List;

import App.Edge;
import App.ICS_PathFinding;
import App.Tasks;
import App.task;

public class decode1 extends ByteToMessageDecoder {
    static ICS_PathFinding ics;
    protected void decode(ChannelHandlerContext ctx, ByteBuf msg,List<Object> out) throws Exception {
     
        String string;
        Tasks received_tasks = new Tasks();
        if (msg.hasArray()) {
            string = new String(msg.array(), msg.arrayOffset() + msg.readerIndex(), msg.readableBytes());
        } else {
            byte[] bytes = new byte[msg.readableBytes()];
            msg.getBytes(msg.readerIndex(), bytes);
            string = new String(bytes, 0, msg.readableBytes());
        }
        System.out.println("******接收到的任务信息是******: " + string);

        JSONObject json = JSONObject.fromObject(string);
      //解析任务数据 包括新任务、正在进行的任务以及故障弧
        System.out.println("******读取到地图状态是******" + json.getInt("map"));

        int map_info = json.getInt("map");
        double double_time = json.getInt("double_time");
        String standard_time = json.getString("standard_time");
        System.out.println("******两种时间是******"+standard_time+" 和 "+double_time);
        //收到地图信息和时间信息
        received_tasks.setFlag(map_info);
        received_tasks.setCur_time(double_time/1000);
        //得到新任务
        String new_info = json.getString("new_task");
        JSONObject j_new = JSONObject.fromObject(new_info);
        int new_number = j_new.getInt("new_task_number");
        if (new_number==0){
        	System.out.println("******本次没有新任务******");
        }else{
        	System.out.println("******本次有 "+new_number+" 个新任务******");
            String new_tsk_list = j_new.getString("new_task_list");
            JSONArray json_new_task = JSONArray.fromObject(new_tsk_list);
            // json转换成java集合对象
            for (int j = 0; j < json_new_task.size(); j++) {
                String js = json_new_task.get(j).toString();
                JSONObject jso = JSONObject.fromObject(js);
                task new_Task=new task();
				new_Task.setTask_ID(jso.getInt("task_id"));
				new_Task.setPallet_ID(jso.getInt("pallet_id"));
				new_Task.setStar(jso.getInt("start"));
				new_Task.setGoal(jso.getInt("end"));
				received_tasks.getNew_tasks_list().add(new_Task);
            }
        }
        //正在执行的任务
        String now_info = json.getString("now_task");
        JSONObject j_now =  JSONObject.fromObject(now_info);;
        int now_number = j_now.getInt("now_task_number");
        if (now_number==0){
            System.out.println("******没有正在执行的任务******");
        }else{
        	System.out.println("******目前还有 "+now_number+" 个正在执行的任务******");
            String now_task_list = j_now.getString("now_task_list");
            JSONArray json_now_task = JSONArray.fromObject(now_task_list);
            // 转java对象
            for (int j = 0; j < json_now_task.size(); j++) {
                String js = json_now_task.get(j).toString();
                JSONObject jso = JSONObject.fromObject(js);
              //分别代表任务编号，托盘编号，起点，终点，
              //正在通过弧段的起点，终点以及到达弧段起点的时间(暂时按照当前时间)
                task ON_task=new task();
				ON_task.setTask_ID(jso.getInt("task_id"));
				ON_task.setPallet_ID(jso.getInt("pallet_id"));
				ON_task.setStar(jso.getInt("start"));
				ON_task.setGoal(jso.getInt("end"));
				ON_task.setPassed_vertex_location(jso.getInt("now_start"));
				ON_task.setPass_vertex_location(jso.getInt("now_end"));
				ON_task.setPass_time(jso.getDouble("double_time"));
				received_tasks.getOnpath_tasks_list().add(ON_task);
				received_tasks.getOnpath_task_ID().add(ON_task.getTask_ID());
            }
        }
        //得到故障弧
        String problem_info = json.getString("problem_arc");
        JSONObject j_problem =  JSONObject.fromObject(problem_info);;
        int problem_number = j_problem.getInt("problem_arc_number");
        if (problem_number==0){
        	System.out.println("******目前没有故障弧******");
        }else{
        	System.out.println("******目前还有 "+problem_number+" 个故障弧******");
            String problem_arc_list = j_problem.getString("problem_arc_list");
            JSONArray json_problem_arc = JSONArray.fromObject(problem_arc_list);
            // 转换成java对象
            for (int j=0;j<json_problem_arc.size();j++) {
                String js = json_problem_arc.get(j).toString();
                JSONObject jso = JSONObject.fromObject(js);
              //三个数字，第1个是(0,1)分别代表未修好的故障弧/修好的故障弧、故障弧起点、终点，
                int state = jso.getInt("state");
                int problem_start = jso.getInt("problem_start");
                int problem_end = jso.getInt("problem_end");
                for (Edge e:ics.getMap().getE()) {
					if (e.getStar()==problem_start&&e.getEnd()==problem_end) {
						if (state==0) {
							received_tasks.getFault_edges().add(e);
						}else {
							received_tasks.getRepaired_edges().add(e);
						}
						break;
					}
				}
            }
        }
        ics.ICS_path_finding(received_tasks, ics.getMap(), received_tasks.getCur_time(), ics);
        System.out.println(ics.getSaved_routes().get(2));
       
        SocketClientHandler sch = new SocketClientHandler();
        JSONObject json_solution = sch.getSolution(ics.getSaved_routes());
        String str = json_solution.toString();
        ByteBuf message = ctx.alloc().buffer(4* str.length());
        message.writeBytes(str.getBytes());
        ctx.writeAndFlush(message);
        System.out.println("******发生解成解******");
    }
	public static ICS_PathFinding getIcs() {
		return ics;
	}
	public static void setIcs(ICS_PathFinding ics1) {
		System.out.println();
		ics = ics1;
	}
}
