from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Language


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
