package communication;
import io.netty.bootstrap.Bootstrap;
import io.netty.channel.ChannelFuture;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelOption;
import io.netty.channel.EventLoopGroup;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.handler.logging.LogLevel;
import io.netty.handler.logging.LoggingHandler;
import io.netty.handler.timeout.IdleStateHandler;

import java.util.concurrent.TimeUnit;

public class SocketClient {
    /**	 * 连接服务器	 * 	 * @param port	 * @param host	 * @throws Exception	 */
    public void connect(int port, String host) throws Exception {
        // 配置客户端NIO线程组
        EventLoopGroup group = new NioEventLoopGroup();
        try {
            // 客户端辅助启动类 对客户端配置
            Bootstrap b = new Bootstrap();
            b.handler(new LoggingHandler(LogLevel.INFO));
            b.group(group)
             .channel(NioSocketChannel.class)
                    .option(ChannelOption.TCP_NODELAY, true)
                    .handler(new ClientChannelHandler());
            // 异步链接服务器 同步等待连接成功
            ChannelFuture f = b.connect(host, port).sync();
            // 等待链接关闭
            f.channel().closeFuture().sync();
        } finally {
//            group.shutdownGracefully();
            System.out.println("*****客户端优雅的释放了线程资源...将要重新寻找服务端*****");
            try{
                TimeUnit.SECONDS.sleep(5);
                try{
                    System.out.println("*****重新链接*****");
                    connect(9999,"192.168.1.201");
                }
                catch (Exception e){
                    e.printStackTrace();
                }
            }
            catch (Exception e){
                e.printStackTrace();
            }
        }
    }

    /**	 * 网络事件处理器	 */
    private class ClientChannelHandler extends
            ChannelInitializer<SocketChannel> {
        @Override
        protected void initChannel(SocketChannel ch) throws Exception {
        	 // 客户端的处理器
            //每个1秒发送一次心跳包
            ch.pipeline().addLast("ping",new IdleStateHandler(0,2,0, TimeUnit.SECONDS));
            ch.pipeline().addLast(new LoggingHandler(LogLevel.INFO));
            ch.pipeline().addLast(new decode1());
            ch.pipeline().addLast(new SocketClientHandler());
        }
    }

    public static void main(String[] args) throws Exception {
        new SocketClient().connect(9999, "127.0.0.1");
    }
}

