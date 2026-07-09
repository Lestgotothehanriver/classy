from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChatRoom, ChatMessage, Image
from config.apps.notification.models import DeviceToken
from .serializers import ChatRoomListSerializer, ChatRoomSerializer, ChatMessageSerializer
from rest_framework.views import APIView
from config.apps.block.utils import get_blocked_user_ids



class ChatRoomViewSet(viewsets.ModelViewSet):
    """
    URL: /chatrooms/
    URL: /chatrooms/<pk>/
    URL: /chatrooms/<pk>/like/
    URL: /chatrooms/<pk>/message/
    URL: /chatrooms/<pk>/mute/
    URL: /chatrooms/<pk>/out/
    URL: /chatrooms/<pk>/read/<msg_id>/

    1:1 과외 문의 및 상담을 위한 '채팅방(ChatRoom)'을 관리하는 API ViewSet입니다.

    GET /chatrooms/ 요청 시 본인이 참여 중인 전체 활성 채팅방 목록을 조회하며 차단한 유저의 방은 배제합니다.
    GET /chatrooms/<pk>/ 요청 시 특정 채팅방의 상세 정보와 이전 대화 메시지 내역을 조회합니다.
    POST /chatrooms/<pk>/message/ 요청 시 텍스트나 사전에 업로드한 이미지 ID들을 첨부하여 상대방에게 전송합니다.
    POST /chatrooms/<pk>/read/<msg_id>/ 요청 시 특정 메시지를 읽은 사람 목록에 자신을 추가합니다.
    DELETE /chatrooms/<pk>/out/ 요청 시 채팅방을 삭제하고 퇴장합니다.
    POST /chatrooms/<pk>/like/ 요청 시 특정 채팅방을 찜 목록에 추가하거나 취소합니다.
    POST /chatrooms/<pk>/mute/ 요청 시 채팅방의 알림 수신 상태를 음소거로 변경하거나 취소합니다.

    Path Parameters:
        pk (int): 대상 채팅방 ID.
        msg_id (int): 읽음 처리할 메시지 ID.

    Query Parameters:
        role (str, optional): 'student' | 'instructor' 필터링 역할.

    Request Body (POST /chatrooms/<pk>/message/):
        text (str, optional): 전송할 메시지 내용.
        img_ids (list[int], optional): 사전 업로드된 이미지 파일 ID 목록.

    Returns:
        Response (GET /chatrooms/): List[ChatRoomListSerializer] 데이터
        Response (GET /chatrooms/<pk>/): ChatRoomSerializer 데이터
        Response (POST /chatrooms/<pk>/message/): ChatMessageSerializer 데이터
        Response (POST /chatrooms/<pk>/read/<msg_id>/): {
            "read_count": int
        }
        Response (POST /chatrooms/<pk>/like/): {
            "is_liked": bool
        }
        Response (POST /chatrooms/<pk>/mute/): {
            "is_muted": bool
        }
        Response (DELETE /chatrooms/<pk>/out/): {
            "message": "채팅방을 삭제하고 나갔습니다."
        }
    """

    queryset = ChatRoom.objects.all()  # 기본적으로 전체 방을 가져오지만 아래 get_queryset에서 필터링함
    permission_classes = [permissions.IsAuthenticated]  # 로그인한 사람만 접근 가능
    serializer_class = ChatRoomSerializer  # 기본 직렬화 클래스

    def get_serializer_class(self):
        if self.action == "list":
            return ChatRoomListSerializer

        elif self.action == "retrieve":
            return ChatRoomSerializer

        return self.serializer_class  

    def paginate_queryset(self, queryset):
        if self.action == 'list':  # list일 때만 페이지네이션 끄기
            return None
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        """
        오버라이딩: 전체 방이 아닌,
        현재 로그인한 유저가 '참여자'로 들어있는 방만 필터링해서 보여줌.
        차단된 사용자와의 채팅방은 제외하고 반환합니다.
        GET 요청 시 자동으로 호출됨. 
        GET: /api/chatrooms/
        GET: /api/chatrooms/3
        """
        role = self.request.query_params.get('role')
        from django.db.models import Q
        
        qs = ChatRoom.objects.all()
        
        blocked_user_ids = get_blocked_user_ids(self.request.user)
        if blocked_user_ids:
            # 상대방(학생 혹은 강사)이 차단된 경우 제외
            qs = qs.exclude(
                Q(student__user_id__in=blocked_user_ids) |
                Q(instructor__user_id__in=blocked_user_ids)
            )

        if role == 'student':
            return qs.filter(student__user=self.request.user)
        elif role == 'instructor':
            return qs.filter(instructor__user=self.request.user)

        return qs.filter(
            Q(student__user=self.request.user) | Q(instructor__user=self.request.user)
        )

    # perform_create는 삭제합니다 (Room 생성은 이제 tutoring 뷰에서 처리)

    #_______________________________________________________________________
    #  메시지 전송 기능 (텍스트 + 파일 첨부 가능)
    #_______________________________________________________________________
    @action(detail=True, methods=["post"])
    def message(self, request, pk=None):
        """
        POST /chatrooms/<pk>/message/
        특정 채팅방에 메시지를 보냄 (텍스트 or 첨부파일 포함 가능)
        
        Request:
        {
            "text": "안녕하세요",
            "img_ids": [1, 2]
        }
        
        Response (201):
        {
            "id": 10,                      // int
            "room": 1,                     // int
            "sender": 9,                   // int
            "text": "안녕하세요",             // string (nullable)
            "created_at": "2026-03-04T12:00:00Z", // date string
            "images": ["/media/abc.jpg"]   // list of strings (urls)
        }
        """
        room = self.get_object()  # 채팅방 가져오기 (pk 기준)

        # 0. 수락 전 가드 로직
        if not room.is_accepted and room.initiated_by_id == request.user.id:
            return Response({"error": "상대방이 수락하기 전까지 메시지를 보낼 수 없습니다."}, status=status.HTTP_403_FORBIDDEN)

        ser = ChatMessageSerializer(data=request.data)  # 메시지 데이터 받기
        ser.is_valid(raise_exception=True)  # 유효성 검사 (에러 나면 바로 응답 종료)
        
        # 1. 메시지 저장
        message_obj = ser.save(room=room, sender=request.user)  # 메시지 저장 + 보낸 사람 지정
        
        # 2. 넘겨받은 img_ids 배열이 있다면 해당 Image 모델들의 message를 현재 메시지로 매핑
        img_ids = request.data.get("img_ids", [])
        if img_ids:
            Image.objects.filter(id__in=img_ids).update(message=message_obj)
            
        # 2.5. 수락 로직 (상대방이 첫 답장을 보내면 수락 처리)
        if not room.is_accepted and room.initiated_by_id and room.initiated_by_id != request.user.id:
            room.is_accepted = True
            room.save(update_fields=['is_accepted'])
            # 제안자에게 수락 알림
            from config.apps.notification.helpers import notify_tutoring_accept
            notify_tutoring_accept(room, acceptor=request.user)
            
        # 3. 이미지가 매핑된 최신 상태로 다시 직렬화해서 응답
        updated_ser = ChatMessageSerializer(message_obj)
        return Response(updated_ser.data, status=200)

    #_______________________________________________________________________
    # 👇 메시지 읽음 처리 기능 (읽은 사람 목록에 추가)
    #_______________________________________________________________________
    @action(detail=True, methods=["post"], url_path="read/(?P<msg_id>[^/.]+)")
    def read(self, request, pk=None, msg_id=None):
        """
        POST /chatrooms/<pk>/read/<msg_id>/
        특정 메시지를 읽은 걸로 처리함 (읽은 사람 목록에 현재 유저 추가)
        
        Response (200):
        {
            "read_count": 2                // int
        }
        """
        # 해당 방의 해당 메시지 가져오기
        msg = ChatMessage.objects.filter(pk=msg_id, room_id=pk).first()
        if not msg:
            return Response(status=404)  # 메시지 없으면 404 응답

        # 읽은 사람 목록에 현재 유저 추가
        msg.read_by.add(request.user)

        # 현재까지 몇 명이 읽었는지 숫자로 응답
        return Response({"read_count": msg.read_by.count()}, status=200)

    @action(detail=True, methods=["delete"])
    def out(self, request, pk=None):
        """
        DELETE /chatrooms/<pk>/out/
        현재 유저가 채팅방 나가기를 누르면 방을 삭제함 (또는 기능 변경).
        
        Response (200):
        {
            "message": "채팅방을 삭제하고 나갔습니다." // string
        }
        """
        room = self.get_object()
        room.delete()

        return Response({"message": "채팅방을 삭제하고 나갔습니다."}, status=200)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        room = self.get_object()
        if room.liked_by.filter(pk=request.user.pk).exists():
            room.liked_by.remove(request.user)
            return Response({"is_liked": False}, status=200)
        else:
            room.liked_by.add(request.user)
            return Response({"is_liked": True}, status=200)

    @action(detail=True, methods=["post"])
    def mute(self, request, pk=None):
        room = self.get_object()
        if room.muted_by.filter(pk=request.user.pk).exists():
            room.muted_by.remove(request.user)
            return Response({"is_muted": False}, status=200)
        else:
            room.muted_by.add(request.user)
            return Response({"is_muted": True}, status=200)

class ImageUploadView(APIView):
    """
    URL: /images/

    채팅방 내 메시지에 첨부될 '이미지 파일(Image)'을 사전 업로드하는 API View입니다.

    POST 요청 시 하나 이상의 이미지 파일을 수신하여 Image 레코드로 저장하고, 이후 메시지 발송 API에 첨부할 수 있도록 업로드된 이미지들의 고유 ID 리스트를 반환합니다.

    Request Body (Multipart):
        images (File): 업로드할 이미지 파일 (다중 첨부 가능).

    Returns:
        Response: {
            "image_ids": List[int]
        }
    """

    permission_classes = [permissions.IsAuthenticated]  # 로그인한 사람만 접근 가능

    def post(self, request):
        """
        POST /images/  (urls.py 설정 기준 /api/chat/images/ 등)
        이미지 파일을 받아서 저장하고 URL 반환
        
        Request (multipart/form-data):
        - images: <FILE> (여러 개 가능)
        
        Response (201):
        {
            "image_ids": [1, 2]            // list of ints
        }
        """
        if 'images' not in request.FILES:
            return Response({"error": "이미지 파일이 필요합니다."}, status=400)

        images = request.FILES.getlist('images')
        img_ids = []
        for image in images:
            img = Image.objects.create(image=image)
            img_ids.append(img.id)
        
        return Response({"image_ids": img_ids}, status=200)

class DeviceTokenView(APIView):
    """
    URL: /device-token/

    FCM 푸시 알림 전송용 '디바이스 토큰(DeviceToken)' 정보를 조회 및 갱신하는 API View입니다.

    GET 요청 시 현재 로그인한 유저의 최신 디바이스 토큰의 푸시 동의 및 활성화 여부를 조회합니다.
    POST 요청 시 최신 단말 토큰 정보를 등록받아 생성 및 갱신하며, 타 유저가 이전에 쓰던 중복 토큰이 있을 경우 즉시 삭제합니다.
    PUT 요청 시 등록된 토큰의 푸시 활성 여부(is_active)를 토글(True/False)합니다.

    Request Body (POST):
        token (str): FCM 디바이스 토큰 문자열 (필수).
        platform (str, optional): 디바이스 플랫폼 종류 (기본값 'android').

    Returns:
        Response (GET): {
            "is_active": bool
        }
        Response (POST): {
            "ok": True,
            "id": int
        }
        Response (PUT): {
            "ok": True
        }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        token = DeviceToken.objects.filter(user=request.user).order_by("-updated_at").first()
        if not token:
            return Response({"error": "디바이스 토큰이 없습니다."}, status=404)

        return Response({
            "is_active": token.is_active
        }, status=200)

    def post(self, request):
        """
        POST /device-token/
        디바이스 토큰을 저장하거나 업데이트합니다.
        
        Request:
        {
            "token": "abc123efg...",
            "platform": "ios"
        }
        
        Response (200/201):
        {
            "ok": true,                    // boolean
            "id": 1                        // int
        }
        """
        token = request.data.get("token")
        if not token:
            return Response({"error": "토큰이 필요합니다."}, status=400)
        platform = request.data.get("platform", "android")

        # 다른 유저가 사용하던 동일한 토큰은 삭제
        DeviceToken.objects.filter(token=token).exclude(user=request.user).delete()

        obj, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={"user": request.user, "platform": platform, "is_active": True}
        )
        return Response({"ok": True, "id": obj.id}, status=200)

    def put(self, request):
        tokens = DeviceToken.objects.filter(user=request.user)
        if not tokens.exists():
            return Response({"error": "디바이스 토큰이 없습니다."}, status=404)

        token_status = tokens.first().is_active
        token_status = not token_status
        tokens.update(is_active=token_status) 
        return Response({"ok": True}, status=200)

class ChatNotificationToggleView(APIView):
    """
    URL: /chat-notification/

    채팅 관련 알림 수신 동의 여부만 독립적으로 수정하는 API View입니다.

    PUT 요청 시 현재 로그인한 사용자의 DeviceToken 내역을 확인하고, 다른 푸시 알림과 무관하게 오직 1:1 채팅 메시지 푸시 알림 상태(is_chat_active) 값만 반전(토글)합니다.

    Returns:
        Response: {
            "is_chat_active": bool
        }
    """
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        tokens = DeviceToken.objects.filter(user=request.user)
        if not tokens.exists():
            return Response({"error": "등록된 디바이스 토큰이 없습니다. 먼저 토큰을 등록해 주세요."}, status=400)
        
        new_state = not tokens.first().is_chat_active
        tokens.update(is_chat_active=new_state)
        return Response({"is_chat_active": new_state}, status=200)

