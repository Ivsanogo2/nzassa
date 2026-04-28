import json
import logging
import os
import re
import socket
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.db.models import Q
from django.utils import timezone

from .models import (
    CoachConversation,
    CoachMessage,
    Course,
    Language,
    LearnedWord,
    Lesson,
    PronunciationAttempt,
    Traduction,
)


logger = logging.getLogger(__name__)

NZASSA_AI_PROVIDER = os.environ.get("NZASSA_AI_PROVIDER", "auto")
OPENAI_API_URL = os.environ.get("OPENAI_API_URL", "https://api.openai.com/v1/responses")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "medium")
OPENROUTER_API_URL = os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
HUGGINGFACE_API_URL = os.environ.get("HUGGINGFACE_API_URL", "https://router.huggingface.co/v1/chat/completions")
HUGGINGFACE_MODEL = os.environ.get("HUGGINGFACE_MODEL", "Qwen/Qwen2.5-7B-Instruct-1M:fastest")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_URL = os.environ.get("OLLAMA_CHAT_URL", f"{OLLAMA_BASE_URL}/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "2.5"))

WORD_RE = re.compile(r"[a-zA-Z'-]{2,}")

FRENCH_STOPWORDS = {
    "alors",
    "apprendre",
    "apprends",
    "avec",
    "aussi",
    "aux",
    "avoir",
    "bien",
    "bonjour",
    "comment",
    "comme",
    "cours",
    "dans",
    "des",
    "donc",
    "elle",
    "elles",
    "encore",
    "entre",
    "est",
    "etre",
    "faire",
    "faut",
    "ici",
    "ils",
    "je",
    "langue",
    "langues",
    "leur",
    "mais",
    "mes",
    "mieux",
    "mon",
    "mot",
    "mots",
    "nous",
    "notre",
    "par",
    "parcours",
    "pas",
    "plus",
    "pour",
    "quoi",
    "salut",
    "sans",
    "ses",
    "sur",
    "tes",
    "toi",
    "ton",
    "tous",
    "tout",
    "tres",
    "une",
    "veux",
    "vers",
    "votre",
    "vous",
}

LANGUAGE_VOICE_MAP = {
    "FR": "fr-FR",
    "BAO": "fr-CI",
    "DIO": "fr-CI",
    "LSI": "fr-FR",
    "francais": "fr-FR",
    "baoule": "fr-CI",
    "dioula": "fr-CI",
    "langue des signes": "fr-FR",
}

LANGUAGE_HINTS = {
    "francais": "Lis avec des voyelles nettes et un rythme regulier.",
    "baoule": "Marque les voyelles doucement et garde un debit pose.",
    "dioula": "Va mot par mot avec une diction courte et claire.",
    "langue des signes": "Observe le geste, puis redis le sens a voix haute pour le fixer.",
}


def get_requested_ai_provider():
    return (os.environ.get("NZASSA_AI_PROVIDER", NZASSA_AI_PROVIDER) or "auto").strip().lower()


def request_json(url, timeout=3):
    with urllib_request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_is_available():
    try:
        request_json(f"{os.environ.get('OLLAMA_BASE_URL', OLLAMA_BASE_URL)}/api/tags", timeout=1.2)
        return True
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError, socket.timeout, ValueError):
        return False


def get_remote_ai_provider():
    requested = get_requested_ai_provider()
    if requested in {"local", "none", "offline"}:
        return None

    provider_checks = {
        "ollama": ollama_is_available(),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
        "huggingface": bool(os.environ.get("HF_TOKEN")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
    }

    if requested in provider_checks:
        return requested if provider_checks[requested] else None

    if provider_checks["ollama"]:
        return "ollama"
    if provider_checks["openrouter"]:
        return "openrouter"
    if provider_checks["huggingface"]:
        return "huggingface"
    if provider_checks["openai"]:
        return "openai"
    return None


def get_remote_ai_status():
    provider = get_remote_ai_provider()
    if provider == "ollama":
        return {
            "enabled": True,
            "provider": "ollama",
            "label": "Ollama local",
            "model": os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL),
        }
    if provider == "openrouter":
        return {
            "enabled": True,
            "provider": "openrouter",
            "label": "OpenRouter gratuit",
            "model": os.environ.get("OPENROUTER_MODEL", OPENROUTER_MODEL),
        }
    if provider == "huggingface":
        return {
            "enabled": True,
            "provider": "huggingface",
            "label": "Hugging Face",
            "model": os.environ.get("HUGGINGFACE_MODEL", HUGGINGFACE_MODEL),
        }
    if provider == "openai":
        return {
            "enabled": True,
            "provider": "openai",
            "label": "OpenAI",
            "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
        }
    return {
        "enabled": False,
        "provider": "local",
        "label": "Mode local intelligent",
        "model": "",
    }


def strip_accents(text):
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_lookup_text(text):
    lowered = strip_accents((text or "").strip().lower())
    return re.sub(r"\s+", " ", lowered)


def extract_words(text):
    cleaned = normalize_lookup_text(text)
    words = []
    for word in WORD_RE.findall(cleaned):
        if word in FRENCH_STOPWORDS:
            continue
        words.append(word)
    return words


def build_owner_key(user=None, session_key=""):
    if user and user.is_authenticated:
        return f"user:{user.id}"
    return f"session:{session_key or 'anonymous'}"


def ensure_session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def get_voice(language_code="", language_label="", selected_language=None):
    if language_code and language_code in LANGUAGE_VOICE_MAP:
        return LANGUAGE_VOICE_MAP[language_code]

    if language_label:
        lookup = normalize_lookup_text(language_label)
        if lookup in LANGUAGE_VOICE_MAP:
            return LANGUAGE_VOICE_MAP[lookup]

    if selected_language:
        if selected_language.code in LANGUAGE_VOICE_MAP:
            return LANGUAGE_VOICE_MAP[selected_language.code]
        lookup = normalize_lookup_text(selected_language.name)
        if lookup in LANGUAGE_VOICE_MAP:
            return LANGUAGE_VOICE_MAP[lookup]

    return "fr-FR"


def get_pronunciation_hint(language_label):
    lookup = normalize_lookup_text(language_label)
    return LANGUAGE_HINTS.get(
        lookup,
        "Commence lentement, repete trois fois, puis reutilise le mot dans une phrase simple.",
    )


def serialize_message(message):
    return {
        "role": message.role,
        "content": message.content,
        "used_openai": message.used_openai,
        "created_at": message.created_at.isoformat(),
    }


def serialize_word(word):
    return {
        "word": word.word,
        "language": word.language_label or (word.language.name if word.language_id else "Francais"),
        "meaning": word.meaning,
        "example": word.example,
        "pronunciation_hint": word.pronunciation_hint,
        "times_seen": word.times_seen,
        "times_practiced": word.times_practiced,
        "times_correct": word.times_correct,
        "mastery_level": word.mastery_level,
        "success_rate": word.success_rate,
    }


def serialize_course(course):
    return {
        "title": course.title,
        "language": course.language.name,
        "level": course.level,
        "short_description": course.short_description,
        "slug": course.slug,
    }


def serialize_lesson(lesson):
    return {
        "title": lesson.title,
        "course": lesson.module.course.title,
        "lesson_type": lesson.lesson_type,
        "key_phrase": lesson.key_phrase,
    }


def get_or_create_conversation(request, selected_language=None, channel="coach"):
    session_key = ensure_session_key(request)
    session_name = f"nzassa_{channel}_conversation_id"
    conversation_id = request.session.get(session_name)

    conversation = None
    if conversation_id:
        queryset = CoachConversation.objects.filter(id=conversation_id, channel=channel)
        if request.user.is_authenticated:
            queryset = queryset.filter(user=request.user)
        else:
            queryset = queryset.filter(session_key=session_key)
        conversation = queryset.first()

    if not conversation:
        conversation = CoachConversation.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key=session_key,
            channel=channel,
            selected_language=selected_language,
        )
        request.session[session_name] = conversation.id
    else:
        fields_to_update = []
        if conversation.session_key != session_key:
            conversation.session_key = session_key
            fields_to_update.append("session_key")
        if request.user.is_authenticated and conversation.user_id != request.user.id:
            conversation.user = request.user
            fields_to_update.append("user")
        if selected_language and conversation.selected_language_id != selected_language.id:
            conversation.selected_language = selected_language
            fields_to_update.append("selected_language")
        if fields_to_update:
            conversation.save(update_fields=fields_to_update + ["updated_at"])

    return conversation


def get_memory_queryset(conversation):
    queryset = LearnedWord.objects.filter(owner_key=build_owner_key(conversation.user, conversation.session_key))
    if conversation.user_id:
        queryset = queryset.filter(Q(user=conversation.user) | Q(user__isnull=True))
    return queryset.select_related("language")


def build_discovered_vocabulary(limit=18):
    word_counter = Counter()
    word_sources = {}

    for traduction in Traduction.objects.all():
        for word in extract_words(traduction.mot_origine):
            word_counter[word] += 3
            word_sources.setdefault(
                word,
                {
                    "word": word,
                    "language": traduction.get_langue_cible_display(),
                    "language_code": traduction.langue_cible,
                    "source": "Dictionnaire Nzassa",
                    "hint": traduction.resultat_traduction,
                },
            )

        for word in extract_words(traduction.resultat_traduction):
            word_counter[word] += 1
            word_sources.setdefault(
                word,
                {
                    "word": word,
                    "language": traduction.get_langue_cible_display(),
                    "language_code": traduction.langue_cible,
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
        for word in extract_words(payload):
            word_counter[word] += 1
            word_sources.setdefault(
                word,
                {
                    "word": word,
                    "language": lesson.module.course.language.name,
                    "language_code": lesson.module.course.language.code,
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


def build_pronunciation_cards(
    prompt,
    translations,
    discovered_vocabulary,
    selected_language=None,
    learned_words=None,
):
    cards = []
    seen = set()

    for learned_word in learned_words or []:
        key = (normalize_lookup_text(learned_word.word), learned_word.language_label)
        if key in seen:
            continue
        seen.add(key)
        cards.append(
            {
                "word": learned_word.word,
                "origin": learned_word.meaning or "Mot deja pratique",
                "language": learned_word.language_label or "Francais",
                "voice": get_voice(language_label=learned_word.language_label, selected_language=selected_language),
                "pronunciation_tip": learned_word.pronunciation_hint or get_pronunciation_hint(learned_word.language_label or "francais"),
                "coach_prompt": learned_word.example or f"Repete {learned_word.word} a voix haute puis fais une phrase courte.",
            }
        )

    for traduction in translations:
        language_label = traduction.get_langue_cible_display()
        card = {
            "word": traduction.resultat_traduction,
            "origin": traduction.mot_origine,
            "language": language_label,
            "voice": get_voice(language_code=traduction.langue_cible, language_label=language_label, selected_language=selected_language),
            "pronunciation_tip": get_pronunciation_hint(language_label),
            "coach_prompt": f"Ecoute {traduction.resultat_traduction}, puis redis-le en pensant a {traduction.mot_origine}.",
        }
        key = (normalize_lookup_text(card["word"]), card["language"])
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)

    for item in discovered_vocabulary:
        if prompt:
            prompt_lookup = normalize_lookup_text(prompt)
            word_lookup = normalize_lookup_text(item["word"])
            if prompt_lookup not in word_lookup and word_lookup not in prompt_lookup:
                continue

        card = {
            "word": item["word"].title(),
            "origin": item["hint"],
            "language": item["language"],
            "voice": get_voice(language_code=item.get("language_code", ""), language_label=item["language"], selected_language=selected_language),
            "pronunciation_tip": get_pronunciation_hint(item["language"]),
            "coach_prompt": f"Repete {item['word']} trois fois, puis dis une phrase avec ce mot.",
        }
        key = (normalize_lookup_text(card["word"]), card["language"])
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)
        if len(cards) >= 6:
            break

    if not cards:
        cards.append(
            {
                "word": (prompt or "Nzassa").title(),
                "origin": "Mot de depart",
                "language": selected_language.name if selected_language else "Francais",
                "voice": get_voice(selected_language=selected_language),
                "pronunciation_tip": "Ecoute une fois, repete lentement, puis redis le mot avec plus de fluidite.",
                "coach_prompt": "Commence par prononcer le mot, puis utilise-le dans une phrase simple.",
            }
        )

    return cards[:6]


def gather_knowledge(prompt, selected_language=None):
    prompt = (prompt or "").strip()
    words = extract_words(prompt)
    lookup_terms = words or [normalize_lookup_text(prompt)] if prompt else []

    translation_query = Q()
    course_query = Q()
    lesson_query = Q()
    for term in lookup_terms:
        translation_query |= Q(mot_origine__icontains=term) | Q(resultat_traduction__icontains=term)
        course_query |= Q(title__icontains=term) | Q(short_description__icontains=term) | Q(description__icontains=term)
        lesson_query |= Q(title__icontains=term) | Q(content__icontains=term) | Q(key_phrase__icontains=term)

    translations = []
    if translation_query:
        translations = list(Traduction.objects.filter(translation_query)[:6])

    related_courses = Course.objects.filter(is_published=True).select_related("language")
    if selected_language:
        related_courses = related_courses.filter(language=selected_language)
    if course_query:
        related_courses = list(related_courses.filter(course_query)[:4])
    else:
        related_courses = list(related_courses[:4])

    related_lessons = Lesson.objects.select_related("module__course", "module__course__language")
    if lesson_query:
        related_lessons = list(related_lessons.filter(lesson_query)[:4])
    else:
        related_lessons = list(related_lessons[:4])

    discovered = build_discovered_vocabulary(limit=12)
    prompt_lookup = normalize_lookup_text(prompt)
    discovered_matches = [
        item
        for item in discovered
        if prompt_lookup and (
            prompt_lookup in normalize_lookup_text(item["word"])
            or normalize_lookup_text(item["word"]) in prompt_lookup
        )
    ]

    return {
        "translations": translations,
        "courses": related_courses,
        "lessons": related_lessons,
        "discovered": discovered,
        "discovered_matches": discovered_matches,
    }


def build_follow_up_suggestions(knowledge, learned_words, selected_language=None):
    suggestions = []

    if knowledge["translations"]:
        first = knowledge["translations"][0]
        suggestions.append(f"Prononcer {first.resultat_traduction}")
        suggestions.append(f"Faire une phrase avec {first.resultat_traduction}")

    if learned_words:
        suggestions.append(f"Reviser {learned_words[0].word}")

    if selected_language:
        suggestions.append(f"Une conversation en {selected_language.name}")
    else:
        suggestions.append("Apprendre le baoule")

    if knowledge["lessons"]:
        suggestions.append(f"Exercice sur {knowledge['lessons'][0].title}")

    deduped = []
    for item in suggestions:
        if item not in deduped:
            deduped.append(item)
    return deduped[:4]


def build_local_reply(message, knowledge, memory_words, selected_language=None):
    message = (message or "").strip()
    translations = knowledge["translations"]
    lessons = knowledge["lessons"]
    courses = knowledge["courses"]

    lines = []

    if memory_words:
        lines.append(
            f"Je me souviens que tu as deja travaille {memory_words[0].word}. On va avancer a partir de la."
        )
    else:
        lines.append("On va apprendre ce point pas a pas, comme dans une vraie discussion de coach.")

    if translations:
        for traduction in translations[:2]:
            language_label = traduction.get_langue_cible_display()
            lines.append(
                f"En {language_label}, '{traduction.mot_origine}' se dit '{traduction.resultat_traduction}'. "
                f"Prononciation: {get_pronunciation_hint(language_label)}"
            )
        lines.append(
            f"Mini-exercice: repete '{translations[0].resultat_traduction}' trois fois, puis utilise-le dans une phrase courte."
        )
    elif lessons:
        lesson = lessons[0]
        lines.append(
            f"Je n'ai pas trouve une traduction exacte pour '{message}', mais j'ai trouve la lecon '{lesson.title}' dans le parcours '{lesson.module.course.title}'."
        )
        if lesson.key_phrase:
            lines.append(f"Phrase utile a retenir: {lesson.key_phrase}.")
        lines.append("Je peux maintenant t'aider a transformer cette lecon en mots faciles a retenir et a prononcer.")
    elif courses:
        course = courses[0]
        lines.append(
            f"Le meilleur point d'entree pour '{message}' est le parcours '{course.title}' en {course.language.name}."
        )
        lines.append(
            "Je peux te construire une mini-seance avec 3 mots, leur sens, la prononciation et un petit test oral."
        )
    else:
        language_name = selected_language.name if selected_language else "Nzassa"
        lines.append(
            f"Je n'ai pas encore ce mot dans ma base locale, mais je peux le ranger dans ton parcours et l'expliquer en lien avec {language_name}."
        )
        lines.append(
            "Commence par me dire si tu veux le sens, une phrase d'exemple ou un exercice de prononciation."
        )

    lines.append("Dis-moi maintenant: tu veux le sens, la prononciation ou une phrase complete ?")
    return "\n".join(lines)


def build_openai_instructions(selected_language=None):
    language_hint = selected_language.name if selected_language else "francais"
    return (
        "Tu es Coach Nzassa, un tuteur conversationnel pour apprendre les langues et cultures africaines. "
        "Tu ne repetes pas mecanquement. Tu raisonnes, tu relies les mots au contexte, tu te souviens des mots deja vus, "
        "et tu aides a mieux prononcer. Reponds en francais simple sauf demande contraire. "
        "N'enseigne pas plus de 3 mots nouveaux a la fois. Pour chaque mot, donne le sens, un conseil de prononciation "
        "et une mini-phrase. Termine toujours par un exercice ou une question. "
        f"La langue preferee actuelle de l'apprenant est: {language_hint}. "
        "Si une traduction n'apparait pas dans la base locale fournie, dis-le clairement au lieu d'inventer."
    )


def build_openai_context(message, knowledge, memory_words, selected_language=None):
    translation_lines = [
        f"- {item.mot_origine} -> {item.resultat_traduction} ({item.get_langue_cible_display()})"
        for item in knowledge["translations"][:6]
    ]
    lesson_lines = [
        f"- {item.title} | parcours: {item.module.course.title} | phrase cle: {item.key_phrase or 'aucune'}"
        for item in knowledge["lessons"][:4]
    ]
    course_lines = [
        f"- {item.title} ({item.language.name}, {item.level})"
        for item in knowledge["courses"][:4]
    ]
    memory_lines = [
        f"- {item.word} | maitrise: {item.mastery_level}% | succes prononciation: {item.success_rate}%"
        for item in memory_words[:6]
    ]

    return "\n".join(
        [
            "Contexte local Nzassa:",
            f"Langue preferee: {selected_language.name if selected_language else 'non definie'}",
            "Traductions disponibles:",
            "\n".join(translation_lines) if translation_lines else "- aucune correspondance exacte",
            "Lecons reliees:",
            "\n".join(lesson_lines) if lesson_lines else "- aucune lecon ciblee",
            "Parcours relies:",
            "\n".join(course_lines) if course_lines else "- aucun parcours cible",
            "Memoire apprenant:",
            "\n".join(memory_lines) if memory_lines else "- aucun mot memorise pour l'instant",
            f"Message de l'apprenant: {message}",
        ]
    )


def extract_response_text(payload):
    if payload.get("output_text"):
        return payload["output_text"].strip()

    pieces = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text") or content.get("output_text")
            if text:
                pieces.append(text)
    return "\n".join(piece.strip() for piece in pieces if piece).strip()


def extract_chat_completion_text(payload):
    choices = payload.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    pieces = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            pieces.append(item["text"])
    return "\n".join(piece.strip() for piece in pieces if piece).strip()


def extract_ollama_text(payload):
    message = payload.get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    return ""


def post_json_request(url, body, headers, timeout=45):
    request = urllib_request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    with urllib_request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_remote_chat_messages(message, conversation, knowledge, memory_words, selected_language=None):
    history = list(conversation.messages.order_by("-created_at")[1:9])
    history.reverse()

    messages = [
        {
            "role": "system",
            "content": build_openai_instructions(selected_language),
        }
    ]
    messages.extend(
        {"role": past_message.role, "content": past_message.content}
        for past_message in history
    )
    messages.append(
        {
            "role": "user",
            "content": build_openai_context(message, knowledge, memory_words, selected_language),
        }
    )
    return messages


def call_openai_reply(message, conversation, knowledge, memory_words, selected_language=None):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    body = {
        "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
        "instructions": build_openai_instructions(selected_language),
        "input": build_remote_chat_messages(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        )[1:],
        "reasoning": {"effort": os.environ.get("OPENAI_REASONING_EFFORT", OPENAI_REASONING_EFFORT)},
    }

    try:
        payload = post_json_request(
            os.environ.get("OPENAI_API_URL", OPENAI_API_URL),
            body,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        logger.warning("OpenAI HTTP error: %s", details)
        return None
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("OpenAI request failed: %s", exc)
        return None

    text = extract_response_text(payload)
    if not text:
        return None

    return {
        "text": text,
        "response_id": payload.get("id", ""),
        "provider": "openai",
        "provider_label": "OpenAI",
        "provider_model": payload.get("model", body["model"]),
    }


def call_openrouter_reply(message, conversation, knowledge, memory_words, selected_language=None):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    body = {
        "model": os.environ.get("OPENROUTER_MODEL", OPENROUTER_MODEL),
        "messages": build_remote_chat_messages(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        ),
        "temperature": 0.35,
        "max_tokens": 700,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nzassa.local",
        "X-Title": "Nzassa School",
    }

    try:
        payload = post_json_request(
            os.environ.get("OPENROUTER_API_URL", OPENROUTER_API_URL),
            body,
            headers,
        )
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        logger.warning("OpenRouter HTTP error: %s", details)
        return None
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("OpenRouter request failed: %s", exc)
        return None

    text = extract_chat_completion_text(payload)
    if not text:
        return None

    return {
        "text": text,
        "response_id": payload.get("id", ""),
        "provider": "openrouter",
        "provider_label": "OpenRouter gratuit",
        "provider_model": payload.get("model", body["model"]),
    }


def call_ollama_reply(message, conversation, knowledge, memory_words, selected_language=None):
    if not ollama_is_available():
        return None

    body = {
        "model": os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL),
        "messages": build_remote_chat_messages(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        ),
        "stream": False,
    }

    try:
        payload = post_json_request(
            os.environ.get("OLLAMA_CHAT_URL", OLLAMA_CHAT_URL),
            body,
            {
                "Content-Type": "application/json",
            },
            timeout=max(10, OLLAMA_TIMEOUT_S * 2),
        )
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        logger.warning("Ollama HTTP error: %s", details)
        return None
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError, socket.timeout, ValueError) as exc:
        logger.warning("Ollama request failed: %s", exc)
        return None

    text = extract_ollama_text(payload)
    if not text:
        return None

    return {
        "text": text,
        "response_id": "",
        "provider": "ollama",
        "provider_label": "Ollama local",
        "provider_model": body["model"],
    }


def call_huggingface_reply(message, conversation, knowledge, memory_words, selected_language=None):
    api_key = os.environ.get("HF_TOKEN")
    if not api_key:
        return None

    body = {
        "model": os.environ.get("HUGGINGFACE_MODEL", HUGGINGFACE_MODEL),
        "messages": build_remote_chat_messages(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        ),
        "max_tokens": 700,
        "temperature": 0.35,
    }

    try:
        payload = post_json_request(
            os.environ.get("HUGGINGFACE_API_URL", HUGGINGFACE_API_URL),
            body,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        logger.warning("Hugging Face HTTP error: %s", details)
        return None
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Hugging Face request failed: %s", exc)
        return None

    text = extract_chat_completion_text(payload)
    if not text:
        return None

    return {
        "text": text,
        "response_id": payload.get("id", ""),
        "provider": "huggingface",
        "provider_label": "Hugging Face",
        "provider_model": payload.get("model", body["model"]),
    }


def call_remote_reply(message, conversation, knowledge, memory_words, selected_language=None):
    provider = get_remote_ai_provider()
    if provider == "ollama":
        return call_ollama_reply(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        )
    if provider == "openrouter":
        return call_openrouter_reply(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        )
    if provider == "huggingface":
        return call_huggingface_reply(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        )
    if provider == "openai":
        return call_openai_reply(
            message,
            conversation,
            knowledge,
            memory_words,
            selected_language=selected_language,
        )
    return None


def sync_learned_words(conversation, cards, selected_language=None):
    owner_key = build_owner_key(conversation.user, conversation.session_key)
    synced_entries = []

    for card in cards[:6]:
        normalized_word = normalize_lookup_text(card["word"])
        language_label = card["language"]
        defaults = {
            "conversation": conversation,
            "user": conversation.user,
            "session_key": conversation.session_key,
            "language": selected_language,
            "word": card["word"],
            "meaning": card["origin"],
            "example": card["coach_prompt"],
            "pronunciation_hint": card["pronunciation_tip"],
        }
        entry, _ = LearnedWord.objects.get_or_create(
            owner_key=owner_key,
            normalized_word=normalized_word,
            language_label=language_label,
            defaults=defaults,
        )

        entry.conversation = conversation
        entry.user = conversation.user
        entry.session_key = conversation.session_key
        if not entry.word:
            entry.word = card["word"]
        if not entry.meaning:
            entry.meaning = card["origin"]
        if not entry.example:
            entry.example = card["coach_prompt"]
        if not entry.pronunciation_hint:
            entry.pronunciation_hint = card["pronunciation_tip"]
        if selected_language and not entry.language_id:
            entry.language = selected_language
        entry.times_seen += 1
        entry.mastery_level = min(100, (entry.times_correct * 15) + (entry.times_seen * 5))
        entry.save()
        synced_entries.append(entry)

    return synced_entries


def chat_with_coach(conversation, message, selected_language=None):
    clean_message = (message or "").strip()
    if not clean_message:
        return {
            "error": "Le message est vide.",
            "status": 400,
        }

    knowledge = gather_knowledge(clean_message, selected_language=selected_language)
    memory_words = list(get_memory_queryset(conversation)[:6])

    CoachMessage.objects.create(
        conversation=conversation,
        role="user",
        content=clean_message,
        used_openai=False,
    )

    remote_reply = call_remote_reply(
        clean_message,
        conversation,
        knowledge,
        memory_words,
        selected_language=selected_language,
    )

    if remote_reply:
        assistant_text = remote_reply["text"]
        used_openai = True
        conversation.last_remote_response_id = remote_reply["response_id"]
        conversation.save(update_fields=["last_remote_response_id", "updated_at"])
    else:
        assistant_text = build_local_reply(
            clean_message,
            knowledge,
            memory_words,
            selected_language=selected_language,
        )
        used_openai = False

    if not conversation.title:
        conversation.title = clean_message[:180]
        conversation.save(update_fields=["title", "updated_at"])

    assistant_message = CoachMessage.objects.create(
        conversation=conversation,
        role="assistant",
        content=assistant_text,
        used_openai=used_openai,
    )

    cards = build_pronunciation_cards(
        clean_message,
        knowledge["translations"],
        knowledge["discovered_matches"] or knowledge["discovered"],
        selected_language=selected_language,
        learned_words=memory_words,
    )
    sync_learned_words(conversation, cards, selected_language=selected_language)
    refreshed_words = list(get_memory_queryset(conversation)[:8])
    suggestions = build_follow_up_suggestions(knowledge, refreshed_words, selected_language=selected_language)

    first_language = cards[0]["language"] if cards else "francais"
    speech_language = normalize_lookup_text(first_language)
    if speech_language not in {"baoule", "dioula", "francais"}:
        speech_language = "francais"

    return {
        "conversation_id": conversation.id,
        "reply": assistant_message.content,
        "source": remote_reply["provider"] if remote_reply else "local",
        "provider_label": remote_reply["provider_label"] if remote_reply else "Mode local intelligent",
        "provider_model": remote_reply["provider_model"] if remote_reply else "",
        "voice": cards[0]["voice"] if cards else get_voice(selected_language=selected_language),
        "language": speech_language,
        "suggestions": suggestions,
        "pronunciation_cards": cards,
        "learned_words": [serialize_word(word) for word in refreshed_words],
        "related_courses": [serialize_course(course) for course in knowledge["courses"][:3]],
        "related_lessons": [serialize_lesson(lesson) for lesson in knowledge["lessons"][:3]],
        "messages": [serialize_message(message) for message in conversation.messages.order_by("-created_at")[:12]][::-1],
    }


def build_pronunciation_feedback(score):
    if score >= 92:
        return "Tres bonne prononciation. Garde ce rythme et essaie maintenant une phrase complete."
    if score >= 75:
        return "Bonne tentative. Ralentis un peu sur les syllabes et repete encore deux fois."
    if score >= 55:
        return "On commence a reconnaitre le mot. Coupe-le en syllabes puis recommence plus lentement."
    return "Le mot n'est pas encore reconnu correctement. Ecoute le modele puis repete mot par mot."


def score_pronunciation(expected_word, transcript):
    expected = normalize_lookup_text(expected_word)
    spoken = normalize_lookup_text(transcript)

    if not expected:
        return 0
    if not spoken:
        return 0

    variants = [spoken] + spoken.split()
    ratios = [SequenceMatcher(None, expected, variant).ratio() for variant in variants if variant]
    return round(max(ratios, default=0) * 100)


def evaluate_pronunciation(conversation, word, transcript, language_label="", meaning="", selected_language=None):
    clean_word = (word or "").strip()
    clean_transcript = (transcript or "").strip()

    if not clean_word:
        return {"error": "Aucun mot a evaluer.", "status": 400}

    owner_key = build_owner_key(conversation.user, conversation.session_key)
    language_label = language_label or (selected_language.name if selected_language else "Francais")
    normalized_word = normalize_lookup_text(clean_word)

    learned_word, _ = LearnedWord.objects.get_or_create(
        owner_key=owner_key,
        normalized_word=normalized_word,
        language_label=language_label,
        defaults={
            "conversation": conversation,
            "user": conversation.user,
            "session_key": conversation.session_key,
            "language": selected_language,
            "word": clean_word,
            "meaning": meaning,
            "pronunciation_hint": get_pronunciation_hint(language_label),
        },
    )

    score = score_pronunciation(clean_word, clean_transcript)
    feedback = build_pronunciation_feedback(score)

    learned_word.conversation = conversation
    learned_word.user = conversation.user
    learned_word.session_key = conversation.session_key
    learned_word.word = learned_word.word or clean_word
    learned_word.times_practiced += 1
    learned_word.times_seen = max(learned_word.times_seen, 1)
    if meaning and not learned_word.meaning:
        learned_word.meaning = meaning
    if score >= 75:
        learned_word.times_correct += 1
    learned_word.last_practiced_at = timezone.now()
    learned_word.mastery_level = min(
        100,
        (learned_word.times_correct * 20) + (learned_word.times_seen * 5),
    )
    learned_word.save()

    PronunciationAttempt.objects.create(
        learned_word=learned_word,
        conversation=conversation,
        expected_word=clean_word,
        transcript=clean_transcript,
        score=score,
        feedback=feedback,
    )

    return {
        "word": clean_word,
        "transcript": clean_transcript,
        "score": score,
        "feedback": feedback,
        "mastery_level": learned_word.mastery_level,
        "success_rate": learned_word.success_rate,
        "times_practiced": learned_word.times_practiced,
    }
