from rest_framework import serializers
from django.db.models import Count

from config.apps.accounts.models import Subject, Instructor
from .models import Lecture, Comment, SearchHistory
from .utils import extract_video_duration_seconds, transcode_video_for_mobile_playback
from config.apps.common.serializers import AbsoluteFileField, AbsoluteImageField


# ────────────────────────────────────────────────────────────────────
# Instructor (업로더) 요약 Serializer
# ────────────────────────────────────────────────────────────────────

class LectureInstructorSerializer(serializers.ModelSerializer):
    """강의 응답에 포함되는 강사(업로더) 요약 정보.

    앱의 강의 상세/목록에서 업로더 프로필(닉네임·프로필이미지·대학·학과·학번)을
    표시하기 위해 사용합니다.
    """
    user_name = serializers.CharField(source="user.user_name", read_only=True)
    profile_image = AbsoluteImageField(source="user.profile_image", read_only=True)

    class Meta:
        model = Instructor
        fields = [
            "id", "user", "user_name",
            "university", "department", "student_number",
            "instruction", "profile_image",
        ]


# ────────────────────────────────────────────────────────────────────
# 유틸: Subject number 리스트 → M2M set
# ────────────────────────────────────────────────────────────────────
def _sync_subjects(manager, numbers):
    """Subject.number 리스트를 받아 M2M set."""
    objs = [Subject.objects.get_or_create(number=n)[0] for n in numbers]
    manager.set(objs)


# ────────────────────────────────────────────────────────────────────
# Lecture Serializers
# ────────────────────────────────────────────────────────────────────

class LectureListSerializer(serializers.ModelSerializer):
    """강의 목록 — video 필드 제외."""
    like_count = serializers.IntegerField(read_only=True, default=0)
    is_liked = serializers.BooleanField(read_only=True, default=False)
    instructor_name = serializers.CharField(source="instructor.user.user_name", read_only=True)
    instructor = LectureInstructorSerializer(read_only=True)
    subjects = serializers.SlugRelatedField(many=True, read_only=True, slug_field="number")
    thumbnail = AbsoluteImageField(read_only=True)

    class Meta:
        model = Lecture
        exclude = ["video"]


class LectureStreamSerializer(serializers.ModelSerializer):
    """스트리밍 뷰 — 절대 video URL + 기본 정보."""
    video = serializers.SerializerMethodField()

    class Meta:
        model = Lecture
        fields = ["id", "video", "title"]

    def get_video(self, obj):
        if not obj.video:
            return ""

        request = self.context.get("request")
        from config.apps.common.utils import get_absolute_media_url
        return get_absolute_media_url(obj.video, request)


class LectureDetailSerializer(serializers.ModelSerializer):
    """강의 상세 — video 제외 (스트리밍 URL은 /stream/ 엔드포인트에서만 제공)."""
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked = serializers.BooleanField(read_only=True, default=False)
    instructor = LectureInstructorSerializer(read_only=True)
    subjects = serializers.SlugRelatedField(many=True, read_only=True, slug_field="number")
    thumbnail = AbsoluteImageField(read_only=True)

    class Meta:
        model = Lecture
        exclude = ["video"]

    def get_like_count(self, obj):
        return obj.likes.count()

    def get_comment_count(self, obj):
        return obj.comments.count()


class LecturePreviewSerializer(serializers.ModelSerializer):
    """프리뷰 강의 — 같은 강사의 is_preview=True 영상."""
    subjects = serializers.SlugRelatedField(many=True, read_only=True, slug_field="number")
    video = AbsoluteFileField(read_only=True)
    thumbnail = AbsoluteImageField(read_only=True)
    instructor = LectureInstructorSerializer(read_only=True)

    class Meta:
        model = Lecture
        fields = [
            'id', 'video', 'video_duration', 'thumbnail', 'title', 
            'subjects', 'price', 'instructor', 'is_preview', 
            'view_count', 'likes', 'rental_period', 'created_at', 
            'is_active', 'is_delete', 'deleted_at'
        ]


class LectureRecommendSerializer(serializers.ModelSerializer):
    """추천 강의 — video 필드 제외, 좋아요 수 포함."""
    like_count = serializers.IntegerField(read_only=True, default=0)
    instructor = LectureInstructorSerializer(read_only=True)
    subjects = serializers.SlugRelatedField(many=True, read_only=True, slug_field="number")
    thumbnail = AbsoluteImageField(read_only=True)

    class Meta:
        model = Lecture
        exclude = ["video"]


class LectureWriteSerializer(serializers.ModelSerializer):
    """강의 생성/수정용. subjects는 Subject.number 리스트로 받는다."""
    subjects = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True
    )
    video = AbsoluteFileField(required=False)
    thumbnail = AbsoluteImageField(required=False)

    class Meta:
        model = Lecture
        exclude = ["instructor", "likes", "view_count"]

    def validate_subjects(self, value):
        if len(value) > 3:
            raise serializers.ValidationError("과목은 최대 3개까지만 선택할 수 있습니다.")
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("가격은 0 캐시 이상이어야 합니다.")
        return value

    def validate_rental_period(self, value):
        # 정책: 모든 유료 강의 대여는 30일 고정. 외부 입력값은 무시하고 항상 30으로 강제한다.
        from config.apps.cash.constants import LECTURE_RENTAL_DAYS
        return LECTURE_RENTAL_DAYS

    def _populate_video_duration(self, validated_data):
        current_duration = validated_data.get("video_duration", 0) or 0
        if current_duration > 0:
            return

        inferred_duration = extract_video_duration_seconds(validated_data.get("video"))
        if inferred_duration is not None:
            validated_data["video_duration"] = inferred_duration

    def _prepare_video_for_playback(self, validated_data):
        video = validated_data.get("video")
        if not video:
            return None

        playable_video, cleanup = transcode_video_for_mobile_playback(video)
        validated_data["video"] = playable_video
        return cleanup

    def create(self, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        cleanup = self._prepare_video_for_playback(validated_data)
        try:
            self._populate_video_duration(validated_data)
            instance = super().create(validated_data)
            if subjects_data is not None:
                _sync_subjects(instance.subjects, subjects_data)
            return instance
        finally:
            if cleanup:
                cleanup()

    def update(self, instance, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        cleanup = self._prepare_video_for_playback(validated_data)
        try:
            self._populate_video_duration(validated_data)
            instance = super().update(instance, validated_data)
            if subjects_data is not None:
                _sync_subjects(instance.subjects, subjects_data)
            return instance
        finally:
            if cleanup:
                cleanup()


# ────────────────────────────────────────────────────────────────────
# Comment Serializers
# ────────────────────────────────────────────────────────────────────

class _CommentAuthorMixin(serializers.Serializer):
    """댓글 작성자 공통 필드.

    앱에서 작성자 프로필 이미지, '내 댓글' 여부, 강사 작성 여부를 표시하기 위해
    사용합니다.
    """
    author_name = serializers.CharField(source="author.user_name", read_only=True)
    author_profile_image = AbsoluteImageField(source="author.profile_image", read_only=True)
    is_mine = serializers.SerializerMethodField()

    def get_is_mine(self, obj):
        request = self.context.get("request")
        return bool(
            request
            and request.user
            and request.user.is_authenticated
            and obj.author_id == request.user.id
        )


class CommentReplySerializer(_CommentAuthorMixin, serializers.ModelSerializer):
    """대댓글(reply) 반환용 — 중첩 없이 1단 표시."""
    referenced_person_name = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id", "author", "author_name", "author_profile_image",
            "is_mine", "content",
            "referenced_person", "referenced_person_name",
            "created_at",
        ]

    def get_referenced_person_name(self, obj):
        if obj.referenced_person:
            return obj.referenced_person.user_name
        return None


class CommentSerializer(_CommentAuthorMixin, serializers.ModelSerializer):
    """댓글 목록 — 최상위 댓글 + replies 중첩."""
    replies = CommentReplySerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id", "lecture", "author", "author_name", "author_profile_image",
            "is_mine", "content", "parent",
            "referenced_person", "created_at", "replies",
        ]


class CommentWriteSerializer(serializers.ModelSerializer):
    """댓글 생성/수정용."""

    class Meta:
        model = Comment
        fields = ["lecture", "parent", "content", "referenced_person"]

    def validate(self, attrs):
        parent = attrs.get("parent")
        lecture = attrs.get("lecture")

        if parent:
            # parent가 같은 lecture에 속해야 한다
            if parent.lecture_id != lecture.id:
                raise serializers.ValidationError(
                    {"parent": "대댓글은 같은 강의의 댓글에만 달 수 있습니다."}
                )
            # 대대댓글 금지
            if parent.parent_id is not None:
                raise serializers.ValidationError(
                    {"parent": "대댓글에 대한 답글은 허용되지 않습니다."}
                )
        return attrs


# ────────────────────────────────────────────────────────────────────
# SearchHistory Serializer
# ────────────────────────────────────────────────────────────────────

class SearchHistorySerializer(serializers.ModelSerializer):
    """검색 기록 직렬화 — student는 뷰에서 자동 할당하므로 클라이언트에 노출하지 않는다."""

    class Meta:
        model = SearchHistory
        fields = ["id", "query", "created_at"]
        read_only_fields = ["id", "created_at"]
