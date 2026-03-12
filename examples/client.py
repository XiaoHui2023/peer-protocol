import asyncio
import logging

from peer_protocol.client import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

async def main():
    client = Client(url="http://127.0.0.1:8080/ws")

    @client.on_connect
    async def _(ws):
        await client.send({"type": "hello", "message": "world"})

    @client.on_receive
    async def _(payload):
        await client.stop()

    await client.run()

if __name__ == "__main__":
    asyncio.run(main())