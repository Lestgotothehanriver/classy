from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChatRoom, ChatMessage, Image, UserDeviceToken
from .serializers import ChatRoomListSerializer, ChatRoomSerializer, ChatMessageSerializer
from rest_framework.views import APIView



class ChatRoomViewSet(viewsets.ModelViewSet):
    """
    채팅방 관련 API
    GET /chatrooms/?role=student      : 참여 중인 채팅방 목록
    GET /chatrooms/<pk>/ : 채팅방 상세 정보 (메시지 이력 포함)

    Response (GET /chatrooms/):
    [
        {
            "id": 1,                       // int
            "title": "과외 문의",               // string (nullable)
            "instructor": 5,               // int
            "student": 9,                  // int
            "post_id": 101,                // int
            "created_at": "2026-03-04T12:00:00Z", // date string
            "last_message": "안녕하세요"         // string (nullable)
        }
    ]
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
        GET 요청 시 자동으로 호출됨. 
        GET: /api/chatrooms/
        GET: /api/chatrooms/3
        """
        role = self.request.query_params.get('role')
        if role == 'student':
            return ChatRoom.objects.filter(student__user=self.request.user)
        elif role == 'instructor':
            return ChatRoom.objects.filter(instructor__user=self.request.user)

        from django.db.models import Q
        return ChatRoom.objects.filter(
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
        ser = ChatMessageSerializer(data=request.data)  # 메시지 데이터 받기
        ser.is_valid(raise_exception=True)  # 유효성 검사 (에러 나면 바로 응답 종료)
        
        # 1. 메시지 저장
        message_obj = ser.save(room=room, sender=request.user)  # 메시지 저장 + 보낸 사람 지정
        
        # 2. 넘겨받은 img_ids 배열이 있다면 해당 Image 모델들의 message를 현재 메시지로 매핑
        img_ids = request.data.get("img_ids", [])
        if img_ids:
            Image.objects.filter(id__in=img_ids).update(message=message_obj)
            
        # 3. 이미지가 매핑된 최신 상태로 다시 직렬화해서 응답
        updated_ser = ChatMessageSerializer(message_obj)
        return Response(updated_ser.data, status=201)

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
        return Response({"read_count": msg.read_by.count()})

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

        return Response({"message": "채팅방을 삭제하고 나갔습니다."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        """
        POST /chatrooms/<pk>/like/
        찜 토글. 이미 찜했으면 취소, 아니면 추가.

        Response (200):
        {
            "is_liked": true   // boolean
        }
        """
        room = self.get_object()
        user = request.user
        if room.liked_by.filter(pk=user.pk).exists():
            room.liked_by.remove(user)
            return Response({"is_liked": False})
        else:
            room.liked_by.add(user)
            return Response({"is_liked": True})

    @action(detail=True, methods=["post"])
    def mute(self, request, pk=None):
        """
        POST /chatrooms/<pk>/mute/
        채팅방 알림 뮤트 토글.

        Response (200):
        {
            "is_muted": true   // boolean
        }
        """
        room = self.get_object()
        user = request.user
        if room.muted_by.filter(pk=user.pk).exists():
            room.muted_by.remove(user)
            return Response({"is_muted": False})
        else:
            room.muted_by.add(user)
            return Response({"is_muted": True})

class ImageUploadView(APIView):
    """
    채팅방 메시지에 첨부할 이미지를 업로드하는 API.
    POST 요청으로 이미지 파일을 받음.
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
            return Response({"error": "이미지 파일이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        images = request.FILES.getlist('images')
        img_ids = []
        for image in images:
            img = Image.objects.create(image=image)
            img_ids.append(img.id)
        
        return Response({"image_ids": img_ids}, status=status.HTTP_201_CREATED)

class DeviceTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /device-token/
        현재 로그인한 사용자의 디바이스 토큰 상태를 조회합니다
        
        Response (200):
        {
            "is_active": true              // boolean
        }
        """
        token = UserDeviceToken.objects.filter(user=request.user).first()
        if not token:
            return Response({"error": "디바이스 토큰이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "is_active": token.is_active
        })

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
            return Response({"error": "토큰이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        platform = request.data.get("platform", "a")

        if UserDeviceToken.objects.filter(user=request.user, is_active=True).exists() or not UserDeviceToken.objects.filter(user=request.user).exists():
            obj, created = UserDeviceToken.objects.update_or_create(
                user=request.user,
                defaults={"token": token, "platform": platform, "is_active": True}
            )
        # platform: ios, android
        return Response({"ok": True, "id": obj.id})

    def put(self, request):
        """
        PUT /device-token/
        단말 토큰 상태 변경 (is_active 상태 토글)
        
        Response (200):
        {
            "ok": true                     // boolean
        }
        """
        token_status = UserDeviceToken.objects.get(user=request.user).is_active 
        token_status = not token_status
        UserDeviceToken.objects.filter(user=request.user).update(is_active=token_status) 
        return Response({"ok": True}, status=status.HTTP_200_OK)


        
        
