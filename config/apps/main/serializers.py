from rest_framework import serializers
from config.apps.accounts.models import Instructor, Student
from config.apps.tutoring.constant import STUDENT_SUBJECT_CHOICES
from django.db.models import Avg

class StudentMainTutorSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.user_name', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    region = serializers.CharField(source='user.region', read_only=True)
    sex = serializers.CharField(source='user.sex', read_only=True)
    birth_date = serializers.DateField(source='user.birth_date', read_only=True)
    # subjects replaces subject_numbers with actual names
    subjects = serializers.SerializerMethodField()
    subject_numbers = serializers.SerializerMethodField()
    average_rate = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    is_liked = serializers.BooleanField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Instructor
        fields = [
            'id', 'user_name', 'first_name', 'last_name', 
            'university', 'department', 'subjects', 'subject_numbers', 
            'average_rate', 'profile_image',
            'region', 'student_number', 'sex', 'birth_date', 'is_liked', 'like_count'
        ]

    def get_subjects(self, obj):
        subject_dict = dict(STUDENT_SUBJECT_CHOICES)
        return [subject_dict.get(s.number, str(s.number)) for s in obj.subjects.all()]

    def get_subject_numbers(self, obj):
        return list(obj.subjects.values_list('number', flat=True))

    def get_average_rate(self, obj):
        # average of professionalism, teaching_skill, punctuality from InstructorReview
        reviews = obj.instructor_reviews.all()
        if not reviews.exists():
            return 0.0
        
        # Calculate the average across all three fields. 
        # For each review, the score is (prof + teach + punc)/3.
        # So overall is the average of those scores.
        avg_scores = reviews.aggregate(
            p=Avg('professionalism'),
            t=Avg('teaching_skill'),
            c=Avg('punctuality')
        )
        total_avg = (avg_scores['p'] + avg_scores['t'] + avg_scores['c']) / 3.0
        return round(total_avg, 2)

    def get_profile_image(self, obj):
        if obj.user.profile_image:
            return obj.user.profile_image.url
        return None

class InstructorMainStudentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.user_name', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    subjects = serializers.SerializerMethodField()
    subject_numbers = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    post_id = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ['id', 'user_name', 'first_name', 'last_name', 'subjects', 'subject_numbers', 'profile_image', 'post_id']

    def get_subjects(self, obj):
        subject_dict = dict(STUDENT_SUBJECT_CHOICES)
        return [subject_dict.get(s.number, str(s.number)) for s in obj.subjects.all()]

    def get_subject_numbers(self, obj):
        return list(obj.subjects.values_list('number', flat=True))

    def get_profile_image(self, obj):
        if obj.user.profile_image:
            return obj.user.profile_image.url
        return None

    def get_post_id(self, obj):
        post = obj.tutoring_posts.filter(is_active=True).order_by('-created_at').first()
        return post.id if post else None
        
