from rest_framework import serializers
from django.db.models import Count

from config.apps.accounts.models import Subject
from .models import Lecture, Comment


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
    instructor_name = serializers.CharField(source="instructor.user.user_name", read_only=True)

    class Meta:
        model = Lecture
        exclude = ["video"]


class LectureStreamSerializer(serializers.ModelSerializer):
    """스트리밍 뷰 — 영상 + 기본 정보."""

    class Meta:
        model = Lecture
        fields = ["id", "video", "title"]


class LectureDetailSerializer(serializers.ModelSerializer):
    """강의 상세 — 모든 필드 반환."""
    like_count = serializers.SerializerMethodField()

    class Meta:
        model = Lecture
        fields = "__all__"

    def get_like_count(self, obj):
        return obj.likes.count()


class LecturePreviewSerializer(serializers.ModelSerializer):
    """프리뷰 강의 — 같은 강사의 is_preview=True 영상."""

    class Meta:
        model = Lecture
        fields = "__all__"


class LectureRecommendSerializer(serializers.ModelSerializer):
    """추천 강의 — video 필드 제외, 좋아요 수 포함."""
    like_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Lecture
        exclude = ["video"]


class LectureWriteSerializer(serializers.ModelSerializer):
    """강의 생성/수정용. subjects는 Subject.number 리스트로 받는다."""
    subjects = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True
    )

    class Meta:
        model = Lecture
        exclude = ["instructor", "likes", "view_count"]

    def validate_subjects(self, value):
        if len(value) > 3:
            raise serializers.ValidationError("과목은 최대 3개까지만 선택할 수 있습니다.")
        return value

    def create(self, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        instance = super().create(validated_data)
        if subjects_data is not None:
            _sync_subjects(instance.subjects, subjects_data)
        return instance

    def update(self, instance, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        instance = super().update(instance, validated_data)
        if subjects_data is not None:
            _sync_subjects(instance.subjects, subjects_data)
        return instance


# ────────────────────────────────────────────────────────────────────
# Comment Serializers
# ────────────────────────────────────────────────────────────────────

class CommentReplySerializer(serializers.ModelSerializer):
    """대댓글(reply) 반환용 — 중첩 없이 1단 표시."""
    author_name = serializers.CharField(source="author.user_name", read_only=True)
    referenced_person_name = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id", "author", "author_name", "content",
            "referenced_person", "referenced_person_name",
            "created_at",
        ]

    def get_referenced_person_name(self, obj):
        if obj.referenced_person:
            return obj.referenced_person.user_name
        return None


class CommentSerializer(serializers.ModelSerializer):
    """댓글 목록 — 최상위 댓글 + replies 중첩."""
    replies = CommentReplySerializer(many=True, read_only=True)
    author_name = serializers.CharField(source="author.user_name", read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id", "lecture", "author", "author_name",
            "content", "parent", "referenced_person",
            "created_at", "replies",
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
