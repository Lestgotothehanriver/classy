import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .models import ChatRoom, ChatMessage, Image
from .serializers import ChatMessageSerializer

from urllib.parse import parse_qs
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache


class ChatConsumer(AsyncWebsocketConsumer):
    """
    📡 WebSocket 채팅 Consumer

    ── 클라이언트 → 서버 예시 ──
      { "type": "message", "text": "안녕", "attachment": null }
      { "type": "read",    "msg_id": 123 }

    ── 서버 → 클라이언트 브로드캐스트 예시 ──
      { "event": "message", ...serialized ChatMessage... }
      { "event": "read",    "msg_id": 123, "user_id": 7, "read_count": 2 }
    """
    

    # ────────────────────────── 연결 / 종료 ──────────────────────────
    async def connect(self):
        # URL 예: /ws/chat/5/ → room_id = 5
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_grp = f"chat_{self.room_id}"
        query_string = self.scope["query_string"].decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if not token_key:
            # 헤더에서 토큰 추출 시도
            headers = dict(self.scope.get("headers", []))
            print("HEADERS:", headers)
            auth_header = headers.get(b"authorization", b"").decode()
            print("AUTH HEADER:", auth_header)
            if auth_header.lower().startswith("token "):
                token_key = auth_header.split(" ")[1]

        print("TOKEN KEY:", token_key)
        self.user = await self.get_user_from_token(token_key)
        print("USER:", getattr(self.user, "is_anonymous", True), getattr(self.user, "id", None))

        # 비로그인 사용자는 거부
        if getattr(self.user, "is_anonymous", True):  # isinstance(self.user, AnonymousUser) 확인보다 안전함
            print("REJECTING: Anonymous user")
            await self.close()
            return

        # 방 참가자가 아니면 거부
        in_room = await self.user_in_room()
        print("USER IN ROOM:", in_room)
        if not in_room:
            print("REJECTING: User not in room")
            await self.close()
            return

        # 그룹 등록 후 연결 수락
        # channel_layer.group_add 함수는, 그룹 이름을 첫 번째 인자로 받고,
        # 해당 이름의 그룹이 존재하지 않는다면 새로 생성, 이미 존재한다면 그룹에 추가합니다.
        # 두 번째 인자는 현재 WebSocket 연결의 채널 이름입니다.
        # channel은 유저마다 완벽히 독립된 것으로, 서버가 웹소켓 연결 하나를 식별하는 고유한 이름입니다.

        await self.channel_layer.group_add(self.room_grp, self.channel_name)
        await self.accept()

        cur = self._get_online_set(self.room_id)
        cur.add(self.user.id)  # 현재 유저 ID를 온라인 목록에 추가
        self._save_online_set(self.room_id, cur)

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.room_grp, self.channel_name)
        # 연결 종료 시, 현재 유저를 온라인 목록에서 제거
        cur = self._get_online_set(self.room_id)
        if self.user and getattr(self.user, 'id', None) in cur:
            cur.remove(self.user.id)
            self._save_online_set(self.room_id, cur)

    # ────────────────────────── 수신 메시지 처리 ──────────────────────────
    async def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data or "{}")

        if data.get("type") == "message":
            msg = await self.save_message(
                text=data.get("text", ""),
            )
            msg_id = msg.get("id")
            img_ids = data.get("img_ids")
            img_urls = await self.save_image(img_ids, msg_id) if img_ids else []

            # 같은 방 유저들에게 브로드캐스트
            await self.channel_layer.group_send(
                self.room_grp,
                {"type": "chat_message", "msg": msg, "img_urls": img_urls}
            )


        elif data.get("type") == "read":
            msg_id = data.get("msg_id")
            read_cnt = await self.add_read(msg_id)
            await self.channel_layer.group_send(
                self.room_grp,
                {
                    "type": "chat_read",
                    "msg_id": msg_id,
                    "user_id": self.user.id,
                    "read_count": read_cnt,
                },
            )

    # ────────────────────────── DB I/O (sync → async) ──────────────────────────

    PRESENCE_KEY = "chat:room:{room_id}:online"
    PRESENCE_TTL = 60 * 60 * 24  # 24h (원하면 조절)

    def _presence_key(self, room_id: int) -> str:
        """
        채팅방의 온라인 유저를 저장할 Redis 키 생성
        """
        return self.PRESENCE_KEY.format(room_id=room_id)

    def _get_online_set(self, room_id: int):
        """
        채팅방의 온라인 유저를 저장할 Redis Set 객체 반환
        """
        return set(cache.get(self._presence_key(room_id)) or [])

    def _save_online_set(self, room_id: int, s: set) -> None:
        """
        채팅방의 온라인 유저를 Redis에 저장
        """
        cache.set(self._presence_key(room_id), list(s), timeout = self.PRESENCE_TTL)

    @database_sync_to_async
    def user_in_room(self) -> bool:
        from django.db.models import Q
        return ChatRoom.objects.filter(
            Q(pk=self.room_id) & (Q(student__user=self.user) | Q(instructor__user=self.user))
        ).exists()

    @database_sync_to_async
    def save_message(self, text: str,):
        msg = ChatMessage.objects.create(
            room_id=self.room_id,
            sender=self.user,
            text=text,
        )
        return ChatMessageSerializer(msg).data

    @database_sync_to_async
    def add_read(self, msg_id: int) -> int:
        """
        msg_id 이하(포함) 모든 메시지에 self.user를 read_by에 추가.
        반환: msg_id 메시지의 read_count
        """
        qs = ChatMessage.objects.filter(room_id=self.room_id, pk__lte=msg_id)
        for m in qs.exclude(read_by=self.user):
            m.read_by.add(self.user)

        latest = qs.filter(pk=msg_id).first()
        return latest.read_by.count() if latest else 0

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        try:
            token = Token.objects.get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return AnonymousUser()

    @database_sync_to_async
    def save_image(self, image_ids, message_id):
        """
        이미지 ID 목록을 받아서 해당 이미지들에 대해 message 필드를 설정합니다.
        """
        images = Image.objects.filter(id__in=image_ids)
        message = ChatMessage.objects.get(id=message_id)
        img_urls = [img.image.url for img in images]
        for img in images:
            img.message = message
            img.save()

        return img_urls

    # ────────────────────────── 그룹 → 클라이언트 전송 ──────────────────────────
    async def chat_message(self, event):
        await self.send(json.dumps({
            "event": "message",
            **event["msg"],
            "img_urls": event.get("img_urls", [])
        }))

    async def chat_read(self, event):
        await self.send(json.dumps({
            "event": "read",
            "msg_id": event["msg_id"],
            "user_id": event["user_id"],
            "read_count": event["read_count"]
        }))
        
    


# -----------------------------------------------
# 1. AsyncWebsocketConsumer
# -----------------------------------------------
# - Django Channels에서 제공하는 "비동기 WebSocket 처리 클래스"
# - WebSocket 연결 / 메시지 수신 / 연결 종료를 담당
# - asyncio 기반이므로 async/await 문법 사용 가능
#
# 비유:
#   -> 카카오톡 서버에서 채팅방 매니저 역할
#   -> connect() = 유저 입장, receive() = 메시지 처리, disconnect() = 퇴장
#
# 장점:
#   1) 비동기 지원으로 동시에 많은 연결 처리 가능
#   2) 그룹 브로드캐스팅 기능 제공 (여러 클라이언트 동시 메시지 전송)
#   3) asyncio 이벤트 루프에서 동작 → await로 비동기 함수 호출 가능
#
# 주의:
#   - DB ORM 접근은 동기 코드이므로, 직접 호출하면 이벤트 루프가 멈출 수 있음
#     (→ @database_sync_to_async로 감싸야 함)
# -----------------------------------------------

# -----------------------------------------------
# 2. @database_sync_to_async
# -----------------------------------------------
# - 비동기 코드(AsyncWebsocketConsumer)에서 동기 코드(Django ORM 등)를 안전하게 실행하게 해주는 데코레이터
# - 동기 함수를 스레드 풀(ThreadPoolExecutor)에서 실행하여 이벤트 루프가 멈추지 않도록 함
#
# 동작 원리:
#   (1) async 함수에서 ORM 직접 호출 시 → 이벤트 루프 블로킹 (서버 전체 지연 가능)
#   (2) @database_sync_to_async로 감싸면 → 별도 스레드에서 동작 후 결과 반환
#   (3) async 함수에서 await로 결과를 안전하게 받을 수 있음
#
# 사용 예:
#   @database_sync_to_async
#   def get_user_by_token(token):
#       return User.objects.get(auth_token=token)
# -----------------------------------------------