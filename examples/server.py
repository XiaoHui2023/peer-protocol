import asyncio
import logging

from peer_protocol.server import Server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

async def main():
    server = Server(host="0.0.0.0", port=8080)

    @server.on_receive
    async def _(payload):
        await server.broadcast(payload)

    await server.run()

if __name__ == "__main__":
    asyncio.run(main())