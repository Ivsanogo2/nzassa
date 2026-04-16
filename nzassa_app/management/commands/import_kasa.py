import csv
import os
from django.core.management.base import BaseCommand
from nzassa_app.models import Traduction # On utilise le modèle Traduction déjà créé

class Command(BaseCommand):
    help = 'Importation massive des données Kasa'

    def handle(self, *args, **options):
        # Chemin du fichier CSV
        file_path = 'kasa_data.csv'
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"Fichier {file_path} introuvable !"))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            traductions_a_creer = []
            
            for row in reader:
                traductions_a_creer.append(Traduction(
                    mot_origine=row['french'],
                    langue_cible='BAO' if row['language'] == 'Baoulé' else 'DIO', # Adaptation rapide
                    resultat_traduction=row['native_text']
                ))
            
            # Injection massive dans la base de données
            Traduction.objects.bulk_create(traductions_a_creer)
            
        self.stdout.write(self.style.SUCCESS('Succès : Le dictionnaire Kasa est maintenant opérationnel !'))