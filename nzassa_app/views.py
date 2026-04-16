import re
from collections import Counter
from datetime import date

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Avg, Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from .forms import NzassaLoginForm, NzassaRegistrationForm
from .models import (
    Badge,
    Course,
    CulturalExperience,
    Enrollment,
    Language,
    Lesson,
    LessonProgress,
    Module,
    QuizAttempt,
    Traduction,
    UserBadge,
    UserProfile,
)


FRENCH_STOPWORDS = {
    "alors", "apprendre", "apprends", "avec", "aussi", "aux", "avoir", "bien",
    "comment", "comme", "cours", "dans", "des", "donc", "elle", "elles", "encore",
    "entre", "est", "etre", "faire", "faut", "ici", "ils", "langue", "langues",
    "leur", "mais", "mes", "mieux", "mot", "mots", "nous", "notre", "par", "parcours",
    "pas", "plus", "pour", "quoi", "sans", "ses", "sur", "tes", "toi", "ton", "tous",
    "tout", "tres", "une", "vers", "votre", "vous",
}


def get_or_create_profile(user):
    return UserProfile.objects.get_or_create(user=user)[0]


def refresh_badges(profile):
    badges = Badge.objects.filter(xp_threshold__lte=profile.total_xp)
    for badge in badges:
        UserBadge.objects.get_or_create(user=profile.user, badge=badge)


def refresh_streak(profile):
    today = date.today()
    if profile.last_learning_date == today:
        return
    if profile.last_learning_date and (today - profile.last_learning_date).days == 1:
        profile.streak_days += 1
    else:
        profile.streak_days = 1
    profile.last_learning_date = today
    profile.save(update_fields=["streak_days", "last_learning_date"])


def update_enrollment_progress(user, course):
    total_lessons = Lesson.objects.filter(module__course=course).count()
    completed_lessons = LessonProgress.objects.filter(
        user=user,
        lesson__module__course=course,
        completed=True,
    ).count()

    enrollment, _ = Enrollment.objects.get_or_create(user=user, course=course)
    progress = int((completed_lessons / total_lessons) * 100) if total_lessons else 0
    enrollment.progress_percent = progress
    if progress == 100:
        enrollment.status = "completed"
    enrollment.save(update_fields=["progress_percent", "status", "updated_at"])
    return enrollment


def normalize_words(text):
    return [
        word.lower()
        for word in re.findall(r"[A-Za-zÀ-ÿ'-]{3,}", text or "")
        if word.lower() not in FRENCH_STOPWORDS
    ]


def build_discovered_vocabulary(limit=18):
    word_counter = Counter()
    word_sources = {}

    for traduction in Traduction.objects.all():
        for word in normalize_words(traduction.mot_origine):
            word_counter[word] += 3
            word_sources.setdefault(
                word,
                {
                    "word": word,
                    "language": traduction.get_langue_cible_display(),
                    "source": "Dictionnaire IA",
                    "hint": traduction.resultat_traduction,
                },
            )

        for word in normalize_words(traduction.resultat_traduction):
            word_counter[word] += 1
            word_sources.setdefault(
                word,
                {
                    "word": word,
                    "language": traduction.get_langue_cible_display(),
                    "source": "Correspondance enrichie",
                    "hint": traduction.mot_origine,
                },
            )

    for lesson in Lesson.objects.select_related("module__course__language"):
        payload = " ".join(
            [
                lesson.title,
                lesson.key_phrase,
                lesson.content,
                lesson.culture_note,
                lesson.module.title,
                lesson.module.course.title,
            ]
        )
        for word in normalize_words(payload):
            word_counter[word] += 1
            word_sources.setdefault(
                word,
                {
                    "word": word,
                    "language": lesson.module.course.language.name,
                    "source": lesson.module.course.title,
                    "hint": lesson.key_phrase or lesson.lesson_type,
                },
            )

    discovered = []
    for word, score in word_counter.most_common():
        discovered.append({**word_sources[word], "score": score})
        if len(discovered) >= limit:
            break
    return discovered


def build_ai_guidance(prompt, selected_language=None):
    prompt = (prompt or "").strip()
    prompt_lower = prompt.lower()
    discovered_vocabulary = build_discovered_vocabulary(limit=10)

    if not prompt:
        return {
            "headline": "Coach pret",
            "summary": "Je peux relier un mot, une lecon et un parcours pour t'aider a apprendre plus vite.",
            "actions": [
                "Tape un mot comme bonjour, merci ou famille.",
                "Demande un parcours debutant en baoule, dioula ou langue des signes.",
                "Teste une requete comme: apprends-moi des mots pour voyager.",
            ],
            "matches": [],
            "related_courses": list(Course.objects.filter(is_published=True).select_related("language")[:3]),
            "discovered_vocabulary": discovered_vocabulary,
        }

    translations = list(Traduction.objects.filter(mot_origine__icontains=prompt_lower)[:4])
    if not translations:
        translations = list(Traduction.objects.filter(resultat_traduction__icontains=prompt_lower)[:4])

    course_queryset = Course.objects.filter(is_published=True).select_related("language")
    if selected_language:
        course_queryset = course_queryset.filter(language=selected_language)

    related_courses = list(course_queryset.filter(title__icontains=prompt_lower)[:3])
    if not related_courses:
        related_courses = list(course_queryset.filter(description__icontains=prompt_lower)[:3])
    if not related_courses:
        related_courses = list(course_queryset[:3])

    related_lessons = list(
        Lesson.objects.select_related("module__course")
        .filter(title__icontains=prompt_lower)[:3]
    )
    if not related_lessons:
        related_lessons = list(
            Lesson.objects.select_related("module__course")
            .filter(content__icontains=prompt_lower)[:3]
        )

    discovered_matches = [
        item
        for item in discovered_vocabulary
        if prompt_lower in item["word"] or item["word"] in prompt_lower
    ]

    actions = []
    matches = []

    for traduction in translations:
        matches.append(
            f"{traduction.mot_origine} -> {traduction.resultat_traduction} ({traduction.get_langue_cible_display()})"
        )
        actions.append(
            f"Repete {traduction.resultat_traduction} cinq fois puis reutilise ce mot dans une phrase courte."
        )

    for lesson in related_lessons[:2]:
        actions.append(
            f"Travaille la lecon {lesson.title} du parcours {lesson.module.course.title} pour fixer ce vocabulaire."
        )

    for item in discovered_matches[:2]:
        actions.append(
            f"Mot appris automatiquement: {item['word']} via {item['source']}."
        )

    if not actions:
        actions = [
            "Je n'ai pas trouve une traduction exacte, mais j'ai relie ta demande aux contenus deja presents dans la plateforme.",
            "Commence par un parcours debutant puis reviens demander un theme plus precis au coach.",
        ]

    if translations:
        headline = "Traduction retrouvee"
        summary = "Le coach a retrouve des correspondances dans la base et les relie a des contenus utiles."
    elif related_lessons or related_courses:
        headline = "Parcours recommande"
        summary = "Je n'ai pas une equivalence parfaite, mais j'ai trouve un chemin d'apprentissage adapte."
    else:
        headline = "Suggestion de depart"
        summary = "La memoire locale de l'IA grandit avec les contenus de la plateforme."

    return {
        "headline": headline,
        "summary": summary,
        "actions": actions[:4],
        "matches": matches[:4],
        "related_courses": related_courses,
        "related_lessons": related_lessons[:3],
        "discovered_vocabulary": discovered_vocabulary,
    }


def accueil(request):
    featured_courses = Course.objects.filter(is_published=True)[:3]
    featured_experiences = CulturalExperience.objects.all()[:3]
    discovered_vocabulary = build_discovered_vocabulary(limit=8)
    stats = {
        "languages": Language.objects.filter(is_active=True).count(),
        "courses": Course.objects.filter(is_published=True).count(),
        "lessons": Lesson.objects.count(),
        "experiences": CulturalExperience.objects.count(),
    }
    return render(
        request,
        "nzassa_app/index.html",
        {
            "featured_courses": featured_courses,
            "featured_experiences": featured_experiences,
            "discovered_vocabulary": discovered_vocabulary,
            "stats": stats,
        },
    )


class NzassaLoginView(LoginView):
    template_name = "nzassa_app/auth/login.html"
    authentication_form = NzassaLoginForm
    redirect_authenticated_user = True


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = NzassaRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.first_name = form.cleaned_data["first_name"]
            user.save()

            profile = get_or_create_profile(user)
            profile.selected_language = form.cleaned_data["selected_language"]
            profile.goal = form.cleaned_data["goal"]
            profile.level = form.cleaned_data["level"]
            profile.save()

            login(request, user)
            messages.success(request, "Bienvenue sur Nzassa School. Votre parcours est pret.")
            return redirect("dashboard")
    else:
        form = NzassaRegistrationForm()

    return render(request, "nzassa_app/auth/register.html", {"form": form})


@login_required
def dashboard(request):
    profile = get_or_create_profile(request.user)
    enrollments = Enrollment.objects.filter(user=request.user).select_related("course", "course__language")
    lesson_progress = LessonProgress.objects.filter(user=request.user, completed=True)
    quiz_stats = QuizAttempt.objects.filter(user=request.user).aggregate(
        avg_score=Avg("score"),
        attempts=Count("id"),
    )
    recommended_courses = Course.objects.filter(is_published=True).exclude(
        id__in=enrollments.values_list("course_id", flat=True)
    )[:3]

    context = {
        "profile": profile,
        "enrollments": enrollments,
        "completed_lessons": lesson_progress.count(),
        "quiz_attempts": quiz_stats["attempts"] or 0,
        "avg_score": round(quiz_stats["avg_score"] or 0),
        "earned_badges": UserBadge.objects.filter(user=request.user).select_related("badge"),
        "recommended_courses": recommended_courses,
    }
    return render(request, "nzassa_app/dashboard.html", context)


def course_catalog(request):
    courses = Course.objects.filter(is_published=True).select_related("language")
    experiences = CulturalExperience.objects.all()[:4]
    return render(
        request,
        "nzassa_app/course_catalog.html",
        {"courses": courses, "experiences": experiences},
    )


def course_detail(request, slug):
    course = get_object_or_404(Course.objects.select_related("language"), slug=slug, is_published=True)
    modules = Module.objects.filter(course=course).prefetch_related("lessons")
    enrollment = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()

    return render(
        request,
        "nzassa_app/course_detail.html",
        {
            "course": course,
            "modules": modules,
            "enrollment": enrollment,
        },
    )


@login_required
def enroll_course(request, slug):
    course = get_object_or_404(Course, slug=slug, is_published=True)
    Enrollment.objects.get_or_create(user=request.user, course=course)
    messages.success(request, "Parcours ajoute a votre dashboard.")
    return redirect("course_detail", slug=course.slug)


@login_required
def lesson_detail(request, course_slug, lesson_id):
    course = get_object_or_404(Course, slug=course_slug, is_published=True)
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course"),
        id=lesson_id,
        module__course=course,
    )
    profile = get_or_create_profile(request.user)
    progress, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
    questions = lesson.questions.all()
    submission = None

    if request.method == "POST":
        total_questions = questions.count()
        correct_answers = 0
        results = []

        for question in questions:
            selected = request.POST.get(f"question_{question.id}", "").upper()
            is_correct = selected == question.correct_choice
            if is_correct:
                correct_answers += 1
            results.append(
                {
                    "question": question,
                    "selected": selected,
                    "is_correct": is_correct,
                }
            )

        score = int((correct_answers / total_questions) * 100) if total_questions else 100
        QuizAttempt.objects.create(
            user=request.user,
            lesson=lesson,
            score=score,
            correct_answers=correct_answers,
            total_questions=total_questions,
        )

        was_completed = progress.completed
        progress.completed = True
        progress.score = max(progress.score, score)
        progress.completed_at = timezone.now()
        progress.save()

        if not was_completed:
            profile.total_xp += lesson.xp_reward
            profile.save(update_fields=["total_xp"])

        refresh_streak(profile)
        refresh_badges(profile)
        enrollment = update_enrollment_progress(request.user, course)

        submission = {
            "score": score,
            "correct_answers": correct_answers,
            "total_questions": total_questions,
            "results": results,
            "enrollment": enrollment,
        }
        messages.success(request, "Lecon validee. Votre progression a ete mise a jour.")

    return render(
        request,
        "nzassa_app/lesson_detail.html",
        {
            "course": course,
            "lesson": lesson,
            "questions": questions,
            "progress": progress,
            "submission": submission,
        },
    )


def pricing(request):
    return render(request, "nzassa_app/pricing.html")


def ai_coach(request):
    profile = None
    selected_language = None

    if request.user.is_authenticated:
        profile = get_or_create_profile(request.user)
        selected_language = profile.selected_language

    prompt = request.GET.get("prompt", "")
    guidance = build_ai_guidance(prompt, selected_language=selected_language)

    return render(
        request,
        "nzassa_app/coach_ia.html",
        {
            "prompt": prompt,
            "guidance": guidance,
            "profile": profile,
            "selected_language": selected_language,
            "featured_courses": Course.objects.filter(is_published=True).select_related("language")[:4],
        },
    )


def reconnaissance_signes(request):
    return render(request, "nzassa_app/ia_signes.html")


def immersion_vr(request):
    return render(request, "nzassa_app/immersion.html")


def chercher_mot(request):
    query = request.GET.get("q", "")
    resultats = Traduction.objects.filter(mot_origine__icontains=query)[:5]

    data = [
        {
            "origine": r.mot_origine,
            "traduction": r.resultat_traduction,
            "langue": r.get_langue_cible_display(),
        }
        for r in resultats
    ]
    return JsonResponse({"data": data})
