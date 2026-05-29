"""内部 MCP 消息总线 — 基于 asyncio 的进程间通信"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

from shared.models import MCPRequest, MCPResponse
from shared.constants import JSONRPC_VERSION

logger = logging.getLogger("pulsar.mcp_bus")

MessageHandler = Callable[[MCPRequest], Coroutine[Any, Any, MCPResponse]]


class MCPBus:
    """内部 MCP 消息总线

    基于 asyncio.Queue 的进程间通信机制，支持：
    - 点对点请求/响应 (send)
    - 发布/订阅模式 (publish/subscribe)
    - 工具列表查询 (list_tools)
    """

    def __init__(self):
        self._handlers: dict[str, MessageHandler] = {}
        self._subscribers: dict[str, list[MessageHandler]] = {}
        self._running = False
        self._request_queue: asyncio.Queue[MCPRequest] = asyncio.Queue()
        self._response_queue: asyncio.Queue[MCPResponse] = asyncio.Queue()

    def register_handler(self, method: str, handler: MessageHandler) -> None:
        """注册方法处理器

        Args:
            method: 方法名，如 "tools/call", "system/ping"
            handler: 异步处理函数
        """
        self._handlers[method] = handler
        logger.debug(f"注册 MCP 方法处理器: {method}")

    def unregister_handler(self, method: str) -> None:
        """注销方法处理器"""
        self._handlers.pop(method, None)
        logger.debug(f"注销 MCP 方法处理器: {method}")

    async def send(self, request: MCPRequest, timeout: float = 30.0) -> MCPResponse:
        """发送请求并等待响应

        Args:
            request: MCP 请求
            timeout: 超时秒数

        Returns:
            MCP 响应

        Raises:
            asyncio.TimeoutError: 超时
        """
        future: asyncio.Future[MCPResponse] = asyncio.Future()

        # 创建临时响应处理器
        async def _response_handler(req: MCPRequest) -> MCPResponse:
            if req.id == request.id:
                # 这是一个响应，设置 future 结果
                response = MCPResponse(
                    id=req.id,
                    result=req.params.get("result"),
                    error=req.params.get("error"),
                )
                if not future.done():
                    future.set_result(response)
            return MCPResponse(id=req.id, result={"status": "ok"})

        # 注册临时处理器
        response_method = f"response/{request.id}"
        self.register_handler(response_method, _response_handler)

        try:
            # 处理请求
            handler = self._handlers.get(request.method)
            if handler:
                response = await handler(request)
                if not future.done():
                    future.set_result(response)
            else:
                future.set_result(
                    MCPResponse(
                        id=request.id,
                        error={"code": -32601, "message": f"方法未找到: {request.method}"},
                    )
                )

            # 等待响应（带超时）
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.unregister_handler(response_method)

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """发布事件到主题

        Args:
            topic: 事件主题
            data: 事件数据
        """
        subscribers = self._subscribers.get(topic, [])
        if not subscribers:
            return

        request = MCPRequest(
            method="event/publish",
            params={"topic": topic, "data": data},
        )

        results = await asyncio.gather(
            *[handler(request) for handler in subscribers],
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"订阅者 {i} 处理事件 {topic} 失败: {result}")

    def subscribe(self, topic: str, handler: MessageHandler) -> None:
        """订阅事件主题

        Args:
            topic: 事件主题
            handler: 事件处理函数
        """
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.debug(f"订阅事件主题: {topic}")

    def unsubscribe(self, topic: str, handler: MessageHandler) -> None:
        """取消订阅"""
        subscribers = self._subscribers.get(topic, [])
        if handler in subscribers:
            subscribers.remove(handler)

    async def list_tools(self, agent_name: str = "") -> list[dict[str, Any]]:
        """查询可用工具列表

        Args:
            agent_name: 指定 Agent，为空则查询所有

        Returns:
            工具定义列表
        """
        request = MCPRequest(
            method="tools/list",
            params={"agent": agent_name},
        )
        response = await self.send(request)
        if response.error:
            logger.error(f"查询工具列表失败: {response.error}")
            return []
        return response.result.get("tools", []) if response.result else []

    async def listen(self) -> None:
        """启动消息监听循环"""
        self._running = True
        logger.info("MCP 消息总线已启动")
        while self._running:
            try:
                request = await asyncio.wait_for(
                    self._request_queue.get(), timeout=1.0
                )
                asyncio.create_task(self._dispatch(request))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"MCP 总线监听异常: {e}")

    async def _dispatch(self, request: MCPRequest) -> None:
        """分发请求到对应处理器"""
        handler = self._handlers.get(request.method)
        if handler:
            try:
                response = await handler(request)
                await self._response_queue.put(response)
            except Exception as e:
                logger.error(f"处理 MCP 请求 {request.method} 失败: {e}")
                error_response = MCPResponse(
                    id=request.id,
                    error={"code": -32603, "message": f"内部错误: {e}"},
                )
                await self._response_queue.put(error_response)
        else:
            logger.warning(f"未找到方法处理器: {request.method}")
            error_response = MCPResponse(
                id=request.id,
                error={"code": -32601, "message": f"方法未找到: {request.method}"},
            )
            await self._response_queue.put(error_response)

    async def close(self) -> None:
        """关闭消息总线"""
        self._running = False
        self._handlers.clear()
        self._subscribers.clear()
        logger.info("MCP 消息总线已关闭")