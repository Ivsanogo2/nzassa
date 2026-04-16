from django.core.management.base import BaseCommand

from nzassa_app.models import (
    Badge,
    Course,
    CulturalExperience,
    Language,
    Lesson,
    Module,
    QuizQuestion,
    Traduction,
)


class Command(BaseCommand):
    help = "Injecte un jeu de donnees demo pour Nzassa School."

    def handle(self, *args, **options):
        baoule, _ = Language.objects.get_or_create(
            code="BAO",
            defaults={
                "name": "Baoule",
                "description": "Apprentissage progressif du baoule avec culture et oral.",
                "difficulty": "Debutant",
            },
        )
        dioula, _ = Language.objects.get_or_create(
            code="DIO",
            defaults={
                "name": "Dioula",
                "description": "Parcours utile pour voyage, commerce et conversation.",
                "difficulty": "Debutant",
            },
        )
        lsi, _ = Language.objects.get_or_create(
            code="LSI",
            defaults={
                "name": "Langue des signes ivoirienne",
                "description": "Accessibilite, inclusion et pratique gestuelle.",
                "category": "sign",
                "difficulty": "Intermediaire",
            },
        )

        self.create_course(
            language=baoule,
            title="Baoule Essentiel",
            short_description="Premiers mots, salutations, famille et culture baoule.",
            description="Un parcours d'entree pour apprendre les bases du baoule avec contexte culturel et mini quiz.",
            focus="language",
            level="Debutant",
            lessons_data=[
                {
                    "module": "Demarrer",
                    "summary": "Les premieres expressions utiles.",
                    "lessons": [
                        {
                            "title": "Saluer avec respect",
                            "type": "conversation",
                            "content": "Apprenez a dire bonjour, merci et bienvenue dans un contexte quotidien.",
                            "culture_note": "La salutation est un marqueur de respect et de lien social.",
                            "key_phrase": "Akwaba",
                            "questions": [
                                ("Comment dire bienvenue ?", "Akwaba", "Bia", "Nanan", "Aman", "A", "Akwaba signifie bienvenue."),
                                ("Quel geste accompagne souvent la salutation ?", "Ignorer", "Saluer avec respect", "Tourner le dos", "Crier", "B", "La politesse compte dans la culture locale."),
                            ],
                        },
                        {
                            "title": "Famille et quotidien",
                            "type": "vocabulary",
                            "content": "Maitrisez quelques mots pour la famille et la vie de tous les jours.",
                            "culture_note": "La famille et les aines occupent une place centrale.",
                            "key_phrase": "Nanan",
                            "questions": [
                                ("Nanan evoque surtout...", "Un vehicule", "Le respect des aines", "Une ville", "Un aliment", "B", "Le mot est souvent associe aux aines et a l'autorite."),
                            ],
                        },
                    ],
                }
            ],
        )

        self.create_course(
            language=dioula,
            title="Dioula Voyageur",
            short_description="Phrases utiles pour demander, negocier et se repérer.",
            description="Un parcours pratique pour se deplacer, demander des informations et tenir une conversation simple.",
            focus="language",
            level="Debutant",
            lessons_data=[
                {
                    "module": "Se debrouiller partout",
                    "summary": "Les bases utiles pour le terrain.",
                    "lessons": [
                        {
                            "title": "Demander son chemin",
                            "type": "conversation",
                            "content": "Apprenez a demander ou aller et comprendre les reponses simples.",
                            "culture_note": "Le dioula joue souvent un role de langue de contact.",
                            "key_phrase": "I ni ce",
                            "questions": [
                                ("I ni ce correspond a...", "Merci", "Bonjour", "Au revoir", "Pardon", "B", "C'est une formule de salutation."),
                            ],
                        }
                    ],
                }
            ],
        )

        self.create_course(
            language=lsi,
            title="Signes et Inclusion",
            short_description="Comprendre des signes utiles et construire des messages simples.",
            description="Parcours d'introduction a la langue des signes avec repetition, reconnaissance et accessibilite.",
            focus="sign",
            level="Intermediaire",
            is_premium=True,
            lessons_data=[
                {
                    "module": "Premiers gestes",
                    "summary": "Mains, rythme et lecture du geste.",
                    "lessons": [
                        {
                            "title": "Signes du quotidien",
                            "type": "sign",
                            "content": "Associez les gestes aux besoins quotidiens comme manger, boire et bonjour.",
                            "culture_note": "L'inclusion passe par l'apprentissage visible et la repetition.",
                            "key_phrase": "MANGER",
                            "questions": [
                                ("Quel mot est deja detecte dans la demo signes ?", "Dormir", "MANGER", "Ecole", "Maison", "B", "Le prototype actuel reconnait deja MANGER."),
                            ],
                        }
                    ],
                }
            ],
        )

        for threshold, name, description in [
            (30, "Premier pas", "Valider une premiere lecon."),
            (90, "Explorateur culturel", "Accumuler assez de XP pour installer une habitude."),
            (150, "Ambassadeur Nzassa", "Montrer une progression forte sur plusieurs modules."),
        ]:
            Badge.objects.get_or_create(
                name=name,
                defaults={"xp_threshold": threshold, "description": description},
            )

        experiences = [
            (
                "Village VR Baoule",
                "vr",
                "Immersion dans un decor culturel avec objets, habitat et vocabulaire contextuel.",
                "Entrer en VR",
                "/immersion/",
                True,
            ),
            (
                "Atelier signes",
                "sign",
                "Pratique des gestes avec reconnaissance visuelle et feedback instantane.",
                "Tester les signes",
                "/ia-signes/",
                False,
            ),
            (
                "Coach IA",
                "ai",
                "Conversation guidee, correction et encouragement personalise.",
                "Bientot disponible",
                "",
                True,
            ),
        ]
        for title, experience_type, description, cta_label, cta_url, is_premium in experiences:
            CulturalExperience.objects.get_or_create(
                title=title,
                defaults={
                    "experience_type": experience_type,
                    "description": description,
                    "cta_label": cta_label,
                    "cta_url": cta_url,
                    "is_premium": is_premium,
                },
            )

        for mot_origine, langue_cible, resultat in [
            ("bonjour", "BAO", "Akwaba"),
            ("merci", "BAO", "Mo ni"),
            ("bienvenue", "DIO", "I ni sogoma"),
        ]:
            Traduction.objects.get_or_create(
                mot_origine=mot_origine,
                langue_cible=langue_cible,
                defaults={"resultat_traduction": resultat},
            )

        self.stdout.write(self.style.SUCCESS("Jeu de donnees Nzassa injecte."))

    def create_course(
        self,
        language,
        title,
        short_description,
        description,
        focus,
        level,
        lessons_data,
        is_premium=False,
    ):
        course, _ = Course.objects.get_or_create(
            title=title,
            defaults={
                "language": language,
                "short_description": short_description,
                "description": description,
                "focus": focus,
                "level": level,
                "estimated_minutes": 45,
                "xp_reward": 120,
                "is_premium": is_premium,
            },
        )

        if course.modules.exists():
            return course

        for module_index, module_data in enumerate(lessons_data, start=1):
            module = Module.objects.create(
                course=course,
                title=module_data["module"],
                order=module_index,
                summary=module_data["summary"],
            )
            for lesson_index, lesson_data in enumerate(module_data["lessons"], start=1):
                lesson = Lesson.objects.create(
                    module=module,
                    title=lesson_data["title"],
                    order=lesson_index,
                    lesson_type=lesson_data["type"],
                    content=lesson_data["content"],
                    culture_note=lesson_data["culture_note"],
                    key_phrase=lesson_data["key_phrase"],
                    estimated_minutes=12,
                    xp_reward=30,
                )
                for prompt, a, b, c, d, correct, explanation in lesson_data["questions"]:
                    QuizQuestion.objects.create(
                        lesson=lesson,
                        prompt=prompt,
                        choice_a=a,
                        choice_b=b,
                        choice_c=c,
                        choice_d=d,
                        correct_choice=correct,
                        explanation=explanation,
                    )
        return course
