import asyncio
import logging
from pydantic import BaseModel
from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, Any, TypeVar, Generic, Union, get_origin, get_args
from aiohttp import web
from .callback import Callback

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
        self._on_start: list[Callback] = []
        self._on_stop: list[Callback] = []
        self._on_send: list[Callback] = []
        self._on_receive: list[Callback] = []
        self._on_connect: list[Callback] = []
        self._on_disconnect: list[Callback] = []
        self._runner: Optional[web.AppRunner] = None
        self._stop_event = asyncio.Event()

        self._render_callback()

    def on_start(self, fn: Callable[[], Awaitable[None]]) -> None:
        """注册启动回调"""
        self._on_start.append(Callback(fn))

    def on_stop(self, fn: Callable[[], Awaitable[None]]) -> None:
        """注册停止回调"""
        self._on_stop.append(Callback(fn))

    def on_send(self, fn: Callable[[Any], Awaitable[None]]) -> None:
        """注册发送消息回调"""
        self._on_send.append(Callback(fn,strict=False))

    def on_receive(self, fn: Callable[[Any], Awaitable[None]]) -> None:
        """注册接受消息回调"""
        self._on_receive.append(Callback(fn,strict=False))

    def on_connect(self, fn: Callable[[T_Connect], Awaitable[None]]) -> None:
        """注册连接成功回调"""
        self._on_connect.append(Callback(fn))

    def on_disconnect(self, fn: Callable[[T_Disconnect], Awaitable[None]]) -> None:
        """注册连接断开回调"""
        self._on_disconnect.append(Callback(fn))

    def _callback(self, callbacks: list[Callback], *args: Any) -> None:
        for callback in callbacks:
            try:
                coro = callback(*args)
                if coro is None:
                    continue
                if asyncio.iscoroutine(coro):
                    asyncio.create_task(coro)
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

    def _to_serializable(self, payload: Any) -> Any:
        """将对象转为 JSON 可序列化格式"""
        if isinstance(payload, BaseModel):
            return payload.model_dump()
        if hasattr(payload, '__dict__') and not isinstance(payload, (dict, list, str, int, float, bool, type(None))):
            return payload.__dict__  # 或 dataclasses.asdict 等
        return payload