import asyncio
import websockets

async def test_ws():
    uri = "ws://localhost:8002/ws/chat/1/"
    headers = {
        "authorization": "Token 1bd7505a96e946da27672c44190823748f7472bc"
    }
    try:
        async with websockets.connect(uri, additional_headers=headers) as websocket:
            print("Successfully connected!")
            # await websocket.send('{"type":"message","text":"hello"}')
            # res = await websocket.recv()
            # print("Received:", res)
    except Exception as e:
        print(f"Connection failed: {e}")

asyncio.run(test_ws())
