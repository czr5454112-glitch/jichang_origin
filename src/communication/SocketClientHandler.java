package communication;
import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelInboundHandlerAdapter;
import io.netty.handler.timeout.IdleState;
import io.netty.handler.timeout.IdleStateEvent;
import net.sf.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;

import App.Node;

public class SocketClientHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead (ChannelHandlerContext ctx, Object msg)throws Exception{
        System.out.println("接受到的任务是"+msg);
    }

    @Override	public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) throws Exception {
        ctx.close();
    }

    @Override
    public void channelActive(ChannelHandlerContext ctx) throws Exception {
        System.out.println("channelActive: 激活");
    }

    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) throws Exception {
        System.out.println("***********发送心跳包***********");
        super.userEventTriggered(ctx, evt);
        if (evt instanceof IdleStateEvent) {
            IdleStateEvent event = (IdleStateEvent) evt;
            if(event.state().equals(IdleState.WRITER_IDLE)) {
                JSONObject json =  getInitialization(); // 0 表示发送心跳包/初始化
                String str = json.toString();
                ByteBuf message = ctx.alloc().buffer(4 * str.length());
                message.writeBytes(str.getBytes());
                ctx.writeAndFlush(message);
            } else if (event.state().equals(IdleState.ALL_IDLE)) {

            }
        }
    }
    public JSONObject getInitialization (){
        Map<String,String> iniParameter = new HashMap<>();
        iniParameter.put("information_type","Initialization");  
        JSONObject json = JSONObject.fromObject(iniParameter);
        return json;
    }

    public JSONObject getSolution (HashMap<Integer, ArrayList<Node>> saveroutes){
        HashMap<String,Object> route = Transform(saveroutes);
//        for (String a :route.keySet()) {
//			System.out.println("key: "+a+"     value: "+route.get(a));
//		}
        JSONObject json = JSONObject.fromObject(route);
        String str = json.toString();

        // 得到发送给服务端的完整解信息
        Map<String,Object> solution = new HashMap<>();
        solution.put("information_type","Solution");
        solution.put("route",str);
        JSONObject json_solution = JSONObject.fromObject(solution);
        return json_solution;
    }

	private HashMap<String, Object> Transform(HashMap<Integer, ArrayList<Node>> solution) {
		HashMap<String,Object> route = new HashMap<String, Object>();
		for (int key :solution.keySet()) {
			String aString = String.valueOf(key);
			ArrayList<Integer>list =new ArrayList<Integer>();
			for (Node node : solution.get(key)) {
				list.add(node.getLocation());
			}
			route.put(aString,list);
		}
		return route;
	}
}

