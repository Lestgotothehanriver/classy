from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from config.apps.accounts.models import Instructor
from config.apps.lecture.models import Lecture


class WebBrowseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        owner = get_user_model().objects.create_user(username="web-owner", user_name="web-owner")
        self.instructor = Instructor.objects.create(user=owner, university="Test")

    def test_guest_can_browse_only_saleable_metadata(self):
        visible = Lecture.objects.create(instructor=self.instructor, title="Visible", video="lectures/private.mp4")
        Lecture.objects.create(instructor=self.instructor, title="Paused", is_active=False)
        Lecture.objects.create(instructor=self.instructor, title="Deleted", is_delete=True)
        Lecture.objects.create(instructor=self.instructor, title="Blocked", admin_blocked_at=timezone.now())
        for query in ("", "?instructor=me"):
            response = self.client.get("/lectures/" + query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([x['id'] for x in response.data['results']], [visible.id])
            self.assertNotIn('video', response.data['results'][0])
        self.assertIn(self.client.get(f"/lectures/{visible.id}/stream/").status_code, (401, 403))
        self.assertIn(self.client.post("/lectures/write/", {}).status_code, (401, 403))

    def test_guest_search_and_subject_filter(self):
        Lecture.objects.create(instructor=self.instructor, title="Python")
        Lecture.objects.create(instructor=self.instructor, title="Math")
        response = self.client.get("/lectures/?q=Python")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], "Python")
