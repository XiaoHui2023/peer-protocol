import asyncio
import json
import logging
import aiohttp
from typing import Optional, Any
from urllib.parse import urlparse, ParseResult
from .peer import Peer

logger = logging.getLogger(__name__)

class Client(Peer[aiohttp.ClientWebSocketResponse, aiohttp.ClientWebSocketResponse]):
    def __init__(
        self,
        url: str="http://127.0.0.1:8080",
        retry_interval: float = 2,
        retry_timeout: float = 5,
        *args,
        **kwargs,
    ):
        """
        Args:
            url: 服务端 URL
            retry_interval: 重试间隔时间
            retry_timeout: 重试超时时间
        Attributes:
            _parsed_url: 解析后的 URL
            _session: HTTP 会话
            _ws: WebSocket 连接
            _ws_task: WebSocket 任务
            _running: 是否运行
            _connected: 是否连接
        """
        super().__init__(*args, **kwargs)
        self.url = url
        self.retry_interval = retry_interval
        self.retry_timeout = retry_timeout

        self._parsed_url = self._parse_url(url)
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False
        self._connected = False

    @property
    def connected(self) -> bool:
        """服务端是否在线"""
        return self._connected

    def _parse_url(self, url: str) -> ParseResult:
        """解析 URL"""
        url = url.strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "http://" + url
        parsed = urlparse(url)
        if parsed.hostname is None:
            raise ValueError(
                f"无效的 url: {url!r}，"
                "请使用完整 URL（如 http://127.0.0.1:8080）或 host:port 格式"
            )
        if parsed.port is None:
            if parsed.scheme == "https":
                port = 443
            else:
                port = 80
            parsed = parsed._replace(port=port)
        return parsed

    async def _check_server(self) -> bool:
        """纯 TCP 连通性检测：只检查服务端 IP:端口是否可达"""
        host = self._parsed_url.hostname
        port = self._parsed_url.port
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self.retry_timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _wait_for_server(self):
        """轮询服务端，直到 TCP 可达（无限重试）"""
        while self._running:
            if await self._check_server():
                return
            await asyncio.sleep(self.retry_interval)

    async def _ws_loop(self):
        """WebSocket 连接循环：连接 → 收消息 → 断线重连"""
        while self._running:
            await self._wait_for_server()
            if not self._running:
                break

            try:
                self._ws = await self._session.ws_connect(self.url)
            except Exception:
                logger.exception("WebSocket 连接失败")
                continue

            self._connected = True
            self._callback(self._on_connect, self._ws)

            try:
                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        asyncio.create_task(self._handle_message(msg.data))
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.warning(f"WebSocket 连接异常: {self._ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        break
            except Exception:
                logger.exception("WebSocket 消息循环异常")
            finally:
                self._connected = False
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                self._ws = None
                self._callback(self._on_disconnect, self._ws)

    async def _handle_message(self, raw: str):
        """解析服务端推送的消息，调用回调，发回回复"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"收到无效的 JSON: {raw} - {e}")
            return

        self._callback(self._on_receive, data)

    async def start(self):
        """启动客户端"""
        if self._running:
            return
        self._running = True
        self._session = aiohttp.ClientSession()
        self._ws_task = asyncio.create_task(self._ws_loop())
        self._callback(self._on_start)

    async def stop(self):
        """停止客户端，清理所有资源"""
        if not self._running:
            return
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

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        self._callback(self._on_stop)
        self._stop_event.set()

    async def send(self, payload: Any):
        """发送消息"""
        self._callback(self._on_send, payload)

        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps(self._to_serializable(payload), ensure_ascii=False))
            except Exception:
                logger.exception("发送消息失败")

    def _render_callback(self):
        """渲染回调"""
        super()._render_callback()

        @self.on_start
        async def _():
            logger.info(f"正在连接服务端: {self.url}")

        @self.on_stop
        async def _():
            logger.info(f"停止客户端")

        @self.on_connect
        async def _(ws: aiohttp.ClientWebSocketResponse):
            logger.info(f"连接到服务端: {self.url}")

        @self.on_disconnect
        async def _(ws: aiohttp.ClientWebSocketResponse):
            logger.info(f"与服务端断开连接: {self.url}")