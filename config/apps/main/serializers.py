from rest_framework import serializers
from config.apps.accounts.models import Instructor, Student
from django.db.models import Avg

class StudentMainTutorSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.user_name', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    subject_numbers = serializers.SerializerMethodField()
    average_rate = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = ['id', 'user_name', 'first_name', 'last_name', 'subject_numbers', 'average_rate']

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

class InstructorMainStudentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.user_name', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    subject_numbers = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ['id', 'user_name', 'first_name', 'last_name', 'subject_numbers']

    def get_subject_numbers(self, obj):
        return list(obj.subjects.values_list('number', flat=True))

