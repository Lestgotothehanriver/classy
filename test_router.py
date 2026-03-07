import os
import django
import sys
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from channels.routing import URLRouter
from config.apps.chat_app.routing import websocket_urlpatterns

async def test():
    router = URLRouter(websocket_urlpatterns)
    scope = {"type": "websocket", "path": "/ws/chat/1/"}
    try:
        async def dummy_receive():
            return {}
        async def dummy_send(event):
            pass
        await router(scope, dummy_receive, dummy_send)
        print("Matched Route!")
    except ValueError as e:
        print("ValueError:", e)
    except Exception as e:
        traceback.print_exc()

import asyncio
if __name__ == "__main__":
    asyncio.run(test())
