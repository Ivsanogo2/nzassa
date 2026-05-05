import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db.models import Avg, Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from .ai_services import (
    build_discovered_vocabulary as ai_build_discovered_vocabulary,
    build_learning_activity as ai_build_learning_activity,
    build_pronunciation_cards as ai_build_pronunciation_cards,
    chat_with_coach,
    detect_intents as ai_detect_intents,
    evaluate_pronunciation,
    gather_knowledge as ai_gather_knowledge,
    get_memory_queryset,
    get_or_create_conversation,
    get_remote_ai_status,
)
from .forms import (
    AudioTrackForm,
    BookForm,
    CulturalAIForm,
    LearningGroupForm,
    MicroLessonSubscriptionForm,
    MobileMoneyPaymentForm,
    NzassaLoginForm,
    NzassaRegistrationForm,
    PrivateMessageForm,
    SchoolForm,
    ShortVideoForm,
    SocialCommentForm,
    SocialPostForm,
    StoryCommentForm,
    StoryForm,
)
from .models import (
    AudioTrack,
    Badge,
    Book,
    Certificate,
    Course,
    CulturalExperience,
    EducationalGame,
    Enrollment,
    Ethnicity,
    FriendConnection,
    GroupMembership,
    Language,
    LearningEvent,
    LearningGroup,
    Lesson,
    LessonProgress,
    MicroLessonSubscription,
    MobileMoneyPayment,
    Module,
    Notification,
    OfflinePack,
    PrivateMessage,
    QuizAttempt,
    School,
    SchoolMembership,
    ShortVideo,
    SocialPost,
    Story,
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


def redirect_back(request, fallback_name, **fallback_kwargs):
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback_name, **fallback_kwargs)


def create_notification(recipient, actor, verb, target_label="", target_url=""):
    if not recipient or not actor or recipient == actor:
        return None
    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        verb=verb,
        target_label=target_label[:200],
        target_url=target_url[:255],
    )


def get_unread_notifications(user):
    if not user.is_authenticated:
        return []
    return Notification.objects.filter(recipient=user, is_read=False)[:6]


def log_learning_event(request, event_type, object_label="", metadata=None):
    LearningEvent.objects.create(
        user=request.user if request.user.is_authenticated else None,
        event_type=event_type,
        object_label=object_label[:200],
        metadata=metadata or {},
    )


def build_certificate_code(user, course=None):
    course_part = course.slug[:8].upper() if course else "NZASSA"
    return f"NZ-{course_part}-{user.id}-{get_random_string(6).upper()}"


def escape_pdf_text(text):
    return (text or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_certificate_pdf(certificate):
    learner = certificate.user.get_full_name() or certificate.user.username
    course_title = certificate.course.title if certificate.course_id else "Parcours Nzassa"
    lines = [
        "Nzassa School",
        "Certificat de progression",
        f"Attribue a {learner}",
        f"Parcours: {course_title}",
        f"Niveau: {certificate.level_label or 'Nzassa'}",
        f"Score: {certificate.score}%",
        f"Code: {certificate.code}",
        f"Date: {certificate.issued_at:%d/%m/%Y}",
    ]

    text_commands = ["BT", "/F1 26 Tf", "72 760 Td"]
    for index, line in enumerate(lines):
        if index == 0:
            text_commands.append(f"({escape_pdf_text(line)}) Tj")
        else:
            text_commands.append("0 -52 Td")
            text_commands.append("/F1 18 Tf" if index > 1 else "/F1 22 Tf")
            text_commands.append(f"({escape_pdf_text(line)}) Tj")
    text_commands.append("ET")
    stream = "\n".join(text_commands).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n",
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica-Bold>>endobj\n",
        b"5 0 obj<</Length " + str(len(stream)).encode("ascii") + b">>stream\n" + stream + b"\nendstream\nendobj\n",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_position = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref_position}\n%%EOF".encode("ascii")
    )
    return bytes(pdf)


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
    discovered_vocabulary = ai_build_discovered_vocabulary(limit=10)
    activity_prompt = prompt or "Apprendre le baoule avec prononciation"
    service_knowledge = ai_gather_knowledge(activity_prompt, selected_language=selected_language)
    detected_intents = ai_detect_intents(activity_prompt)
    smart_activity = ai_build_learning_activity(
        activity_prompt,
        service_knowledge,
        [],
        selected_language=selected_language,
        detected_intents=detected_intents,
    )

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
            "pronunciation_cards": ai_build_pronunciation_cards(prompt, [], discovered_vocabulary, selected_language),
            "smart_activity": smart_activity,
            "detected_intents": detected_intents,
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

    pronunciation_cards = ai_build_pronunciation_cards(
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
        "smart_activity": smart_activity,
        "detected_intents": detected_intents,
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
    discovered_vocabulary = ai_build_discovered_vocabulary(limit=8)
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
    certificate = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
        certificate = Certificate.objects.filter(user=request.user, course=course).first()

    return render(
        request,
        "nzassa_app/course_detail.html",
        {
            "course": course,
            "modules": modules,
            "enrollment": enrollment,
            "certificate": certificate,
        },
    )


@require_GET
def story_list(request):
    ethnicity_slug = request.GET.get("ethnie", "").strip()
    location = request.GET.get("lieu", "").strip()
    query = request.GET.get("q", "").strip()

    stories = (
        Story.objects.filter(is_published=True)
        .select_related("ethnicity", "author")
        .annotate(likes_total=Count("likes", distinct=True), comments_total=Count("comments", distinct=True))
    )

    if ethnicity_slug:
        stories = stories.filter(ethnicity__slug=ethnicity_slug)
    if location:
        stories = stories.filter(location__icontains=location)
    if query:
        stories = stories.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
            | Q(ethnicity__name__icontains=query)
        )

    liked_story_ids = []
    if request.user.is_authenticated:
        liked_story_ids = list(
            request.user.liked_stories.filter(is_published=True).values_list("id", flat=True)
        )

    context = {
        "stories": stories,
        "ethnicities": Ethnicity.objects.filter(stories__is_published=True).distinct(),
        "selected_ethnicity": ethnicity_slug,
        "location": location,
        "query": query,
        "liked_story_ids": liked_story_ids,
    }
    return render(request, "nzassa_app/story_list.html", context)


@login_required
def story_add(request):
    if request.method == "POST":
        form = StoryForm(request.POST, request.FILES)
        if form.is_valid():
            story = form.save(commit=False)
            story.author = request.user
            story.save()
            messages.success(request, "Histoire ajoutee avec succes.")
            return redirect("story_detail", slug=story.slug)
    else:
        form = StoryForm()

    return render(
        request,
        "nzassa_app/story_form.html",
        {"form": form, "title": "Ajouter une histoire", "submit_label": "Publier l'histoire"},
    )


@require_GET
def story_detail(request, slug):
    story = get_object_or_404(
        Story.objects.select_related("ethnicity", "author"),
        slug=slug,
        is_published=True,
    )
    comments = story.comments.select_related("author")
    audio_tracks = story.audio_tracks.select_related("language")
    liked = request.user.is_authenticated and story.likes.filter(id=request.user.id).exists()
    related_stories = Story.objects.filter(is_published=True).exclude(id=story.id)
    if story.ethnicity_id:
        related_stories = related_stories.filter(ethnicity=story.ethnicity)
    related_stories = related_stories.select_related("ethnicity")[:3]

    return render(
        request,
        "nzassa_app/story_detail.html",
        {
            "story": story,
            "comments": comments,
            "audio_tracks": audio_tracks,
            "comment_form": StoryCommentForm(),
            "liked": liked,
            "related_stories": related_stories,
        },
    )


@login_required
@require_POST
def story_like(request, slug):
    story = get_object_or_404(Story.objects.select_related("author"), slug=slug, is_published=True)
    if story.likes.filter(id=request.user.id).exists():
        story.likes.remove(request.user)
        messages.info(request, "Like retire.")
    else:
        story.likes.add(request.user)
        create_notification(
            story.author,
            request.user,
            "a aime votre histoire",
            story.title,
            reverse("story_detail", kwargs={"slug": story.slug}),
        )
        messages.success(request, "Histoire ajoutee a vos coups de coeur.")
    return redirect_back(request, "story_detail", slug=story.slug)


@login_required
@require_POST
def story_comment(request, slug):
    story = get_object_or_404(Story.objects.select_related("author"), slug=slug, is_published=True)
    form = StoryCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.story = story
        comment.author = request.user
        comment.save()
        create_notification(
            story.author,
            request.user,
            "a commente votre histoire",
            story.title,
            reverse("story_detail", kwargs={"slug": story.slug}),
        )
        messages.success(request, "Commentaire publie.")
    else:
        messages.error(request, "Le commentaire est vide ou invalide.")
    return redirect("story_detail", slug=story.slug)


@require_GET
def library(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("categorie", "").strip()

    books = Book.objects.filter(is_published=True).select_related("uploaded_by").prefetch_related("favorites")
    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author_name__icontains=query)
            | Q(description__icontains=query)
        )
    if category:
        books = books.filter(category=category)

    favorite_book_ids = []
    if request.user.is_authenticated:
        favorite_book_ids = list(request.user.favorite_books.values_list("id", flat=True))

    return render(
        request,
        "nzassa_app/library.html",
        {
            "books": books,
            "query": query,
            "selected_category": category,
            "categories": Book.CATEGORY_CHOICES,
            "favorite_book_ids": favorite_book_ids,
        },
    )


@login_required
def book_add(request):
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save(commit=False)
            book.uploaded_by = request.user
            book.save()
            messages.success(request, "Livre ajoute dans la librairie.")
            return redirect("book_detail", slug=book.slug)
    else:
        form = BookForm()

    return render(
        request,
        "nzassa_app/book_form.html",
        {"form": form, "title": "Ajouter un livre", "submit_label": "Publier le livre"},
    )


@require_GET
def book_detail(request, slug):
    book = get_object_or_404(Book.objects.select_related("uploaded_by"), slug=slug, is_published=True)
    related_books = Book.objects.filter(is_published=True, category=book.category).exclude(id=book.id)[:3]
    is_favorite = request.user.is_authenticated and book.favorites.filter(id=request.user.id).exists()
    return render(
        request,
        "nzassa_app/book_detail.html",
        {"book": book, "related_books": related_books, "is_favorite": is_favorite},
    )


@require_GET
@xframe_options_sameorigin
def book_read(request, slug):
    book = get_object_or_404(Book, slug=slug, is_published=True)
    try:
        return FileResponse(
            book.pdf_file.open("rb"),
            as_attachment=False,
            content_type="application/pdf",
        )
    except FileNotFoundError as exc:
        raise Http404("Fichier PDF introuvable.") from exc


@require_GET
def book_download(request, slug):
    book = get_object_or_404(Book, slug=slug, is_published=True)
    try:
        return FileResponse(
            book.pdf_file.open("rb"),
            as_attachment=True,
            filename=book.pdf_file.name.rsplit("/", 1)[-1],
        )
    except FileNotFoundError as exc:
        raise Http404("Fichier PDF introuvable.") from exc


@login_required
@require_POST
def book_favorite(request, slug):
    book = get_object_or_404(Book.objects.select_related("uploaded_by"), slug=slug, is_published=True)
    if book.favorites.filter(id=request.user.id).exists():
        book.favorites.remove(request.user)
        messages.info(request, "Livre retire des favoris.")
    else:
        book.favorites.add(request.user)
        create_notification(
            book.uploaded_by,
            request.user,
            "a ajoute votre livre en favori",
            book.title,
            reverse("book_detail", kwargs={"slug": book.slug}),
        )
        messages.success(request, "Livre ajoute a vos favoris.")
    log_learning_event(request, "book_favorite", book.title, {"book_id": book.id})
    return redirect_back(request, "book_detail", slug=book.slug)


@require_GET
def ethnicity_map(request):
    ethnicities = (
        Ethnicity.objects.select_related("language")
        .annotate(story_count=Count("stories", distinct=True))
        .order_by("name")
    )
    map_points = [
        {
            "name": ethnicity.name,
            "slug": ethnicity.slug,
            "language": ethnicity.language.name if ethnicity.language_id else "",
            "region": ethnicity.region,
            "description": ethnicity.description,
            "traditions": ethnicity.traditions,
            "latitude": float(ethnicity.latitude) if ethnicity.latitude is not None else None,
            "longitude": float(ethnicity.longitude) if ethnicity.longitude is not None else None,
            "color": ethnicity.map_color,
            "story_count": ethnicity.story_count,
        }
        for ethnicity in ethnicities
    ]
    return render(
        request,
        "nzassa_app/ethnicity_map.html",
        {
            "ethnicities": ethnicities,
            "map_points_json": json.dumps(map_points),
        },
    )


@require_GET
def audio_library(request):
    query = request.GET.get("q", "").strip()
    tracks = AudioTrack.objects.select_related("story", "lesson", "language")
    if query:
        tracks = tracks.filter(Q(title__icontains=query) | Q(transcript__icontains=query) | Q(language__name__icontains=query))
    return render(
        request,
        "nzassa_app/audio_library.html",
        {"tracks": tracks, "query": query},
    )


@login_required
def audio_add(request):
    if request.method == "POST":
        form = AudioTrackForm(request.POST, request.FILES)
        if form.is_valid():
            track = form.save()
            messages.success(request, "Audio ajoute au catalogue.")
            log_learning_event(request, "audio_created", track.title, {"audio_id": track.id})
            return redirect("audio_library")
    else:
        form = AudioTrackForm()
    return render(
        request,
        "nzassa_app/simple_form.html",
        {"form": form, "title": "Ajouter un audio", "submit_label": "Publier l'audio", "back_url": reverse("audio_library")},
    )


@require_GET
def short_video_feed(request):
    videos = ShortVideo.objects.filter(is_published=True).select_related("language", "author").prefetch_related("likes")
    liked_video_ids = []
    if request.user.is_authenticated:
        liked_video_ids = list(request.user.liked_short_videos.values_list("id", flat=True))
    return render(
        request,
        "nzassa_app/short_video_feed.html",
        {"videos": videos, "liked_video_ids": liked_video_ids},
    )


@login_required
def short_video_add(request):
    if request.method == "POST":
        form = ShortVideoForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.author = request.user
            video.save()
            messages.success(request, "Mini-video publiee.")
            return redirect("short_video_feed")
    else:
        form = ShortVideoForm()
    return render(
        request,
        "nzassa_app/simple_form.html",
        {"form": form, "title": "Ajouter une mini-video", "submit_label": "Publier", "back_url": reverse("short_video_feed")},
    )


@login_required
@require_POST
def short_video_like(request, slug):
    video = get_object_or_404(ShortVideo.objects.select_related("author"), slug=slug, is_published=True)
    if video.likes.filter(id=request.user.id).exists():
        video.likes.remove(request.user)
    else:
        video.likes.add(request.user)
        create_notification(
            video.author,
            request.user,
            "a aime votre mini-video",
            video.title,
            reverse("short_video_feed"),
        )
    return redirect_back(request, "short_video_feed")


@login_required
def learning_groups(request):
    groups = (
        LearningGroup.objects.select_related("language", "owner")
        .annotate(member_count=Count("memberships", distinct=True), post_count=Count("posts", distinct=True))
    )
    my_group_ids = list(request.user.learning_groups.values_list("id", flat=True))
    return render(
        request,
        "nzassa_app/learning_groups.html",
        {"groups": groups, "my_group_ids": my_group_ids},
    )


@login_required
def group_create(request):
    if request.method == "POST":
        form = LearningGroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.owner = request.user
            group.save()
            GroupMembership.objects.get_or_create(group=group, user=request.user, defaults={"role": "owner"})
            messages.success(request, "Groupe cree.")
            return redirect("group_detail", slug=group.slug)
    else:
        form = LearningGroupForm()
    return render(
        request,
        "nzassa_app/simple_form.html",
        {"form": form, "title": "Creer un groupe", "submit_label": "Creer le groupe", "back_url": reverse("learning_groups")},
    )


@login_required
def group_detail(request, slug):
    group = get_object_or_404(LearningGroup.objects.select_related("language", "owner"), slug=slug)
    is_member = GroupMembership.objects.filter(group=group, user=request.user).exists()
    if request.method == "POST" and is_member:
        form = SocialPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.group = group
            post.save()
            messages.success(request, "Publication ajoutee au groupe.")
            return redirect("group_detail", slug=group.slug)
    else:
        form = SocialPostForm(initial={"group": group})

    posts = (
        group.posts.select_related("author")
        .prefetch_related("comments", "comments__author", "likes")
        .annotate(likes_total=Count("likes", distinct=True), comments_total=Count("comments", distinct=True))
    )
    return render(
        request,
        "nzassa_app/group_detail.html",
        {"group": group, "is_member": is_member, "form": form, "posts": posts, "comment_form": SocialCommentForm()},
    )


@login_required
@require_POST
def group_join(request, slug):
    group = get_object_or_404(LearningGroup, slug=slug)
    GroupMembership.objects.get_or_create(group=group, user=request.user)
    messages.success(request, "Vous avez rejoint le groupe.")
    return redirect("group_detail", slug=group.slug)


@login_required
def messages_inbox(request):
    inbox = PrivateMessage.objects.filter(recipient=request.user).select_related("sender", "recipient")
    sent = PrivateMessage.objects.filter(sender=request.user).select_related("sender", "recipient")[:8]
    if request.method == "POST":
        form = PrivateMessageForm(request.POST, request.FILES)
        if form.is_valid():
            private_message = form.save(commit=False)
            private_message.sender = request.user
            private_message.save()
            create_notification(
                private_message.recipient,
                request.user,
                "vous a envoye un message",
                private_message.body[:80],
                reverse("messages_inbox"),
            )
            messages.success(request, "Message envoye.")
            return redirect("messages_inbox")
    else:
        form = PrivateMessageForm()
    return render(
        request,
        "nzassa_app/messages_inbox.html",
        {"form": form, "inbox": inbox, "sent": sent},
    )


@login_required
@require_POST
def friend_request(request, username):
    addressee = get_object_or_404(User, username=username, is_active=True)
    if addressee == request.user:
        messages.error(request, "Impossible de vous ajouter vous-meme.")
    else:
        FriendConnection.objects.get_or_create(requester=request.user, addressee=addressee)
        create_notification(addressee, request.user, "vous a envoye une demande d'ami", "", reverse("notifications"))
        messages.success(request, "Demande envoyee.")
    return redirect_back(request, "discussion_profile", username=username)


@login_required
@require_POST
def friend_accept(request, connection_id):
    connection = get_object_or_404(FriendConnection, id=connection_id, addressee=request.user)
    connection.status = "accepted"
    connection.save(update_fields=["status", "updated_at"])
    messages.success(request, "Demande acceptee.")
    return redirect("notifications")


@login_required
def offline_center(request):
    packs = OfflinePack.objects.filter(user=request.user).select_related("course", "story", "book", "audio")
    downloadable = {
        "courses": Course.objects.filter(is_published=True)[:6],
        "stories": Story.objects.filter(is_published=True)[:6],
        "books": Book.objects.filter(is_published=True)[:6],
        "audio": AudioTrack.objects.filter(is_downloadable=True)[:6],
    }
    return render(
        request,
        "nzassa_app/offline_center.html",
        {"packs": packs, "downloadable": downloadable},
    )


@login_required
@require_POST
def offline_add(request):
    content_type = request.POST.get("content_type")
    object_id = request.POST.get("object_id")
    pack_kwargs = {"user": request.user, "status": "queued"}
    label = "Pack offline"
    if content_type == "course":
        item = get_object_or_404(Course, id=object_id, is_published=True)
        pack_kwargs["course"] = item
        label = item.title
    elif content_type == "story":
        item = get_object_or_404(Story, id=object_id, is_published=True)
        pack_kwargs["story"] = item
        label = item.title
    elif content_type == "book":
        item = get_object_or_404(Book, id=object_id, is_published=True)
        pack_kwargs["book"] = item
        label = item.title
    elif content_type == "audio":
        item = get_object_or_404(AudioTrack, id=object_id, is_downloadable=True)
        pack_kwargs["audio"] = item
        label = item.title
    else:
        messages.error(request, "Contenu offline invalide.")
        return redirect("offline_center")
    OfflinePack.objects.create(**pack_kwargs)
    log_learning_event(request, "offline_pack_queued", label, {"content_type": content_type, "object_id": object_id})
    messages.success(request, "Contenu ajoute a la file offline.")
    return redirect("offline_center")


@login_required
def teacher_dashboard(request):
    owned_schools = School.objects.filter(Q(owner=request.user) | Q(memberships__user=request.user, memberships__role__in=["teacher", "admin"])).distinct()
    teacher_courses = Course.objects.filter(is_published=True).annotate(
        enrolled_count=Count("enrollments", distinct=True),
        completed_count=Count("enrollments", filter=Q(enrollments__status="completed"), distinct=True),
    )
    recent_events = LearningEvent.objects.select_related("user")[:12]
    return render(
        request,
        "nzassa_app/teacher_dashboard.html",
        {
            "owned_schools": owned_schools,
            "teacher_courses": teacher_courses,
            "recent_events": recent_events,
        },
    )


@login_required
def school_create(request):
    if request.method == "POST":
        form = SchoolForm(request.POST)
        if form.is_valid():
            school = form.save(commit=False)
            school.owner = request.user
            school.save()
            SchoolMembership.objects.get_or_create(school=school, user=request.user, defaults={"role": "admin"})
            messages.success(request, "Ecole ajoutee.")
            return redirect("teacher_dashboard")
    else:
        form = SchoolForm()
    return render(
        request,
        "nzassa_app/simple_form.html",
        {"form": form, "title": "Ajouter une ecole", "submit_label": "Creer l'ecole", "back_url": reverse("teacher_dashboard")},
    )


@login_required
@require_POST
def certificate_issue(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug, is_published=True)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    if enrollment.progress_percent < 80:
        messages.error(request, "Le certificat est disponible a partir de 80% de progression.")
        return redirect("course_detail", slug=course.slug)
    certificate = Certificate.objects.create(
        user=request.user,
        course=course,
        code=build_certificate_code(request.user, course),
        level_label=course.level,
        score=enrollment.progress_percent,
    )
    messages.success(request, "Certificat genere.")
    return redirect("certificate_detail", code=certificate.code)


@login_required
@require_GET
def certificate_detail(request, code):
    certificate = get_object_or_404(Certificate.objects.select_related("user", "course"), code=code, user=request.user)
    return render(request, "nzassa_app/certificate_detail.html", {"certificate": certificate})


@login_required
@require_GET
def certificate_pdf(request, code):
    certificate = get_object_or_404(Certificate.objects.select_related("user", "course"), code=code, user=request.user)
    return HttpResponse(
        build_simple_certificate_pdf(certificate),
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{certificate.code}.pdf"'},
    )


@require_GET
def games_hub(request):
    games = EducationalGame.objects.filter(is_published=True).select_related("language")
    fallback_game = build_landing_game_pack()
    return render(
        request,
        "nzassa_app/games_hub.html",
        {"games": games, "fallback_game": fallback_game},
    )


@login_required
def micro_lessons(request):
    if request.method == "POST":
        form = MicroLessonSubscriptionForm(request.POST)
        if form.is_valid():
            subscription = form.save(commit=False)
            subscription.user = request.user
            subscription.save()
            messages.success(request, "Micro-lecons activees.")
            return redirect("micro_lessons")
    else:
        form = MicroLessonSubscriptionForm()
    subscriptions = MicroLessonSubscription.objects.filter(user=request.user).select_related("language")
    return render(
        request,
        "nzassa_app/micro_lessons.html",
        {"form": form, "subscriptions": subscriptions},
    )


@login_required
def mobile_money_payment(request):
    if request.method == "POST":
        form = MobileMoneyPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.user = request.user
            payment.reference = f"NZPAY-{request.user.id}-{get_random_string(8).upper()}"
            payment.save()
            messages.success(request, "Paiement Mobile Money initialise. Statut: en attente.")
            return redirect("pricing")
    else:
        form = MobileMoneyPaymentForm(initial={"amount": 2500})
    return render(
        request,
        "nzassa_app/simple_form.html",
        {"form": form, "title": "Paiement Mobile Money", "submit_label": "Initialiser le paiement", "back_url": reverse("pricing")},
    )


@login_required
def discussion_feed(request):
    if request.method == "POST":
        form = SocialPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            messages.success(request, "Publication ajoutee au fil d'actualite.")
            return redirect("discussion_feed")
    else:
        form = SocialPostForm()

    posts = (
        SocialPost.objects.select_related("author")
        .prefetch_related("likes", "comments", "comments__author")
        .annotate(likes_total=Count("likes", distinct=True), comments_total=Count("comments", distinct=True))
    )
    liked_post_ids = list(request.user.liked_social_posts.values_list("id", flat=True))
    community_stats = {
        "members": User.objects.filter(is_active=True).count(),
        "posts": SocialPost.objects.count(),
        "comments": SocialPost.objects.aggregate(total=Count("comments"))["total"] or 0,
    }
    unread_notifications = get_unread_notifications(request.user)

    return render(
        request,
        "nzassa_app/discussion_feed.html",
        {
            "form": form,
            "comment_form": SocialCommentForm(),
            "posts": posts,
            "liked_post_ids": liked_post_ids,
            "unread_notifications": unread_notifications,
            "community_stats": community_stats,
        },
    )


@login_required
@require_POST
def post_like(request, post_id):
    post = get_object_or_404(SocialPost.objects.select_related("author"), id=post_id)
    if post.likes.filter(id=request.user.id).exists():
        post.likes.remove(request.user)
        messages.info(request, "Like retire.")
    else:
        post.likes.add(request.user)
        create_notification(
            post.author,
            request.user,
            "a aime votre publication",
            post.content[:80],
            reverse("discussion_feed"),
        )
        messages.success(request, "Publication aimee.")
    return redirect_back(request, "discussion_feed")


@login_required
@require_POST
def post_comment(request, post_id):
    post = get_object_or_404(SocialPost.objects.select_related("author"), id=post_id)
    form = SocialCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        create_notification(
            post.author,
            request.user,
            "a commente votre publication",
            post.content[:80],
            reverse("discussion_feed"),
        )
        messages.success(request, "Commentaire ajoute.")
    else:
        messages.error(request, "Le commentaire est vide ou invalide.")
    return redirect_back(request, "discussion_feed")


@login_required
@require_GET
def discussion_profile(request, username):
    profile_user = get_object_or_404(User, username=username, is_active=True)
    user_profile = UserProfile.objects.filter(user=profile_user).select_related("selected_language").first()
    posts = (
        SocialPost.objects.filter(author=profile_user)
        .prefetch_related("likes", "comments")
        .annotate(likes_total=Count("likes", distinct=True), comments_total=Count("comments", distinct=True))
    )
    stats = {
        "posts": posts.count(),
        "comments": sum(post.comments_total for post in posts),
        "likes": sum(post.likes_total for post in posts),
    }
    return render(
        request,
        "nzassa_app/discussion_profile.html",
        {
            "profile_user": profile_user,
            "user_profile": user_profile,
            "posts": posts,
            "stats": stats,
        },
    )


@login_required
def notifications_center(request):
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        messages.success(request, "Notifications marquees comme lues.")
        return redirect("notifications")

    notifications = Notification.objects.filter(recipient=request.user).select_related("actor")
    return render(request, "nzassa_app/notifications.html", {"notifications": notifications})


def build_ai_content_recommendations(prompt, selected_language=None, mode="chat"):
    words = normalize_words(prompt)[:6]

    story_filter = Q(is_published=True)
    book_filter = Q(is_published=True)
    if selected_language:
        story_filter &= Q(ethnicity__name__icontains=selected_language.name) | Q(description__icontains=selected_language.name)
        book_filter &= Q(description__icontains=selected_language.name) | Q(title__icontains=selected_language.name)

    if words:
        story_terms = Q()
        book_terms = Q()
        for word in words:
            story_terms |= (
                Q(title__icontains=word)
                | Q(description__icontains=word)
                | Q(location__icontains=word)
                | Q(ethnicity__name__icontains=word)
            )
            book_terms |= Q(title__icontains=word) | Q(description__icontains=word) | Q(author_name__icontains=word)
        story_filter &= story_terms
        book_filter &= book_terms

    stories = list(Story.objects.filter(story_filter).select_related("ethnicity")[:3])
    books = list(Book.objects.filter(book_filter)[:3])

    if not stories:
        stories = list(Story.objects.filter(is_published=True).select_related("ethnicity")[:3])
    if not books:
        category_map = {"language": "language", "culture": "culture", "quiz": "tale"}
        preferred_category = category_map.get(mode)
        fallback_books = Book.objects.filter(is_published=True)
        if preferred_category:
            fallback_books = fallback_books.filter(category=preferred_category)
        books = list(fallback_books[:3])
        if not books:
            books = list(Book.objects.filter(is_published=True)[:3])

    courses = Course.objects.filter(is_published=True).select_related("language")
    if selected_language:
        courses = courses.filter(language=selected_language)
    return {
        "stories": stories,
        "books": books,
        "courses": list(courses[:3]),
    }


def cultural_ai(request):
    profile = None
    initial = {"mode": "chat", "level": "beginner"}
    selected_language = None
    if request.user.is_authenticated:
        profile = get_or_create_profile(request.user)
        selected_language = profile.selected_language
        initial["target_language"] = selected_language
        initial["level"] = profile.level

    form = CulturalAIForm(request.POST or None, initial=initial)
    ai_result = None
    recommendations = build_ai_content_recommendations("", selected_language=selected_language)
    remote_ai_status = get_remote_ai_status()

    if request.method == "POST" and form.is_valid():
        selected_language = form.cleaned_data["target_language"] or selected_language
        level = form.cleaned_data["level"]
        mode = form.cleaned_data["mode"]
        prompt = form.cleaned_data["prompt"]
        enriched_prompt = (
            f"Niveau apprenant: {level}. Mode demande: {mode}. "
            f"Reponds simplement, propose une activite concrete, puis une suggestion de lecture ou d'histoire. "
            f"Demande: {prompt}"
        )
        conversation = get_or_create_conversation(request, selected_language=selected_language, channel="coach")
        ai_result = chat_with_coach(conversation, enriched_prompt, selected_language=selected_language)
        if ai_result.get("error"):
            messages.error(request, ai_result["error"])
            ai_result = None
        recommendations = build_ai_content_recommendations(prompt, selected_language=selected_language, mode=mode)

    return render(
        request,
        "nzassa_app/cultural_ai.html",
        {
            "form": form,
            "ai_result": ai_result,
            "profile": profile,
            "recommendations": recommendations,
            "remote_ai_status": remote_ai_status,
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
    conversation = get_or_create_conversation(request, selected_language=selected_language, channel="coach")
    recent_messages = list(conversation.messages.order_by("-created_at")[:12])
    recent_messages.reverse()
    learned_words = list(get_memory_queryset(conversation)[:8])
    remote_ai_status = get_remote_ai_status()

    return render(
        request,
        "nzassa_app/coach_ia.html",
        {
            "prompt": prompt,
            "guidance": guidance,
            "profile": profile,
            "selected_language": selected_language,
            "featured_courses": Course.objects.filter(is_published=True).select_related("language")[:4],
            "conversation": conversation,
            "conversation_messages": recent_messages,
            "learned_words": learned_words,
            "remote_ai_status": remote_ai_status,
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

    conversation = get_or_create_conversation(request, selected_language=selected_language, channel="landing")
    response = chat_with_coach(conversation, message, selected_language=selected_language)
    if response.get("error"):
        return JsonResponse({"error": response["error"]}, status=response.get("status", 400))
    return JsonResponse(
        {
            "text": response["reply"],
            "language": response["language"],
            "voice": response["voice"],
            "suggestions": response["suggestions"],
            "source": response["source"],
            "pronunciation_cards": response["pronunciation_cards"],
            "detected_intents": response.get("detected_intents", []),
            "learning_activity": response.get("learning_activity", {}),
        }
    )


@require_POST
def coach_ai_chat(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Payload JSON invalide."}, status=400)

    selected_language = None
    if request.user.is_authenticated:
        selected_language = get_or_create_profile(request.user).selected_language

    conversation = get_or_create_conversation(request, selected_language=selected_language, channel="coach")
    response = chat_with_coach(conversation, payload.get("message", ""), selected_language=selected_language)
    if response.get("error"):
        return JsonResponse({"error": response["error"]}, status=response.get("status", 400))
    return JsonResponse(response)


@require_POST
def coach_pronunciation_feedback(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Payload JSON invalide."}, status=400)

    selected_language = None
    if request.user.is_authenticated:
        selected_language = get_or_create_profile(request.user).selected_language

    conversation = get_or_create_conversation(request, selected_language=selected_language, channel="coach")
    response = evaluate_pronunciation(
        conversation,
        payload.get("word", ""),
        payload.get("transcript", ""),
        language_label=payload.get("language", ""),
        meaning=payload.get("meaning", ""),
        selected_language=selected_language,
    )
    if response.get("error"):
        return JsonResponse({"error": response["error"]}, status=response.get("status", 400))
    return JsonResponse(response)



def ping(request):
    return HttpResponse("OK")

@login_required
@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Vous etes maintenant deconnecte en toute securite.")
    return redirect("accueil")
