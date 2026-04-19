import json
import re
from collections import Counter
from datetime import date

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Avg, Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

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

LANGUAGE_VOICE_MAP = {
    "FR": "fr-FR",
    "BAO": "fr-CI",
    "DIO": "fr-CI",
    "LSI": "fr-FR",
}

LANGUAGE_HINTS = {
    "francais": "Prononce avec un rythme fluide et des voyelles nettes.",
    "baoule": "Appuie doucement les voyelles et garde un debit pose pour mieux entendre la melodie.",
    "dioula": "Va mot par mot avec une diction claire et reguliere.",
    "langue des signes": "Observe le geste, puis lis aussi la phrase a voix haute pour fixer le sens.",
}

LANDING_CONVERSATION_RULES = [
    {
        "patterns": [r"\bbonjour\b", r"\bsalut\b", r"\bbonsoir\b"],
        "language": "fr",
        "response": "Bonjour. Bienvenue sur Nzassa School. Comment vas-tu aujourd'hui ?",
        "follow_up": "Tu veux apprendre le baoule, le dioula ou un mot de culture ?",
    },
    {
        "patterns": [r"\bakwaba\b"],
        "language": "baoule",
        "response": "Akwaba. Me fere. Comment vas-tu aujourd'hui ?",
        "follow_up": "Comment t'appelles-tu ?",
    },
    {
        "patterns": [r"\bi ni sogoma\b", r"\bi ni ce\b", r"\banisogoma\b"],
        "language": "dioula",
        "response": "I ni sogoma. N togo ye Coach Nzassa ye. I ka kene wa ?",
        "follow_up": "I togo di ?",
    },
]


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


def build_pronunciation_cards(prompt, translations, discovered_vocabulary, selected_language=None):
    cards = []
    seen = set()
    preferred_code = selected_language.code if selected_language else "FR"

    for traduction in translations:
        language_label = traduction.get_langue_cible_display()
        card = {
            "word": traduction.resultat_traduction,
            "origin": traduction.mot_origine,
            "language": language_label,
            "voice": LANGUAGE_VOICE_MAP.get(traduction.langue_cible, "fr-FR"),
            "pronunciation_tip": LANGUAGE_HINTS.get(language_label.lower(), "Repete lentement, puis accelere quand le mot devient naturel."),
            "coach_prompt": f"Ecoute {traduction.resultat_traduction}, puis repete-le en pensant a {traduction.mot_origine}.",
        }
        key = (card["word"].lower(), card["language"])
        if key not in seen:
            seen.add(key)
            cards.append(card)

    for item in discovered_vocabulary:
        if prompt and not (prompt.lower() in item["word"] or item["word"] in prompt.lower()):
            continue
        card = {
            "word": item["word"].title(),
            "origin": item["hint"],
            "language": item["language"],
            "voice": LANGUAGE_VOICE_MAP.get(preferred_code, "fr-FR"),
            "pronunciation_tip": LANGUAGE_HINTS.get(
                item["language"].lower(),
                "Lis le mot une premiere fois lentement, puis redis-le en contexte.",
            ),
            "coach_prompt": f"Repete {item['word']} trois fois, puis utilise-le dans une mini-phrase.",
        }
        key = (card["word"].lower(), card["language"])
        if key not in seen:
            seen.add(key)
            cards.append(card)
        if len(cards) >= 6:
            break

    if not cards:
        cards.append(
            {
                "word": prompt.title() if prompt else "Nzassa",
                "origin": "Mot de depart",
                "language": selected_language.name if selected_language else "Francais",
                "voice": LANGUAGE_VOICE_MAP.get(preferred_code, "fr-FR"),
                "pronunciation_tip": "Commence lentement, marque les syllabes, puis repete avec plus de fluidite.",
                "coach_prompt": "Ecoute, repete et essaye de replacer le mot dans une phrase simple.",
            }
        )

    return cards[:6]


def get_translation_examples():
    examples = []
    for traduction in Traduction.objects.order_by("date_ajout")[:6]:
        examples.append(
            {
                "source": traduction.mot_origine,
                "target": traduction.resultat_traduction,
                "language_code": traduction.langue_cible,
                "language": traduction.get_langue_cible_display(),
                "voice": LANGUAGE_VOICE_MAP.get(traduction.langue_cible, "fr-FR"),
            }
        )
    if examples:
        return examples
    return [
        {"source": "bienvenue", "target": "Akwaba", "language_code": "BAO", "language": "Baoule", "voice": "fr-CI"},
        {"source": "bonjour", "target": "I ni sogoma", "language_code": "DIO", "language": "Dioula", "voice": "fr-CI"},
        {"source": "famille", "target": "Awlo", "language_code": "BAO", "language": "Baoule", "voice": "fr-CI"},
    ]


def build_landing_game_pack():
    examples = get_translation_examples()
    primary = examples[0]
    distractors = [item["target"] for item in examples[1:4]]
    if primary["target"] not in distractors:
        choices = [primary["target"], *distractors]
    else:
        choices = [primary["target"], "Sugu", "Waka", "Dja"]

    while len(choices) < 4:
        choices.append(["Sugu", "Waka", "Dja", "Bia"][len(choices) - 1])

    return {
        "quiz": {
            "question": f"Quel mot signifie {primary['source']} ?",
            "answer": primary["target"],
            "choices": choices[:4],
        },
        "match": {
            "prompt": "Quel symbole correspond au mot tambour ?",
            "answer": "Tambour",
            "choices": [
                {"emoji": "🌳", "label": "Arbre"},
                {"emoji": "🥁", "label": "Tambour"},
                {"emoji": "🏠", "label": "Case"},
            ],
        },
        "audio": {
            "prompt": "Ecoute le mot puis choisis la bonne reponse.",
            "answer": primary["target"],
            "voice": primary["voice"],
            "language": primary["language"],
            "choices": [item["target"] for item in examples[:3]],
        },
        "phrase": {
            "prompt": "Complete la phrase d'accueil avec le mot manquant.",
            "sentence": "___, je suis heureux de te rencontrer.",
            "answer": primary["target"],
            "hint": f"Indice: c'est un mot de {primary['language']} pour {primary['source']}.",
        },
    }


def build_cultural_highlights():
    experiences = list(CulturalExperience.objects.all()[:3])
    highlights = []
    for experience in experiences:
        highlights.append(
            {
                "title": experience.title,
                "type": experience.get_experience_type_display(),
                "description": experience.description,
                "cta_label": experience.cta_label,
                "cta_url": experience.cta_url or reverse("immersion"),
            }
        )
    if highlights:
        return highlights
    return [
        {
            "title": "Paroles du village",
            "type": "Culture",
            "description": "Des salutations et des gestes culturels pour entrer dans les usages du quotidien.",
            "cta_label": "Explorer",
            "cta_url": reverse("course_catalog"),
        },
        {
            "title": "Coach IA",
            "type": "IA",
            "description": "Une conversation guidee pour apprendre naturellement et pratiquer la prononciation.",
            "cta_label": "Parler",
            "cta_url": reverse("ai_coach"),
        },
        {
            "title": "Immersion VR",
            "type": "VR",
            "description": "Une porte d'entree vers les lieux, les symboles et les ambiances culturelles africaines.",
            "cta_label": "Visiter",
            "cta_url": reverse("immersion"),
        },
    ]


def build_landing_ai_response(message, request, selected_language=None):
    clean_message = (message or "").strip()
    normalized = clean_message.lower()
    profile_language_name = selected_language.name if selected_language else None
    translations = get_translation_examples()
    learner_name = request.session.get("landing_learner_name")

    name_match = re.search(r"(?:je m'appelle|mon nom est)\s+([A-Za-zÀ-ÿ'\-]+)", clean_message, re.IGNORECASE)
    if name_match:
        learner_name = name_match.group(1)
        request.session["landing_learner_name"] = learner_name
        return {
            "text": f"Enchanté {learner_name}. Dis-moi maintenant: veux-tu une salutation, un mot culturel ou un mini-jeu ?",
            "language": "fr",
            "voice": "fr-FR",
            "suggestions": ["Apprendre le baoule", "Je veux un mot culturel", "Lancer un jeu"],
        }

    for rule in LANDING_CONVERSATION_RULES:
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in rule["patterns"]):
            return {
                "text": f"{rule['response']} {rule['follow_up']}",
                "language": rule["language"],
                "voice": "fr-CI" if rule["language"] in {"baoule", "dioula"} else "fr-FR",
                "suggestions": ["Comment vas-tu ?", "Quel est ton nom ?", "Apprendre une langue"],
            }

    if re.search(r"comment vas-tu|ca va|je vais bien|je vais tres bien", normalized, re.IGNORECASE):
        return {
            "text": "Je vais bien, merci. Quel mot veux-tu apprendre maintenant ?",
            "language": "fr",
            "voice": "fr-FR",
            "suggestions": ["Akwaba", "I ni sogoma", "Tambour"],
        }

    if re.search(r"quel est ton nom|tu t'appelles comment|ton nom", normalized, re.IGNORECASE):
        return {
            "text": "Je suis le Coach Nzassa. Et toi, comment t'appelles-tu ?",
            "language": "fr",
            "voice": "fr-FR",
            "suggestions": ["Je m'appelle Awa", "Je m'appelle Kadi"],
        }

    if re.search(r"baoule|dioula|culture|tradition|afrique|tambour|marche|case", normalized, re.IGNORECASE):
        if "baoule" in normalized:
            return {
                "text": "Tres bon choix. En baoule, commence par Akwaba pour souhaiter la bienvenue. Veux-tu une autre formule ?",
                "language": "fr",
                "voice": "fr-FR",
                "suggestions": ["Akwaba", "Comment vas-tu ?", "Un mini-jeu"],
            }
        if "dioula" in normalized:
            return {
                "text": "Excellent. En dioula, dis I ni sogoma pour bonjour le matin. Veux-tu que je continue la conversation ?",
                "language": "fr",
                "voice": "fr-FR",
                "suggestions": ["I ni sogoma", "Quel est ton nom ?", "Un mot culturel"],
            }
        return {
            "text": "Nzassa School relie les langues aux rites, aux objets, a la musique et aux lieux. Veux-tu commencer par le tambour, le marche ou la case ?",
            "language": "fr",
            "voice": "fr-FR",
            "suggestions": ["Tambour", "Marche", "Case"],
        }

    for translation in translations:
        if translation["source"].lower() in normalized or translation["target"].lower() in normalized:
            return {
                "text": f"{translation['source'].capitalize()} se dit {translation['target']} en {translation['language']}. Essaie maintenant de le redire a voix haute.",
                "language": "fr",
                "voice": translation["voice"],
                "suggestions": [translation["target"], f"Apprendre {translation['language']}", "Une autre salutation"],
            }

    if learner_name:
        return {
            "text": f"{learner_name}, je suis la pour t'accompagner. Essaie une salutation, demande une langue ou lance un mini-jeu pour pratiquer.",
            "language": "fr",
            "voice": "fr-FR",
            "suggestions": ["Bonjour", "Akwaba", "Lancer un jeu"],
        }

    default_language = "fr"
    if profile_language_name:
        default_message = f"Je peux te guider en fonction de ta langue preferee: {profile_language_name}. Commence par une salutation ou un mot culturel."
    else:
        default_message = "Je comprends l'intention generale. Essaie une salutation, demande une langue comme le baoule, ou donne-moi ton nom pour commencer."

    return {
        "text": default_message,
        "language": default_language,
        "voice": "fr-FR",
        "suggestions": ["Bonjour", "Je veux apprendre le baoule", "Je m'appelle Awa"],
    }


def build_ai_guidance(prompt, selected_language=None):
    prompt = (prompt or "").strip()
    prompt_lower = prompt.lower()
    discovered_vocabulary = build_discovered_vocabulary(limit=10)

    if not prompt:
        return {
            "headline": "Coach pret",
            "summary": "Je peux relier un mot, une lecon et un parcours pour t'aider a apprendre plus vite.",
            "conversation_opening": "Bonjour. Donne-moi un mot, une situation ou une langue, et je te proposerai une reponse naturelle avec pratique orale.",
            "actions": [
                "Tape un mot comme bonjour, merci ou famille.",
                "Demande un parcours debutant en baoule, dioula ou langue des signes.",
                "Teste une requete comme: apprends-moi des mots pour voyager.",
            ],
            "matches": [],
            "related_courses": list(Course.objects.filter(is_published=True).select_related("language")[:3]),
            "discovered_vocabulary": discovered_vocabulary,
            "pronunciation_cards": build_pronunciation_cards(prompt, [], discovered_vocabulary, selected_language),
            "practice_loop": [
                "Ecoute le mot une fois.",
                "Repete-le lentement.",
                "Redis-le dans une phrase courte.",
            ],
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

    pronunciation_cards = build_pronunciation_cards(
        prompt,
        translations,
        discovered_matches or discovered_vocabulary,
        selected_language,
    )

    conversation_opening = (
        f"Voici une piste pour '{prompt}'. Je te donne un sens, une pratique orale et un chemin de progression."
        if prompt
        else "Je suis pret a t'accompagner mot par mot."
    )

    return {
        "headline": headline,
        "summary": summary,
        "conversation_opening": conversation_opening,
        "actions": actions[:4],
        "matches": matches[:4],
        "related_courses": related_courses,
        "related_lessons": related_lessons[:3],
        "discovered_vocabulary": discovered_vocabulary,
        "pronunciation_cards": pronunciation_cards,
        "practice_loop": [
            "Ecoute le mot ou l'expression proposee.",
            "Repete a voix haute trois fois.",
            "Refais une phrase avec le mot sans regarder.",
        ],
    }


@require_GET
def accueil(request):
    featured_courses = Course.objects.filter(is_published=True)[:3]
    featured_experiences = CulturalExperience.objects.all()[:3]
    discovered_vocabulary = build_discovered_vocabulary(limit=8)
    landing_games = build_landing_game_pack()
    cultural_highlights = build_cultural_highlights()
    translation_examples = get_translation_examples()
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
            "landing_games": landing_games,
            "cultural_highlights": cultural_highlights,
            "translation_examples": translation_examples,
            "stats": stats,
        },
    )


class NzassaLoginView(LoginView):
    template_name = "nzassa_app/auth/login.html"
    authentication_form = NzassaLoginForm
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard")

    def form_valid(self, form):
        messages.success(self.request, "Connexion reussie. Heureux de vous revoir sur Nzassa School.")
        return super().form_valid(form)


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


@require_GET
def course_catalog(request):
    courses = Course.objects.filter(is_published=True).select_related("language")
    experiences = CulturalExperience.objects.all()[:4]
    return render(
        request,
        "nzassa_app/course_catalog.html",
        {"courses": courses, "experiences": experiences},
    )


@require_GET
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
@require_POST
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


@require_GET
def pricing(request):
    return render(request, "nzassa_app/pricing.html")


@require_GET
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


@require_GET
def reconnaissance_signes(request):
    return render(request, "nzassa_app/ia_signes.html")


def immersion_vr(request):
    scene_presets = [
        {
            "key": "village",
            "label": "Village Senoufo",
            "location": "Korhogo, Cote d'Ivoire",
            "sky": "#d87a33",
            "ground": "#b56a3e",
            "accent": "#2d6a4f",
            "story": "Une place de village avec case, arbre a palabres et narration communautaire.",
            "sound": "Tambours doux, oiseaux et vent leger.",
        },
        {
            "key": "market",
            "label": "Grand Marche",
            "location": "Treichville, Abidjan",
            "sky": "#f2b35a",
            "ground": "#806347",
            "accent": "#bc6c25",
            "story": "Une immersion dans les etals, les salutations et l'energie du commerce quotidien.",
            "sound": "Brouhaha du marche, appels des vendeurs et pas rapides.",
        },
        {
            "key": "sacred",
            "label": "Basilique et esplanade",
            "location": "Yamoussoukro, Cote d'Ivoire",
            "sky": "#94c6d4",
            "ground": "#d9c8a2",
            "accent": "#5c7c89",
            "story": "Un decor plus monumental pour apprendre le lexique de la visite et du patrimoine.",
            "sound": "Ambiance paisible, pas lents et echoes lointains.",
        },
    ]
    return render(request, "nzassa_app/immersion.html", {"scene_presets": scene_presets})


@require_GET
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


@require_POST
def landing_ai_chat(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Payload JSON invalide."}, status=400)

    message = payload.get("message", "")
    selected_language = None
    if request.user.is_authenticated:
        selected_language = get_or_create_profile(request.user).selected_language

    response = build_landing_ai_response(message, request, selected_language=selected_language)
    return JsonResponse(response)


@login_required
@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Vous etes maintenant deconnecte en toute securite.")
    return redirect("accueil")
