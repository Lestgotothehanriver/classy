import asyncio
import websockets

async def test():
    uri = "ws://localhost:8000/ws/chat/1/"
    headers = {
        "authorization": "Token 1bd7505a96e946da27672c44190823748f7472bc"
    }
    try:
        async with websockets.connect(uri, additional_headers=headers) as websocket:
            print("Connected with Header!")
            await websocket.send('{"type": "message", "text": "Testing Header"}')
            res = await websocket.recv()
            print("Received:", res)
    except Exception as e:
        print("Error connecting:", e)

asyncio.run(test())
