import asyncio
import websockets

async def test():
    uri = "ws://localhost:8000/ws/chat/1/"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"Error connecting: Invalid status code {e.status_code}")
    except Exception as e:
        print("Error connecting:", e)

asyncio.run(test())
