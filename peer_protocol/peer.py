import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, Any, TypeVar, Generic
from aiohttp import web

logger = logging.getLogger(__name__)
T_Connect = TypeVar("T_Connect")
T_Disconnect = TypeVar("T_Disconnect")

class Peer(ABC, Generic[T_Connect, T_Disconnect]):
    def __init__(self):
        """
        Attributes:
            _on_start: 启动回调列表
            _on_stop: 停止回调列表
            _on_send: 发送消息回调列表
            _on_receive: 接受消息回调列表
            _on_connect: 连接成功回调列表
            _on_disconnect: 连接断开回调列表
            _runner: 应用运行器
            _stop_event: 停止事件
        """
        self._on_start: list[Callable[[], Awaitable[None]]] = []
        self._on_stop: list[Callable[[], Awaitable[None]]] = []
        self._on_send: list[Callable[[Any], Awaitable[None]]] = []
        self._on_receive: list[Callable[[Any], Awaitable[None]]] = []
        self._on_connect: list[Callable[[T_Connect], Awaitable[None]]] = []
        self._on_disconnect: list[Callable[[T_Disconnect], Awaitable[None]]] = []
        self._runner: Optional[web.AppRunner] = None
        self._stop_event = asyncio.Event()

        self._render_callback()

    def on_start(self, callback: Callable[[], Awaitable[None]]) -> None:
        """注册启动回调"""
        self._on_start.append(callback)

    def on_stop(self, callback: Callable[[], Awaitable[None]]) -> None:
        """注册停止回调"""
        self._on_stop.append(callback)

    def on_send(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """注册发送消息回调"""
        self._on_send.append(callback)

    def on_receive(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """注册接受消息回调"""
        self._on_receive.append(callback)

    def on_connect(self, callback: Callable[[T_Connect], Awaitable[None]]) -> None:
        """注册连接成功回调"""
        self._on_connect.append(callback)

    def on_disconnect(self, callback: Callable[[T_Disconnect], Awaitable[None]]) -> None:
        """注册连接断开回调"""
        self._on_disconnect.append(callback)

    def _callback(self, callbacks: list[Callable[[], Awaitable[None]]], *args: Any, **kwargs: Any) -> None:
        for callback in callbacks:
            try:
                asyncio.create_task(callback(*args, **kwargs))
            except:
                logger.exception(f"回调函数执行失败: {callback}")
                continue

    @abstractmethod
    async def start(self) -> None:
        """启动服务"""

    @abstractmethod
    async def stop(self) -> None:
        """停止服务"""
            
    async def run(self):
        """启动服务并阻塞，直到中断"""
        await self.start()
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def _render_callback(self):
        """渲染回调"""
        @self.on_send
        async def _(payload: Any):
            logger.info(f"发送消息: {payload}")

        @self.on_receive
        async def _(payload: Any):
            logger.info(f"接收消息: {payload}")