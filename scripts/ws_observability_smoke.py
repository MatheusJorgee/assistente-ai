import asyncio
import json
import websockets


async def main() -> None:
    uri = "ws://127.0.0.1:8000/runtime/events/ws"
    print("CONNECT", uri)
    async with websockets.connect(uri) as ws:
        await ws.send("ping")

        got_connection = False
        got_runtime = False

        deadline = asyncio.get_running_loop().time() + 35
        while asyncio.get_running_loop().time() < deadline and not got_runtime:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                continue

            print("MSG", msg)
            data = json.loads(msg)
            if data.get("type") == "connection":
                got_connection = True
            if data.get("type") == "runtime_event":
                got_runtime = True
                break

        print("RESULT", {"connection": got_connection, "runtime_event": got_runtime})


if __name__ == "__main__":
    asyncio.run(main())
