from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    NzassaLoginView,
    accueil,
    ai_coach,
    course_catalog,
    course_detail,
    dashboard,
    enroll_course,
    chercher_mot,
    immersion_vr,
    lesson_detail,
    pricing,
    reconnaissance_signes,
    register,
)

urlpatterns = [
    path("", accueil, name="accueil"),
    path("coach-ia/", ai_coach, name="ai_coach"),
    path("parcours/", course_catalog, name="course_catalog"),
    path("parcours/<slug:slug>/", course_detail, name="course_detail"),
    path("parcours/<slug:slug>/inscription/", enroll_course, name="enroll_course"),
    path("parcours/<slug:course_slug>/lecons/<int:lesson_id>/", lesson_detail, name="lesson_detail"),
    path("dashboard/", dashboard, name="dashboard"),
    path("tarifs/", pricing, name="pricing"),
    path("connexion/", NzassaLoginView.as_view(), name="login"),
    path("inscription/", register, name="register"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("ia-signes/", reconnaissance_signes, name="ia_signes"),
    path("immersion/", immersion_vr, name="immersion"),
    path("chercher/", chercher_mot, name="chercher_mot"),
]
