import asyncio
import logging
from dataclasses import dataclass
from peer_protocol.client import Client
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

@dataclass
class A:
    type: str
    message: str

class B(BaseModel):
    name: str
    age: int

async def main():
    client = Client(url="http://127.0.0.1:8080/ws")

    @client.on_connect
    async def _(ws):
        await client.send(A(type="hello", message="world"))
        await client.send({'name': "John", 'age': 20})

    @client.on_receive
    def _(payload: A):
        print(f"A({type(payload)}): {payload}")

    @client.on_receive
    async def _(payload):
        print(f"A|B({type(payload)}): {payload}")

    @client.on_receive
    async def _(payload: B):
        print(f"B({type(payload)}): {payload}")
        await client.stop()

    await client.run()

if __name__ == "__main__":
    asyncio.run(main())