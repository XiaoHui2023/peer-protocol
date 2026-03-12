import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable, Any
import aiohttp
from aiohttp import web
from . import (
    MessagePayload,
    MessageSegment,
)

logger = logging.getLogger(__name__)

class Server:
    """OneBot 服务端"""
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        reply_timeout: int = 60,
        heartbeat: int = 120,
    ):
        """
        Args:
            host: 服务端主机地址
            port: 服务端端口号
            reply_timeout: 等待客户端回复的超时秒数
            heartbeat: 心跳间隔秒数
        Attributes:
            _on_start: 启动回调列表
            _on_stop: 停止回调列表
            _on_send: 发送消息回调列表
            _on_connect: 连接成功回调列表
            _on_disconnect: 连接断开回调列表
            _runner: 应用运行器
            _clients: 客户端集合
        """
        self.host = host
        self.port = port
        self.reply_timeout = reply_timeout
        self.heartbeat = heartbeat

        self._on_start: list[Callable[[], Awaitable[None]]] = []
        self._on_stop: list[Callable[[], Awaitable[None]]] = []
        self._on_send: list[Callable[[MessagePayload], Awaitable[None]]] = []
        self._on_connect: list[Callable[[web.Request], Awaitable[None]]] = []
        self._on_disconnect: list[Callable[[web.Request], Awaitable[None]]] = []
        self._runner: Optional[web.AppRunner] = None
        self._clients: set[web.WebSocketResponse] = set()

    def on_start(self, callback: Callable[[], Awaitable[None]]) -> None:
        """注册启动回调"""
        self._on_start.append(callback)

    def on_stop(self, callback: Callable[[], Awaitable[None]]) -> None:
        """注册停止回调"""
        self._on_stop.append(callback)

    def on_send(self, callback: Callable[[MessagePayload], Awaitable[None]]) -> None:
        """注册发送消息回调"""
        self._on_send.append(callback)

    def on_connect(self, callback: Callable[[web.Request], Awaitable[None]]) -> None:
        """注册连接成功回调"""
        self._on_connect.append(callback)

    def on_disconnect(self, callback: Callable[[web.Request], Awaitable[None]]) -> None:
        """注册连接断开回调"""
        self._on_disconnect.append(callback)

    def _callback(self, callbacks: list[Callable[[], Awaitable[None]]], default_info: str, *args: Any, **kwargs: Any) -> None:
        if not callbacks:
            logger.info(default_info)
            return
        for callback in callbacks:
            try:
                asyncio.create_task(callback(*args, **kwargs))
            except:
                logger.exception(f"回调函数执行失败: {callback}")
                continue

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket连接"""
        ws = web.WebSocketResponse(heartbeat=self.heartbeat)
        await ws.prepare(request)

        self._callback(self._on_connect, f"WebSocket 客户端已连接: {peer} (当前 {len(self._clients)} 个)", request)
        self._clients.add(ws)
        peer = request.remote

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        payload = MessagePayload.model_validate(data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"收到无效的 JSON: {msg.data} - {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"收到无效的消息: {msg.data} - {e}")
                        continue
                        
                    msg_id = data.get("msg_id", "")
                    fut = self._pending.get(msg_id)
                    if fut and not fut.done():
                        content = data.get("content")
                        logger.info(f"收到客户端回复 [{msg_id}]: {content}")
                        fut.set_result(MessagePayload(content=content))
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning(f"WebSocket 错误: {ws.exception()}")
        finally:
            self._clients.discard(ws)
            self._callback(self._on_disconnect, f"WebSocket 客户端已断开: {peer} (剩余 {len(self._clients)} 个)", request)

        return ws

    async def broadcast(self, request: MessagePayload) -> MessagePayload:
        """
        将消息广播给所有 WebSocket 客户端，等待第一个回复。

        发送 JSON (与原 webhook 格式一致):
            {"source", "content", "msg_id", "event_type", "source_id", "sender_id"}

        期望客户端回复 JSON:
            {"msg_id": "对应的消息ID", "content": "回复内容"}
        """
        logger.info(f"收到消息 {request}")
        if not self._clients:
            logger.warning("没有已连接的 WebSocket 客户端，无法转发消息")
            return MessagePayload(content=None)

        payload = json.dumps({
            "source": request.source.value,
            "content": request.content,
            "msg_id": request.msg_id,
            "event_type": request.event_type,
            "source_id": request.source_id,
            "sender_id": request.sender_id,
        }, ensure_ascii=False)

        fut: asyncio.Future[MessagePayload] = asyncio.get_running_loop().create_future()
        self._pending[request.msg_id] = fut

        dead: set[web.WebSocketResponse] = set()
        for ws in self._clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.add(ws)
        self._clients -= dead

        try:
            return await asyncio.wait_for(fut, timeout=WS_REPLY_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("等待客户端回复超时: %s", request.msg_id)
            return MessagePayload(content=None)
        finally:
            self._pending.pop(request.msg_id, None)

    def _create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/ws", self._handle_ws)
        return app

    async def start(self):
        """启动服务"""
        app = self._create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

    async def stop(self):
        """停止服务"""
        for ws in list(self._clients):
            await ws.close()
        self._clients.clear()

        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            logger.info("服务端已停止")
            
    async def run(self):
        """启动服务并阻塞，直到 Ctrl+C"""
        await self.start()
        try:
            await self._run_forever()
        finally:
            await self.stop()

            
    async def _run_forever(self):
        """内部：保持运行直到被中断"""
        try:
            await asyncio.Event().wait()  # 永久等待
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()