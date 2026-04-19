from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Course, Language, Lesson, Module, QuizQuestion, UserProfile


class NzassaFlowTests(TestCase):
    def setUp(self):
        self.language = Language.objects.create(name="Baoule", code="BAO")
        self.course = Course.objects.create(
            language=self.language,
            title="Baoule Essentiel",
            short_description="Bases",
            description="Description complete",
            focus="language",
            level="Debutant",
        )
        self.module = Module.objects.create(course=self.course, title="Demarrer", order=1)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title="Saluer",
            order=1,
            content="Contenu de lecon",
            lesson_type="conversation",
            xp_reward=30,
        )
        self.question = QuizQuestion.objects.create(
            lesson=self.lesson,
            prompt="Comment dire bienvenue ?",
            choice_a="Akwaba",
            choice_b="Bia",
            choice_c="Ama",
            choice_d="Kouassi",
            correct_choice="A",
            explanation="Akwaba est une formule d'accueil.",
        )

    def test_register_creates_profile_and_redirects(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "aminata",
                "first_name": "Aminata",
                "email": "aminata@example.com",
                "selected_language": self.language.id,
                "goal": "culture",
                "level": "beginner",
                "password1": "NzassaPass123!",
                "password2": "NzassaPass123!",
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="aminata")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.selected_language, self.language)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_logout_requires_post_and_clears_session(self):
        user = User.objects.create_user(username="adiouma", password="NzassaPass123!")
        self.client.login(username="adiouma", password="NzassaPass123!")

        get_response = self.client.get(reverse("logout"))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("logout"), follow=True)
        self.assertRedirects(post_response, reverse("accueil"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ai_coach_page_loads(self):
        response = self.client.get(reverse("ai_coach"), {"prompt": "bonjour"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coach")

    def test_lesson_submission_updates_progress_and_xp(self):
        user = User.objects.create_user(username="kone", password="NzassaPass123!")
        self.client.login(username="kone", password="NzassaPass123!")

        self.client.post(reverse("enroll_course", args=[self.course.slug]))
        response = self.client.post(
            reverse("lesson_detail", args=[self.course.slug, self.lesson.id]),
            {f"question_{self.question.id}": "A"},
        )

        user.refresh_from_db()
        profile = UserProfile.objects.get(user=user)

        self.assertContains(response, "Score")
        self.assertEqual(profile.total_xp, 30)

    def test_search_endpoint_returns_json(self):
        response = self.client.get(reverse("chercher_mot"), {"q": "bon"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_landing_ai_chat_returns_json_response(self):
        response = self.client.post(
            reverse("landing_ai_chat"),
            data='{"message":"bonjour"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("Bonjour", response.json()["text"])
