from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import (
    AudioTrack,
    Book,
    Ethnicity,
    Language,
    LearningGroup,
    MicroLessonSubscription,
    MobileMoneyPayment,
    PrivateMessage,
    School,
    ShortVideo,
    SocialComment,
    SocialPost,
    Story,
    StoryComment,
)


class NzassaRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    selected_language = forms.ModelChoiceField(
        queryset=Language.objects.filter(is_active=True),
        required=False,
        empty_label="Choisir plus tard",
    )
    goal = forms.ChoiceField(
        choices=[
            ("culture", "Culture"),
            ("school", "Etudes"),
            ("travel", "Voyage"),
            ("family", "Famille et diaspora"),
        ]
    )
    level = forms.ChoiceField(
        choices=[
            ("beginner", "Debutant"),
            ("intermediate", "Intermediaire"),
            ("advanced", "Avance"),
        ]
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "email", "selected_language", "goal", "level")


class NzassaLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True}))


class StoryForm(forms.ModelForm):
    new_ethnicity = forms.CharField(
        required=False,
        label="Nouvelle ethnie",
        help_text="Optionnel: utilisez ce champ si l'ethnie n'existe pas encore.",
    )

    class Meta:
        model = Story
        fields = (
            "title",
            "description",
            "image",
            "audio_file",
            "location",
            "youtube_url",
            "ethnicity",
            "new_ethnicity",
            "reading_minutes",
        )
        labels = {
            "title": "Titre",
            "description": "Description",
            "image": "Image",
            "audio_file": "Audio conte ou podcast",
            "location": "Lieu",
            "youtube_url": "Video YouTube",
            "ethnicity": "Ethnie associee",
            "reading_minutes": "Temps de lecture",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 9,
                    "placeholder": "Racontez l'histoire avec des paragraphes, citations ou details culturels.",
                }
            ),
            "location": forms.TextInput(attrs={"placeholder": "Village, ville, region ou pays"}),
            "youtube_url": forms.URLInput(attrs={"placeholder": "https://www.youtube.com/watch?v=..."}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_ethnicity = (self.cleaned_data.get("new_ethnicity") or "").strip()
        if new_ethnicity:
            ethnicity, _ = Ethnicity.objects.get_or_create(name=new_ethnicity)
            instance.ethnicity = ethnicity
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StoryCommentForm(forms.ModelForm):
    class Meta:
        model = StoryComment
        fields = ("content",)
        labels = {"content": "Commentaire"}
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Ajouter une reaction ou un complement culturel..."}
            )
        }


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ("title", "author_name", "description", "cover", "pdf_file", "category")
        labels = {
            "title": "Titre",
            "author_name": "Auteur",
            "description": "Description",
            "cover": "Couverture",
            "pdf_file": "Fichier PDF",
            "category": "Categorie",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 7, "placeholder": "Resume, contexte culturel ou notes de lecture."}),
        }


class SocialPostForm(forms.ModelForm):
    class Meta:
        model = SocialPost
        fields = ("group", "content", "image")
        labels = {"group": "Groupe", "content": "Publication", "image": "Image"}
        widgets = {
            "content": forms.Textarea(attrs={"rows": 4, "placeholder": "Partagez une question, une expression, une photo ou une decouverte."}),
        }


class SocialCommentForm(forms.ModelForm):
    class Meta:
        model = SocialComment
        fields = ("content",)
        labels = {"content": "Commentaire"}
        widgets = {
            "content": forms.TextInput(attrs={"placeholder": "Ecrire un commentaire..."})
        }


class CulturalAIForm(forms.Form):
    MODE_CHOICES = [
        ("chat", "Discussion"),
        ("language", "Langue locale"),
        ("culture", "Question culturelle"),
        ("quiz", "Quiz ou mini-jeu"),
    ]

    prompt = forms.CharField(
        label="Votre demande",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Exemple: apprends-moi 5 salutations baoule avec un mini quiz.",
            }
        ),
    )
    target_language = forms.ModelChoiceField(
        queryset=Language.objects.filter(is_active=True),
        required=False,
        empty_label="Francais / toutes les langues",
        label="Langue cible",
    )
    level = forms.ChoiceField(
        choices=NzassaRegistrationForm.base_fields["level"].choices,
        label="Niveau",
        required=True,
    )
    mode = forms.ChoiceField(choices=MODE_CHOICES, label="Mode")


class AudioTrackForm(forms.ModelForm):
    class Meta:
        model = AudioTrack
        fields = ("title", "story", "lesson", "language", "audio_file", "external_url", "transcript", "duration_seconds", "is_downloadable")
        labels = {
            "title": "Titre",
            "story": "Histoire liee",
            "lesson": "Lecon liee",
            "language": "Langue",
            "audio_file": "Fichier audio",
            "external_url": "Lien audio externe",
            "transcript": "Transcription",
            "duration_seconds": "Duree en secondes",
            "is_downloadable": "Telechargeable offline",
        }
        widgets = {
            "transcript": forms.Textarea(attrs={"rows": 5}),
        }


class ShortVideoForm(forms.ModelForm):
    class Meta:
        model = ShortVideo
        fields = ("title", "language", "caption", "video_file", "video_url", "thumbnail")
        labels = {
            "title": "Titre",
            "language": "Langue",
            "caption": "Legende",
            "video_file": "Video",
            "video_url": "Lien video",
            "thumbnail": "Miniature",
        }
        widgets = {
            "caption": forms.Textarea(attrs={"rows": 4, "placeholder": "Phrase courte, mot du jour ou contexte culturel."}),
        }


class LearningGroupForm(forms.ModelForm):
    class Meta:
        model = LearningGroup
        fields = ("name", "language", "description", "is_public")
        labels = {
            "name": "Nom du groupe",
            "language": "Langue",
            "description": "Description",
            "is_public": "Groupe public",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class PrivateMessageForm(forms.ModelForm):
    class Meta:
        model = PrivateMessage
        fields = ("recipient", "body", "image")
        labels = {"recipient": "Destinataire", "body": "Message", "image": "Image"}
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4, "placeholder": "Ecrire un message prive..."}),
        }


class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ("name", "city")
        labels = {"name": "Nom de l'ecole", "city": "Ville"}


class MicroLessonSubscriptionForm(forms.ModelForm):
    class Meta:
        model = MicroLessonSubscription
        fields = ("channel", "phone_number", "language", "is_active")
        labels = {
            "channel": "Canal",
            "phone_number": "Numero",
            "language": "Langue",
            "is_active": "Actif",
        }


class MobileMoneyPaymentForm(forms.ModelForm):
    class Meta:
        model = MobileMoneyPayment
        fields = ("provider", "phone_number", "amount")
        labels = {
            "provider": "Operateur",
            "phone_number": "Numero Mobile Money",
            "amount": "Montant FCFA",
        }
