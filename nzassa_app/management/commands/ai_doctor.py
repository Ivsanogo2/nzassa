from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from nzassa_app.ai_services import get_remote_ai_status, ollama_is_available


class Command(BaseCommand):
    help = "Affiche l'etat du moteur IA Nzassa et les options disponibles."

    def handle(self, *args, **options):
        env_path = Path(settings.BASE_DIR) / ".env"
        status = get_remote_ai_status()

        self.stdout.write(self.style.SUCCESS("Nzassa AI Doctor"))
        self.stdout.write(f"Fichier .env: {'present' if env_path.exists() else 'absent'}")
        self.stdout.write(f"Provider actif: {status['provider']}")
        self.stdout.write(f"Label: {status['label']}")
        self.stdout.write(f"Modele: {status.get('model', '') or 'aucun'}")
        self.stdout.write(f"Ollama disponible: {'oui' if ollama_is_available() else 'non'}")

        if status["provider"] == "local":
            self.stdout.write("")
            self.stdout.write("Pour passer sur un vrai LLM:")
            self.stdout.write("1. Installe Ollama puis telecharge qwen3:4b")
            self.stdout.write("2. Ou ajoute OPENROUTER_API_KEY dans .env")
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Un moteur conversationnel distant ou local avancé est deja selectionne."))
