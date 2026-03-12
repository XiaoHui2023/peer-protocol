import asyncio
import inspect
import json
import logging
import aiohttp
from typing import Callable, Union, Awaitable, Optional
from urllib.parse import urlparse
from . import MessagePayload,MessageSegment

logger = logging.getLogger(__name__)

MessageHandler = Callable[
    [MessagePayload], Union[MessagePayload, Awaitable[MessagePayload]]
]
LifecycleHook = Callable[[], Union[None, Awaitable[None]]]

class Client:
    """OneBot 客户端"""

    def __init__(self, server_url: str):
        server_url = server_url.strip().rstrip("/")
        # 无 scheme 时自动补全（如 "127.0.0.1:8080" -> "http://127.0.0.1:8080"）
        if server_url and not server_url.startswith(("http://", "https://")):
            server_url = "http://" + server_url
        parsed = urlparse(server_url)
        if parsed.hostname is None:
            raise ValueError(
                f"无效的 server_url: {server_url!r}，"
                "请使用完整 URL（如 http://127.0.0.1:8080）或 host:port 格式"
            )
        self.server_url = server_url

        self._handler: Optional[MessageHandler] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False

        self._connected = False
        self._on_connect: Optional[LifecycleHook] = None
        self._on_disconnect: Optional[LifecycleHook] = None

    # -------- 连接状态 --------

    @property
    def connected(self) -> bool:
        """服务端是否在线"""
        return self._connected

    # -------- 生命周期装饰器 --------

    def on_connect(self, fn: LifecycleHook) -> LifecycleHook:
        """注册服务端连接成功回调（装饰器）"""
        self._on_connect = fn
        return fn

    def on_disconnect(self, fn: LifecycleHook) -> LifecycleHook:
        """注册服务端断连回调（装饰器）"""
        self._on_disconnect = fn
        return fn

    async def _fire(self, hook: Optional[LifecycleHook]):
        if hook is None:
            return
        try:
            result = hook()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("生命周期回调异常")

    # -------- 服务端探测 --------

    async def _check_server(self) -> bool:
        """纯 TCP 连通性检测：只检查服务端 IP:端口是否可达"""
        parsed = urlparse(self.server_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _wait_for_server(self, interval: float = 2):
        """轮询服务端，直到 TCP 可达（无限重试）"""
        logged = False
        while self._running:
            if await self._check_server():
                return
            if not logged:
                logger.info("等待服务端就绪... (%s)", self.server_url)
                logged = True
            else:
                logger.debug("等待服务端就绪... (%s)", self.server_url)
            await asyncio.sleep(interval)

    # -------- WebSocket 消息循环 --------

    async def _ws_loop(self):
        """WebSocket 连接循环：连接 → 收消息 → 断线重连"""
        ws_url = self.server_url + "/ws"
        while self._running:
            await self._wait_for_server()
            if not self._running:
                break

            try:
                self._ws = await self._session.ws_connect(ws_url)
            except Exception:
                logger.warning("WebSocket 连接失败，将在 2 秒后重试...")
                await asyncio.sleep(2)
                continue

            self._connected = True
            logger.info("已连接到服务端: %s", ws_url)
            await self._fire(self._on_connect)

            try:
                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        asyncio.create_task(self._handle_message(msg.data))
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
            except Exception:
                logger.exception("WebSocket 消息循环异常")
            finally:
                self._connected = False
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                self._ws = None

            logger.warning("服务端连接已断开，等待重连... (%s)", self.server_url)
            await self._fire(self._on_disconnect)

            if self._running:
                await asyncio.sleep(2)

    async def _handle_message(self, raw: str):
        """解析服务端推送的消息，调用回调，发回回复"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        request = MessageRequest(
            source=MessageSource(data["source"]),
            content=data.get("content", ""),
            source_id=data.get("source_id", ""),
            msg_id=data.get("msg_id", ""),
            event_type=data.get("event_type", ""),
            sender_id=data.get("sender_id", ""),
        )

        try:
            if inspect.iscoroutinefunction(self._handler):
                result = await self._handler(request)
            else:
                result = await asyncio.to_thread(self._handler, request)
            if result is None:
                result = MessageResponse(content=None)
        except Exception:
            logger.exception("消息处理回调异常")
            result = MessageResponse(content=None)

        content = result.content
        if not isinstance(content, str):
            content = str(content)
        if content is None:
            return
        response = {
            "msg_id": request.msg_id,
            "content": content,
        }

        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_json(response)
            except Exception:
                logger.exception("发送回复失败")

    # -------- 启停 --------

    async def start(self, handler: MessageHandler):
        """
        非阻塞启动客户端。

        1. 等待服务端 TCP 可达
        2. 建立 WebSocket 连接
        3. 在后台任务中持续接收消息并自动重连
        """
        self._handler = handler
        self._running = True
        self._session = aiohttp.ClientSession()
        self._ws_task = asyncio.create_task(self._ws_loop())

    async def stop(self):
        """停止客户端，清理所有资源"""
        self._running = False

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

        if self._connected:
            self._connected = False
            await self._fire(self._on_disconnect)

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        logger.info("客户端已停止")

    def run(self, handler: MessageHandler):
        """阻塞运行客户端（单客户端便捷方法）。"""

        async def _main():
            await self.start(handler)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
            finally:
                await self.stop()

        asyncio.run(_main())


    async def _handle_send(self, request: web.Request) -> web.Response:
        """客户端发送消息"""
        try:
            data = await request.json()
            payload = MessagePayload.model_validate(data)
        except Exception as e:
            return web.json_response(
                {"ok": False, "error": str(e)}, status=400
            )

        try:
            await self._on_send(payload)
            return web.json_response({"ok": True})
        except Exception as e:
            logger.exception("API send 失败")
            return web.json_response({"ok": False, "error": str(e)}, status=500)