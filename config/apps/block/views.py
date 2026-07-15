from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import Block
from .serializers import BlockSerializer

class BlockViewSet(viewsets.ModelViewSet):
    """
    URL: /blocks/
    URL: /blocks/<pk>/

    유저 차단 목록(Block)을 관리하는 API ViewSet입니다.

    GET /blocks/ 요청 시 본인의 전체 차단 유저 리스트를 조회하고, POST /blocks/ 요청 시 입력받은 상대 유저 ID(blocked_user)를 차단 등록합니다.
    DELETE /blocks/<pk>/ 요청 시 등록되었던 차단 관계를 해제(삭제)합니다.

    Path Parameters:
        pk (int): 해제할 차단 관계의 ID.

    Request Body (POST):
        blocked_user (int): 차단할 상대방 유저 ID.

    Returns:
        Response (GET): List[BlockSerializer] 데이터
        Response (POST): BlockSerializer 데이터 (HTTP 201 Created)
        Response (DELETE): HTTP 204 No Content
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BlockSerializer
    pagination_class = None

    def get_queryset(self):
        return Block.objects.filter(user=self.request.user).select_related("blocked_user")

    def create(self, request, *args, **kwargs):
        blocked_user_id = request.data.get('blocked_user')
        if not blocked_user_id:
            return Response({"error": "blocked_user is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        if Block.objects.filter(user=request.user, blocked_user_id=blocked_user_id).exists():
            return Response({"error": "Already blocked"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data={"blocked_user": blocked_user_id})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
