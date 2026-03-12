# peer-protocol

基于 aiohttp 的 WebSocket 双向通信库，支持服务端广播、客户端断线重连。

## 特性

- **服务端**：WebSocket 服务、多客户端广播、自动清理断线连接
- **客户端**：断线自动重连、TCP 探活、统一生命周期回调
- **类型提示**：connect/disconnect 泛型，便于静态检查

## 安装

```bash
pip install peer-protocol
```

## 快速开始

### 服务端

```python
import asyncio
from peer_protocol import Server

async def main():
    server = Server(host="0.0.0.0", port=8080)

    @server.on_receive
    async def _(payload):
        # 收到任意客户端消息时广播给所有客户端
        await server.broadcast(payload)

    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### 客户端

```python
import asyncio
from peer_protocol import Client

async def main():
    # 需包含 /ws 路径
    client = Client(url="http://127.0.0.1:8080/ws")

    @client.on_connect
    async def _(ws):
        await client.send({"type": "hello", "message": "world"})

    @client.on_receive
    async def _(payload):
        print("收到:", payload)
        await client.stop()  # 收到消息后退出

    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## API 概览

### Server

| 参数/方法 | 说明 |
|----------|------|
| `Server(host="0.0.0.0", port=8080, heartbeat=120)` | 创建服务端 |
| `await server.start()` | 启动服务 |
| `await server.stop()` | 停止服务 |
| `await server.run()` | 启动并阻塞直到 `stop()` |
| `await server.broadcast(payload)` | 广播 JSON 数据到所有客户端 |
| `on_start`, `on_stop` | 启动/停止回调 |
| `on_connect`, `on_disconnect` | 连接/断开回调，参数为 `WebSocketResponse` |
| `on_send`, `on_receive` | 发送/接收消息回调 |

### Client

| 参数/方法 | 说明 |
|----------|------|
| `Client(url, retry_interval=2, retry_timeout=5)` | 创建客户端 |
| `await client.start()` | 启动并开始重连 |
| `await client.stop()` | 停止 |
| `await client.run()` | 启动并阻塞直到 `stop()` |
| `await client.send(payload)` | 发送 JSON 数据 |
| `client.connected` | 是否已连接 |
| `on_start`, `on_stop` | 启动/停止回调 |
| `on_connect`, `on_disconnect` | 连接/断开回调，参数为 `ClientWebSocketResponse` |
| `on_send`, `on_receive` | 发送/接收消息回调 |

## 运行示例

```bash
# 终端 1：启动服务端
python -m examples.server

# 终端 2：启动客户端
python -m examples.client
```