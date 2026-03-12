from .peer import Peer
import logging
import json
import aiohttp
from aiohttp import web
from typing import Any

logger = logging.getLogger(__name__)

class Server(Peer[web.WebSocketResponse, web.WebSocketResponse]):
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        heartbeat: int = 120,
        *args,
        **kwargs,
    ):
        """
        Args:
            host: 主机地址
            port: 端口号
            heartbeat: 心跳间隔秒数
        Attributes:
            _clients: 客户端集合
        """
        super().__init__(*args, **kwargs)

        self.host = host
        self.port = port
        self.heartbeat = heartbeat

        self._clients: set[web.WebSocketResponse] = set()

    def _disconnect(self, ws: web.WebSocketResponse):
        """断开客户端连接"""
        if ws not in self._clients:
            return
        self._clients.discard(ws)
        self._callback(self._on_disconnect, ws)
        
    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket连接"""
        ws = web.WebSocketResponse(heartbeat=self.heartbeat)
        await ws.prepare(request)

        self._clients.add(ws)
        self._callback(self._on_connect, ws)

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"收到无效的 JSON: {msg.data} - {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"收到无效的消息: {msg.data} - {e}")
                        continue
                        
                    self._callback(self._on_receive, data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning(f"WebSocket 错误: {ws.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    break
        finally:
            self._disconnect(ws)

        return ws

    async def broadcast(self, payload: Any) -> None:
        """将消息广播给所有客户端 """
        if not self._clients:
            logger.warning("没有已连接的 WebSocket 客户端，无法转发消息")
            return
        
        self._callback(self._on_send, payload)

        dead: set[web.WebSocketResponse] = set()
        for ws in self._clients:
            try:
                await ws.send_str(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._disconnect(ws)

    def _create_app(self) -> web.Application:
        """创建应用"""
        app = web.Application()
        app.router.add_get("/ws", self._handle_ws)
        return app

    async def start(self):
        """启动服务"""
        if self._runner:
            return
        app = self._create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        self._callback(self._on_start)

    async def stop(self):
        """停止服务"""
        if not self._runner:
            return
        for ws in list(self._clients):
            await ws.close()
        self._clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._callback(self._on_stop)
        self._stop_event.set()

    def _render_callback(self):
        """渲染回调"""
        super()._render_callback()

        @self.on_start
        async def _():
            logger.info(f"服务端已启动: {self.host}:{self.port}")

        @self.on_stop
        async def _():
            logger.info(f"服务端已停止: {self.host}:{self.port}")

        @self.on_connect
        async def _(ws: web.WebSocketResponse):
            peername = ws.get_extra_info('peername')
            logger.info(f"客户端已连接: {peername[0]}:{peername[1]}")

        @self.on_disconnect
        async def _(ws: web.WebSocketResponse):
            peername = ws.get_extra_info('peername')
            logger.info(f"客户端已断开: {peername[0]}:{peername[1]}")